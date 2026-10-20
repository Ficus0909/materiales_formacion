#!/bin/sh
# Respaldo diario de materiales-formacion, a imagen del de control-ingresos.
#
#     ./docker/respaldo-programado.sh
#
# Lo invoca cron. Vuelca la base MariaDB y los PDF subidos, comprueba que el
# volcado esté completo, cifra todo con la clave pública GPG de respaldos (el
# servidor cifra pero no puede descifrar), lo apunta en un manifiesto y rota
# los de más de RESPALDO_DIAS_RETENCION días.
set -eu

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

leer_variable() {
    [ -f .env ] || return 0
    grep -E "^${1}=" .env | tail -n 1 | cut -d '=' -f 2- | tr -d '"' | tr -d "'"
}

DIAS_RETENCION="${RESPALDO_DIAS_RETENCION:-$(leer_variable RESPALDO_DIAS_RETENCION)}"
DESTINATARIO_GPG="${RESPALDO_GPG_DESTINATARIO:-$(leer_variable RESPALDO_GPG_DESTINATARIO)}"
DIAS_RETENCION="${DIAS_RETENCION:-30}"
DESTINATARIO_GPG="${DESTINATARIO_GPG:-respaldos@senacasadigital.com}"

DIRECTORIO_RESPALDOS="${RESPALDO_DIRECTORIO:-$RAIZ/respaldos}"
REGISTRO="$DIRECTORIO_RESPALDOS/respaldos.log"
MANIFIESTO="$DIRECTORIO_RESPALDOS/manifiesto.txt"
CERROJO="$DIRECTORIO_RESPALDOS/.cerrojo"

mkdir -p "$DIRECTORIO_RESPALDOS"
chmod 700 "$DIRECTORIO_RESPALDOS"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

anotar() {
    MENSAJE="$(date '+%Y-%m-%d %H:%M:%S') $*"
    echo "$MENSAJE" >> "$REGISTRO"
    echo "$MENSAJE"
    logger -t materiales-formacion-respaldo "$*" 2>/dev/null || true
}

terminar_con_error() {
    anotar "ERROR: $*"
    rm -rf "$TEMPORAL"
    exit 1
}

exec 9>"$CERROJO"
if ! flock -n 9; then
    anotar "Ya hay un respaldo en curso: no se lanza otro."
    exit 0
fi

MARCA="$(date +%Y%m%d_%H%M%S)"
TEMPORAL="$(mktemp -d)"
ARCHIVO_CIFRADO="$DIRECTORIO_RESPALDOS/materiales_formacion_${MARCA}.tar.gpg"

anotar "Iniciando respaldo."

# --- 1. Base de datos ----------------------------------------------------------
# La clave sale del entorno del contenedor: nunca pasa por este guion.
if ! $COMPOSE exec -T db sh -c \
        'mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines --triggers "$MARIADB_DATABASE"' \
        > "$TEMPORAL/materiales.sql" 2>>"$REGISTRO"; then
    terminar_con_error "mariadb-dump falló. ¿Está levantado el servicio db?"
fi

# mariadb-dump escribe esta marca al terminar: si falta, el volcado quedó cortado.
tail -n 1 "$TEMPORAL/materiales.sql" | grep -q "Dump completed" \
    || terminar_con_error "el volcado está incompleto: se descarta."

# --- 2. PDF y archivos subidos ---------------------------------------------------
if ! $COMPOSE exec -T app tar -C /data -cf - uploads > "$TEMPORAL/uploads.tar" 2>>"$REGISTRO"; then
    terminar_con_error "no se pudieron empaquetar los archivos subidos."
fi

TAMANO=$(du -cb "$TEMPORAL"/* | tail -n 1 | cut -f1)
HUELLA_SQL="$(sha256sum "$TEMPORAL/materiales.sql" | cut -d' ' -f1)"

# --- 3. Cifrado ------------------------------------------------------------------
gpg --list-keys "$DESTINATARIO_GPG" > /dev/null 2>&1 \
    || terminar_con_error "no existe la clave pública «$DESTINATARIO_GPG»."

if ! tar -C "$TEMPORAL" -cf - materiales.sql uploads.tar \
        | gpg --batch --yes --trust-model always --encrypt \
              --recipient "$DESTINATARIO_GPG" --output "$ARCHIVO_CIFRADO" 2>/dev/null; then
    rm -f "$ARCHIVO_CIFRADO"
    terminar_con_error "el cifrado con GPG falló."
fi
rm -rf "$TEMPORAL"
chmod 600 "$ARCHIVO_CIFRADO"

TAMANO_CIFRADO=$(wc -c < "$ARCHIVO_CIFRADO")
HUELLA_CIFRADO="$(sha256sum "$ARCHIVO_CIFRADO" | cut -d' ' -f1)"

# --- 4. Manifiesto ---------------------------------------------------------------
printf '%s\t%s\t%s\t%s\t%s\n' \
    "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$(basename "$ARCHIVO_CIFRADO")" \
    "$TAMANO_CIFRADO" "sha256-sql=$HUELLA_SQL" "sha256-cifrado=$HUELLA_CIFRADO" >> "$MANIFIESTO"
chmod 600 "$MANIFIESTO"

anotar "Respaldo creado: $(basename "$ARCHIVO_CIFRADO") (${TAMANO_CIFRADO} bytes, original ${TAMANO})."

# --- 5. Rotación -----------------------------------------------------------------
BORRADOS=$(find "$DIRECTORIO_RESPALDOS" -maxdepth 1 -name 'materiales_formacion_*.tar.gpg' \
    -mtime "+$DIAS_RETENCION" -print -delete | wc -l)
[ "$BORRADOS" -gt 0 ] && anotar "Rotación: ${BORRADOS} respaldo(s) de más de ${DIAS_RETENCION} días eliminados."

CONSERVADOS=$(find "$DIRECTORIO_RESPALDOS" -maxdepth 1 -name 'materiales_formacion_*.tar.gpg' | wc -l)
anotar "Terminado. ${CONSERVADOS} respaldo(s) disponibles."
