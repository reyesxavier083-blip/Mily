# MILY — Plan de mejora técnica

Este documento organiza mejoras incrementales para MILY sin reemplazar el código existente ni mezclarlo con NEXUS.

## Principios
- Cambios pequeños, revisables y reversibles.
- No almacenar claves API, contraseñas ni datos privados en el repositorio.
- Validar entradas antes de ejecutar herramientas o acceder a archivos.
- Mantener separadas la planificación, la autorización y la ejecución.
- Registrar errores útiles sin exponer secretos.

## Arquitectura objetivo
1. **Core / Orquestación**: recibe comandos y coordina el flujo.
2. **Contexto**: reúne el contexto necesario para la petición actual.
3. **AI Engine**: razonamiento y selección de modelos.
4. **Planning Engine**: convierte la petición en un plan estructurado.
5. **Security Engine**: valida permisos y operaciones antes de ejecutarlas.
6. **Task Engine**: ejecuta pasos, aplica límites de tiempo y reintentos controlados.
7. **Tool Engine**: ofrece herramientas con esquemas de entrada y resultados normalizados.
8. **Memory Engine**: gestiona memoria con procedencia, confianza y controles de acceso.

## Prioridades de implementación

### P0 — Seguridad y estabilidad
- Mantener secretos fuera del código; usar variables de entorno y un archivo de ejemplo sin credenciales.
- Validar argumentos de herramientas y restringir rutas al directorio autorizado del proyecto.
- Añadir límites de tiempo, tamaño de salida y número de reintentos.
- Pedir confirmación para operaciones destructivas o acciones externas.
- Normalizar errores y evitar registrar tokens o datos sensibles.

### P1 — Pruebas y calidad
- Añadir pruebas unitarias para el procesador de comandos, planificación y validación de rutas.
- Añadir comprobaciones automáticas de sintaxis y pruebas en integración continua.
- Probar entradas vacías, malformadas, rutas fuera del proyecto, fallos de herramientas y tiempos de espera.
- Documentar cómo ejecutar pruebas localmente.

### P2 — Orquestación fiable
- Definir estados de tarea: pending, running, succeeded, failed y cancelled.
- Validar cada plan con un esquema antes de ejecutarlo.
- Mantener la autorización separada de la planificación: un plan generado no concede permisos.
- Hacer que cada paso devuelva estado, resultado resumido y error normalizado.
- Evitar reintentar operaciones no idempotentes sin autorización explícita.

### P3 — Memoria controlada
- Diferenciar memoria episódica, semántica, procedimental y reflexiva.
- Guardar fuente, fecha, confianza e importancia para cada recuerdo.
- Permitir consultar, corregir y eliminar recuerdos.
- No guardar secretos ni información sensible por defecto.
- Aplicar límites de retención y controles de acceso.

### P4 — Observabilidad y mantenimiento
- Añadir logs estructurados con identificador de tarea y duración.
- Incluir comprobaciones de salud y una versión de MILY.
- Documentar configuración, dependencias y recuperación ante fallos.
- Medir latencia y tasa de errores antes de optimizar rendimiento.

## Criterios de aceptación
- Las pruebas pasan antes de integrar cambios.
- Las herramientas rechazan entradas inválidas y rutas no autorizadas.
- Los errores no exponen secretos.
- Las acciones con efectos externos requieren permisos adecuados.
- La documentación refleja el comportamiento real del código.

## Siguiente paso
Revisar la estructura y los módulos existentes del repositorio y convertir cada prioridad en cambios pequeños sobre los archivos reales. Este plan es una guía; no afirma que las funciones estén implementadas todavía.
