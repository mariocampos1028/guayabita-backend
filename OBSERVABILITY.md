# Observabilidad — fase 0

La API expone métricas por proceso en `GET /internal/metrics` cuando se define
`OBSERVABILITY_METRICS_TOKEN`. Envíe el mismo valor mediante el encabezado
`X-Metrics-Token`. Si la variable no está definida, la ruta responde `404`.

Nunca exponga esta ruta en un navegador público ni registre el token. Con más
de un worker o réplica, el recolector debe consultar cada proceso y agregar las
series: estas métricas son deliberadamente locales al proceso.

Métricas incluidas:

- HTTP: volumen, ruta normalizada, código de respuesta y latencia.
- PostgreSQL: consultas, duración y uso del pool.
- Upstash Redis: operación, resultado y duración.
- Cloudflare R2: operaciones, bytes transferidos y duración.

Las latencias usan una ventana deslizante local de hasta 2.048 muestras por
serie, por lo que no crecen indefinidamente y describen el comportamiento
reciente. Todas las solicitudes reciben un encabezado `X-Request-ID`; el mismo valor se
incluye en los logs JSON de finalización de petición. Configure alertas iniciales
para errores HTTP 5xx, latencia p95, errores Redis/R2 y pool SQL sostenidamente
ocupado. Antes de cambiar polling o capacidad, capture al menos siete días de
esta línea base.
