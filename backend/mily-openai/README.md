# MILY OpenAI Backend

Servicio Node.js para conectar la web y los clientes de MILY con OpenAI sin exponer `OPENAI_API_KEY` en el navegador, APK o repositorio.

## Ejecutar localmente

Requiere Node.js 20 o superior.

1. En esta carpeta, instala dependencias: `npm install`.
2. Define `OPENAI_API_KEY` como variable de entorno. Para pruebas locales puedes dejar `MILY_API_TOKEN` vacío; **no hagas eso en un servidor público**.
3. Ejecuta `npm start`. El servicio escucha en `0.0.0.0:8080` por defecto.
4. Comprueba `GET /health`.
5. En MILY Web, abre **Conexión y ajustes**, introduce la URL del servidor y, si está habilitado, el token de cliente.

## Validación local

```bash
npm run check
npm test
```

Las pruebas verifican que producción rechace tokens ausentes o en blanco y que el desarrollo local permita omitir el token.

## Despliegue público

- Usa este directorio como contexto de construcción Docker.
- Configura `OPENAI_API_KEY` y `MILY_API_TOKEN` como **secretos del proveedor de hosting**, nunca como variables incluidas en el frontend.
- Configura `MILY_ALLOWED_ORIGINS=https://reyesxavier083-blip.github.io` (sin barra final) para permitir la web de GitHub Pages.
- Mantén HTTPS habilitado. Usa un token de cliente largo, aleatorio y exclusivo para MILY.
- La autenticación por token protege las rutas de API, pero un token compartido en una web pública puede copiarse desde el navegador. Para una publicación multiusuario real, sustituye el token compartido por autenticación por usuario y cuotas por cuenta.
- El limitador incluido es básico y en memoria; para despliegues con varias instancias, usa un rate limiter compartido.
- La memoria incluida vive en RAM y se pierde al reiniciar. No la trates como almacenamiento persistente.

## Rutas

- `GET /health`: estado del servicio y modelo predeterminado (sin secretos).
- `POST /v1/mily/responses`: conversación con Responses API.
- `GET/POST /v1/mily/knowledge/vector-stores`, `POST /v1/mily/knowledge/files`, `POST /v1/mily/knowledge/search`: conocimiento opcional.
- `POST /v1/mily/memory/list|upsert|remove`: memoria temporal en RAM.
- `POST /v1/mily/tools/execute`: pasarela de herramientas de lista permitida.
- `POST /v1/mily/live/sessions`: negociación de sesión Live.

Todas las rutas excepto `/health` requieren `Authorization: Bearer <MILY_API_TOKEN>` cuando el token está configurado. En producción, configúralo siempre.

## Android

Configura la URL del backend mediante la configuración de compilación de la app. Si activas `MILY_API_TOKEN`, el cliente Android también debe enviar la cabecera Authorization; no se debe incrustar la clave de OpenAI en el APK. No se afirma compatibilidad autenticada con clientes que no envíen dicha cabecera.
