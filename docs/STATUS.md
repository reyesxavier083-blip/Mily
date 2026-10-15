# Estado de MILY

Última revisión: 2026-10-15 (UTC).

## Cambios integrados en main

- PR #17 integrado: aislamiento profundo de metadatos y resultados de tareas, con prueba de regresión para mutaciones anidadas.
- PR #16 integrado: corrección del flujo de publicación web y panel de actividad de sesión.
- PR #19 integrado: el backend rechaza iniciar en `NODE_ENV=production` si `MILY_API_TOKEN` falta o está vacío; desarrollo local conserva el comportamiento sin token. Incluye cuatro pruebas Node y CI de backend.
- PR #20 integrado: los contadores de mensajes del usuario y respuestas exitosas actualizan el gráfico de sesión.
- PR #21 integrado: el backend respeta el puerto `PORT` inyectado por el hosting y usa `MILY_PORT`/8080 como fallback; la sintaxis y pruebas CI pasaron en la rama.
- El PR #18 obsoleto se cerró como duplicado; su corrección quedó reaplicada en el PR #19.
- Las pruebas Python y las comprobaciones de calidad terminaron correctamente en el commit principal `aa243b943b97bf59886b8ae29b84494502836cb6`.
- En las ramas de seguridad y del gráfico, las pruebas y comprobaciones correspondientes pasaron.
- Se ajustó el workflow Android para que solo se ejecute al cambiar `mily.zip` o el propio workflow, y se añadió concurrencia por rama para reducir builds redundantes.
- Se corrigió la persistencia del archivo Android: el job comprueba si mily.zip cambió antes de sobrescribirlo.
- Se agregó .github/scripts/patch_android_backend_auth.py al workflow Android: incorpora configuración de URL HTTPS y token de cliente en la app, cifra el token con Android Keystore y envía Authorization Bearer tanto en chat como en voz. No incrusta OPENAI_API_KEY ni MILY_API_TOKEN en el APK; el nuevo flujo aún debe pasar la compilación y las pruebas.

## Estado de automatizaciones y bloqueos

- **Python:** workflow de pruebas [#38758625696](https://github.com/reyesxavier083-blip/Mily/actions/runs/38758625696) pasó en el commit `784fb736d91afd271a524ed0ba8ebeb72fb03e15`.
- **Calidad:** workflow [#38758625347](https://github.com/reyesxavier083-blip/Mily/actions/runs/38758625347) pasó en el commit `784fb736d91afd271a524ed0ba8ebeb72fb03e15`.
- **Android — build anterior:** el workflow #38758505149 compiló, probó y verificó el APK; sin embargo, es anterior al arreglo de autenticación que se está validando ahora.
- **Android — autenticación:** la nueva ejecución #38761576180 continúa en curso en Build debug APK. Aún no existe un resultado verificable para este cambio; no marcarlo como compilado hasta que termine.
- **Web / GitHub Pages:** el despliegue falló en `Configure GitHub Pages` porque el repositorio todavía no tiene un sitio Pages habilitado/configurado. La sintaxis de `web/app.js` pasó. El workflow no puede activar Pages por sí solo con la configuración actual.
- **Backend:** código versionado, pero todavía no desplegado en un proveedor externo. No se ha comprobado una conversación real contra un backend público.

## Siguientes pasos necesarios

Consulta `docs/RELEASE_CHECKLIST.md` para la lista operativa completa y los criterios de salida.

1. Habilitar GitHub Pages desde Settings → Pages → Build and deployment → Source: GitHub Actions.
2. Desplegar `backend/mily-openai` en un proveedor autorizado con HTTPS y configurar como secretos `OPENAI_API_KEY` y `MILY_API_TOKEN`; configurar `MILY_ALLOWED_ORIGINS` con el origen web publicado.
3. Probar `GET /health` y una conversación real; comprobar también que una llamada sin token a una ruta protegida devuelva `401`.
4. Confirmar que web y Android envían `Authorization` cuando el token está habilitado. Nunca incrustar `OPENAI_API_KEY` en el frontend ni en el APK.
5. Confirmar que el workflow Android #38761576180 termine correctamente, descargar y revisar sus artefactos, y probar instalación y conversación en un dispositivo o emulador.
6. Validar la integración entre módulos Python y runtime real de MILY, manteniendo permisos explícitos antes de ejecutar acciones con efectos.
7. Hacer una revisión final de configuración, secretos, permisos, costes y modo sin conexión.

## Criterio de finalización

MILY sigue en desarrollo. No declarar la web publicada hasta confirmar GitHub Pages, ni declarar producción lista hasta desplegar y probar el backend. No declarar el APK validado hasta que el workflow Android termine correctamente y se verifique la instalación/prueba básica.
