import express from "express";
import OpenAI, { toFile } from "openai";
import multer from "multer";
import crypto from "node:crypto";
import { assertProductionAuthConfig } from "./config.mjs";

assertProductionAuthConfig(process.env);

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "512kb" }));
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 20 * 1024 * 1024, files: 1 } });
const port = Number(process.env.MILY_PORT || 8080);
const defaultModel = process.env.MILY_DEFAULT_MODEL || "gpt-6-astra";
const vectorStoreId = () => process.env.MILY_VECTOR_STORE_ID?.trim() || "";
const apiKey = process.env.OPENAI_API_KEY?.trim() || "";
const apiToken = process.env.MILY_API_TOKEN?.trim() || "";
const allowedOrigins = new Set((process.env.MILY_ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean));
const rateWindow = Math.max(1000, Number(process.env.MILY_RATE_LIMIT_WINDOW_MS || 60000));
const rateMax = Math.max(1, Number(process.env.MILY_RATE_LIMIT_MAX || 60));
const buckets = new Map();
const client = apiKey ? new OpenAI({ apiKey }) : null;
const memory = new Map();

app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && allowedOrigins.has(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
    res.setHeader("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  }
  if (req.method === "OPTIONS") return origin && !allowedOrigins.has(origin) ? res.sendStatus(403) : res.sendStatus(204);
  if (origin && !allowedOrigins.has(origin)) return res.status(403).json({ error: "Origen no permitido." });
  next();
});

app.use((req, res, next) => {
  if (req.path === "/health") return next();
  const now = Date.now();
  const key = req.ip || req.socket.remoteAddress || "unknown";
  let bucket = buckets.get(key);
  if (!bucket || now - bucket.start >= rateWindow) bucket = { start: now, count: 0 };
  bucket.count += 1;
  buckets.set(key, bucket);
  if (buckets.size > 10000) {
    for (const [k, v] of buckets) if (now - v.start >= rateWindow) buckets.delete(k);
  }
  if (bucket.count > rateMax) return res.status(429).json({ error: "Demasiadas solicitudes. Inténtalo más tarde." });
  next();
});

app.use((req, res, next) => {
  if (req.path === "/health" || !apiToken) return next();
  const auth = req.headers.authorization || "";
  const supplied = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  const a = Buffer.from(supplied);
  const b = Buffer.from(apiToken);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return res.status(401).json({ error: "No autorizado." });
  next();
});

function needOpenAI(res) {
  if (client) return true;
  res.status(503).json({ error: "El backend no tiene OPENAI_API_KEY configurada en el servidor." });
  return false;
}
function memoryKey(userId, id) { return String(userId) + ":" + String(id); }
function listMemory(userId, limit = 30) {
  return [...memory.values()].filter(x => x.userId === userId && x.active).sort((a,b) => b.updatedAt - a.updatedAt).slice(0, limit);
}
function upsertMemory(userId, item) {
  const id = String(item.id || crypto.randomUUID());
  const text = String(item.text || "").trim().slice(0, 4000);
  if (!text) return null;
  const value = { id, userId, text, category: String(item.category || "general").slice(0,80), confidence: Number(item.confidence ?? 0.7), updatedAt: Date.now(), active: item.active !== false };
  memory.set(memoryKey(userId, id), value);
  return value;
}
async function searchKnowledge(id, query, maxNumResults = 8) {
  if (!id || !client) return [];
  const result = await client.vectorStores.search(id, { query: String(query).slice(0,2000), max_num_results: Math.max(1, Math.min(20, Number(maxNumResults) || 8)) });
  return Array.isArray(result.data) ? result.data.map(x => ({ fileId:x.file_id, filename:x.filename, score:x.score, text:(x.content || []).map(c => c.text || "").join("\n") })) : [];
}
function buildContext({ messages, memories, fileResults, deviceContext }) {
  const parts = [];
  const add = (title, lines) => { const value = lines.filter(Boolean).join("\n"); if (value) parts.push(title + ":\n" + value); };
  add("MEMORIA", memories.slice(0,30).map(m => "- [" + (m.category || "general") + "] " + (m.text || m.content || "")));
  add("DOCUMENTOS", fileResults.slice(0,10).map(r => "- " + (r.filename || r.fileId || "archivo") + ": " + String(r.text || "").slice(0,1200)));
  add("DISPOSITIVO", deviceContext ? [String(deviceContext).slice(0,3000)] : []);
  add("CONVERSACIÓN RECIENTE", messages.slice(-12).map(m => m.role + ": " + String(m.content || "").slice(0,1200)));
  return parts.join("\n\n").slice(0,18000);
}
function chooseRoute(prompt, hasDocuments) {
  const p = String(prompt || "").toLowerCase();
  const knowledge = hasDocuments && /(documento|archivo|pdf|según|segun|manual|proyecto|donde dice|qué dice|que dice)/.test(p);
  const device = /(batería|bateria|ram|almacenamiento|teléfono|telefono|celular|dispositivo|hardware)/.test(p);
  return { voice: false, useFileSearch: knowledge, useDeviceContext: device, mode: knowledge ? "knowledge" : device ? "device" : "conversation" };
}

app.get("/health", (_req, res) => res.json({ ok: true, service: "mily-openai-backend", version: "1.1.0", model: defaultModel, liveModel: process.env.MILY_REALTIME_MODEL || "gpt-live-1", configured: Boolean(client), authentication: Boolean(apiToken) }));

app.get("/v1/mily/knowledge/vector-stores", async (_req,res) => {
  if (!needOpenAI(res)) return;
  try { res.json(await client.vectorStores.list({ limit: 100 })); } catch { res.status(502).json({ error: "No fue posible listar Vector Stores." }); }
});
app.post("/v1/mily/knowledge/vector-stores", async (req,res) => {
  if (!needOpenAI(res)) return;
  try { res.status(201).json(await client.vectorStores.create({ name: String(req.body?.name || "Mily Knowledge").slice(0,120) })); } catch { res.status(502).json({ error: "No fue posible crear el Vector Store." }); }
});
app.post("/v1/mily/knowledge/files", upload.single("file"), async (req,res) => {
  if (!needOpenAI(res)) return;
  try {
    const id = String(req.body?.vectorStoreId || vectorStoreId());
    if (!id || !req.file) return res.status(400).json({ error: "vectorStoreId y file son requeridos." });
    const file = await toFile(req.file.buffer, req.file.originalname);
    const uploaded = await client.files.create({ file, purpose: "assistants" });
    const result = await client.vectorStores.files.create(id, { file_id: uploaded.id });
    res.status(201).json({ vectorStoreId: id, fileName: req.file.originalname, file: result });
  } catch (e) { console.error("Knowledge upload error:", e?.message || e); res.status(502).json({ error: "No fue posible agregar el archivo al conocimiento." }); }
});
app.post("/v1/mily/knowledge/search", async (req,res) => {
  if (!needOpenAI(res)) return;
  try { res.json({ results: await searchKnowledge(String(req.body?.vectorStoreId || vectorStoreId()), req.body?.query || "", req.body?.maxNumResults || 8) }); } catch { res.status(502).json({ error: "No fue posible buscar en el conocimiento." }); }
});

app.post("/v1/mily/memory/list", (req,res) => res.json({ items: listMemory(String(req.body?.userId || "default"),30) }));
app.post("/v1/mily/memory/upsert", (req,res) => {
  const item = upsertMemory(String(req.body?.userId || "default"), req.body || {});
  res.status(item ? 201 : 400).json(item || { error: "text requerido." });
});
app.post("/v1/mily/memory/remove", (req,res) => {
  memory.delete(memoryKey(String(req.body?.userId || "default"), String(req.body?.id || "")));
  res.json({ ok: true });
});

app.post("/v1/mily/tools/execute", async (req,res) => {
  const call = req.body?.call;
  const safeNames = new Set(["server_time", "device_context", "memory_list", "memory_upsert", "memory_remove", "knowledge_search"]);
  if (!call || typeof call.name !== "string" || !safeNames.has(call.name)) return res.status(400).json({ error: "Herramienta no permitida." });
  const args = call.arguments && typeof call.arguments === "object" ? call.arguments : {};
  const userId = String(args.userId || "default");
  try {
    switch (call.name) {
      case "server_time": return res.json({ iso: new Date().toISOString() });
      case "device_context": return res.json({ context: String(args.context || "").slice(0,3000) });
      case "memory_list": return res.json(listMemory(userId,30));
      case "memory_upsert": { const item = upsertMemory(userId,args); return res.status(item ? 201 : 400).json(item || { error: "text requerido." }); }
      case "memory_remove": memory.delete(memoryKey(userId,String(args.id || ""))); return res.json({ ok: true });
      case "knowledge_search": if (!needOpenAI(res)) return; return res.json(await searchKnowledge(vectorStoreId(),String(args.query || ""),8));
    }
  } catch { return res.status(502).json({ error: "La herramienta no pudo completarse." }); }
});

app.post("/v1/mily/responses", async (req,res) => {
  if (!needOpenAI(res)) return;
  try {
    const { model, instructions, input, temperature, maxOutputTokens, memoryFacts, enableFileSearch = true, maxFileSearchResults = 6, userId = "default", deviceContext = null } = req.body ?? {};
    if (!Array.isArray(input) || !input.length) return res.status(400).json({ error: "input debe contener al menos un mensaje." });
    const safeMessages = input.slice(-20).map(m => ({ role: m.role === "assistant" ? "assistant" : "user", content: String(m.content ?? "").slice(0,12000) }));
    const memories = [...listMemory(String(userId),30), ...(Array.isArray(memoryFacts) ? memoryFacts.filter(Boolean).slice(0,30).map(text => ({ text: String(text).slice(0,2000), category: "local" })) : [])];
    const route = chooseRoute(safeMessages.at(-1)?.content, Boolean(vectorStoreId()));
    let fileResults = [];
    if (enableFileSearch && vectorStoreId() && route.useFileSearch) fileResults = await searchKnowledge(vectorStoreId(), safeMessages.at(-1)?.content || "", maxFileSearchResults);
    let enriched = String(instructions || "Eres MILY, una asistente útil, clara y segura.").slice(0,12000);
    const context = buildContext({ messages: safeMessages, memories, fileResults, deviceContext });
    if (context) enriched += "\n\nCONTEXTO DE APOYO:\n" + context;
    const tools = [];
    if (enableFileSearch && vectorStoreId()) tools.push({ type: "file_search", vector_store_ids: [vectorStoreId()], max_num_results: Math.max(1,Math.min(20,Number(maxFileSearchResults) || 6)) });
    const result = await client.responses.create({
      model: typeof model === "string" && model.trim() ? model : defaultModel,
      instructions: enriched,
      input: safeMessages,
      tools,
      include: tools.length ? ["file_search_call.results"] : undefined,
      temperature: typeof temperature === "number" ? Math.max(0,Math.min(2,temperature)) : 0.7,
      max_output_tokens: typeof maxOutputTokens === "number" ? Math.max(1,Math.min(4096,maxOutputTokens)) : 2048
    });
    res.json({ outputText: result.output_text || "", responseId: result.id, tokenCount: result.usage?.total_tokens ?? null, route, fileSearchUsed: fileResults.length > 0, fileSearchResults: fileResults });
  } catch (e) { console.error("Responses error:", e?.message || e); res.status(502).json({ error: "No fue posible completar la solicitud con OpenAI." }); }
});

app.post("/v1/mily/live/sessions", async (req,res) => {
  if (!apiKey) return res.status(503).json({ error: "El backend no tiene OPENAI_API_KEY configurada." });
  try {
    const session = req.body?.session && typeof req.body.session === "object" ? req.body.session : { type: "live", model: process.env.MILY_REALTIME_MODEL || "gpt-live-1" };
    const sdp = typeof req.body?.transport?.sdp === "string" ? req.body.transport.sdp : "";
    if (!sdp.trim()) return res.status(400).json({ error: "transport.sdp es requerido." });
    const upstream = await fetch("https://api.openai.com/v1/live/sessions", { method: "POST", headers: { Authorization: "Bearer " + apiKey, "Content-Type": "application/json" }, body: JSON.stringify({ session, transport: { type: "webrtc", sdp } }) });
    const answer = await upstream.text();
    if (!upstream.ok) { console.error("Live upstream error:", answer.slice(0,500)); return res.status(502).json({ error: "No fue posible crear la sesión Live." }); }
    res.status(201).type("application/json").send(answer);
  } catch { res.status(502).json({ error: "Error al conectar MILY con Live." }); }
});

app.use((err, _req, res, _next) => {
  if (err?.type === "entity.too.large") return res.status(413).json({ error: "La solicitud supera el tamaño permitido." });
  console.error("Backend error:", err?.message || err);
  res.status(500).json({ error: "Error interno del backend." });
});
app.listen(port, "0.0.0.0", () => console.log("MILY backend v1.1 escuchando en " + port));
