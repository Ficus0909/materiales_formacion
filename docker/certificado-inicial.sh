#!/bin/sh
# Emisión del primer certificado TLS de materiales-formacion.
#
#     ./docker/certificado-inicial.sh [--ensayo]
#
# Se ejecuta UNA vez, desde la raíz del repositorio, antes de montar
# docker/nginx/materiales.conf.template en el proxy (Nginx no arranca si falta
# el certificado que declara).
#
# A diferencia de control-ingresos no se detiene el proxy: el bloque por
# defecto de ci-proxy ya sirve /.well-known/acme-challenge/ desde el volumen
# compartido con ci-certbot, así que se emite por webroot sin cortar el
# servicio. Las renovaciones las hace el bucle de ci-certbot, que recorre todos
# los certificados del volumen.
#
# --ensayo usa el entorno de pruebas de Let's Encrypt (no gasta cuota).
set -eu

DOMINIO="materiales-formacion.senacasadigital.com"
CERTBOT="ci-certbot"

ENSAYO=""
[ "${1:-}" = "--ensayo" ] && ENSAYO="--staging"

leer_variable() {
  grep -E "^${1}=" .env | tail -n 1 | cut -d '=' -f 2- | tr -d '"' | tr -d "'"
}

[ -f .env ] || { echo "ERROR: ejecute desde la raíz del repositorio, con el .env creado." >&2; exit 1; }
CERTBOT_EMAIL="$(leer_variable CERTBOT_EMAIL)"
[ -n "$CERTBOT_EMAIL" ] || { echo "ERROR: defina CERTBOT_EMAIL en el .env." >&2; exit 1; }

IP_SERVIDOR="$(curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null || echo '')"
IP_DOMINIO="$(getent hosts "$DOMINIO" 2>/dev/null | awk '{print $1}' | head -n 1 || echo '')"
if [ -z "$IP_DOMINIO" ]; then
  echo "ERROR: $DOMINIO todavía no resuelve. Cree el registro A y espere a que propague." >&2
  exit 1
fi
if [ -n "$IP_SERVIDOR" ] && [ "$IP_SERVIDOR" != "$IP_DOMINIO" ]; then
  echo "ERROR: $DOMINIO resuelve a $IP_DOMINIO, pero este servidor es $IP_SERVIDOR." >&2
  exit 1
fi

# Un certificado de ensayo previo haría que certbot respondiera «not yet due»
# y se quedara con él: se borra antes de pedir el definitivo.
if [ -z "$ENSAYO" ] && docker exec "$CERTBOT" sh -c \
    "openssl x509 -in /etc/letsencrypt/live/$DOMINIO/fullchain.pem -noout -issuer 2>/dev/null | grep -q STAGING"; then
  echo "Se encontró un certificado de ENSAYO: se elimina."
  docker exec "$CERTBOT" certbot delete --cert-name "$DOMINIO" --non-interactive
fi

echo "Solicitando el certificado para $DOMINIO…"
docker exec "$CERTBOT" certbot certonly \
  --webroot --webroot-path /var/www/certbot \
  --non-interactive --agree-tos --no-eff-email \
  --email "$CERTBOT_EMAIL" \
  -d "$DOMINIO" $ENSAYO

echo
echo "Certificado emitido. Siguiente paso: montar la plantilla en ci-proxy (docker/README.md)."
