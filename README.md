# LEYRA IA

Asistente de inteligencia artificial multimodal: interfaz de centro de control,
voz con interrupción, herramientas que se ejecutan de verdad, memoria estructurada y
un motor de integración con aplicaciones Android que respeta el aislamiento del
sistema.

> LEYRA IA sucede a la etapa MILY del proyecto. Los módulos `mily_core/` y el backend
> Node `backend/mily-openai/` se conservan como legado compatible; el producto actual
> está en `leyra_core/`, `backend/leyra-api/` y `web/`.

## Qué funciona hoy

- **Interfaz LEYRA** (`web/`): rediseño completo con identidad propia, núcleo
  energético con 9 estados reales, paneles de cristal, degradados ambientales,
  partículas eficientes y navegación adaptable. Incluye conversación con Markdown,
  tablas, código con copia, fórmulas, adjuntos, imágenes, acciones por respuesta,
  historial, proyectos, biblioteca, herramientas, agentes, aplicaciones vinculadas,
  tareas, diagnóstico y configuración.
- **Voz**: reconocimiento en vivo, síntesis configurable por voz/idioma/velocidad/tono,
  pausas expresivas, reproducción por fragmentos, modo conversación continua y
  *barge-in* (te calla en cuanto vuelves a hablar).
- **Herramientas reales** (`leyra_core/tools.py`): calculadora segura, unidades y
  temperatura, fecha/hora, estadísticas de texto, análisis de datos con histograma,
  JSON y lectura de PDF (con `pypdf`). Búsqueda web y monedas se muestran **no
  disponibles** hasta configurar proveedor: no se inventan resultados.
- **IA multimodelo** (`leyra_core/models.py`): router por capacidades, proveedores
  OpenAI/Anthropic/Google/modelo local, fallback explicable, credenciales solo en el
  servidor y jamás expuestas al cliente.
- **Integración Android** (`leyra_core/apps/`): descubrimiento, catálogo de
  compatibilidad real, vinculación por niveles, permisos revocables, planificación de
  instrucciones en lenguaje natural, confirmación de acciones externas, auditoría y
  denegación segura. El puente Kotlin de referencia está en `android/app-integration/`.
- **Memoria y datos** (`leyra_core/storage.py`): SQLite con conversaciones, recuerdos
  con procedencia y deduplicación, ajustes y registro de integración.
- **Diagnóstico** (`/v1/diagnostics`): 10 comprobaciones reales; nada se marca
  operativo sin pasar su prueba.

## Arranque rápido

```bash
python -m venv .venv
.venv/bin/pip install -r backend/leyra-api/requirements.txt

export OPENAI_API_KEY="tu-clave"      # opcional: sin clave, la app arranca en diagnóstico
.venv/bin/python backend/leyra-api/run.py --host 0.0.0.0 --port 8000
```

Abre `http://localhost:8000`. La interfaz y el API se sirven desde el mismo proceso y
no requieren compilación ni dependencias de Node.

Guía completa del API, variables de entorno y despliegue: `docs/LEYRA_API.md`.

## Estructura

```
leyra_core/                 Motores independientes y probados
├── apps/                   ANDROID APP INTEGRATION ENGINE
│   ├── models.py           Conectores, acciones, niveles, resultados
│   ├── registry.py         Apps descubiertas, vínculos, historial, persistencia
│   ├── policy.py           Niveles máximos, bloqueos, confirmaciones
│   └── engine.py           Catálogo, resolución de instrucciones, ejecución
├── tools.py                TOOLS ENGINE con implementaciones reales
├── models.py               Registry/router multimodelo y proveedores
├── storage.py              SQLite (conversaciones, memoria, ajustes, auditoría)
├── diagnostics.py          Comprobaciones y agregación de estado
└── voice.py                Configuración de voz, pausas y troceado

backend/leyra-api/          FastAPI: API + interfaz web
├── app/config.py           Entorno, límites, autenticación
├── app/providers.py        Adaptadores OpenAI/Anthropic/Gemini/local
├── app/state.py            Composición de motores y diagnóstico
├── app/main.py             Rutas, SSE, archivos, seguridad
├── tests/                  Pruebas de API con proveedor simulado local
├── requirements.txt
├── Dockerfile
└── run.py

web/                        Interfaz LEYRA IA (HTML/CSS/JS, sin dependencias)
android/app-integration/    Puente Kotlin de referencia (no compilado aquí)

docs/LEYRA_ESPECIFICACION_MAESTRA.md   Trazabilidad completa de la orden maestra
docs/LEYRA_ANDROID_APP_INTEGRATION.md  Contrato de integración y límites de Android
docs/LEYRA_API.md                      Referencia del API y despliegue
```

## Pruebas

```bash
python -m unittest discover -s tests -v                       # 135 pruebas de motores
PYTHONPATH=.:backend/leyra-api \
  python -m unittest discover -s backend/leyra-api/tests -v   # 37 pruebas de API
node --check web/app.js
```

GitHub Actions ejecuta las tres suites (`tests.yml` y `quality.yml`).

## Límites declarados

Nada de esto se presenta como terminado porque no lo esté:

- **Android nativo**: el proyecto vive en `mily.zip`; este repositorio entrega el
  motor, la API y el puente de referencia. Falta integrarlo y probarlo en dispositivo.
- **Chat**: requiere una clave de proveedor en el servidor. Sin ella el API responde
  503 con la explicación exacta.
- **Búsqueda web y monedas**: necesitan proveedor configurado; no hay resultados
  simulados.
- **PostgreSQL/pgvector**: no implementado; se usa SQLite con búsqueda textual.
- **Cifrado de memoria en reposo y sincronización**: pendientes; el diagnóstico
  degrada el módulo de memoria por ello.
- **Agentes**: son perfiles de razonamiento transparentes, no procesos autónomos
  colaborando entre sí.
- **Accesibilidad (nivel 5)**: desactivada por defecto, exige opt-in explícito; su
  implementación nativa y su cumplimiento de Play quedan pendientes.

## Seguridad

- Ninguna clave de proveedor en el cliente, en el repositorio ni en logs.
- Token Bearer opcional, CORS con allowlist y mismo origen, límite por IP y de
  tamaño, validación estricta y errores sanitizados.
- Herramientas y acciones externas sujetas a permisos y confirmación por llamada.
- La integración con apps usa exclusivamente interfaces públicas de Android; no lee
  datos privados, no instala APK en silencio y no elude permisos.

Detalle de riesgos y estado verificado en `docs/STATUS.md`.
