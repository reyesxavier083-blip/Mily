# MILY Web + Android: arquitectura de integración

## Estado real

Este repositorio contiene el núcleo Python de MILY y ahora una interfaz web estática inicial en `web/`. La interfaz usa el contrato HTTP del backend MILY existente en el archivo Android V18: `GET /health` y `POST /v1/mily/responses`.

La interfaz web **no incluye una clave de proveedor**, no ejecuta el modelo por sí sola y no sustituye al backend. El backend Node.js ya está versionado en `backend/mily-openai/`; el proyecto Android V18 permanece en el archivo integrado por separado y no está expandido como fuentes en este repositorio. Para obtener respuestas de IA, el backend debe desplegarse y configurarse en un proveedor externo.

## Componentes

- **Web client** (`web/`): HTML, CSS y JavaScript sin framework ni compilación; diseño adaptable a móvil y escritorio.
- **Backend HTTP** (`backend/mily-openai/`): conserva la clave API, valida solicitudes, llama a Responses API y devuelve `outputText`. Incluye autenticación Bearer configurable, allowlist CORS, limitación básica por IP y rutas de memoria/herramientas/knowledge. Contrato principal: `POST /v1/mily/responses`.
- **Android**: debe apuntar al mismo backend mediante `MILY_BACKEND_URL`, de acuerdo con la configuración de la app.
- **Core Python**: aporta módulos de seguridad, permisos, tareas, eventos, memoria y observabilidad. La interfaz web no los importa directamente; conectarlos requiere un adaptador explícito y pruebas de integración.

## Probar la interfaz

Abre `web/index.html` en un navegador para revisar el diseño. Para usar el chat, sirve el directorio por HTTPS y configura la URL base del backend desde **Conexión y ajustes**. En desarrollo local puedes usar una URL HTTP local, según las reglas del navegador y la red.

La interfaz comprueba `/health` y envía los últimos 20 mensajes a `/v1/mily/responses`. El endpoint debe aceptar `model`, `instructions`, `input`, `temperature` y `maxOutputTokens`, y devolver `outputText` (o `text`). El contrato coincide con el backend Node.js incluido en el archivo V18.

## Seguridad antes de producción

1. No añadas claves API al HTML, JavaScript, almacenamiento local ni al repositorio.
2. Para producción, configura `MILY_API_TOKEN` y `OPENAI_API_KEY` como secretos del proveedor; no los guardes en Git.
3. Usa HTTPS y define `MILY_ALLOWED_ORIGINS` solo con los orígenes web previstos.
4. El limitador actual es básico y en memoria; configura cuotas/costes en el proveedor y usa limitador compartido si escalas a varias instancias.
5. No guardes conversaciones en el navegador salvo que se diseñe una política de privacidad y retención explícita.
6. La memoria, las herramientas y las acciones con efectos deben seguir sujetos a permisos del backend; el cliente web no concede permisos.

## Siguientes pasos

- Desplegar el backend Node.js de este repositorio como servicio controlado y configurar sus secretos.
- Alinear la configuración Android con la URL HTTPS de producción.
- Diseñar un adaptador entre las solicitudes del backend y los módulos Python de MILY, sin mezclar permisos, planificación y ejecución.
- Probar flujo web y Android contra el mismo backend, incluidos errores, desconexión y solicitudes inválidas.
- Automatizar pruebas del cliente web y una comprobación de despliegue.
