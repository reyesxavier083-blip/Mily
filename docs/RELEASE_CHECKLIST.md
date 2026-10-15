# Lista de salida y validación de MILY

Este documento separa lo que ya está comprobado de lo que exige acceso al hosting o un dispositivo de prueba. No declarar producción lista solo porque la compilación terminó.

## Estado confirmado en GitHub Actions (15 de octubre de 2026)

- Rama principal más reciente revisada: `784fb736d91afd271a524ed0ba8ebeb72fb03e15`.
- CI de pruebas y backend: correcto en el commit anterior indicado. Incluye pruebas Python, sintaxis JavaScript de web/backend y prueba de la guardia de autenticación de producción.
- CI de calidad: correcto en el commit principal revisado. Incluye compilación de fuentes Python, pruebas, y análisis de sintaxis de web/backend.
- APK Android de depuración: el workflow `38758505149` terminó correctamente. Compiló, ejecutó las pruebas unitarias, verificó el APK, y persistió el archivo de fuentes Android validado.
- Artefactos del workflow Android: `mily-android-debug-apk` (SHA-256 del archivo ZIP de artefacto: `0e9270654bbc8ba3f79946ab74b739fc52767f56eba76c36245737800b034736`) y `mily-android-patched-source` (SHA-256 del ZIP: `0279b9edfad14d8aa037a4b843868e213e7010945501bec688e21fd1a1826614`). Estos son artefactos de GitHub Actions, no una publicación firmada de producción.
- Este APK aún necesita una instalación y prueba real en dispositivo/emulador. El artefacto se generó durante una ejecución cuyo SHA de entrada era `9006eab2d50745aa6fd4947cd1df78ad8f07e1d0`; no afirmar que ya se probó manualmente en el teléfono.
- GitHub Pages no se considera publicado: una ejecución anterior del workflow de Pages falló en la configuración de Pages del repositorio. No es algo que el workflow pueda activar por sí solo si la configuración del repositorio no está habilitada.
- Backend: el código y la plantilla de Render están en el repositorio, pero todavía no hay evidencia de un despliegue externo ni de una conversación real contra un servidor público.

## Bloqueos de lanzamiento

### A. Habilitar y comprobar GitHub Pages

1. En el repositorio, abre **Settings → Pages**.
2. En **Build and deployment**, selecciona **GitHub Actions** como origen.
3. Revisa **Actions → Deploy MILY Web to GitHub Pages** y confirma que la ejecución termine en `success`.
4. Abre la URL que indique GitHub Pages en la configuración y comprueba que carguen los estilos y el JavaScript.
5. La web inicialmente mostrará el backend como desconectado hasta configurar un servicio de backend funcional.

### B. Desplegar el backend en un hosting autorizado

1. En Render, usa **New + → Blueprint** y selecciona este repositorio, o crea un servicio Docker con `backend/mily-openai` como directorio raíz.
2. Configura como secretos del hosting `OPENAI_API_KEY` y `MILY_API_TOKEN`. No los pongas en el repositorio, en el código del frontend, ni dentro del APK.
3. Configura `MILY_ALLOWED_ORIGINS` con el origen exacto que muestre Pages. Mantén HTTPS activo.
4. Comprueba `GET /health`: debe devolver `ok: true` y `configured: true`. El endpoint no demuestra por sí solo que las conversaciones funcionen.
5. Sin token, una llamada a `POST /v1/mily/responses` debe devolver `401`; con token, una solicitud válida debe llegar al proveedor y responder correctamente.
6. Prueba CORS desde el origen publicado, revisa registros del hosting y configura límites de gasto/cuotas.

### C. Validar la web y la conversación

1. Abre la web publicada y configura la URL HTTPS del backend.
2. Introduce únicamente el token de cliente correspondiente, nunca `OPENAI_API_KEY`.
3. Prueba conexión, conversación normal, respuesta a entrada vacía/malformada y recuperación cuando el backend no responde.
4. Confirma que el backend rechaza solicitudes de orígenes no permitidos.

**Advertencia:** el token de cliente guardado en el navegador puede ser leído por JavaScript que se ejecute en ese mismo origen. Un token compartido sirve para una instancia personal controlada, pero no constituye autenticación por usuario para un servicio público multiusuario. Antes de abrir MILY al público, implementar identidad por usuario, cuotas por usuario y tokens de corta duración.

### D. Validar Android

1. Descarga el artefacto `mily-android-debug-apk` desde la ejecución de GitHub Actions enlazada en `docs/STATUS.md`.
2. Verifica que el artefacto provenga de la ejecución exitosa esperada y que no haya caducado.
3. Instala el APK en un dispositivo de prueba o emulador; confirma que Android permite instalarlo y que la app se abre sin cerrarse.
4. Prueba la navegación y una conversación contra el backend con token configurado.
5. Verifica que el cliente Android envíe `Authorization: Bearer …` cuando se exige autenticación. No incrustes la clave del proveedor de IA en el APK.
6. Repite la compilación tras los cambios que alteren `mily.zip` o el workflow Android.

### E. Seguridad y confiabilidad antes de producción

- [ ] Confirmar que los secretos solo existen en el gestor de secretos del hosting.
- [ ] Activar HTTPS y limitar CORS al origen correcto.
- [ ] Probar denegación por ausencia de token y por token incorrecto.
- [ ] Poner límites de coste y de solicitudes; el rate limit actual es en memoria y no sustituye cuotas por usuario.
- [ ] Decidir la política de almacenamiento. La memoria actual del backend se guarda en RAM y se pierde al reiniciar; no almacenar secretos ni datos sensibles en ella.
- [ ] Probar errores de red, peticiones inválidas y límites de carga.
- [ ] Guardar una versión estable y mantener plan de reversión.
- [ ] Ejecutar la suite de pruebas y revisar todos los workflows después de cada cambio importante.

## Criterio final

MILY puede considerarse **compilada** cuando el workflow correspondiente pasa; **validada en dispositivo** solo tras instalar y probar el APK; **web publicada** solo tras confirmar Pages y abrir la URL real; y **lista para producción** solo después de desplegar y probar el backend, autenticar las peticiones y completar la revisión de costes y seguridad.
