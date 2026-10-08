# Reglas de negocio — Materiales de Formación (SENA CASA)

Fuentes analizadas en `contexto/`:

- **ESTADO_ACTUAL_DEL_PROYECTO.docx** — diagnóstico del prototipo anterior y decisiones pendientes (sección 10).
- **MOCKUPS_PWA_ESTUDIO_MERCADOS (docx/pptx)** — 16 pantallas con reglas por pantalla.
- **ESTUDIO DE MERCADOS_BCTUCU_CASA_2026.xlsx** — el proceso real: listado maestro (LM-2026: 1.399 filas, 11 lotes) y el *Formato de análisis de precios y consolidación* por lote (hojas L1…L11).

El Excel es la fuente más fiel del proceso, así que cuando un documento contradice a otro **manda el Excel**, porque es lo que el SENA firma.

---

## 1. Decisiones sobre los puntos abiertos

| # | Punto pendiente (Estado actual §10) | Decisión adoptada | Por qué |
|---|---|---|---|
| 1 | Modelo de cotizaciones: ¿"por artículo" o "2 cotizaciones lado a lado"? | **Una cotización = un documento PDF de un proveedor** para un lote y una vigencia, con **precios para muchos artículos** (`Cotizacion` 1—N `CotizacionItem`). | Así funciona en la realidad: el proveedor envía un solo PDF con todos los precios. En el Excel, P1/P2/P3 son columnas de proveedor y cada una cubre decenas de artículos. Subir un PDF por artículo (el modelo anterior) significaba unas 1.400 cargas. |
| 2 | ¿Obligar a 2 proveedores diferentes? | Parámetro `min_cotizaciones` (por defecto **2**). Si un artículo no llega al mínimo se usan los **precios históricos indexados**. Si tampoco hay históricos, el precio queda marcado como *Cotización insuficiente*. Un artículo **sin ningún precio** no se puede enviar. | En el Excel 2026, 404 artículos se valoraron con históricos y 65 con una sola cotización. Bloquear todo lo que tenga menos de 2 cotizaciones haría inviable el proceso. |
| 3 | ¿El líder "elige" una cotización? | **No.** El precio de referencia es el **promedio de las cotizaciones válidas**. El analista puede excluir atípicos. | Es el método del formato oficial: "Se toma el precio promedio entre las cotizaciones recibidas…". Elegir la cotización más barata no es un estudio de mercado. |
| 4 | Validación UNSPSC | Se valida el formato: **8 dígitos**. | La importación encontró un código de 7 dígitos en LM-2026 (fila 662, *Fosfato monobásico de calcio*). No existe un catálogo oficial descargable para validarlo contra él. |
| 5 | Carga del catálogo | Importador asistido desde Excel: el usuario elige la hoja, ve una **previsualización** con errores y advertencias y luego confirma. Los artículos se identifican por **lote + nombre** (el UNSPSC se repite entre productos). | Con el archivo real (LM-2026): 1.385 artículos importados en 11 lotes, 2 filas con errores y 12 duplicados detectados. |
| 6 | Precios históricos y captura automática | Al **aprobar** una solicitud, sus precios se **congelan** y se guardan como históricos del año de la vigencia. Los históricos se indexan con **IPC + puntos adicionales** (PAAG), configurables por año. | Es la nota al pie del formato: "VF = VP·(1+IPC1)·(1+IPC2)…, IPC 2023 9,28 %, 2024 5,2 %, 2025 5,1 % más dos puntos". |
| 7 | Estados post-aprobación | Por defecto: En Compra → En Camino → En el Punto. Son **configurables**, **solo avanzan** y cada cambio exige observación. | Reglas de los mockups. |
| 8 | Notificaciones | **Dentro de la aplicación y por correo** (SMTP configurable). El correo se envía solo si la operación se guarda bien. Si el SMTP no está configurado, las notificaciones quedan solo en la aplicación. | Confirmado por el SENA. |
| 10 | Acceso de los usuarios | **Cuentas creadas por el administrador** (correo + contraseña temporal que llega por correo y debe cambiarse en el primer ingreso). **Sin SSO institucional.** | Confirmado por el SENA. |
| 11 | Hoja LM-IB (Integralidad y Bilingüismo) | **No se incluye.** Fue lote 12 durante un tiempo y se eliminó por decisión del SENA. No se importa. | Decisión del SENA. Si se necesita más adelante, se crea en Lotes y se importa la hoja LM-IB desde el importador. |
| 9 | Una solicitud por… | **Una solicitud por lote y vigencia** (restricción única en la base de datos). | Los mockups dicen "por lote/líder", y un líder tiene un solo lote. Como cada lote pertenece a un centro, hay una solicitud por lote de cada centro. |
| 12 | Varios centros de formación | Cada **centro de formación** (sucursal) tiene su propio listado maestro, lotes, líderes, cotizaciones, análisis de precios, históricos y solicitudes. Los **proveedores** (por NIT) y las **vigencias** son comunes. Un **manager** está por encima de los administradores de los centros. | Decisión del SENA: cada centro maneja sus propios usuarios y su propio catálogo. |

## 2. Roles

- **Manager** (no pertenece a ningún centro): crea, edita y desactiva **centros de formación**, y crea y gestiona sus **administradores** (también puede crear otros managers y líderes). Gestiona lo común a todos los centros: **vigencias** (crear, abrir, cerrar), **parámetros** del análisis de precios, **estados post-aprobación** e **índices IPC**. Consulta todos los centros: tablero por centro, bandeja de solicitudes, detalle, reportes y consolidado Excel (todos o uno). **No opera dentro de un centro**: no crea lotes ni artículos, no carga cotizaciones ni aprueba solicitudes.
- **Administrador / Analista** (de un centro): gestiona los **líderes de su centro**, los lotes y el listado maestro de su centro (con UNSPSC), los proveedores, y las propuestas de artículos de sus líderes. Hace el análisis de precios: excluye atípicos, fija el método o el precio de experto. Aprueba, rechaza o devuelve las solicitudes de su centro y lleva el ciclo de compra. Consulta las vigencias y la configuración, pero no las modifica. No ve datos de otros centros.
- **Líder de lote**: trabaja solo sobre **su** lote, dentro de su centro. Registra proveedores, carga cotizaciones (PDF + precios), arma la solicitud por lote desde el listado maestro, propone artículos nuevos y consulta el seguimiento y los reportes de su lote.

## 3. Flujo

```
Admin crea y ABRE la vigencia ─► Líder carga cotizaciones (PDF + precios, a mano o con plantilla Excel)
        │                               │
        │                       Sistema calcula el precio de referencia por artículo
        ▼                               ▼
Líder arma su SOLICITUD POR LOTE (selección masiva, cantidades, plantilla Excel, clonar vigencia anterior; autoguardado)
        ▼
ENVIADA ─► EN_REVISION ─► APROBADA ─► En Compra ─► En Camino ─► En el Punto (configurable)
                      ├─► DEVUELTA ─► (corrige y reenvía; se cuentan los reenvíos)
                      └─► RECHAZADA (cerrada)
Cierre de vigencia: BORRADOR / DEVUELTA ─► CANCELADA
```

## 4. Reglas por entidad

### Centros de formación
- Código y nombre únicos (sin distinguir mayúsculas). Solo el manager los crea y edita.
- **Desactivar** un centro bloquea el ingreso de sus administradores y líderes, incluso con una sesión abierta. Sus datos se conservan.
- Un centro con lotes o usuarios no se elimina: se desactiva.
- No se crean usuarios en un centro inactivo.
- Al crear un centro se carga **por defecto el listado maestro** del centro por defecto (CASA): se copian sus lotes y sus artículos activos. El manager puede elegir otro centro de origen o empezar sin listado. Un centro que aún no tiene lotes puede recibir el listado después, con el botón **Cargar listado** (solo el manager). Si el centro ya tiene lotes, se actualiza con el importador. No se copian cotizaciones, precios históricos, análisis ni solicitudes, porque cada centro hace su propio estudio de mercados.
- Puesta en marcha: el manager crea el centro (con el listado predeterminado) y su administrador. El administrador ajusta el listado (editarlo o reemplazarlo con el importador) y crea los líderes.
- El centro por defecto (`CENTRO_CODIGO`, CASA) recibe al administrador inicial y el listado maestro del Excel de carga. Al actualizar una base anterior a los centros, recibe todos los datos existentes.

### Usuarios
- Administradores y líderes pertenecen a **un** centro. El manager no tiene centro.
- El administrador solo crea, edita, desactiva o elimina **líderes de su centro**. Si envía otro centro, se ignora. A los administradores los gestiona el manager.
- El lote de un líder debe pertenecer a su centro.
- Un usuario con solicitudes o cotizaciones no se traslada de centro: se desactiva y se crea uno nuevo en el otro centro. Así el historial queda en el centro donde ocurrió.
- Nadie puede cambiarse su propio rol ni desactivarse.

### Lotes
- Son propios de cada centro. El número y la abreviatura son únicos **dentro del centro**: dos centros pueden tener un lote 1 «Agric».
- Un lote está **en operación** cuando tiene al menos un líder activo. Los tableros y reportes (cobertura de precios, lotes sin solicitud y cobertura por centro del manager) solo muestran los lotes en operación. Así, una sede nueva con el listado maestro copiado no muestra sus lotes hasta que el administrador les asigna líder. Sus artículos siguen en el listado maestro.
- Solo el administrador del centro los crea y edita.

### Vigencias
- Son **comunes a todos los centros** y solo el manager las crea, edita, abre, cierra o elimina. Los administradores las consultan con los conteos de su centro.
- Estados PROGRAMADA → ABIERTA → CERRADA. Solo puede haber **una abierta**.
- Al abrirla se avisa a los líderes y administradores de todos los centros activos.
- Mientras está abierta solo se puede **extender** la fecha de cierre.
- Al cerrarla, las solicitudes en BORRADOR o DEVUELTA de **todos los centros** pasan a **CANCELADA** y se avisa al líder.
- No se puede eliminar una vigencia que tenga solicitudes o cotizaciones.
- El campo `anio` es el año de precios que se usa para indexar los históricos.

### Listado maestro
- Cada centro tiene el suyo: un artículo pertenece a un lote, y el lote a un centro.
- Solo el administrador del centro crea o edita artículos. El UNSPSC tiene 8 dígitos y la unidad es la de SECOP II.
- La importación busca los lotes del archivo (por abreviatura o número) **solo entre los lotes del centro** del administrador. Lo mismo hace la importación de precios históricos.
- No se puede repetir el nombre dentro del mismo lote.
- Un artículo con cotizaciones o en solicitudes no se elimina: se **desactiva**. Si ya tiene cotizaciones, tampoco se puede cambiar de lote.
- La importación puede **desactivar los ausentes** cuando se carga el listado de una vigencia nueva.
- El líder puede **proponer** artículos. El administrador de su centro les asigna el UNSPSC y los aprueba o rechaza.

### Cotizaciones
- Las cargan el líder (en su lote) o el administrador (en un lote de su centro). El manager solo las consulta.
- Los proveedores son comunes: el mismo proveedor puede cotizar en varios centros. Como los artículos son de cada centro, el promedio, el máximo por artículo y los históricos se calculan **por centro**.
- Requisitos: vigencia abierta, proveedor activo, **PDF obligatorio** (se valida la firma `%PDF`, máximo 10 MB) y fecha no futura.
- Un proveedor tiene **una sola cotización por lote y vigencia**. Si necesita cambios, se edita.
- Hay un máximo de cotizaciones por artículo y vigencia (`max_cotizaciones`, por defecto 3).
- La etiqueta P1, P2, … se asigna sola por lote y vigencia, igual que en el formato.
- **Bloqueo**: cuando la solicitud del lote está ENVIADA, EN_REVISION o APROBADA, el líder ya no puede modificar las cotizaciones. Así los precios no cambian durante la revisión.

### Análisis de precios (réplica de las hojas L1…L11)
- **Dispersión** = coeficiente de variación muestral (DESVEST/PROMEDIO). Se verificó contra el Excel: 0,111872… para *Aceite agrícola*.
- **Método automático**:
  1. COTIZACIONES, si las cotizaciones válidas son ≥ `min_cotizaciones`.
  2. Si no, HISTORICOS: promedio de los históricos de los últimos `anios_historicos` años, indexados.
  3. Si no, COTIZACIONES con soporte *insuficiente*.
  4. Si no, EXPERTO, cuando hay precio de experto.
- **Semáforo**: verde ≤ 25 %, naranja ≤ 40 %, rojo > 40 % (parametrizable).
- **Atípicos**: con 3 o más cotizaciones y dispersión por encima del umbral, el sistema **sugiere** como atípico el valor más alejado de la mediana. El analista lo excluye indicando el motivo ("su valor notoriamente alto/bajo") y la justificación se redacta igual que en el formato.
- Un cambio manual de método exige justificación.
- Una vez aprobada la solicitud del lote, los precios quedan **congelados**.

### Solicitudes (por lote)
- Se crea en BORRADOR la primera vez que el líder entra a "Mi solicitud" con una vigencia abierta.
- **Autoguardado por lotes**: los cambios se envían en bloque y una cantidad 0 retira el artículo.
- La **plantilla Excel** de cantidades reemplaza la solicitud completa.
- **Clonar** solo desde solicitudes **aprobadas** del mismo lote:
  - copia artículos y cantidades, no precios;
  - omite los artículos desactivados del maestro;
  - no duplica los que ya están;
  - deja como *pendientes de precio* los que no tienen precio de referencia.
- **Enviar** exige al menos 1 artículo, todos activos, con cantidad > 0 y con precio de referencia.
- Solo el administrador del centro de la solicitud la revisa, decide y avanza en el ciclo de compra. El manager la consulta.
- Las observaciones son obligatorias para **devolver** o **rechazar**. Una solicitud rechazada no se reabre.
- El consolidado Excel incluye la columna de centro. El administrador exporta su centro; el manager, todos o uno.
- El historial es inmutable: registra fecha, estado anterior y nuevo, responsable y observaciones.

### Correo
- Se envía correo a la persona notificada en estos casos:
  - el manager o el administrador crea un usuario o le restablece la contraseña (credenciales temporales);
  - se abre una vigencia (a los líderes y administradores de todos los centros activos);
  - un líder envía o reenvía su solicitud, o propone un artículo (a los administradores **de su centro**);
  - una solicitud pasa a revisión, se aprueba, se devuelve, se rechaza, se cancela al cerrar la vigencia o avanza en el ciclo de compra (al líder);
  - se responde una propuesta de artículo (al líder).
- El envío ocurre en segundo plano después de guardar. Una falla del correo nunca revierte la operación y queda registrada en el log del servidor.
- En Configuración → Correo, el manager y el administrador ven el estado del SMTP y pueden enviarse un correo de prueba.

### Seguridad
- JWT con 8 horas de vigencia. Bloqueo de 15 minutos tras 3 intentos fallidos.
- Política de contraseña: 8 caracteres o más, con mayúscula, número y carácter especial.
- Cambio obligatorio de la contraseña temporal en el primer ingreso.
- Cada endpoint valida el rol y el centro. El líder solo accede a datos de su lote. El administrador solo accede a datos de su centro: usuarios, lotes, artículos, cotizaciones, PDF, análisis, propuestas, solicitudes, tablero y actividad. El manager consulta todos los centros, pero solo modifica centros, usuarios y la configuración común.
- Los usuarios con historial no se eliminan: se desactivan.

## 5. Calidad de datos encontrada en el Excel 2026

- Fila 270, *BROCAS DE PRECISIÓN*: sin unidad de medida.
- Fila 662, *Fosfato monobásico de calcio*: UNSPSC `5182400`, de 7 dígitos.
- 12 productos repetidos dentro del mismo lote.
- Unidades con mayúsculas y minúsculas inconsistentes (`Kg`, `kG`) y `KL`. Se normalizan a `KG`.
- La hoja **LM-IB** (Integralidad y Bilingüismo, 132 ítems) no se usa en la aplicación por decisión del SENA.

## 6. Pendiente de definir con el SENA

1. IPC 2026 definitivo. Mientras tanto se usa el parámetro por defecto (5,1 % + 2 puntos).
2. Firmas del formato de análisis (elaboró y revisó): **se definirán más adelante**. Hoy se dejan espacios en blanco.
3. Cuenta de correo remitente y servidor SMTP institucional para producción.

### Decisiones cerradas
- El lote *Integralidad y Bilingüismo* (hoja LM-IB) no hace parte de la aplicación.
- Notificaciones también por correo.
- Acceso con cuentas asignadas por el administrador, sin SSO.
