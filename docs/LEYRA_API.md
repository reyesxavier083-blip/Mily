# LEYRA API — referencia y despliegue

Backend de LEYRA IA en FastAPI. Sirve la interfaz web y el API que consumen web y
Android. Todos los motores son reales: si falta una credencial, una dependencia o un
puente de dispositivo, el API lo declara y no simula resultados.

## Arranque local

```bash
python -m venv .venv
.venv/bin/pip install -r backend/leyra-api/requirements.txt

# Proveedor de IA (solo la presencia de la clave; el valor nunca se expone)
export OPENAI_API_KEY="..."

.venv/bin/python backend/leyra-api/run.py --host 0.0.0.0 --port 8000
```

Abre `http://localhost:8000`. La interfaz se sirve desde el mismo proceso, por lo que
por defecto no hay CORS ni URL que configurar.

Sin ninguna clave de proveedor la app funciona en modo diagnóstico: herramientas,
memoria, conversaciones, voz y planificación de integraciones están operativas; el
chat responde `503` con la explicación exacta de qué falta.

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` | Credenciales de proveedor (servidor) |
| `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, `GOOGLE_BASE_URL` | Pasarelas compatibles |
| `LEYRA_LOCAL_MODEL_URL` | Servidor local tipo Ollama (`http://127.0.0.1:11434`) |
| `LEYRA_API_TOKEN` | Si se define, `/v1/*` exige `Authorization: Bearer` |
| `LEYRA_ALLOWED_ORIGINS` | Orígenes CORS permitidos (coma). Vacío = mismo origen |
| `LEYRA_DATA_DIR` | Carpeta de SQLite y de archivos subidos |
| `LEYRA_WEB_DIR` | Carpeta de la interfaz web |
| `LEYRA_DEFAULT_MODEL` | Modelo preferido si hay varias credenciales |
| `LEYRA_RATE_MAX`, `LEYRA_RATE_WINDOW_SECONDS` | Límite por IP |
| `LEYRA_MAX_UPLOAD_BYTES`, `LEYRA_MAX_BODY_BYTES` | Límites de tamaño |
| `LEYRA_TEMPERATURE`, `LEYRA_MAX_OUTPUT_TOKENS` | Parámetros de generación |

Nunca se guardan claves en el repositorio, en la web ni en el cliente. La UI solo
pide la URL del servidor y, opcionalmente, el token de acceso al API.

## Endpoints

### Sistema

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | `/health` | Estado del proceso, proveedores configurados, puente Android |
| GET | `/v1/diagnostics` | Comprobaciones reales por módulo y estado agregado |
| GET | `/v1/models` | Modelos, capacidades, proveedor y si tiene credenciales |
| GET | `/api/docs` | OpenAPI interactivo |

### Chat

| Método | Ruta | Descripción |
| --- | --- | --- |
| POST | `/v1/chat` | Respuesta completa con bucle real de herramientas |
| POST | `/v1/chat/stream` | SSE: `delta`, `meta`, `error`, `done` |

```json
{
  "message": "Calcula el 18 % de 2.450 y compártelo con WhatsApp",
  "conversationId": null,
  "model": null,
  "useTools": true,
  "reasoning": false,
  "images": ["data:image/png;base64,..."],
  "confirmedTools": false
}
```

- `useTools` habilita el catálogo de herramientas al modelo (solo adaptadores
  compatibles con OpenAI).
- `images` acepta hasta 4 data URLs; el router exige un modelo con visión.
- `confirmedTools` autoriza, **para esta llamada**, herramientas de riesgo externo.

### Conversaciones, memoria, voz y archivos

| Método | Ruta |
| --- | --- |
| GET/POST | `/v1/conversations` (búsqueda con `q`, límite) |
| GET/DELETE | `/v1/conversations/{id}` |
| POST | `/v1/conversations/{id}/rename`, `/pin` |
| GET/POST/DELETE | `/v1/memory`, `/v1/memory/{id}`, `/v1/memory/export` |
| GET/PUT | `/v1/voice` |
| POST | `/v1/voice/prepare` (troceado y pausas para TTS) |
| GET/DELETE | `/v1/files`, `/v1/files/{id}` |

### Herramientas

| Método | Ruta |
| --- | --- |
| GET | `/v1/tools` (con disponibilidad real y motivo si falta) |
| POST | `/v1/tools/{name}/run` |

Códigos: `200` OK o confirmación requerida, `422` argumentos inválidos, `403`
denegado por permisos, `503` herramienta no disponible (falta proveedor o
dependencia).

### Integración de aplicaciones Android

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | `/v1/apps` | Catálogo, vínculos, conectores, política, puente e historial |
| POST | `/v1/apps/discovery` | Sincroniza apps descubiertas (`PackageManager`) |
| POST | `/v1/apps/connectors` | Valida e importa un manifiesto de conector |
| POST | `/v1/apps/{paquete}/link` | Vincula con permisos concedidos |
| POST | `/v1/apps/{paquete}/unlink`, `/permissions`, `/enabled` | Administración del vínculo |
| PUT | `/v1/apps/policy` | Nivel máximo, accesibilidad, apps bloqueadas |
| POST | `/v1/apps/resolve` | Resuelve una instrucción; `confirmed: true` intenta ejecutar |

Sin puente Android, `resolve` devuelve el plan y `unavailable` al ejecutar. Es el
comportamiento correcto: el servidor no puede tocar el móvil.

## Seguridad

- Bearer con comparación en tiempo constante; `/health` y la web quedan públicos para
  permitir el arranque, el resto exige token si está configurado.
- CORS: allowlist explícita y aceptación de mismo origen (comprobando `Origin` frente
  a `Host`); cualquier otro origen se rechaza con 403.
- Límite por IP en memoria (para varias instancias, usa Redis o el límite del hosting).
- Validación Pydantic de todo el cuerpo; los errores del proveedor se recortan y no
  exponen detalles internos.
- Subidas con nombre saneado, prefijo aleatorio y resolución de rutas que rechaza
  `..`; no se sirve nada fuera de la carpeta de datos.
- Los archivos se guardan sin cifrar: protege el volumen y rota el token si se filtra.

## Despliegue

Cualquier host que ejecute Python 3.10+ y uvicorn:

```bash
uvicorn app.main:create_app --factory --host 0.0.0.0 --port "$PORT" --app-dir backend/leyra-api
```

Añade el volumen persistente para `LEYRA_DATA_DIR` y define las claves como secretos
del hosting. Detrás de un proxy, uvicorn se inicia con `proxy_headers=True`
(`run.py` ya lo hace); sirve siempre por HTTPS.

## Pruebas

```bash
python -m unittest discover -s tests -v                        # motores (135)
PYTHONPATH=.:backend/leyra-api python -m unittest discover \
  -s backend/leyra-api/tests -v                                # API (37)
node --check web/app.js
```

## Base de datos

SQLite con tablas `conversations`, `messages`, `memories`, `settings` e
`integration_log`. El esquema es portable a PostgreSQL, pero pgvector y búsqueda
semántica **no están implementados**; la memoria usa búsqueda textual normalizada y
deduplicación exacta.
