# LEYRA IA — Integración con aplicaciones Android

Este documento define cómo LEYRA descubre, vincula y utiliza otras aplicaciones
Android **sin romper el aislamiento del sistema**. Es el contrato entre
`leyra_core/apps` (motor ya implementado y probado) y el dispositivo.

## Qué es posible y qué no

Android ejecuta cada aplicación en su propio proceso y sandbox. Desde otra app solo
se puede:

1. **Abrir** una aplicación con un intent de lanzamiento público.
2. **Intercambiar** datos con `Intent`, `ACTION_SEND`, deep links, App Links,
   `ContentProvider` públicos, shortcuts y resultados de actividad.
3. **Llamar** a una API/SDK oficial con su propia autenticación.
4. **Implementar** un conector LEYRA publicado por la otra app (plugin).
5. **Interactuar** con elementos visibles mediante un servicio de accesibilidad
   activado expresamente por el usuario.

No es posible —y LEYRA no lo intenta— leer bases de datos privadas, extraer
almacenamiento interno ajeno, inyectar eventos sin accesibilidad, desactivar
protecciones, instalar APK en silencio ni eludir permisos. Cualquier afirmación
contraria sería falsa.

## Arquitectura

```
LEYRA CORE
   │  instrucción en lenguaje natural
   ▼
APP INTEGRATION ENGINE (Python, ya implementado)
   │  catálogo real · política · plan · confirmaciones · auditoría
   ▼
PlatformBridge  (Android, Kotlin)
   │  PackageManager · Intent · ClipData · ContentResolver · Shortcuts
   ▼
Aplicación de destino
   │  resultado público
   ▼
ExecutionResult → historial → respuesta al usuario
```

El motor puede ejecutarse dentro de la app (recomendado, sin red) o en el servidor
con el dispositivo como ejecutor. Si no hay puente, el motor devuelve
`unavailable`; nunca simula éxito.

## Contrato `PlatformBridge`

```kotlin
interface PlatformBridge {
    val name: String
    fun available(): Boolean
    fun discover(): List<DiscoveredApp>
    fun dispatch(step: ActionStep): ExecutionResult
}
```

`ActionStep` recibido del motor:

```json
{
  "connectorId": "whatsapp.public",
  "packageName": "com.whatsapp",
  "actionId": "share_text",
  "actionLabel": "Compartir texto",
  "arguments": { "text": "Hola equipo" },
  "requiresConfirmation": true,
  "reason": "La operación envía datos fuera de LEYRA; requiere tu confirmación explícita."
}
```

`ExecutionResult` devuelto: `status` ∈ `ok | unavailable | denied | failed |
confirmation_required | cancelled`, `detail` legible y `data` opcional.

La implementación de referencia está en `android/app-integration/`:
`PackageDiscovery.kt` (descubrimiento) y `AppIntegrationBridge.kt` (despacho).

## Visibilidad de paquetes

Desde Android 11, `PackageManager` solo devuelve apps visibles. Declara en
`AndroidManifest.xml` las consultas mínimas necesarias:

```xml
<queries>
  <!-- Apps con actividad de lanzamiento (catálogo de apertura) -->
  <intent>
    <action android:name="android.intent.action.MAIN" />
    <category android:name="android.intent.category.LAUNCHER" />
  </intent>
  <!-- Destinos de compartir texto -->
  <intent>
    <action android:name="android.intent.action.SEND" />
    <data android:mimeType="text/plain" />
  </intent>
  <!-- Apertura de enlaces en apps concretas -->
  <intent>
    <action android:name="android.intent.action.VIEW" />
    <data android:scheme="https" />
  </intent>
</queries>
```

`QUERY_ALL_PACKAGES` debe evitarse: Google Play exige justificarlo y declararlo en el
formulario de seguridad de datos. Prefiere `queries` específicas y explica en la app
qué se consulta.

## Flujo de vinculación

1. La app llama a `discover()` y envía el resultado a
   `POST /v1/apps/discovery` (o lo pasa directamente al motor embebido).
2. El motor anota la compatibilidad real de cada app.
3. El usuario abre **Aplicaciones vinculadas**, revisa permisos y vincula.
4. `POST /v1/apps/{paquete}/link` con los permisos concedidos.
5. Al revocar permisos, la integración pasa a **parcial** y las acciones afectadas
   dejan de planificarse.

## Niveles de integración

| Nivel | Mecanismo | Control en LEYRA |
| --- | --- | --- |
| 1 | Intent de lanzamiento público | Permitido por defecto |
| 2 | Compartir, deep links, App Links, providers públicos | Permitido; compartir exige confirmación |
| 3 | API/SDK oficial con auth | Requiere nivel 3 en la política y credenciales del conector |
| 4 | Plugin/conector firmado por la app | Requiere nivel 4; registro como no confiable hasta verificación |
| 5 | Servicio de accesibilidad | Desactivado; exige opt-in explícito y visible |

El nivel máximo efectivo nunca supera el configurado en la política. El nivel 5 sin
`accessibilityOptIn` se degrada a 4 y el diagnóstico lo refleja.

## Accesibilidad (nivel 5)

Si se implementa, debe ser un `AccessibilityService` propio, declarado en el
manifiesto, activado por el usuario en Ajustes → Accesibilidad, con:

- descripción explícita de qué elementos lee y qué acciones realiza;
- indicador permanente en la app cuando está activo;
- registro local de acciones;
- ningún acceso a texto de campos sensibles (`isPassword`, `isVisibleToUser=false`);
- desactivación inmediata desde la app.

Debe cumplir la política de Google Play sobre accesibilidad: uso declarado, no
encubierto y estrictamente necesario para la función del usuario.

## Plugins de otras apps

Una app puede publicar un conector LEYRA con un manifiesto JSON:

```json
{
  "id": "midominio.acciones",
  "name": "Mi App",
  "packageName": "com.midominio.app",
  "version": "1.4.0",
  "level": 3,
  "auth": "oauth2",
  "notes": "Exporta acciones de facturación mediante su SDK.",
  "actions": [{
    "id": "create_invoice",
    "label": "Crear factura",
    "kind": "intent",
    "level": 3,
    "destructive": true,
    "permissions": ["com.midominio.permission.INVOICE"],
    "parameters": [
      {"name": "amount", "type": "number", "required": true},
      {"name": "currency", "type": "string", "required": true}
    ]
  }]
}
```

El manifiesto se valida (`ConnectorManifest`): identificadores, versión, nivel
coherente, acciones únicas y parámetros tipados. Se registra como **no confiable**
hasta que exista verificación de firma (pendiente) y consentimiento del usuario.

## Seguridad aplicada en el motor

- Lista de apps bloqueadas y nivel máximo.
- Confirmación explícita por llamada en acciones que salen de LEYRA.
- Límite de pasos por plan y de tamaño de archivo.
- Denegación si el vínculo está desactivado, falta un permiso o la app no está
  instalada.
- Auditoría de vinculación, permisos, ejecución y errores (`/v1/apps` → `history`).
- Sin ejecución de código de terceros en el servidor.

## Integración con el proyecto Android existente

El proyecto Android vive en `mily.zip`. Pasos sugeridos:

1. Descomprimir y abrir en Android Studio (Kotlin, Compose).
2. Copiar `android/app-integration/src/main/java/ai/leyra/integration/*` al módulo
   `app` (paquete `ai.leyra.integration`).
3. Añadir el bloque `<queries>` al `AndroidManifest.xml`.
4. Registrar un `LeyraBridge` que implemente `PlatformBridge` y se inyecte en
   `AppIntegrationEngine(bridge = ...)`.
5. Exponer el catálogo y el despacho al WebView mediante `@JavascriptInterface`, o
   consumir la API con la URL del servidor y ejecutar localmente.
6. Probar en dispositivo real: apertura, compartir texto, deep link, permisos
   revocados, app desinstalada y política en nivel 1.

Sin prueba en dispositivo no se puede declarar la integración como operativa; el
repositorio lo mantiene como *especificado*.
