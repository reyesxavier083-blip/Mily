# LEYRA IA — Especificación maestra implementada

Última revisión: 2026-11-05.

Este documento traza **cada bloque de la orden maestra** contra lo que existe hoy en
el repositorio y lo que falta. La regla es simple: si un módulo no se puede ejecutar
y verificar, aquí aparece como *parcial* o *pendiente*, nunca como operativo.

Estados usados:

- **Implementado y probado**: hay código ejecutable y pruebas automatizadas que pasan.
- **Parcial**: existe una base real, pero falta una parte funcional (adaptador de
  dispositivo, proveedor externo o interfaz de usuario concreta).
- **Especificado**: contrato y plan definidos; sin implementación ejecutable en este
  repositorio.

## Resumen

| Bloque | Estado | Dónde está |
| --- | --- | --- |
| 1. Identidad visual y núcleo | Implementado | `web/styles.css`, `web/index.html`, `web/app.js` |
| 2. Interfaz principal avanzada | Implementado | `web/` |
| 3. Voice engine | Parcial (síntesis y reconocimiento en cliente) | `leyra_core/voice.py`, `web/app.js` (`Voice`) |
| 4. APP INTEGRATION ENGINE | Implementado en lógica; ejecución en dispositivo **especificada** | `leyra_core/apps/`, `android/app-integration/` |
| 5. Tools engine | Implementado (7/10 herramientas con ejecución real) | `leyra_core/tools.py`, `backend/leyra-api/app/main.py` |
| 6. IA multimodelo | Parcial (router probado; adaptadores requieren credenciales) | `leyra_core/models.py`, `backend/leyra-api/app/providers.py` |
| 7. Agentes especializados | Parcial (perfiles de razonamiento, sin orquestación autónoma) | `web/app.js` (`AGENTS`), prompt del sistema |
| 8. Visión | Parcial (requiere proveedor con visión) | `/v1/chat` (`images`), adaptadores OpenAI/Anthropic/Gemini |
| 9. Memoria avanzada | Parcial (SQLite con deduplicación, sin cifrado ni sync) | `leyra_core/storage.py` |
| 10. Aplicación Android | Pendiente en este repositorio (fuente en `mily.zip`) | `android/app-integration/` |
| 11. Aplicación web | Implementado | `web/` |
| 12. Backend y servicios | Implementado con FastAPI + SQLite (no PostgreSQL/pgvector) | `backend/leyra-api/` |
| 13. Plugins y extensiones | Parcial (validación de manifiestos de conector) | `leyra_core/apps/models.py` |
| 14. Configuración central | Implementado | vista Configuración en `web/` |
| 15. Personalización | Implementado | tokens CSS, prefs de apariencia |
| 16. Calidad | Implementado (pruebas unitarias y de API) | `tests/`, `backend/leyra-api/tests/` |
| 17. Diagnóstico | Implementado con estados reales | `leyra_core/diagnostics.py`, `/v1/diagnostics` |
| 18. Modo local / sin conexión | Parcial (modelo local vía Ollama; UI sin caché offline) | `ModelRouter`, docs |

---

## 1. Rediseño visual completo

Identidad LEYRA IA aplicada en `web/`:

- Paleta completa de la especificación como variables CSS en `:root`
  (`--c-deep`, `--c-space`, `--c-electric`, `--c-cyan`, `--c-violet`, `--c-purple`,
  `--c-white`, `--c-muted`, `--c-success`, `--c-danger`).
- Tokens de superficies, bordes, sombras, radios, tipografía y movimiento. Cambiar
  un token afecta a todas las pantallas.
- Fondos con degradados dinámicos (`aurora-*`), rejilla enmascarada, partículas en
  canvas, transparencias con `backdrop-filter`, bordes luminosos y profundidad.
- Logotipo: núcleo energético circular con anillos cónicos y núcleo radial.
- Estados del núcleo implementados como `data-state`: `idle`, `listening`,
  `processing`, `reasoning`, `tools`, `speaking`, `interrupted`, `error`, `offline`.
  Se activan con eventos reales del cliente (micrófono, envío, herramientas, TTS,
  caída de conexión).
- Animaciones eficientes (transform/opacity, animaciones pausadas cuando el usuario
  elige intensidad reducida o desactivada; respeto a `prefers-reduced-motion`).

## 2. Interfaz principal

- Barra lateral con logotipo, nueva conversación, historial, buscador de
  conversaciones, fijadas, proyectos, biblioteca, herramientas, agentes,
  aplicaciones vinculadas, tareas, diagnóstico, configuración y perfil.
- Área central con Markdown, tablas, bloques de código con copia, fórmulas,
  indicadores de herramientas, metadatos del modelo y fuentes cuando existan.
- Barra de entrada expansible con adjuntos, imágenes, selector de modelo, agente,
  herramientas, razonamiento, micrófono, modo voz, envío e interrupción. Soporta
  arrastrar y soltar y pegar imágenes.
- Acciones por respuesta: copiar, compartir, leer en voz alta, detener, regenerar,
  editar, continuar, valorar, guardar en memoria y exportar.
- Adaptable a móvil, tablet y escritorio; la navegación se convierte en panel
  deslizante por debajo de 1180 px.

## 3. Sistema de voz

- `leyra_core/voice.py`: validación de velocidad/tono/volumen/idioma/estilo, pausas
  expresivas, troceado por frases para reproducción progresiva y estimación de
  duración. Persistencia en `/v1/voice` y preparación en `/v1/voice/prepare`.
- Cliente: `SpeechSynthesis` (progresivo por fragmentos, selección de voz por idioma,
  velocidad y tono configurables) y `SpeechRecognition`/`webkitSpeechRecognition`
  con transcripción en vivo, detección de silencio del motor y **barge-in**: al
  detectar voz durante la reproducción se cancela el audio y se procesa el nuevo
  turno.
- Modo conversación continua: escuchar → transcribir → CORE → respuesta → voz →
  escuchar de nuevo, con botón de interrupción y estados visuales.
- Límites honestos: la síntesis se ejecuta en el dispositivo/navegador; no hay motor
  TTS propio en el servidor. El reconocimiento del navegador puede usar servicios
  del proveedor del navegador (se advierte en la interfaz). En Android se debe
  conectar `TextToSpeech`/`SpeechRecognizer` o un proveedor externo.

## 4. APP INTEGRATION ENGINE

Implementado en `leyra_core/apps/` con la estructura solicitada, mapeada a módulos:

| Carpeta del diseño | Implementación |
| --- | --- |
| `discovery/` | `engine.sync_discovery`, `engine.catalog` (datos del `PackageManager` vía API) |
| `registry/` | `registry.py` (`AppRegistry`: apps, conectores, vínculos, historial, persistencia JSON) |
| `connectors/` | `models.py` (`ConnectorManifest`, `ConnectorAction`, validación estricta) |
| `intents/`, `deep_links/`, `app_links/`, `share/`, `shortcuts/` | `ActionKind` + validación de argumentos + planificación |
| `content_providers/` | `ActionKind.CONTENT_PROVIDER` (declaración y política; lectura real requiere adaptador Android) |
| `accessibility/` | Nivel 5, desactivado por defecto, requiere opt-in explícito |
| `permissions/` | Permisos declarados por conector, concesión y revocación con degradación a parcial |
| `security/` | `policy.py` (niveles máximos, apps bloqueadas, confirmaciones, límites) |
| `execution/` | `engine.execute` con `PlatformBridge` inyectable y auditoría |
| `diagnostics/` | `engine.health()` + integración en `/v1/diagnostics` |

Flujo real: descubrimiento → catálogo → vinculación → resolución de instrucción →
planificación → confirmación → despacho por puente → resultado → registro → respuesta.

El **puente Android** (`PlatformBridge`) es la pieza que convierte un paso en un
`Intent`. En este entorno web no existe, y el motor devuelve `unavailable` con una
explicación clara. El contrato y la implementación de referencia Kotlin están en
`android/app-integration/` y `docs/LEYRA_ANDROID_APP_INTEGRATION.md`.

Límites explícitos y aplicados:

- No se leen datos privados de otras apps, ni bases de datos, ni almacenamiento
  interno ajeno.
- No se eluden permisos, no se instalan APK en silencio, no se desactivan
  protecciones del sistema.
- Las acciones que envían datos fuera de LEYRA o modifican contenido requieren
  confirmación explícita por llamada.
- La compatibilidad se declara como completa, parcial, solo apertura o no
  compatible según el conector y los permisos **reales**.

## 5. Herramientas reales

`leyra_core/tools.py` + `/v1/tools`, `/v1/tools/{name}/run`.

| Herramienta | Estado |
| --- | --- |
| Calculadora segura (AST restringido) | Real y probada |
| Conversión de unidades | Real y probada |
| Conversión de temperatura | Real y probada |
| Fecha y hora UTC | Real |
| Estadísticas de texto | Real |
| Análisis de datos con histograma | Real |
| Formateo de JSON | Real |
| Lectura de PDF | Real si `pypdf` está instalado; si no, no disponible |
| Búsqueda web | Requiere proveedor; se muestra no disponible y no inventa resultados |
| Conversión de monedas | Requiere proveedor de tipos de cambio; no disponible por defecto |

Ciclo de ejecución implementado: validar esquema → comprobar riesgo y confirmación
(`mily_core.permission_manager`) → comprobar disponibilidad real → ejecutar →
capturar resultado/errores → informar. No hay ejecuciones simuladas.

## 6. IA multimodelo

- `ModelRegistry`, `Provider`, `ModelRouter` con selección por capacidades (visión,
  herramientas, JSON, contexto largo), tarea, coste y preferencia local.
- Adaptadores reales: OpenAI-compatible (incluye Ollama con `/v1`), Anthropic y
  Google Gemini, con soporte de imágenes y de streaming en el adaptador compatible.
- Credenciales solo por entorno en el servidor; `/v1/models` expone únicamente el
  nombre de la variable y si está configurada. El frontend nunca pide ni guarda
  claves de proveedor.
- Fallback: cadena ordenada y explicada; si ningún modelo cubre la capacidad pedida,
  se devuelve un error legible en lugar de degradar en silencio.
- Pendiente: `TokenManager` (contabilidad de tokens), embeddings/pgvector y
  presupuestos por usuario.

## 7. Razonamiento y agentes

Los agentes son **perfiles de instrucciones** transparentes (investigación,
programación, análisis, visión, redacción, planificación, seguridad, integración
Android). Se muestran al usuario y se añaden literalmente al mensaje. No se simula
colaboración multiagente ni subtareas autónomas: eso requiere orquestador y
herramientas de planificación adicionales (pendiente).

## 8. Visión

Envío de hasta 4 imágenes por mensaje como data URL; el router exige un modelo con
capacidad de visión y el adaptador construye bloques de imagen (OpenAI/Anthropic/
Gemini). Sin proveedor con visión, la comprobación de diagnóstico lo declara no
disponible. Compartir imágenes desde Android requiere el conector correspondiente
(nivel 2) en la app nativa.

## 9. Memoria

`leyra_core/storage.py`: SQLite con conversaciones, mensajes, recuerdos, ajustes y
auditoría de integración. Los recuerdos tienen categoría, procedencia, confianza,
deduplicación por texto normalizado, búsqueda, exportación y borrado. La memoria se
inyecta en el prompt del sistema cuando existe.

Pendiente y declarado en la UI: cifrado en reposo, sincronización entre dispositivos
y relaciones semánticas. Mientras tanto se recomienda cifrado de disco del servidor.

## 10. Aplicación Android

El código nativo no está expandido en este repositorio (reside en `mily.zip`). Se
entrega el contrato completo (ver `docs/LEYRA_ANDROID_APP_INTEGRATION.md`) y una
implementación de referencia del puente en `android/app-integration/`, que **no se
compila** en este repositorio: la app debe integrarla y verificarla en dispositivo.
No se marca como probado.

## 11. Aplicación web

HTML/CSS/JS sin dependencias, servida por el propio backend (`/`). Comparte la lógica
mediante la API; no duplica motores de inteligencia. Funciona igual en escritorio,
tablet y móvil. `node --check web/app.js` valida la sintaxis; la verificación de
interfaz se realizó con un arnés DOM (jsdom) contra el servidor real.

## 12. Backend y servicios

`backend/leyra-api/` con FastAPI:

- `/health`, `/v1/diagnostics`, `/v1/models`, `/v1/chat`, `/v1/chat/stream` (SSE),
  `/v1/conversations`, `/v1/memory`, `/v1/voice`, `/v1/tools`, `/v1/apps`,
  `/v1/files`.
- Autenticación Bearer opcional, CORS con allowlist + mismo origen, límite de tasa
  por IP, límite de cuerpo, límite de subida, validación Pydantic y errores
  sanitizados.
- Persistencia SQLite. **PostgreSQL/pgvector no están implementados**; el diseño de
  tablas es portable, pero migrar y añadir búsqueda vectorial queda pendiente.

## 13. Plugins

Un conector es un manifiesto validado (id, nombre, paquete, versión, nivel, auth,
acciones, permisos, parámetros). Se importan por API y se registran como *no
confiables* hasta que la app los publique. No hay ejecución de código de terceros ni
sandbox de plugins en el servidor: solo declaración de capacidades y despacho por el
puente. Firma/verificación de plugins: pendiente.

## 14. Configuración central

Vista Configuración con conexión, voz, apariencia, memoria/privacidad, modelos y
proveedores. La política de integración (niveles, accesibilidad, apps bloqueadas) se
administra en Aplicaciones vinculadas. Permisos de conector revisables y revocables.

## 15. Personalización

Temas oscuro, negro espacial y claro; acentos azul/cian/violeta; intensidad de
animación completa/reducida/desactivada; cristal on/off; densidad. Persistencia local
y aplicación inmediata mediante atributos `data-*` en `<html>`.

## 16. Calidad

- 134 pruebas de Python (motores) + 33 de API = **167 pruebas** en verde.
- `python -m compileall`, `node --check`, pruebas de integración con proveedor falso
  (sin red), pruebas de seguridad de herramientas (bloqueo de ejecución arbitraria).
- Reglas aplicadas: errores centralizados y sanitizados, logs sin credenciales,
  validación estricta de entrada, sin secretos en el repositorio, sin botones sin
  función.
- Pendiente: pruebas instrumentadas de Android, pruebas E2E en navegador real y
  auditoría de accesibilidad con lector de pantalla.

## 17. Diagnóstico

`/v1/diagnostics` ejecuta comprobaciones reales: core, motor de IA (credenciales y
modelos), herramientas (disponibilidad individual), integración de apps (puente,
conectores, vínculos), almacenamiento, memoria (degradada por falta de cifrado),
voz, visión, web y disco. El peor estado determina el global y el panel muestra los
datos crudos. Nada se marca operativo sin superar su comprobación.

## 18. Modo local

El router admite un endpoint local compatible con Ollama (`LEYRA_LOCAL_MODEL_URL`) y
`prefer_local`. El servidor y la UI funcionan en red local. Pendiente: caché offline
de conversaciones y ejecución totalmente sin red (la UI actual necesita el backend
para historial y herramientas).
