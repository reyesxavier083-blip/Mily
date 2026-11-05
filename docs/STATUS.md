# Estado de LEYRA IA

Última revisión: 2026-11-05 (UTC).

## LEYRA IA — estado verificado en esta revisión

**Probado automáticamente**

- 135 pruebas de motores (`tests/`): integración de apps, herramientas, router
  multimodelo, memoria SQLite, voz y diagnóstico. Todas en verde.
- 37 pruebas de API (`backend/leyra-api/tests/`): salud, autenticación, CORS implícito,
  chat con proveedor falso, bucle real de herramientas, herramientas, integraciones
  Android, memoria, conversaciones, voz y archivos. Todas en verde.
- `node --check web/app.js` correcto.
- Arranque real del servidor (`run.py`) y verificación manual de `/health`,
  `/v1/diagnostics`, `/v1/tools`, `/v1/apps/*`, `/v1/memory`, `/v1/conversations`,
  `/v1/voice` y `/v1/files` con `curl`.
- Interfaz verificada con un arnés DOM (jsdom) contra el servidor real: arranque sin
  errores de JavaScript, navegación por las diez vistas, envío de mensaje con aviso
  honesto por falta de proveedor, ejecución de herramienta desde la UI, diagnóstico,
  resolución de instrucción de integración y cambio de preferencias.

**No verificado / pendiente**

- Conversación real contra un proveedor de IA: no hay credenciales en este entorno.
  El camino está probado con un proveedor simulado, no con tráfico real.
- App Android: el puente Kotlin de `android/app-integration/` no se ha compilado ni
  ejecutado en dispositivo. No se declara operativo.
- Reconocimiento y síntesis de voz reales: dependen del navegador del usuario; no se
  probaron con micrófono ni altavoces en este entorno.
- Lectura de PDF: `pypdf` figura en `requirements.txt` pero no se ejecutó una prueba
  con un PDF real en esta sesión.
- PostgreSQL/pgvector, cifrado en reposo, sincronización de memoria, firma de plugins
  y servicio de accesibilidad: no implementados.
- Despliegue público: no se ha publicado esta versión en ningún hosting.

**Riesgos conocidos**

- SQLite y el limitador de tasa son locales al proceso; no escalan horizontalmente.
- La memoria y los archivos se almacenan sin cifrar.
- Un token de API compartido no sustituye autenticación por usuario.
- El reconocimiento de voz del navegador puede procesar audio en servidores del
  proveedor del navegador; se advierte en la interfaz.
- `confirmed: true` en `/v1/apps/resolve` confirma la llamada, no una sesión; la UI
  pide confirmación explícita antes de enviarlo.

---

## Etapa anterior (MILY) — histórico

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
