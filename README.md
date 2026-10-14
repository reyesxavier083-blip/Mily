# MILY

Asistente de IA modular en desarrollo. MILY se mantiene como proyecto independiente de NEXUS.

## Módulos actuales

- `mily_core/security.py`: valida rutas relativas y bloquea escapes del espacio de trabajo, incluidos enlaces simbólicos.
- `mily_core/permission_manager.py`: autoriza herramientas mediante una lista de confianza y exige confirmación explícita para escritura, acciones externas y operaciones destructivas; no ejecuta herramientas ni conserva aprobaciones.
- `mily_core/tasks.py`: máquina de estados con transiciones permitidas para tareas; no ejecuta herramientas ni concede permisos.
- `mily_core/task_manager.py`: coordina creación, inicio, éxito, fallo y cancelación de tareas; publica eventos y registra duración sin escribir errores crudos en los logs.
- `mily_core/event_bus.py`: bus de eventos en memoria, con aislamiento entre suscriptores y registro de resultados de despacho sin registrar los payloads.
- `mily_core/observability.py`: logs JSON con límites de tamaño y redacción de patrones comunes de credenciales.
- `mily_core/memory.py`: memoria temporal en proceso con categorías, procedencia, búsqueda y límite de capacidad. No guarda datos en disco.
- `web/`: interfaz web adaptable (HTML/CSS/JavaScript) que se conecta al backend mediante `/health` y `/v1/mily/responses`.
- `tests/`: pruebas unitarias de seguridad, tareas, memoria, eventos, observabilidad y coordinación de tareas.
- `docs/MEJORA_ARQUITECTURA_MILY.md`: hoja de ruta técnica.
- `docs/STATUS.md`: estado comprobado y bloqueos pendientes del proyecto.
- `docs/WEB_ANDROID_ARQUITECTURA.md`: contrato de integración web/Android y requisitos de despliegue.

## MILY Web

La interfaz inicial está en `web/index.html`. Puede abrirse para revisar el diseño, pero para conversar con el modelo necesita un backend accesible. Abre **Conexión y ajustes** e indica la URL base del servidor. La web no contiene ni solicita una clave API del proveedor.

El backend Node.js está ahora en `backend/mily-openai/` e incluye Dockerfile, configuración de ejemplo, autenticación Bearer configurable, allowlist CORS, límite básico de solicitudes, Responses API, memoria temporal y File Search opcional. Consulta `backend/mily-openai/README.md` y `docs/WEB_BACKEND_DEPLOY.md`.

Para producción, configura `OPENAI_API_KEY`, `MILY_API_TOKEN` y `MILY_ALLOWED_ORIGINS` como variables/secretos del hosting, habilita HTTPS y revisa el límite de costes. El backend todavía necesita ser desplegado en un proveedor externo; GitHub Pages solo publica la web estática. La app Android del archivo integrado no está expandida en este repositorio y debe enviar Authorization si se habilita el token.

## Ejecutar las pruebas

Requiere Python 3.10 o posterior. Desde la raíz del repositorio:

```bash
python -m compileall -q mily_core tests
python -m unittest discover -s tests -v
```

Si tienes Node.js instalado, valida también el JavaScript de la interfaz:

```bash
node --check web/app.js
node --check backend/mily-openai/server.mjs
```

GitHub Actions ejecuta automáticamente las comprobaciones de sintaxis y las pruebas en los cambios de `main` y en pull requests.

## Ejemplo: administrar una tarea

```python
from mily_core.task_manager import TaskManager

tasks = TaskManager()
tasks.create("demo-1", metadata={"source": "manual"})
tasks.start("demo-1")
tasks.succeed("demo-1", result={"ok": True})
print(tasks.get("demo-1").status.value)  # succeeded
```

El coordinador solo gestiona estados y eventos: no ejecuta herramientas, no concede permisos ni sustituye la autorización de operaciones externas.

## Nota de seguridad

La memoria actual es volátil y no debe usarse para secretos ni datos personales sensibles. Las comprobaciones de rutas deben aplicarse en las herramientas que leen o escriben archivos. Los logs intentan redactar credenciales comunes, pero eso no convierte en seguro registrar contenido privado: evita pasar secretos o datos personales a los logs. No guardes claves API ni contraseñas en el repositorio.
