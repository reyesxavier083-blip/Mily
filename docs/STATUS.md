# Estado de MILY

Última revisión: 2026-10-15 (UTC).

## Cambios verificados

- PR #16 y #20 corrigieron publicación web y métricas de sesión.
- PR #17 reforzó el aislamiento de metadatos y resultados de tareas.
- PR #19 añadió un control de inicio seguro en producción; PR #21 corrigió la selección del puerto del servidor.
- El workflow Android ahora corrige el archivo de fuentes, agrega configuración HTTPS y token de cliente cifrado en Android Keystore, y autoriza peticiones de chat y voz.
- Workflow Android #38761576180: **éxito**. Gradle build, pruebas unitarias, verificación del APK y subida de artefactos pasaron. La app declara el identificador `com.mily.ai`.
- APK de depuración: artefacto `mily-android-debug-apk`, SHA-256 del ZIP `ea05e179c62359e3e8f32c864f61035c1a0916cdb496e419066b14838282934d`.
- Fuentes Android parcheadas: artefacto `mily-android-patched-source`, SHA-256 del ZIP `6edfb0bb1d7cc36d4173e17c96ff99208fbd52eb01a5ddf57860cb9ec5dd2fba`.
- En un commit posterior se corrigieron las comillas del resumen del APK y se actualizaron acciones del workflow. Sus nuevas ejecuciones deben revisarse antes de considerar ese último ajuste cerrado.
- La instalación manual del APK y la conversación real contra el backend aún no están probadas.

## Bloqueos externos

- **GitHub Pages:** el despliegue previo falló porque Pages no estaba habilitado/configurado. En el repositorio, abrir Settings → Pages → Build and deployment → Source y elegir GitHub Actions. Luego comprobar el despliegue y abrir la URL pública.
- **Backend:** existe el código y la plantilla de despliegue, pero no se ha confirmado publicación externa. Tras desplegarlo con secretos guardados en el hosting, probar /health, el rechazo sin token, CORS y una conversación real.
- **Android:** instalar el APK en un dispositivo o emulador; probar apertura, navegación, chat y voz.

## Riesgos que faltan

La memoria y el limitador actual están en RAM y se pierden al reiniciar. Un token de cliente compartido no es suficiente para un servicio público multiusuario. Antes de producción revisar autenticación por usuario, cuotas, costes, permisos, recuperación y modo sin conexión.

## Criterio de finalización

Compilado significa que CI pasó; validado en dispositivo exige una prueba manual; web publicada exige Pages funcionando; producción lista exige backend público probado y revisión final de seguridad.
