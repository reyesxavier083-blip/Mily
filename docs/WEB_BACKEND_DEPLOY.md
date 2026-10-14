# MILY Web + Backend: puesta en marcha

## Estado del proyecto

- La web estática vive en `web/` y se publica con GitHub Actions / GitHub Pages.
- El backend Node.js está en `backend/mily-openai/`.
- La web necesita la URL HTTPS del backend y, si está habilitado, un token de cliente.
- El backend necesita que el propietario configure secretos y despliegue el servicio en un proveedor de hosting. GitHub Pages no ejecuta Node.js.

## 1. Publicar el backend

1. Crea un servicio de contenedor Docker usando `backend/mily-openai/Dockerfile` como Dockerfile y `backend/mily-openai` como contexto.
2. En los secretos/variables privadas del proveedor configura `OPENAI_API_KEY` y `MILY_API_TOKEN`. No los escribas en el repositorio, issues, frontend o APK.
3. Configura `MILY_ALLOWED_ORIGINS=https://reyesxavier083-blip.github.io`.
4. Usa el puerto que el proveedor inyecte o configura `MILY_PORT=8080`; activa HTTPS.
5. Comprueba `GET https://TU-SERVIDOR/health`. Debe responder JSON con `ok: true` y `configured: true`.

No se ha desplegado el backend a un proveedor externo desde este repositorio: eso requiere una cuenta/entorno de hosting autorizado y sus secretos.

## 2. Conectar MILY Web

1. Abre la web de MILY.
2. Pulsa **Conexión y ajustes**.
3. Introduce la URL HTTPS base del backend.
4. Pega el valor de `MILY_API_TOKEN` en el campo de token del cliente.
5. Pulsa **Probar conexión** y después **Guardar ajustes**.
6. Envía un mensaje de prueba. Revisa logs del backend si devuelve un error.

El token de cliente puede ser visto por quien tenga acceso al navegador. Para un producto público multiusuario, usa login individual, cuotas y tokens de corta duración.

## 3. Android

El backend puede compartir las rutas con Android, pero al activar `MILY_API_TOKEN` el cliente Android debe enviar `Authorization: Bearer ...`. Verifica el proveedor Android y la configuración de compilación antes de usar el mismo servidor. Nunca pongas `OPENAI_API_KEY` dentro del APK.

## 4. Validación

- `npm install && npm run check` dentro de `backend/mily-openai`.
- `node --check web/app.js` desde la raíz.
- `GET /health` responde sin revelar claves.
- Una llamada a una ruta API sin token devuelve `401` si se configuró `MILY_API_TOKEN`.
- Las solicitudes de orígenes no incluidos en `MILY_ALLOWED_ORIGINS` se rechazan.
- Las rutas API están limitadas por IP en memoria; en varias instancias se recomienda un limitador compartido.

La memoria actual se conserva en RAM y se pierde al reiniciar. La persistencia, autenticación por usuario, observabilidad y cuotas por usuario son etapas separadas.
