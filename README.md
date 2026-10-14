# MILY

Asistente de IA modular en desarrollo. MILY se mantiene como proyecto independiente de NEXUS.

## Desarrollo

- `mily_core/security.py`: valida rutas para limitar el acceso al espacio de trabajo autorizado.
- `mily_core/tasks.py`: máquina de estados para el ciclo de vida de tareas; no ejecuta herramientas ni concede permisos.
- `tests/`: pruebas unitarias de seguridad y estados de tareas.
- `docs/MEJORA_ARQUITECTURA_MILY.md`: hoja de ruta técnica.

## Ejecutar las pruebas

Requiere Python 3.10 o posterior. Desde la raíz del repositorio:

```bash
python -m unittest discover -s tests -v
```

Las pruebas también se ejecutan automáticamente mediante GitHub Actions en cada push a `main` y en cada pull request.

## Nota de seguridad

Las comprobaciones de rutas deben aplicarse en las herramientas que leen o escriben archivos. La máquina de estados de tareas no sustituye la autorización de acciones externas o destructivas. No guardes claves API ni contraseñas en el repositorio.
