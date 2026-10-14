# MILY Web + Android: arquitectura de integración

## Estado real

Este repositorio contiene el núcleo Python de MILY y ahora una interfaz web estática inicial en `web/`. La interfaz usa el contrato HTTP del backend MILY existente en el archivo Android V18: `GET /health` y `POST /v1/mily/responses`.

La interfaz web **no incluye una clave de proveedor**, no ejecuta el modelo por sí sola y no sustituye al backend. Para obtener respuestas de IA debe conectarse a un backend desplegado y configurado. El código del backend Node.js y el proyecto Android V18 se encuentran en el archivo integrado por separado; no se asume que formen parte de este repositorio Git.

## Componentes

- **Web client** (`web/`): HTML, CSS y JavaScript sin framework ni compilación; diseño adaptable a móvil y escritorio.
- **Backend HTTP**: conserva las claves API, valida solicitudes, llama al proveedor y devuelve `outputText`. Contrato esperado: `POST /v1/mily/responses`.
- **Android**: debe apuntar al mismo backend mediante `MILY_BACKEND_URL`, de acuerdo con la configuración de la app.
- **Core Python**: aporta módulos de seguridad, permisos, tareas, eventos, memoria y observabilidad. La interfaz web no los importa directamente; conectarlos requiere un adaptador explícito y pruebas de integración.

## Probar la interfaz

Abre `web/index.html` en un navegador para revisar el diseño. Para usar el chat, sirve el directorio por HTTPS y configura la URL base del backend desde **Conexión y ajustes**. En desarrollo local puedes usar una URL HTTP local, según las reglas del navegador y la red.

La interfaz comprueba `/health` y envía los últimos 20 mensajes a `/v1/mily/responses`. El endpoint debe aceptar `model`, `instructions`, `input`, `temperature` y `maxOutputTokens`, y devolver `outputText` (o `text`). El contrato coincide con el backend Node.js incluido en el archivo V18.

## Seguridad antes de producción

1. No añadas claves API al HTML, JavaScript, almacenamiento local ni al repositorio.
2. No expongas el backend públicamente hasta implementar autenticación de clientes, límites de frecuencia y límites de coste.
3. Usa HTTPS en producción y configura CORS solo para los dominios web previstos.
4. Añade protección contra abuso, límites de cuerpo y validación del lado del servidor.
5. No guardes conversaciones en el navegador salvo que se diseñe una política de privacidad y retención explícita.
6. La memoria, las herramientas y las acciones con efectos deben seguir sujetos a permisos del backend; el cliente web no concede permisos.

## Siguientes pasos

- Integrar o desplegar el backend Node.js desde el archivo V18 como servicio controlado.
- Añadir autenticación y límites de uso antes de habilitar acceso público.
- Alinear la configuración Android con la URL HTTPS de producción.
- Diseñar un adaptador entre las solicitudes del backend y los módulos Python de MILY, sin mezclar permisos, planificación y ejecución.
- Probar flujo web y Android contra el mismo backend, incluidos errores, desconexión y solicitudes inválidas.
- Automatizar pruebas del cliente web y una comprobación de despliegue.
