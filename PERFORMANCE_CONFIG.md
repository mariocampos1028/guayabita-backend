# Configuración de rendimiento — fase 1

Configura el pool de PostgreSQL por proceso mediante variables de entorno:

```text
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5
DB_POOL_TIMEOUT_SECONDS=30
DB_POOL_RECYCLE_SECONDS=1800
```

Los valores anteriores son conservadores para una instancia única. El total
máximo de conexiones por proceso es `DB_POOL_SIZE + DB_MAX_OVERFLOW`; al usar
varios workers o réplicas, multiplica ese total y mantenlo por debajo del límite
del proveedor PostgreSQL dejando margen para migraciones y administración.

Ejemplo: con un límite de 30 conexiones y dos workers, empezar con `5 + 5` por
worker deja 10 conexiones disponibles. Ajusta únicamente después de revisar las
métricas de pool y consultas de la fase 0.
