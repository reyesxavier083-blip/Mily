# Estado de MILY

Última revisión: 2026-10-15 (UTC).

## Cambios integrados en main

- PR #17 integrado: aislamiento profundo de metadatos y resultados de tareas. Las pruebas de Python y las comprobaciones de calidad pasaron en la rama antes de integrar.
- PR #16 integrado: corrección del flujo de GitHub Pages y panel de actividad de sesión.
- PR #19 integrado: el backend ahora rechaza iniciar en `NODE_ENV=production` si `MILY_API_TOKEN` falta o está vacío; desarrollo local conserva el comportamiento sin token. Incluye cuatro pruebas Node y un job de CI para backend.
- PR #20 integrado: el contador de mensajes del usuario y el de respuestas reales de MILY actualizan el gráfico de sesión.
- El PR #18 anterior se cerró como duplicado obsoleto; su corrección quedó reaplicada y validada en el PR #19.
- Las pruebas de Python del último commit principal terminaron correctamente.
- En la rama de seguridad, las pruebas Python, la sintaxis del backend y las cuatro pruebas del guard de autenticación pasaron en GitHub Actions.
- En la rama del gráfico, las pruebas y la comprobación de calidad de JavaScript pasaron.

## Estado de automatizaciones al revisar

- GitHub Actions de pruebas de Python en el último commit de main: correcto.
- Comprobaciones de calidad del último commit de main: en ejecución durante esta revisión; volver a comprobar antes de publicar una versión.
- Compilación Android desde el archivo de fuentes integrado: en ejecución; todavía no declarar APK validado hasta que terminen compilación, pruebas, inspección del APK y carga del artefacto.
- Despliegue web a GitHub Pages: falló en `Configure GitHub Pages` porque el repositorio aún no tiene un sitio Pages habilitado/configurado. La sintaxis de `web/app.js` sí pasó. Esto es una configuración del repositorio, no un error de sintaxis de la web.

## Seguridad y despliegue pendientes

1. Habilitar GitHub Pages desde Settings → Pages → Build and deployment → Source: GitHub Actions. La automatización no pudo activar Pages por sí sola.
2. Desplegar `backend/mily-openai` en un proveedor externo con HTTPS y configurar como secretos `OPENAI_API_KEY` y `MILY_API_TOKEN`; configurar `MILY_ALLOWED_ORIGINS` para el dominio publicado.
3. Probar `GET /health` y una conversación real con credenciales de prueba, sin publicar secretos en el repositorio ni en el cliente.
4. Confirmar que los clientes web y Android envían la cabecera Authorization cuando el token está habilitado. No incrustar `OPENAI_API_KEY` en el APK.
5. Esperar y revisar el workflow Android: build, pruebas, verificación de integridad y artefactos. Después probar instalación y conversación básica en un dispositivo o emulador.
6. Verificar que los módulos Python se conectan en el runtime real y que las herramientas requieren permisos explícitos antes de ejecutar acciones con efectos.
7. Hacer una comprobación final de configuración, secretos, permisos, costes y modo sin conexión.

## Criterio de finalización

MILY sigue en desarrollo. No declararla lista para producción ni afirmar que la web está publicada hasta confirmar Pages, el backend desplegado y una conversación real. No declarar el APK validado hasta que el workflow Android termine correctamente, el APK pase sus verificaciones y se confirme una instalación/prueba básica.
