# LEYRA — Puente de integración Android

Implementación de referencia del `PlatformBridge` que conecta el motor
`leyra_core/apps` con el dispositivo. **No se compila en este repositorio**: el
proyecto Android vive en `mily.zip` y debe integrar estos archivos y verificarlos en
un dispositivo real.

## Contenido

| Archivo | Función |
| --- | --- |
| `Contracts.kt` | `PlatformBridge`, `DiscoveredApp`, `ActionStep`, `ExecutionResult`, espejos de conectores |
| `PackageDiscovery.kt` | Descubrimiento con `PackageManager` y consultas visibles |
| `AppIntegrationBridge.kt` | Despacho de `launch`, `share`, `deep_link`/`app_link`, `content_provider`, `shortcut` |
| `../AndroidManifest.queries.xml` | Bloque `<queries>` mínimo para el manifiesto |

## Integración

1. Copia `src/main/java/ai/leyra/integration` al módulo `app` del proyecto Android.
2. Añade el bloque `<queries>` del archivo XML al `AndroidManifest.xml`.
3. Si vas a compartir archivos, declara un `FileProvider` y pasa su authority:
   `AppIntegrationBridge(context, fileProviderAuthority = "${applicationId}.files")`.
4. Inyecta el puente en el motor. Si el motor corre en el servidor, envía el catálogo
   a `POST /v1/apps/discovery` y ejecuta localmente los pasos devueltos por el plan,
   enviando el resultado de vuelta.
5. Prueba en dispositivo: apertura, compartir texto, deep link, app desinstalada,
   permisos revocados y política en nivel 1.

## Reglas de seguridad

- No se leen datos privados de otras apps.
- No se eluden permisos ni se desactivan protecciones del sistema.
- Toda acción externa requiere confirmación del usuario en la UI.
- Los errores de Android (`SecurityException`, `ActivityNotFoundException`) se
  reportan como `denied`/`failed`, nunca como éxito.

## Pendiente en la app nativa

- UI Compose completa de LEYRA (el diseño está en `web/` como referencia).
- Servicio de accesibilidad opcional con opt-in explícito (nivel 5).
- Registro de plugins con verificación de firma.
- Pruebas instrumentadas (`androidTest`) del puente y del catálogo.
