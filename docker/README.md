# Despliegue en producción

El VPS `senacasa-vps` aloja también control-ingresos, cuyo proxy (`ci-proxy`)
ocupa los puertos 80 y 443. Materiales no publica puertos: entra por ese mismo
proxy, que lo alcanza por la red `control_ingresos_red` con el alias
`materiales-app`.

URL: <https://materiales-formacion.senacasadigital.com>

| Archivo | Propósito |
|---|---|
| `docker-compose.prod.yml` | Superposición de producción: sin puertos, unido a la red del proxy. |
| `docker/nginx/materiales.conf.template` | Sitio HTTPS, montado como plantilla adicional en `ci-proxy`. |
| `docker/certificado-inicial.sh` | Primera emisión del certificado (webroot, sin detener el proxy). |
| `docker/respaldo-programado.sh` | Respaldo diario cifrado de la base y los PDF (cron). |

## Primer despliegue

```bash
cd /opt/materiales-formacion
cp .env.example .env   # y cambiar todos los valores
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Con el registro DNS A ya apuntando al servidor:
./docker/certificado-inicial.sh --ensayo   # opcional, no gasta cuota
./docker/certificado-inicial.sh
```

Después se monta la plantilla en el proxy, añadiendo en
`/opt/control-ingresos/docker-compose.prod.yml`, servicio `proxy`, `volumes`:

```yaml
- /opt/materiales-formacion/docker/nginx/materiales.conf.template:/etc/nginx/templates/materiales.conf.template:ro
```

y recreando solo el proxy:

```bash
cd /opt/control-ingresos
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d proxy
```

Las renovaciones las hace `ci-certbot`, y `ci-proxy` recarga cada seis horas.

## Actualizar

```bash
cd /opt/materiales-formacion
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Respaldos

Cron, a las 02:30 (después del de control-ingresos):

```
30 2 * * * /opt/materiales-formacion/docker/respaldo-programado.sh >> /opt/materiales-formacion/respaldos/cron.log 2>&1
```

Cada archivo `respaldos/materiales_formacion_*.tar.gpg` contiene `materiales.sql`
y `uploads.tar`. Se descifra fuera del servidor con la clave privada de
`respaldos@senacasadigital.com`.
