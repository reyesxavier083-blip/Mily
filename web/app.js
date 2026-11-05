/* ==========================================================================
   LEYRA IA — web client
   Single-page, dependency-free. Talks to the LEYRA API over the same origin by
   default; every module below is honest about what it can and cannot do.
   ========================================================================== */
(() => {
  "use strict";

  /* ------------------------------------------------------------------ *
   * Constants
   * ------------------------------------------------------------------ */
  const PREFS_KEY = "leyra.prefs.v1";
  const CONN_KEY = "leyra.connection.v1";
  const TASKS_KEY = "leyra.tasks.v1";
  const RATINGS_KEY = "leyra.ratings.v1";
  const MAX_IMAGES = 4;
  const MAX_IMAGE_BYTES = 6 * 1024 * 1024;
  const MAX_FILE_CONTEXT = 8000;

  const AGENTS = [
    { id: "research", name: "Investigación", icon: "i-search", level: "Profundo",
      prompt: "Actúa como agente de investigación: descompón la pregunta, contrasta fuentes y marca la incertidumbre.",
      desc: "Descompone preguntas, ordena evidencia y separa hechos de hipótesis." },
    { id: "coding", name: "Programación", icon: "i-tools", level: "Técnico",
      prompt: "Actúa como agente de programación: propone código ejecutable, explica decisiones y señala los casos límite.",
      desc: "Código, depuración y revisión con criterios de producción." },
    { id: "analysis", name: "Análisis de datos", icon: "i-diag", level: "Analítico",
      prompt: "Actúa como agente de análisis: usa estadística descriptiva, explica el método y evita conclusiones sin datos.",
      desc: "Resume datos reales con las herramientas disponibles en el servidor." },
    { id: "vision", name: "Visión", icon: "i-image", level: "Multimodal",
      prompt: "Actúa como agente de visión: describe lo observable, transcribe texto con fidelidad y no adivines detalles.",
      desc: "Interpreta imágenes y capturas cuando el modelo configurado tiene visión." },
    { id: "writing", name: "Redacción", icon: "i-spark", level: "Editorial",
      prompt: "Actúa como agente de redacción: escribe con claridad, estructura explícita y tono natural.",
      desc: "Textos, resúmenes y reescritura con control de estilo." },
    { id: "planning", name: "Planificación", icon: "i-tasks", level: "Operativo",
      prompt: "Actúa como agente de planificación: genera pasos concretos, dependencias y criterios de éxito medibles.",
      desc: "Convierte objetivos difusos en planes ejecutables." },
    { id: "security", name: "Seguridad", icon: "i-shield", level: "Defensivo",
      prompt: "Actúa como agente de seguridad: identifica riesgos, permisos excesivos y límites de Android sin proponer evasiones.",
      desc: "Revisa permisos, integraciones y superficie de riesgo." },
    { id: "android", name: "Integración Android", icon: "i-apps", level: "Dispositivo",
      prompt: "Actúa como agente de integración Android: usa solo interfaces públicas (Intent, deep links, SDK) y explica qué no es posible.",
      desc: "Explica qué apps pueden integrarse y con qué límites reales." }
  ];

  const CORE_LABELS = {
    idle: "En reposo", listening: "Escuchando", processing: "Procesando",
    reasoning: "Razonando", tools: "Usando herramientas", speaking: "Hablando",
    interrupted: "Interrumpida", error: "Error", offline: "Sin conexión"
  };

  /* ------------------------------------------------------------------ *
   * Utilities
   * ------------------------------------------------------------------ */
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key === "html") node.innerHTML = value;
      else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
      else if (key === "dataset") Object.assign(node.dataset, value);
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  const icon = (name) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#${name}`);
    svg.append(use);
    return svg;
  };

  const escapeHtml = (value) => String(value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  function formatBytes(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }

  function timeAgo(timestamp) {
    const seconds = Math.max(0, (Date.now() - Number(timestamp) * 1000) / 1000);
    if (seconds < 60) return "ahora";
    if (seconds < 3600) return `hace ${Math.round(seconds / 60)} min`;
    if (seconds < 86400) return `hace ${Math.round(seconds / 3600)} h`;
    const date = new Date(Number(timestamp) * 1000);
    return date.toLocaleDateString("es", { day: "2-digit", month: "short" });
  }

  const clock = (timestamp) => new Date(Number(timestamp) * 1000)
    .toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });

  function debounce(fn, wait = 220) {
    let handle = null;
    return (...args) => {
      clearTimeout(handle);
      handle = setTimeout(() => fn(...args), wait);
    };
  }

  function toast(message, kind = "", detail = "") {
    const stack = $("#toasts");
    if (!stack) return;
    const node = el("div", { class: `toast ${kind}`, role: "status" },
      el("span", { text: message }), detail ? el("small", { text: detail }) : null);
    stack.append(node);
    setTimeout(() => node.remove(), kind === "error" ? 6200 : 3800);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const area = el("textarea", { style: "position:fixed;opacity:0" });
      area.value = text;
      document.body.append(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    }
  }

  function downloadText(filename, text, mime = "text/markdown") {
    const blob = new Blob([text], { type: `${mime};charset=utf-8` });
    const link = el("a", { href: URL.createObjectURL(blob), download: filename });
    document.body.append(link);
    link.click();
    setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 1500);
  }

  const json = (key, fallback) => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch { return fallback; }
  };
  const persist = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage full */ }
  };

  /* ------------------------------------------------------------------ *
   * Preferences and appearance
   * ------------------------------------------------------------------ */
  const prefs = Object.assign(
    { theme: "dark", accent: "electric", motion: "full", glass: "on", density: "comfortable" },
    json(PREFS_KEY, {})
  );

  function applyPrefs() {
    const root = document.documentElement;
    root.dataset.theme = prefs.theme;
    root.dataset.accent = prefs.accent;
    root.dataset.motion = prefs.motion;
    root.dataset.glass = prefs.glass;
    root.dataset.density = prefs.density;
    const meta = $('meta[name="theme-color"]');
    if (meta) meta.content = prefs.theme === "light" ? "#eef3fb" : "#07111F";
    Particles.setIntensity(prefs.motion);
  }

  function savePrefs() {
    persist(PREFS_KEY, prefs);
    applyPrefs();
    syncPrefControls();
  }

  function syncPrefControls() {
    const map = {
      "pref-theme": prefs.theme, "pref-accent": prefs.accent,
      "pref-motion": prefs.motion, "pref-glass": prefs.glass, "pref-density": prefs.density
    };
    for (const [id, value] of Object.entries(map)) {
      const node = document.getElementById(id);
      if (node) node.value = value;
    }
  }

  /* ------------------------------------------------------------------ *
   * Connection + API client
   * ------------------------------------------------------------------ */
  const connection = Object.assign({ base: "", token: "" }, json(CONN_KEY, {}));
  const state = {
    conversationId: null,
    messages: [],
    busy: false,
    online: null,
    controller: null,
    models: [],
    providers: [],
    tools: [],
    voice: null,
    diagnostics: null,
    apps: null,
    attachments: [],
    images: [],
    pendingAgent: "",
    ratings: json(RATINGS_KEY, {})
  };

  function apiUrl(path) {
    const base = (connection.base || "").replace(/\/+$/, "");
    return `${base}${path}`;
  }

  function authHeaders(extra = {}) {
    const headers = { ...extra };
    if (connection.token) headers.Authorization = `Bearer ${connection.token}`;
    return headers;
  }

  async function api(path, options = {}) {
    const init = {
      method: options.method || "GET",
      headers: authHeaders(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      signal: options.signal
    };
    if (options.body !== undefined) {
      init.body = options.body instanceof FormData ? options.body : JSON.stringify(options.body);
    }
    let response;
    try {
      response = await fetch(apiUrl(path), init);
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new Error("No se pudo contactar con el servidor de LEYRA.");
    }
    const type = response.headers.get("content-type") || "";
    const payload = type.includes("application/json") ? await response.json().catch(() => null) : await response.text();
    if (!response.ok) {
      const detail = payload && typeof payload === "object" ? payload.detail || payload.error : payload;
      const message = typeof detail === "string" && detail.trim() ? detail : `El servidor respondió ${response.status}.`;
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  async function checkHealth(showFeedback = false) {
    setStatus(null, "Comprobando…", "Consultando el servidor");
    try {
      const response = await fetch(apiUrl("/health"), { headers: authHeaders(), signal: AbortSignal.timeout(8000) });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const model = Array.isArray(data.providersConfigured) && data.providersConfigured.length
        ? data.providersConfigured[0] : "sin proveedor configurado";
      setStatus(true, "LEYRA conectada", `${data.app} · ${model}`);
      if (showFeedback) toast("Conexión correcta con el servidor.", "success");
      return data;
    } catch (error) {
      setStatus(false, "Sin conexión", "Revisa la URL del servidor");
      if (showFeedback) toast("No se pudo conectar con el servidor.", "error", error.message);
      return null;
    }
  }

  function setStatus(online, label, detail) {
    if (online === true || online === false) state.online = online;
    const dot = $("#status-dot");
    if (dot) {
      dot.classList.toggle("online", online === true);
      dot.classList.toggle("offline", online === false);
    }
    $("#status-label").textContent = label;
    $("#status-detail").textContent = detail;
    if (online === false) {
      setCoreState("offline");
    } else if (online === true && core.state === "offline") {
      setCoreState("idle");
    }
  }

  /* ------------------------------------------------------------------ *
   * Energy core state
   * ------------------------------------------------------------------ */
  const core = { state: "idle" };

  function setCoreState(next, label) {
    core.state = next;
    const nodes = [$("#hero-core"), $("#voice-core"), $(".brand-core"), $("#state-pill")].filter(Boolean);
    for (const node of nodes) node.dataset.state = next;
    const text = label || CORE_LABELS[next] || next;
    const stateLabel = $("#state-label");
    if (stateLabel) stateLabel.textContent = text;
    const voiceLabel = $("#voice-state-label");
    if (voiceLabel) voiceLabel.textContent = text.toUpperCase();
    if (next === "interrupted") {
      setTimeout(() => { if (core.state === "interrupted") setCoreState(state.busy ? "processing" : "idle"); }, 900);
    }
  }

  /* ------------------------------------------------------------------ *
   * Markdown renderer (escaped input, conservative HTML output)
   * ------------------------------------------------------------------ */
  function renderInline(text) {
    let out = escapeHtml(text);
    out = out.replace(/`([^`]+)`/g, (_, code) => `<code>${code}</code>`);
    out = out.replace(/\*\*\*([^*]+)\*\*\*/g, "<strong><em>$1</em></strong>");
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    out = out.replace(/(^|[\s(])_([^_\n]+)_/g, "$1<em>$2</em>");
    out = out.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      (_, label, url) => `<a href="${url}" target="_blank" rel="noopener noreferrer nofollow">${label}</a>`);
    out = out.replace(/(^|[\s>])(https?:\/\/[^\s<]+)/g,
      (_, prefix, url) => `${prefix}<a href="${url}" target="_blank" rel="noopener noreferrer nofollow">${url}</a>`);
    return out;
  }

  function renderMarkdown(source) {
    const lines = String(source || "").replace(/\r\n/g, "\n").split("\n");
    const html = [];
    let index = 0;

    const flushParagraph = (buffer) => {
      if (!buffer.length) return;
      html.push(`<p>${buffer.map(renderInline).join("<br>")}</p>`);
      buffer.length = 0;
    };
    const paragraph = [];

    while (index < lines.length) {
      const line = lines[index];

      if (/^```/.test(line)) {
        flushParagraph(paragraph);
        const language = line.replace(/^```/, "").trim() || "código";
        const code = [];
        index += 1;
        while (index < lines.length && !/^```/.test(lines[index])) {
          code.push(lines[index]);
          index += 1;
        }
        index += 1;
        const id = `code-${Math.random().toString(36).slice(2, 9)}`;
        html.push(
          `<div class="code-block"><div class="code-head"><span>${escapeHtml(language)}</span>` +
          `<button type="button" data-copy="${id}">Copiar</button></div>` +
          `<pre><code id="${id}">${escapeHtml(code.join("\n"))}</code></pre></div>`
        );
        continue;
      }

      const heading = line.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        flushParagraph(paragraph);
        const level = heading[1].length;
        html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
        index += 1;
        continue;
      }

      if (/^\s*---+\s*$/.test(line)) {
        flushParagraph(paragraph);
        html.push("<hr>");
        index += 1;
        continue;
      }

      if (/^>\s?/.test(line)) {
        flushParagraph(paragraph);
        const quote = [];
        while (index < lines.length && /^>\s?/.test(lines[index])) {
          quote.push(lines[index].replace(/^>\s?/, ""));
          index += 1;
        }
        html.push(`<blockquote>${quote.map(renderInline).join("<br>")}</blockquote>`);
        continue;
      }

      if (/^\s*[-*+]\s+/.test(line)) {
        flushParagraph(paragraph);
        const items = [];
        while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) {
          items.push(`<li>${renderInline(lines[index].replace(/^\s*[-*+]\s+/, ""))}</li>`);
          index += 1;
        }
        html.push(`<ul>${items.join("")}</ul>`);
        continue;
      }

      if (/^\s*\d+[.)]\s+/.test(line)) {
        flushParagraph(paragraph);
        const items = [];
        while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
          items.push(`<li>${renderInline(lines[index].replace(/^\s*\d+[.)]\s+/, ""))}</li>`);
          index += 1;
        }
        html.push(`<ol>${items.join("")}</ol>`);
        continue;
      }

      if (/^\s*\|.*\|\s*$/.test(line) && index + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[index + 1])) {
        flushParagraph(paragraph);
        const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
        const head = cells(line);
        index += 2;
        const rows = [];
        while (index < lines.length && /^\s*\|.*\|\s*$/.test(lines[index])) {
          rows.push(cells(lines[index]));
          index += 1;
        }
        html.push(
          `<table><thead><tr>${head.map((cell) => `<th>${renderInline(cell)}</th>`).join("")}</tr></thead>` +
          `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`
        );
        continue;
      }

      if (/^\s*\$\$.*\$\$\s*$/.test(line)) {
        flushParagraph(paragraph);
        html.push(`<span class="formula">${escapeHtml(line.trim().replace(/^\$\$|\$\$$/g, ""))}</span>`);
        index += 1;
        continue;
      }

      if (line.trim() === "") {
        flushParagraph(paragraph);
        index += 1;
        continue;
      }

      paragraph.push(line);
      index += 1;
    }
    flushParagraph(paragraph);
    return html.join("");
  }

  /* ------------------------------------------------------------------ *
   * Chat rendering
   * ------------------------------------------------------------------ */
  const ACTIONS = [
    ["copy", "Copiar", "i-copy"], ["speak", "Leer", "i-play"], ["share", "Compartir", "i-broadcast"],
    ["regen", "Regenerar", "i-refresh"], ["edit", "Editar", "i-spark"], ["continue", "Continuar", "i-chevron"],
    ["memory", "Guardar en memoria", "i-shield"], ["export", "Exportar", "i-download"],
    ["up", "Útil", "i-check"], ["down", "Mejorable", "i-x"]
  ];

  function messageShell(role, meta = {}) {
    const wrapper = el("article", { class: `message ${role}`, dataset: { id: meta.id || "" } });
    const avatar = el("div", { class: "message-avatar", "aria-hidden": "true", text: role === "user" ? "TÚ" : "L" });
    const body = el("div", { class: "message-body" });
    const metaRow = el("div", { class: "message-meta" });
    metaRow.append(el("span", { text: role === "user" ? "TÚ" : "LEYRA" }));
    if (meta.model) metaRow.append(el("span", { class: "tag", text: meta.model }));
    if (meta.reasoning) metaRow.append(el("span", { class: "tag", text: "razonamiento" }));
    metaRow.append(el("span", { text: clock(Date.now() / 1000) }));
    body.append(metaRow);
    wrapper.append(avatar, body);
    return { wrapper, body, metaRow };
  }

  function addUserMessage(text, attachments = []) {
    const { wrapper, body } = messageShell("user", {});
    const bubble = el("div", { class: "bubble" });
    const content = el("div", { class: "md" });
    content.innerHTML = renderMarkdown(text);
    bubble.append(content);
    if (attachments.length) {
      const strip = el("div", { class: "attachments" });
      for (const item of attachments) {
        strip.append(el("div", { class: "attachment" },
          el("span", { class: "file-glyph", text: (item.kind || "arch").slice(0, 4) }),
          el("span", { text: item.name || "adjunto" }),
          el("small", { text: item.sizeLabel || "" })));
      }
      bubble.append(strip);
    }
    body.append(bubble);
    $("#messages").append(wrapper);
    scrollToEnd();
    return wrapper;
  }

  function addAssistantMessage(meta = {}) {
    const { wrapper, body, metaRow } = messageShell("assistant", meta);
    const bubble = el("div", { class: "bubble typing" });
    bubble.setAttribute("aria-label", "LEYRA está respondiendo");
    for (let i = 0; i < 3; i += 1) bubble.append(el("span", { class: "typing-dot" }));
    body.append(bubble);
    $("#messages").append(wrapper);
    scrollToEnd();
    return { wrapper, body, metaRow, bubble };
  }

  function attachActions(wrapper, text, meta = {}) {
    $$(".msg-actions", wrapper).forEach((node) => node.remove());
    const actions = el("div", { class: "msg-actions" });
    const rating = state.ratings[meta.id];
    for (const [key, label, iconName] of ACTIONS) {
      if (key === "up" || key === "down") {
        actions.append(el("button", {
          class: `msg-action ${rating === key ? "is-on" : ""}`, type: "button",
          "data-action": key, title: label, "aria-label": label
        }, icon(iconName), el("span", { text: key === "up" ? "Útil" : "Mejorable" })));
      } else {
        actions.append(el("button", {
          class: "msg-action", type: "button", "data-action": key, title: label, "aria-label": label
        }, icon(iconName)));
      }
    }
    wrapper.querySelector(".message-body").append(actions);
    actions.addEventListener("click", (event) => {
      const button = event.target.closest("[data-action]");
      if (!button) return;
      handleMessageAction(button.dataset.action, wrapper, text, meta);
    });
  }

  function finalizeAssistant(node, text, meta = {}) {
    node.bubble.classList.remove("typing");
    node.bubble.innerHTML = "";
    const content = el("div", { class: "md" });
    content.innerHTML = renderMarkdown(text);
    node.bubble.append(content);
    if (meta.toolRuns && meta.toolRuns.length) {
      const runs = el("div", { class: "tool-runs" });
      for (const run of meta.toolRuns) {
        const ok = run.status === "ok";
        const statusClass = ok ? "ok" : (run.status === "confirmation_required" || run.status === "denied" ? "blocked" : "");
        runs.append(el("div", { class: `tool-run ${statusClass}` },
          el("span", { class: "dot" }),
          el("span", {}, el("b", { text: run.tool }), " · ",
            el("span", { text: run.status }),
            run.detail ? el("div", { text: run.detail }) : null)));
      }
      node.body.append(runs);
    }
    if (meta.routing && meta.routing.model) {
      node.metaRow.append(el("span", { class: "tag", text: `${meta.routing.provider}/${meta.routing.model}` }));
    }
    attachActions(node.wrapper, text, meta);
    scrollToEnd();
  }

  function addErrorMessage(message) {
    const { wrapper, body } = messageShell("assistant", {});
    body.querySelector(".message-meta").append(el("span", { class: "tag", text: "aviso" }));
    const bubble = el("div", { class: "bubble error" });
    bubble.append(el("div", { class: "md", html: renderMarkdown(message) }));
    body.append(bubble);
    $("#messages").append(wrapper);
    scrollToEnd();
  }

  function scrollToEnd() {
    const area = $("#conversation");
    if (area) area.scrollTop = area.scrollHeight;
  }

  async function handleMessageAction(action, wrapper, text, meta) {
    switch (action) {
      case "copy":
        await copyText(text);
        toast("Respuesta copiada.", "success");
        break;
      case "speak":
        Voice.speak(text);
        break;
      case "share": {
        if (navigator.share) {
          try { await navigator.share({ title: "LEYRA IA", text }); } catch { /* cancelled */ }
        } else {
          await copyText(text);
          toast("Compartir no está disponible: texto copiado al portapapeles.");
        }
        break;
      }
      case "regen": {
        const userNode = wrapper.previousElementSibling;
        const prompt = userNode?.querySelector(".md")?.textContent?.trim();
        const from = userNode && userNode.classList.contains("user") ? userNode : wrapper;
        if (prompt) Chat.send(prompt, { replaceFrom: from });
        break;
      }
      case "edit": {
        const userNode = wrapper.previousElementSibling;
        const prompt = userNode?.querySelector(".md")?.textContent?.trim();
        const input = $("#message-input");
        input.value = prompt || text;
        input.dispatchEvent(new Event("input"));
        input.focus();
        break;
      }
      case "continue":
        Chat.send("Continúa desde donde lo dejaste, sin repetir lo anterior.");
        break;
      case "memory":
        try {
          await api("/v1/memory", { method: "POST", body: { text, category: "conversacion", provenance: "respuesta", confidence: 0.6 } });
          toast("Guardado en memoria.", "success");
        } catch (error) {
          toast("No se pudo guardar en memoria.", "error", error.message);
        }
        break;
      case "export":
        downloadText(`leyra-${Date.now()}.md`, `# LEYRA IA\n\n${text}\n`);
        break;
      case "up":
      case "down": {
        state.ratings[meta.id || text.slice(0, 40)] = action;
        persist(RATINGS_KEY, state.ratings);
        wrapper.querySelectorAll("[data-rating], [data-action='up'], [data-action='down']").forEach((node) => {
          node.classList.toggle("is-on", node.dataset.action === action);
        });
        toast(action === "up" ? "Gracias por la valoración." : "Anotado: intentaré mejorar la respuesta.");
        break;
      }
      default:
        break;
    }
  }

  /* ------------------------------------------------------------------ *
   * Chat controller
   * ------------------------------------------------------------------ */
  const Chat = {
    async send(rawText, options = {}) {
      const attachments = state.attachments.slice();
      const images = state.images.slice();
      const text = rawText.trim();
      if (!text && !attachments.length && !images.length) {
        toast("Escribe un mensaje o adjunta un archivo.");
        return;
      }
      if (state.busy) return;

      const agent = AGENTS.find((item) => item.id === state.pendingAgent);
      let outgoing = text;
      if (agent) outgoing = `${agent.prompt}\n\n${text}`;

      if (options.replaceFrom) {
        let node = options.replaceFrom;
        while (node) {
          const next = node.nextElementSibling;
          node.remove();
          node = next;
        }
      }

      if (!$("#hero").hidden) $("#hero").hidden = true;
      const displayAttachments = attachments.map((item) => ({
        name: item.name, kind: item.name.split(".").pop() || "archivo",
        sizeLabel: formatBytes(item.sizeBytes || 0)
      }));
      addUserMessage(text || "(adjuntos)", displayAttachments);

      const fileContext = attachments
        .filter((item) => item.text)
        .map((item) => `Archivo adjunto «${item.name}»:\n"""\n${item.text.slice(0, MAX_FILE_CONTEXT)}\n"""`)
        .join("\n\n");
      const payload = {
        message: fileContext ? `${outgoing}\n\n${fileContext}` : outgoing,
        conversationId: state.conversationId,
        useTools: $("#btn-tools").getAttribute("aria-pressed") === "true",
        reasoning: $("#btn-reasoning").getAttribute("aria-pressed") === "true",
        images: images.map((item) => item.dataUrl),
        model: $("#model-select").value || null
      };

      state.attachments = [];
      state.images = [];
      renderAttachments();
      clearComposer();

      const node = addAssistantMessage({ model: $("#model-select").value || "auto", reasoning: payload.reasoning });
      state.busy = true;
      toggleBusy(true);
      setCoreState(payload.reasoning ? "reasoning" : "processing");
      state.controller = new AbortController();
      let streamed = "";
      let meta = {};

      try {
        const result = await streamChat(payload, state.controller.signal, (delta) => {
          streamed += delta;
          node.bubble.classList.remove("typing");
          node.bubble.innerHTML = `<div class="md">${renderMarkdown(streamed)}</div>`;
          scrollToEnd();
        });
        meta = result;
        state.conversationId = result.conversationId || state.conversationId;
        const finalText = (streamed || result.content || "").trim() || "No se recibió contenido del modelo.";
        finalizeAssistant(node, finalText, {
          id: result.messageId, toolRuns: result.toolRuns, routing: result.routing
        });
        if (Voice.settings.autoSpeak) Voice.speak(finalText);
        refreshHistorySoon();
        if (result.toolRuns && result.toolRuns.length) setCoreState("idle");
      } catch (error) {
        node.wrapper.remove();
        if (error.name === "AbortError") {
          setCoreState("interrupted");
          const partial = streamed.trim();
          if (partial) {
            const partialNode = addAssistantMessage({});
            finalizeAssistant(partialNode, `${partial}\n\n_— Generación interrumpida por el usuario._`, {});
          } else {
            addErrorMessage("Generación detenida. Puedes reformular o volver a intentarlo.");
          }
        } else {
          setCoreState("error");
          addErrorMessage(`**No pude completar la respuesta.** ${error.message}`);
          setTimeout(() => setCoreState("idle"), 2200);
        }
      } finally {
        state.busy = false;
        state.controller = null;
        toggleBusy(false);
        if (core.state !== "offline" && core.state !== "error") setCoreState("idle");
      }
    },

    stop() {
      if (state.controller) state.controller.abort();
      if (Voice.speaking) Voice.stop();
    },

    reset() {
      state.conversationId = null;
      $("#messages").innerHTML = "";
      $("#hero").hidden = false;
      setCoreState("idle");
      $("#message-input").focus();
      showRoute("chat");
    },

    async load(conversationId) {
      try {
        const conversation = await api(`/v1/conversations/${encodeURIComponent(conversationId)}`);
        state.conversationId = conversation.id;
        $("#messages").innerHTML = "";
        $("#hero").hidden = true;
        for (const message of conversation.messages) {
          if (message.role === "user") {
            addUserMessage(message.content, []);
          } else if (message.role === "assistant") {
            const node = addAssistantMessage({});
            finalizeAssistant(node, message.content, {
              id: message.id, toolRuns: message.meta?.toolRuns || [], routing: message.meta || {}
            });
          }
        }
        showRoute("chat");
        scrollToEnd();
      } catch (error) {
        toast("No se pudo abrir la conversación.", "error", error.message);
      }
    }
  };

  async function streamChat(payload, signal, onDelta) {
    let response;
    try {
      response = await fetch(apiUrl("/v1/chat/stream"), {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json", Accept: "text/event-stream" }),
        body: JSON.stringify(payload),
        signal
      });
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new Error("No se pudo contactar con el servidor de LEYRA.");
    }

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const error = new Error(data.detail || `El servidor respondió ${response.status}.`);
      error.status = response.status;
      throw error;
    }

    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("text/event-stream")) {
      const data = await response.json();
      return { ...data, content: data.message?.content || "" };
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let meta = {};
    let content = "";
    let failure = null;

    while (true) {
      let chunk;
      try {
        chunk = await reader.read();
      } catch (error) {
        if (signal.aborted) throw new DOMException("Aborted", "AbortError");
        throw error;
      }
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";
      for (const block of events) {
        let eventName = "message";
        let dataLine = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
        }
        if (!dataLine) continue;
        let data;
        try { data = JSON.parse(dataLine); } catch { continue; }
        if (eventName === "delta") {
          content += data.text || "";
          onDelta(data.text || "");
        } else if (eventName === "meta") {
          meta = data;
        } else if (eventName === "error") {
          failure = new Error(data.detail || "La generación falló.");
        } else if (eventName === "done") {
          meta.conversationId = meta.conversationId || data.conversationId;
        }
      }
    }

    if (failure) throw failure;
    if (!meta.conversationId) {
      throw new Error("El servidor no confirmó la conversación. Revisa la configuración del backend.");
    }
    return { ...meta, content };
  }

  function toggleBusy(busy) {
    const button = $("#btn-send");
    button.classList.toggle("is-busy", busy);
    button.title = busy ? "Detener generación" : "Enviar mensaje";
    $("#composer").setAttribute("aria-busy", busy ? "true" : "false");
  }

  function clearComposer() {
    const input = $("#message-input");
    input.value = "";
    input.style.height = "auto";
    $("#char-count").textContent = "0 / 20000";
  }

  /* ------------------------------------------------------------------ *
   * Attachments
   * ------------------------------------------------------------------ */
  function renderAttachments() {
    const strip = $("#attachments");
    strip.innerHTML = "";
    const total = state.attachments.length + state.images.length;
    strip.hidden = total === 0;
    for (const item of state.attachments) {
      strip.append(el("div", { class: `attachment ${item.uploading ? "is-uploading" : ""} ${item.error ? "is-error" : ""}` },
        el("span", { class: "file-glyph", text: (item.name.split(".").pop() || "arch").slice(0, 4) }),
        el("span", { text: item.name }),
        el("small", { text: item.uploading ? "subiendo…" : (item.error ? "error" : formatBytes(item.sizeBytes)) }),
        el("button", {
          type: "button", "aria-label": `Quitar ${item.name}`,
          onclick: () => { state.attachments = state.attachments.filter((entry) => entry !== item); renderAttachments(); }
        }, icon("i-x"))));
    }
    for (const image of state.images) {
      strip.append(el("div", { class: "attachment" },
        el("img", { src: image.dataUrl, alt: image.name }),
        el("span", { text: image.name }),
        el("small", { text: "visión" }),
        el("button", {
          type: "button", "aria-label": `Quitar ${image.name}`,
          onclick: () => { state.images = state.images.filter((entry) => entry !== image); renderAttachments(); }
        }, icon("i-x"))));
    }
  }

  async function uploadFile(file) {
    const item = { name: file.name, sizeBytes: file.size, uploading: true };
    state.attachments.push(item);
    renderAttachments();
    const form = new FormData();
    form.append("file", file);
    try {
      const data = await api("/v1/files", { method: "POST", body: form });
      Object.assign(item, {
        uploading: false, id: data.id, text: data.text, note: data.note,
        sizeBytes: data.sizeBytes, textCharacters: data.textCharacters
      });
      if (!data.text) toast(`«${file.name}» guardado, pero sin texto extraíble.`, "", data.note);
    } catch (error) {
      item.uploading = false;
      item.error = true;
      toast(`No se pudo subir «${file.name}».`, "error", error.message);
    }
    renderAttachments();
  }

  function addImage(file) {
    if (state.images.length >= MAX_IMAGES) {
      toast(`Máximo ${MAX_IMAGES} imágenes por mensaje.`);
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      toast("La imagen supera 6 MB.", "error");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      state.images.push({ name: file.name, dataUrl: reader.result });
      renderAttachments();
      const model = state.models.find((item) => item.id === $("#model-select").value);
      if (model && !model.capabilities.includes("vision")) {
        toast("El modelo seleccionado no admite visión; elige uno con capacidad de imagen.", "error");
      }
    };
    reader.readAsDataURL(file);
  }

  /* ------------------------------------------------------------------ *
   * Voice engine (Web Speech API + SpeechSynthesis)
   * ------------------------------------------------------------------ */
  const Voice = {
    settings: {
      voiceName: "LEYRA", voiceId: "", language: "es-MX", rate: 1, pitch: 1, volume: 1,
      style: "calida", expressivePauses: true, autoSpeak: false, bargeIn: true
    },
    voices: [],
    speaking: false,
    listening: false,
    mode: false,
    recognition: null,
    queueToken: 0,
    utterance: null,
    barge: null,

    init() {
      this.loadVoices();
      if (window.speechSynthesis) {
        window.speechSynthesis.addEventListener("voiceschanged", () => this.loadVoices());
      }
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const note = $("#voice-note");
      if (!Recognition) {
        note.textContent = "Tu navegador no incluye reconocimiento de voz. Puedes configurar un proveedor externo en la app Android.";
      } else if (!window.speechSynthesis) {
        note.textContent = "Tu navegador no incluye síntesis de voz. La lectura de respuestas no está disponible aquí.";
      } else {
        note.textContent = "El reconocimiento usa el servicio de voz del navegador: el audio puede procesarse en servidores del proveedor del navegador. LEYRA no almacena ese audio.";
      }
    },

    loadVoices() {
      if (!window.speechSynthesis) return;
      this.voices = window.speechSynthesis.getVoices() || [];
      const select = $("#voice-select");
      if (!select) return;
      const current = select.value || this.settings.voiceId;
      select.innerHTML = "";
      const matching = this.voices.filter((voice) => voice.lang.toLowerCase().startsWith(this.settings.language.slice(0, 2)));
      const pool = matching.length ? matching : this.voices;
      if (!pool.length) {
        select.append(el("option", { value: "", text: "Sin voces disponibles en este navegador" }));
        return;
      }
      for (const voice of pool) {
        select.append(el("option", { value: voice.name, text: `${voice.name} (${voice.lang})${voice.localService ? " · local" : ""}` }));
      }
      if (current && pool.some((voice) => voice.name === current)) select.value = current;
    },

    pickVoice() {
      if (!this.voices.length) return null;
      if (this.settings.voiceId) {
        const exact = this.voices.find((voice) => voice.name === this.settings.voiceId);
        if (exact) return exact;
      }
      const language = this.settings.language.slice(0, 2);
      const local = this.voices.find((voice) => voice.localService && voice.lang.toLowerCase().startsWith(language));
      return local || this.voices.find((voice) => voice.lang.toLowerCase().startsWith(language)) || this.voices[0];
    },

    apply(settings) {
      this.settings = { ...this.settings, ...settings };
      this.loadVoices();
      const select = $("#voice-select");
      if (select && this.settings.voiceId) select.value = this.settings.voiceId;
      if (this.recognition) this.recognition.lang = this.settings.language;
    },

    async speak(text, options = {}) {
      if (!window.speechSynthesis) {
        toast("Este navegador no soporta síntesis de voz.", "error");
        return;
      }
      const chunks = this.chunk(text);
      if (!chunks.length) return;
      this.stop(true);
      const token = ++this.queueToken;
      this.speaking = true;
      setCoreState("speaking");
      const voice = this.pickVoice();

      for (const chunk of chunks) {
        if (token !== this.queueToken) break;
        await new Promise((resolve) => {
          const utterance = new SpeechSynthesisUtterance(chunk);
          if (voice) utterance.voice = voice;
          utterance.lang = this.settings.language;
          utterance.rate = this.settings.rate;
          utterance.pitch = this.settings.pitch;
          utterance.volume = this.settings.volume;
          utterance.onend = resolve;
          utterance.onerror = resolve;
          this.utterance = utterance;
          window.speechSynthesis.speak(utterance);
        });
      }

      if (token === this.queueToken) {
        this.speaking = false;
        if (!this.mode) setCoreState("idle");
        if (options.onDone) options.onDone();
        else if (this.mode) this.listenOnce();
      }
    },

    chunk(text) {
      const clean = String(text || "")
        .replace(/```[\s\S]*?```/g, " bloque de código omitido ")
        .replace(/`[^`]*`/g, " ")
        .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
        .replace(/[*_#>~|]/g, " ")
        .replace(/\s+/g, " ").trim();
      if (!clean) return [];
      const sentences = clean.split(/(?<=[.!?…])\s+/);
      const chunks = [];
      let current = "";
      for (const sentence of sentences) {
        if ((current + " " + sentence).trim().length <= 220) {
          current = (current + " " + sentence).trim();
        } else {
          if (current) chunks.push(current);
          current = sentence;
        }
      }
      if (current) chunks.push(current);
      return chunks.slice(0, 40);
    },

    stop(silent = false) {
      this.queueToken += 1;
      this.speaking = false;
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      if (!silent) setCoreState(this.listening ? "listening" : "interrupted");
    },

    toggleDictation() {
      if (this.listening && !this.mode) {
        this.stopListening();
        return;
      }
      this.startListening({
        onSubmit: (transcript) => {
          const input = $("#message-input");
          input.value = `${input.value}${input.value ? " " : ""}${transcript}`.trim();
          input.dispatchEvent(new Event("input"));
          input.focus();
        }
      });
    },

    listenOnce() {
      if (!this.mode || state.busy || this.listening || this.speaking) return;
      this.startListening({ onSubmit: (transcript) => this.handleVoiceUtterance(transcript) });
    },

    /**
     * Continuous voice conversation: listen → send → speak → listen.
     * While LEYRA speaks, a "barge monitor" keeps the microphone open so that
     * the user's voice immediately cancels playback and becomes the next turn.
     */
    async handleVoiceUtterance(transcript) {
      if (!this.mode) return;
      const text = String(transcript || "").trim();
      if (!text) return;
      this.stopListening();
      $("#voice-transcript").textContent = text;
      setCoreState("processing");
      await Chat.send(text);
      if (!this.mode) return;
      const bubbles = $$("#messages .message.assistant .md");
      const answer = bubbles.length ? bubbles[bubbles.length - 1].textContent.trim() : "";
      if (!answer) {
        setCoreState("idle");
        this.listenOnce();
        return;
      }
      if (this.settings.bargeIn) this.startBargeMonitor();
      this.speak(answer, {
        onDone: () => {
          if (!this.mode) return;
          this.stopBargeMonitor();
          this.listenOnce();
        }
      });
    },

    startBargeMonitor() {
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Recognition) return;
      this.stopBargeMonitor();
      const recognition = new Recognition();
      recognition.lang = this.settings.language;
      recognition.continuous = true;
      recognition.interimResults = true;
      let finalText = "";
      recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i];
          if (result.isFinal) finalText += result[0].transcript;
          else interim += result[0].transcript;
        }
        const combined = `${finalText}${interim}`.trim();
        if (!combined) return;
        $("#voice-transcript").textContent = combined;
        if (this.speaking) this.stop();
        if (finalText.trim()) {
          const text = finalText.trim();
          finalText = "";
          this.stopBargeMonitor();
          this.handleVoiceUtterance(text);
        }
      };
      recognition.onerror = () => { this.listening = false; };
      recognition.onend = () => { this.listening = false; };
      this.barge = recognition;
      this.listening = true;
      try {
        recognition.start();
      } catch {
        this.listening = false;
      }
    },

    stopBargeMonitor() {
      if (this.barge) {
        try { this.barge.abort(); } catch { /* ignore */ }
        this.barge = null;
      }
      if (this.mode) this.listening = false;
    },

    startListening(options = {}) {
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Recognition) {
        toast("Reconocimiento de voz no disponible en este navegador.", "error");
        return;
      }
      this.stopBargeMonitor();
      if (this.recognition) {
        try { this.recognition.abort(); } catch { /* ignore */ }
      }
      const recognition = new Recognition();
      recognition.lang = this.settings.language;
      recognition.continuous = Boolean(options.continuous);
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      this.recognition = recognition;
      this.listening = true;
      setCoreState("listening");
      const mic = $("#btn-mic");
      const voiceListen = $("#voice-listen");
      mic.setAttribute("aria-pressed", "true");
      if (voiceListen) voiceListen.setAttribute("aria-pressed", "true");
      $("#waveform")?.classList.add("is-live");

      let finalText = "";
      recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i];
          const transcript = result[0].transcript;
          if (result.isFinal) finalText += transcript;
          else interim += transcript;
        }
        const combined = `${finalText}${interim}`.trim();
        if (combined) {
          $("#voice-transcript").textContent = combined;
          if (this.speaking && this.settings.bargeIn) this.stop();
        }
        if (finalText.trim()) {
          const text = finalText.trim();
          finalText = "";
          this.stopListening();
          if (options.onSubmit) options.onSubmit(text);
        }
      };
      recognition.onerror = (event) => {
        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          toast("Permiso de micrófono denegado.", "error", "Autoriza el micrófono en el navegador para usar la voz.");
          this.stopListening();
        } else if (event.error !== "aborted" && event.error !== "no-speech") {
          toast(`Reconocimiento de voz: ${event.error}`, "error");
        }
      };
      recognition.onend = () => {
        this.listening = false;
        mic.setAttribute("aria-pressed", "false");
        if (voiceListen) voiceListen.setAttribute("aria-pressed", "false");
        $("#waveform")?.classList.remove("is-live");
        if (!this.speaking) setCoreState("idle");
        if (options.onEnd) options.onEnd();
      };
      try {
        recognition.start();
      } catch (error) {
        this.listening = false;
        toast("No se pudo iniciar el micrófono.", "error", error.message);
      }
    },

    stopListening() {
      if (this.recognition) {
        try { this.recognition.stop(); } catch { /* ignore */ }
      }
      this.listening = false;
      $("#btn-mic").setAttribute("aria-pressed", "false");
      $("#voice-listen")?.setAttribute("aria-pressed", "false");
      $("#waveform")?.classList.remove("is-live");
    },

    openMode() {
      this.mode = true;
      $("#voice-overlay").hidden = false;
      $("#voice-transcript").textContent = "Te escucho. Puedes interrumpirme hablando mientras respondo.";
      this.buildWaveform();
      setCoreState("idle");
      this.listenOnce();
    },

    closeMode() {
      this.mode = false;
      this.stopBargeMonitor();
      this.stopListening();
      this.stop();
      $("#voice-overlay").hidden = true;
      setCoreState("idle");
    },

    startVoiceModeLoop() {
      this.listenOnce();
    },

    buildWaveform() {
      const wave = $("#waveform");
      if (!wave || wave.childElementCount) return;
      for (let i = 0; i < 26; i += 1) {
        const bar = el("i");
        bar.style.animationDelay = `${(i % 7) * 0.1}s`;
        bar.style.animationDuration = `${0.8 + (i % 5) * 0.12}s`;
        wave.append(bar);
      }
    }
  };

  /* ------------------------------------------------------------------ *
   * Particles
   * ------------------------------------------------------------------ */
  const Particles = {
    canvas: null, context: null, items: [], frame: null, intensity: "full",

    start() {
      this.canvas = $("#particles");
      if (!this.canvas) return;
      this.context = this.canvas.getContext("2d");
      this.resize();
      window.addEventListener("resize", debounce(() => this.resize(), 200));
      this.seed();
      this.loop();
    },

    setIntensity(level) {
      this.intensity = level;
      if (!this.canvas) return;
      if (level === "off") {
        cancelAnimationFrame(this.frame);
        this.context?.clearRect(0, 0, this.canvas.width, this.canvas.height);
        return;
      }
      if (!this.frame) this.loop();
    },

    resize() {
      if (!this.canvas) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      this.canvas.width = window.innerWidth * ratio;
      this.canvas.height = window.innerHeight * ratio;
      this.context?.setTransform(ratio, 0, 0, ratio, 0, 0);
      this.seed();
    },

    seed() {
      const count = this.intensity === "reduced" ? 18 : 42;
      const width = window.innerWidth;
      const height = window.innerHeight;
      this.items = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.16,
        vy: (Math.random() - 0.5) * 0.16,
        r: Math.random() * 1.6 + 0.5,
        alpha: Math.random() * 0.45 + 0.12
      }));
    },

    loop() {
      if (this.intensity === "off") { this.frame = null; return; }
      const ctx = this.context;
      if (!ctx) return;
      const width = window.innerWidth;
      const height = window.innerHeight;
      ctx.clearRect(0, 0, width, height);
      for (const item of this.items) {
        item.x += item.vx;
        item.y += item.vy;
        if (item.x < -10) item.x = width + 10;
        if (item.x > width + 10) item.x = -10;
        if (item.y < -10) item.y = height + 10;
        if (item.y > height + 10) item.y = -10;
        ctx.beginPath();
        ctx.arc(item.x, item.y, item.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(120, 200, 255, ${item.alpha})`;
        ctx.fill();
      }
      this.frame = requestAnimationFrame(() => this.loop());
    }
  };

  /* ------------------------------------------------------------------ *
   * Dialog helper
   * ------------------------------------------------------------------ */
  function openFormDialog({ title, description = "", fields = [], submit = "Guardar" }) {
    return new Promise((resolve) => {
      const dialog = el("dialog", { class: "dialog" });
      const form = el("form", { class: "dialog-inner", method: "dialog" });
      const header = el("header", {}, el("h2", { text: title }),
        el("button", { class: "icon-btn", value: "cancel", "aria-label": "Cerrar" }, icon("i-x")));
      form.append(header);
      if (description) form.append(el("p", { text: description }));
      const inputs = {};
      for (const field of fields) {
        const input = field.type === "textarea"
          ? el("textarea", { rows: field.rows || 6, placeholder: field.placeholder || "", value: field.value || "" })
          : el("input", { type: field.type || "text", placeholder: field.placeholder || "", value: field.value || "" });
        inputs[field.name] = input;
        form.append(el("label", {}, field.label, input));
      }
      let result = null;
      form.append(el("footer", {},
        el("button", { class: "ghost-btn", value: "cancel", text: "Cancelar" }),
        el("button", { class: "primary-btn", value: "submit", text: submit,
          onclick: (event) => {
            event.preventDefault();
            result = {};
            for (const [name, input] of Object.entries(inputs)) result[name] = input.value.trim();
            dialog.close();
          } })));
      dialog.append(form);
      dialog.addEventListener("close", () => { dialog.remove(); resolve(result); });
      document.body.append(dialog);
      dialog.showModal();
      Object.values(inputs)[0]?.focus();
    });
  }

  /* ------------------------------------------------------------------ *
   * Router
   * ------------------------------------------------------------------ */
  const ROUTES = {
    chat: { eyebrow: "CENTRO DE CONTROL", title: "Conversación" },
    history: { eyebrow: "MEMORIA DE CONVERSACIONES", title: "Historial" },
    projects: { eyebrow: "ESPACIOS DE TRABAJO", title: "Proyectos" },
    library: { eyebrow: "ARCHIVOS Y DOCUMENTOS", title: "Biblioteca" },
    tools: { eyebrow: "TOOLS ENGINE", title: "Herramientas" },
    agents: { eyebrow: "RAZONAMIENTO ESPECIALIZADO", title: "Agentes" },
    apps: { eyebrow: "ANDROID APP INTEGRATION ENGINE", title: "Aplicaciones vinculadas" },
    tasks: { eyebrow: "FLUJOS DE TRABAJO", title: "Tareas" },
    diagnostics: { eyebrow: "CENTRO DE DIAGNÓSTICO", title: "Diagnóstico" },
    settings: { eyebrow: "CONTROL CENTRAL", title: "Configuración" }
  };

  const LOADERS = {
    history: () => HistoryView.load(),
    projects: () => ProjectsView.load(),
    library: () => LibraryView.load(),
    tools: () => ToolsView.load(),
    agents: () => AgentsView.render(),
    apps: () => AppsView.load(),
    tasks: () => TasksView.render(),
    diagnostics: () => DiagnosticsView.load(),
    settings: () => SettingsView.load()
  };

  function parseHash() {
    const hash = location.hash.replace(/^#/, "");
    const [route, param] = hash.split("/");
    return { route: ROUTES[route] ? route : "chat", param: param || "" };
  }

  function showRoute(route, param = "") {
    if (!ROUTES[route]) route = "chat";
    const target = route + (param ? `/${param}` : "");
    if (location.hash.replace(/^#/, "") !== target) {
      history.replaceState(null, "", `#${target}`);
    }
    $$(".view").forEach((view) => view.classList.toggle("is-active", view.dataset.view === route));
    $$(".rail-link").forEach((link) => link.classList.toggle("is-active", link.dataset.route === route));
    $("#view-eyebrow").textContent = ROUTES[route].eyebrow;
    $("#view-title").textContent = ROUTES[route].title;
    $("#rail").classList.remove("is-open");
    if (route === "chat" && param) Chat.load(param);
    if (LOADERS[route]) {
      Promise.resolve(LOADERS[route]()).catch((error) => {
        toast("No se pudo cargar la sección.", "error", error.message);
      });
    }
    if (route === "chat" && !param) setTimeout(() => $("#message-input")?.focus(), 60);
  }

  window.addEventListener("hashchange", () => {
    const { route, param } = parseHash();
    showRoute(route, param);
  });

  /* ------------------------------------------------------------------ *
   * History
   * ------------------------------------------------------------------ */
  const HistoryView = {
    items: [],

    async load(query = "") {
      const list = $("#history-list");
      if (!list.dataset.loaded) list.innerHTML = '<p class="empty">Cargando conversaciones…</p>';
      try {
        const data = await api(`/v1/conversations?limit=100&q=${encodeURIComponent(query)}`);
        this.items = data.conversations || [];
        list.dataset.loaded = "1";
        this.render(query);
        this.renderPinned();
        $("#apps-count").textContent = String(this.items.length);
      } catch (error) {
        list.innerHTML = "";
        list.append(el("p", { class: "empty", text: `No se pudo cargar el historial: ${error.message}` }));
      }
    },

    render(query) {
      const list = $("#history-list");
      list.innerHTML = "";
      if (!this.items.length) {
        list.append(el("p", { class: "empty", text: query ? "Sin resultados para esa búsqueda." : "Todavía no hay conversaciones guardadas." }));
        return;
      }
      for (const item of this.items) {
        const node = el("div", { class: `list-item ${item.pinned ? "is-pinned" : ""}` },
          el("div", { class: "grow" },
            el("h3", {}, item.pinned ? el("span", { class: "badge-pill info", text: "fijada" }) : null, item.title),
            el("p", { text: item.lastMessage || "Sin mensajes" }),
            el("div", { class: "meta" },
              el("span", { text: timeAgo(item.updatedAt) }),
              item.project ? el("span", { text: `proyecto: ${item.project}` }) : null)),
          el("div", { class: "actions" },
            el("button", { class: "icon-action", title: "Abrir", "aria-label": "Abrir", onclick: () => { location.hash = `#chat/${item.id}`; } }, icon("i-chevron")),
            el("button", { class: "icon-action", title: item.pinned ? "Quitar fijada" : "Fijar", "aria-label": "Fijar", onclick: () => this.pin(item) }, icon("i-spark")),
            el("button", { class: "icon-action", title: "Renombrar", "aria-label": "Renombrar", onclick: () => this.rename(item) }, icon("i-spark")),
            el("button", { class: "icon-action danger", title: "Eliminar", "aria-label": "Eliminar", onclick: () => this.remove(item) }, icon("i-x"))));
        list.append(node);
      }
    },

    renderPinned() {
      const pinned = this.items.filter((item) => item.pinned).slice(0, 6);
      const section = $("#pinned-section");
      const container = $("#rail-pinned");
      section.hidden = pinned.length === 0;
      container.innerHTML = "";
      for (const item of pinned) {
        container.append(el("a", { class: "rail-pin", href: `#chat/${item.id}` }, el("span", { text: item.title })));
      }
    },

    async pin(item) {
      try {
        await api(`/v1/conversations/${item.id}/pin`, { method: "POST", body: { enabled: !item.pinned } });
        await this.load($("#history-search").value || "");
      } catch (error) {
        toast("No se pudo fijar la conversación.", "error", error.message);
      }
    },

    async rename(item) {
      const values = await openFormDialog({
        title: "Renombrar conversación",
        fields: [{ name: "title", label: "Nuevo título", value: item.title }]
      });
      if (!values || !values.title) return;
      try {
        await api(`/v1/conversations/${item.id}/rename`, { method: "POST", body: { title: values.title } });
        await this.load($("#history-search").value || "");
      } catch (error) {
        toast("No se pudo renombrar.", "error", error.message);
      }
    },

    async remove(item) {
      if (!window.confirm(`¿Eliminar «${item.title}»? Esta acción no se puede deshacer.`)) return;
      try {
        await api(`/v1/conversations/${item.id}`, { method: "DELETE" });
        if (state.conversationId === item.id) Chat.reset();
        await this.load($("#history-search").value || "");
      } catch (error) {
        toast("No se pudo eliminar.", "error", error.message);
      }
    }
  };

  const refreshHistorySoon = debounce(() => {
    if ($(".view[data-view='history']").classList.contains("is-active")) HistoryView.load($("#history-search").value || "");
    else HistoryView.load("");
  }, 500);

  /* ------------------------------------------------------------------ *
   * Projects
   * ------------------------------------------------------------------ */
  const ProjectsView = {
    async load() {
      const grid = $("#projects-grid");
      try {
        const data = await api("/v1/conversations?limit=200");
        const groups = new Map();
        for (const conversation of data.conversations || []) {
          if (!conversation.project) continue;
          const list = groups.get(conversation.project) || [];
          list.push(conversation);
          groups.set(conversation.project, list);
        }
        grid.innerHTML = "";
        if (!groups.size) {
          grid.append(el("p", { class: "empty", text: "Aún no hay proyectos. Crea uno para agrupar conversaciones bajo un mismo contexto." }));
          return;
        }
        for (const [name, items] of groups) {
          grid.append(el("div", { class: "card" },
            el("div", { class: "card-icon" }, icon("i-project")),
            el("h3", { text: name }),
            el("p", { text: `${items.length} conversación(es). Última actividad ${timeAgo(items[0].updatedAt)}.` }),
            el("div", { class: "card-foot" },
              el("button", { class: "ghost-btn", text: "Abrir última", onclick: () => { location.hash = `#chat/${items[0].id}`; } }),
              el("button", { class: "ghost-btn", text: "Nueva conversación", onclick: () => this.create(name) }))));
        }
      } catch (error) {
        grid.innerHTML = "";
        grid.append(el("p", { class: "empty", text: `No se pudieron cargar los proyectos: ${error.message}` }));
      }
    },

    async create(name) {
      let projectName = name;
      if (!projectName) {
        const values = await openFormDialog({
          title: "Nuevo proyecto",
          description: "El proyecto agrupa conversaciones en el servidor de LEYRA.",
          fields: [{ name: "name", label: "Nombre del proyecto", placeholder: "Ej.: Lanzamiento web" }]
        });
        projectName = values?.name;
      }
      if (!projectName) return;
      try {
        const conversation = await api("/v1/conversations", {
          method: "POST", body: { title: `Proyecto: ${projectName}`, project: projectName }
        });
        location.hash = `#chat/${conversation.id}`;
      } catch (error) {
        toast("No se pudo crear el proyecto.", "error", error.message);
      }
    }
  };

  /* ------------------------------------------------------------------ *
   * Library
   * ------------------------------------------------------------------ */
  const LibraryView = {
    async load() {
      const list = $("#library-list");
      try {
        const data = await api("/v1/files");
        list.innerHTML = "";
        if (!data.files.length) {
          list.append(el("p", { class: "empty", text: "La biblioteca está vacía. Sube un archivo para usarlo como contexto del chat." }));
          return;
        }
        for (const file of data.files) {
          list.append(el("div", { class: "list-item" },
            el("div", { class: "grow" },
              el("h3", {}, file.name),
              el("div", { class: "meta" },
                el("span", { text: formatBytes(file.sizeBytes) }),
                el("span", { text: timeAgo(file.updatedAt) }))),
            el("div", { class: "actions" },
              el("a", { class: "icon-action", href: apiUrl(file.downloadPath), target: "_blank", rel: "noopener", title: "Descargar", "aria-label": "Descargar" }, icon("i-download")),
              el("button", { class: "icon-action danger", title: "Eliminar", "aria-label": "Eliminar", onclick: () => this.remove(file) }, icon("i-x")))));
        }
      } catch (error) {
        list.innerHTML = "";
        list.append(el("p", { class: "empty", text: `No se pudo cargar la biblioteca: ${error.message}` }));
      }
    },

    async remove(file) {
      if (!window.confirm(`¿Eliminar «${file.name}» del servidor?`)) return;
      try {
        await api(`/v1/files/${file.id}`, { method: "DELETE" });
        await this.load();
      } catch (error) {
        toast("No se pudo eliminar el archivo.", "error", error.message);
      }
    },

    upload() {
      const input = el("input", { type: "file", multiple: true, style: "display:none" });
      document.body.append(input);
      input.addEventListener("change", async () => {
        for (const file of Array.from(input.files || [])) {
          const item = { name: file.name, sizeBytes: file.size, uploading: true };
          state.attachments.push(item);
          renderAttachments();
          const form = new FormData();
          form.append("file", file);
          try {
            const data = await api("/v1/files", { method: "POST", body: form });
            Object.assign(item, { uploading: false, id: data.id, text: data.text, sizeBytes: data.sizeBytes });
          } catch (error) {
            item.uploading = false;
            item.error = true;
          }
        }
        input.remove();
        await this.load();
      });
      input.click();
    }
  };

  /* ------------------------------------------------------------------ *
   * Tools
   * ------------------------------------------------------------------ */
  const ToolsView = {
    async load() {
      const list = $("#tools-list");
      try {
        const data = await api("/v1/tools");
        state.tools = data.tools || [];
        list.innerHTML = "";
        const grouped = new Map();
        for (const tool of state.tools) {
          const key = tool.category || "general";
          const items = grouped.get(key) || [];
          items.push(tool);
          grouped.set(key, items);
        }
        for (const [category, items] of grouped) {
          list.append(el("p", { class: "eyebrow", style: "margin:14px 0 2px", text: category.toUpperCase() }));
          for (const tool of items) {
            const badge = tool.available
              ? el("span", { class: "badge-pill ok", text: "disponible" })
              : el("span", { class: "badge-pill err", text: "no disponible" });
            const riskBadge = el("span", { class: `badge-pill ${tool.risk === "read_only" ? "info" : "warn"}`, text: tool.risk });
            list.append(el("div", { class: "list-item" },
              el("div", { class: "grow" },
                el("h3", {}, tool.title, badge, riskBadge),
                el("p", { text: tool.description }),
                el("div", { class: "meta" }, el("span", { text: tool.name }),
                  tool.available ? null : el("span", { text: tool.unavailableReason }))),
              el("div", { class: "actions" },
                el("button", {
                  class: "ghost-btn", text: "Abrir",
                  onclick: () => this.openRunner(tool)
                }))));
          }
        }
        $("#tools-count").textContent = `${state.tools.filter((tool) => tool.available).length}/${state.tools.length}`;
      } catch (error) {
        list.innerHTML = "";
        list.append(el("p", { class: "empty", text: `No se pudieron cargar las herramientas: ${error.message}` }));
      }
    },

    openRunner(tool) {
      const runner = $("#tool-runner");
      runner.innerHTML = "";
      runner.append(
        el("h3", { text: tool.title }),
        el("p", { class: "hint", text: tool.description }),
        el("p", { class: "hint" },
          el("span", { class: "badge-pill info", text: tool.name }),
          " ",
          tool.available ? el("span", { class: "badge-pill ok", text: "disponible" })
            : el("span", { class: "badge-pill err", text: "no disponible" }))
      );
      if (!tool.available) runner.append(el("p", { class: "hint", text: tool.unavailableReason }));

      const form = el("form", {});
      const inputs = {};
      for (const parameter of tool.parameters) {
        let input;
        if (parameter.choices?.length) {
          input = el("select", {});
          for (const choice of parameter.choices) input.append(el("option", { value: choice, text: choice }));
        } else if (parameter.kind === "boolean") {
          input = el("input", { type: "checkbox" });
        } else if (parameter.kind === "json" || parameter.kind === "text") {
          input = el("textarea", { rows: 4, placeholder: parameter.description, value: parameter.default ?? "" });
        } else {
          input = el("input", {
            type: parameter.kind === "number" || parameter.kind === "integer" ? "number" : "text",
            step: parameter.kind === "integer" ? "1" : "any",
            placeholder: parameter.description, value: parameter.default ?? ""
          });
        }
        inputs[parameter.name] = { input, parameter };
        form.append(el("div", { class: "field" },
          el("label", { text: `${parameter.name}${parameter.required ? " *" : ""}` }), input));
      }
      let confirmBox = null;
      if (tool.risk !== "read_only") {
        confirmBox = el("input", { type: "checkbox" });
        form.append(el("label", { class: "switch" }, confirmBox, `Confirmo ejecutar «${tool.name}» (${tool.risk})`));
      }
      const output = el("div", { class: "result-box" }, el("p", { class: "empty", text: "Sin ejecutar." }));
      form.append(el("div", { class: "row" },
        el("button", { class: "primary-btn", type: "submit", text: "Ejecutar" })));
      runner.append(form, output);

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const args = {};
        for (const [name, { input, parameter }] of Object.entries(inputs)) {
          if (parameter.kind === "boolean") { args[name] = input.checked; continue; }
          const raw = input.value.trim();
          if (raw === "") continue;
          if (parameter.kind === "number" || parameter.kind === "integer") args[name] = Number(raw);
          else if (parameter.kind === "json") {
            try { args[name] = JSON.parse(raw); } catch { toast(`«${name}» no es JSON válido.`, "error"); return; }
          } else args[name] = raw;
        }
        output.textContent = "Ejecutando…";
        try {
          const result = await api(`/v1/tools/${encodeURIComponent(tool.name)}/run`, {
            method: "POST",
            body: { arguments: args, confirmed: confirmBox ? confirmBox.checked : false }
          });
          output.textContent = JSON.stringify(result, null, 2);
          setCoreState("tools");
          setTimeout(() => setCoreState("idle"), 1200);
        } catch (error) {
          output.textContent = error.message;
        }
      });
    }
  };

  /* ------------------------------------------------------------------ *
   * Agents
   * ------------------------------------------------------------------ */
  const AgentsView = {
    render() {
      const grid = $("#agents-grid");
      grid.innerHTML = "";
      for (const agent of AGENTS) {
        const active = state.pendingAgent === agent.id;
        grid.append(el("div", { class: "card" },
          el("div", { class: "card-icon" }, icon(agent.icon)),
          el("h3", {}, agent.name, el("span", { class: "badge-pill info", text: agent.level })),
          el("p", { text: agent.desc }),
          el("p", { class: "meta", style: "font-size:10.5px;color:var(--muted)", text: `Instrucción: ${agent.prompt}` }),
          el("div", { class: "card-foot" },
            el("button", {
              class: active ? "primary-btn" : "ghost-btn", text: active ? "Agente activo" : "Usar agente",
              onclick: () => {
                state.pendingAgent = active ? "" : agent.id;
                $("#agent-select").value = state.pendingAgent;
                this.render();
                toast(active ? "Agente desactivado." : `Agente «${agent.name}» activo para el próximo mensaje.`);
                if (!active) showRoute("chat");
              }
            }))));
      }
    }
  };

  /* ------------------------------------------------------------------ *
   * Android app integration
   * ------------------------------------------------------------------ */
  const AppsView = {
    data: null,
    tab: "catalog",

    async load() {
      const catalog = $("#apps-catalog");
      try {
        const data = await api("/v1/apps");
        this.data = data;
        $("#apps-count").textContent = String(data.linked.filter((item) => item.enabled).length);
        this.renderBanner(data);
        this.renderCatalog();
        this.renderLinked();
        this.renderPolicy();
        this.renderHistory();
      } catch (error) {
        catalog.innerHTML = "";
        catalog.append(el("p", { class: "empty", text: `No se pudo cargar la integración: ${error.message}` }));
      }
    },

    renderBanner(data) {
      const banner = $("#bridge-banner");
      banner.hidden = false;
      banner.className = "banner";
      banner.innerHTML = "";
      if (data.bridge.available) {
        banner.classList.add("ok");
        banner.append(icon("i-check"), el("div", {},
          el("strong", { text: `Puente Android conectado (${data.bridge.name})` }),
          el("span", { text: "Las acciones autorizadas se ejecutan en el dispositivo mediante intents públicos." })));
        return;
      }
      banner.append(icon("i-shield"), el("div", {},
        el("strong", { text: "Sin puente Android en este entorno" }),
        el("span", { text: "Estás usando la interfaz web: LEYRA puede descubrir conectores, planificar acciones y validar permisos, pero no puede abrir ni controlar aplicaciones del móvil desde aquí. Abre LEYRA en Android para ejecutar. Android aísla los datos de cada app: solo se usan interfaces públicas (Intent, deep links, SDK, plugins) y nunca se accede a datos privados ni se eluden permisos." })));
    },

    matches(entry, query) {
      if (!query) return true;
      const needle = query.toLowerCase();
      return entry.label.toLowerCase().includes(needle) || entry.packageName.toLowerCase().includes(needle);
    },

    renderCatalog() {
      const container = $("#apps-catalog");
      const query = ($("#apps-search").value || "").trim();
      container.innerHTML = "";
      const items = (this.data?.catalog || []).filter((entry) => this.matches(entry, query));
      if (!items.length) {
        container.append(el("p", { class: "empty", text: this.data?.catalog?.length
          ? "Ninguna aplicación coincide con la búsqueda."
          : "No se han descubierto aplicaciones. En Android, LEYRA consulta PackageManager al abrir esta sección; en la web no hay acceso al dispositivo." }));
        return;
      }
      for (const entry of items) {
        const status = {
          full: ["ok", "completa"], partial: ["warn", "parcial"],
          open_only: ["info", "solo apertura"], incompatible: ["err", "no compatible"]
        }[entry.status] || ["info", entry.status];
        const connector = (this.data.connectors || []).find((manifest) => manifest.packageName === entry.packageName);
        container.append(el("div", { class: "list-item" },
          el("div", { class: "grow" },
            el("h3", {}, entry.label,
              el("span", { class: `badge-pill ${status[0]}`, text: status[1] }),
              entry.linked ? el("span", { class: "badge-pill info", text: "vinculada" }) : null),
            el("div", { class: "meta" },
              el("span", { text: entry.packageName }),
              el("span", { text: `v${entry.versionName}` }),
              el("span", { text: `nivel ${entry.level}` }),
              el("span", { text: `${entry.actions.length} acciones` })),
            el("p", { text: entry.note || "" })),
          el("div", { class: "actions" },
            el("button", {
              class: "ghost-btn", text: entry.linked ? "Vinculada" : "Vincular",
              disabled: entry.linked || entry.status === "incompatible",
              onclick: () => this.link(entry, connector)
            }))));
      }
    },

    async link(entry, connector) {
      const permissions = connector ? connector.permissions : [];
      const description = permissions.length
        ? `El conector declara estos permisos de integración: ${permissions.join(", ")}. Se concederán al vincular y podrás revocarlos después.`
        : "La aplicación se vinculará en nivel de solo apertura.";
      const confirmation = await openFormDialog({
        title: `Vincular ${entry.label}`,
        description,
        fields: permissions.length ? [{ name: "permissions", label: "Permisos a conceder (separados por comas)", value: permissions.join(", ") }] : [],
        submit: "Vincular"
      });
      if (!confirmation) return;
      const granted = permissions.length
        ? (confirmation.permissions || "").split(",").map((item) => item.trim()).filter(Boolean)
        : [];
      try {
        await api(`/v1/apps/${encodeURIComponent(entry.packageName)}/link`, {
          method: "POST", body: { grantedPermissions: granted }
        });
        toast("Aplicación vinculada.", "success");
        await this.load();
      } catch (error) {
        toast("No se pudo vincular la aplicación.", "error", error.message);
      }
    },

    renderLinked() {
      const container = $("#apps-linked");
      container.innerHTML = "";
      const linked = this.data?.linked || [];
      if (!linked.length) {
        container.append(el("p", { class: "empty", text: "No hay aplicaciones vinculadas. Vincula una desde el catálogo para autorizar su uso." }));
        return;
      }
      for (const link of linked) {
        const connector = (this.data.connectors || []).find((manifest) => manifest.packageName === link.packageName);
        const permissions = connector ? connector.permissions : [];
        const node = el("div", { class: "list-item" },
          el("div", { class: "grow" },
            el("h3", {}, link.label,
              el("span", { class: `badge-pill ${link.enabled ? "ok" : "warn"}`, text: link.enabled ? "activa" : "desactivada" }),
              el("span", { class: "badge-pill info", text: `nivel ${link.level}` })),
            el("div", { class: "meta" },
              el("span", { text: link.packageName }),
              el("span", { text: link.status }),
              el("span", { text: link.grantedPermissions.length ? link.grantedPermissions.join(", ") : "sin permisos" })),
            link.lastError ? el("p", { text: link.lastError }) : null,
            el("div", { class: "meta", style: "gap:8px" },
              el("button", { class: "ghost-btn", text: link.enabled ? "Desactivar" : "Activar", onclick: () => this.toggle(link) }),
              el("button", { class: "ghost-btn", text: "Permisos", onclick: () => this.editPermissions(link, permissions) }),
              el("button", { class: "danger-btn", text: "Desvincular", onclick: () => this.unlink(link) }))));
        container.append(node);
      }
    },

    async toggle(link) {
      try {
        await api(`/v1/apps/${encodeURIComponent(link.packageName)}/enabled`, {
          method: "POST", body: { enabled: !link.enabled }
        });
        await this.load();
      } catch (error) { toast("No se pudo cambiar el estado.", "error", error.message); }
    },

    async editPermissions(link, permissions) {
      const values = await openFormDialog({
        title: `Permisos de ${link.label}`,
        description: "Revoca o concede los permisos declarados por el conector. Los no concedidos degradan la integración a parcial.",
        fields: [{ name: "permissions", label: "Permisos concedidos (separados por comas)", value: link.grantedPermissions.join(", ") }],
        submit: "Guardar permisos"
      });
      if (!values) return;
      try {
        await api(`/v1/apps/${encodeURIComponent(link.packageName)}/permissions`, {
          method: "POST",
          body: { grantedPermissions: (values.permissions || "").split(",").map((item) => item.trim()).filter(Boolean) }
        });
        await this.load();
        toast("Permisos actualizados.", "success");
      } catch (error) { toast("No se pudieron actualizar los permisos.", "error", error.message); }
    },

    async unlink(link) {
      if (!window.confirm(`¿Desvincular «${link.label}» de LEYRA?`)) return;
      try {
        await api(`/v1/apps/${encodeURIComponent(link.packageName)}/unlink`, { method: "POST" });
        await this.load();
      } catch (error) { toast("No se pudo desvincular.", "error", error.message); }
    },

    renderPolicy() {
      const container = $("#apps-policy");
      const policy = this.data?.policy || {};
      container.innerHTML = "";
      const levels = [
        [1, "Apertura", "Lanzar la app con un intent público."],
        [2, "Interoperabilidad", "Compartir texto/archivos, deep links y app links."],
        [3, "API oficial", "SDK o API documentada con autenticación propia."],
        [4, "Plugins", "Conectores firmados que implementan el contrato de LEYRA."],
        [5, "Accesibilidad", "Interacción con elementos visibles, solo con autorización expresa."]
      ];
      const list = el("div", { class: "level-list" });
      for (const [level, name, description] of levels) {
        const input = el("input", { type: "radio", name: "max-level", value: String(level), checked: Number(policy.maxLevel) === level });
        list.append(el("div", { class: "level-row" }, input,
          el("b", { text: String(level) }), el("span", {}, el("strong", { text: name }), " — ", description)));
      }
      const accessibility = el("input", { type: "checkbox", checked: Boolean(policy.accessibilityOptIn) });
      const blocked = el("textarea", { rows: 3, placeholder: "com.app.no.permitida, otra.app" });
      blocked.value = (policy.blockedPackages || []).join(", ");
      container.append(
        el("p", { class: "panel-note", text: `Política efectiva: nivel ${policy.effectiveLevel}. Los niveles superiores al activo se rechazan; el nivel 5 exige activación explícita y nunca accede a datos privados.` }),
        list,
        el("label", { class: "switch", style: "margin-top:12px" }, accessibility,
          "Activar integración asistida por accesibilidad (opcional, visible en Android y desactivable)"),
        el("div", { class: "field", style: "margin-top:12px" }, el("label", { text: "Aplicaciones bloqueadas" }), blocked),
        el("div", { class: "row" }, el("button", {
          class: "primary-btn", text: "Guardar política",
          onclick: async () => {
            const selected = container.querySelector("input[name='max-level']:checked");
            try {
              await api("/v1/apps/policy", {
                method: "PUT",
                body: {
                  maxLevel: Number(selected?.value || 2),
                  accessibilityOptIn: accessibility.checked,
                  blockedPackages: blocked.value.split(",").map((item) => item.trim()).filter(Boolean)
                }
              });
              toast("Política actualizada.", "success");
              await this.load();
            } catch (error) { toast("No se pudo guardar la política.", "error", error.message); }
          }
        })),
        el("p", { class: "panel-note", style: "margin-top:14px", text: "LEYRA nunca instala APK en silencio, no desactiva protecciones del sistema, no solicita permisos innecesarios y no evade el aislamiento de Android. Si una app no ofrece API, SDK o un intent público, no es posible integrarla." })
      );
    },

    renderHistory() {
      const container = $("#apps-history");
      container.innerHTML = "";
      const history = this.data?.history || [];
      if (!history.length) {
        container.append(el("p", { class: "empty", text: "Sin actividad registrada. Cada vinculación, cambio de permisos y ejecución queda en este registro." }));
        return;
      }
      for (const entry of history.slice(0, 40)) {
        container.append(el("div", { class: "list-item" },
          el("div", { class: "grow" },
            el("h3", {}, el("span", { class: "badge-pill info", text: entry.event }), entry.packageName),
            el("p", { text: entry.detail }),
            el("div", { class: "meta" }, el("span", { text: timeAgo(entry.at) })))));
      }
    },

    async importConnector() {
      const example = JSON.stringify({
        id: "example.share",
        name: "Ejemplo de conector",
        packageName: "com.example.share",
        version: "1.0",
        level: 2,
        auth: "none",
        notes: "Conector de demostración con acción de compartir texto.",
        actions: [{
          id: "share_text", label: "Compartir texto", kind: "share", level: 2,
          description: "Comparte texto mediante ACTION_SEND.",
          permissions: ["android.intent.action.SEND"],
          parameters: [{ name: "text", type: "text", required: true, description: "Texto a compartir" }]
        }]
      }, null, 2);
      const values = await openFormDialog({
        title: "Importar conector",
        description: "Un conector describe solo capacidades públicas y documentadas. Se registra como no confiable hasta que la app lo publique oficialmente.",
        fields: [{ name: "manifest", label: "Manifiesto JSON", type: "textarea", rows: 14, value: example }],
        submit: "Importar"
      });
      if (!values?.manifest) return;
      let manifest;
      try { manifest = JSON.parse(values.manifest); } catch { toast("El JSON no es válido.", "error"); return; }
      try {
        await api("/v1/apps/connectors", { method: "POST", body: { manifest } });
        toast("Conector validado y registrado.", "success");
        await this.load();
      } catch (error) {
        toast("El conector no pasó la validación.", "error", error.message);
      }
    },

    async resolve(confirmed) {
      const box = $("#integration-result");
      const instruction = $("#integration-instruction").value.trim();
      if (!instruction) { toast("Escribe una instrucción."); return; }
      box.textContent = "Resolviendo…";
      try {
        const data = await api("/v1/apps/resolve", { method: "POST", body: { instruction, confirmed } });
        box.textContent = "";
        box.append(el("pre", { style: "margin:0", text: JSON.stringify(data, null, 2) }));
        if (data.results) {
          const statuses = data.results.map((item) => item.status);
          if (statuses.includes("confirmation_required")) toast("La acción requiere confirmación explícita.", "", "Vuelve a ejecutar marcando la confirmación.");
          else if (statuses.includes("unavailable")) toast("Plan válido, pero no hay puente Android para ejecutarlo.");
          else if (statuses.includes("ok")) { toast("Acción despachada al dispositivo.", "success"); setCoreState("tools"); }
        }
      } catch (error) {
        box.textContent = error.message;
      }
    }
  };

  /* ------------------------------------------------------------------ *
   * Tasks (local)
   * ------------------------------------------------------------------ */
  const TasksView = {
    tasks: json(TASKS_KEY, []),

    add(title, priority) {
      if (!title.trim()) return;
      this.tasks.unshift({ id: crypto.randomUUID?.() || String(Date.now()), title: title.trim(), priority, done: false, at: Date.now() });
      this.save();
    },

    save() {
      persist(TASKS_KEY, this.tasks);
      this.render();
    },

    render() {
      const list = $("#tasks-list");
      list.innerHTML = "";
      if (!this.tasks.length) {
        list.append(el("p", { class: "empty", text: "No hay tareas. Añade una arriba: se guardan en este navegador, no en el servidor." }));
        return;
      }
      for (const task of this.tasks) {
        const checkbox = el("input", { type: "checkbox", checked: task.done, "aria-label": `Completar ${task.title}` });
        checkbox.addEventListener("change", () => { task.done = checkbox.checked; this.save(); });
        list.append(el("div", { class: `task ${task.done ? "is-done" : ""}` },
          checkbox,
          el("span", { class: "title", text: task.title }),
          el("span", { class: `task-prio ${task.priority}`, text: task.priority }),
          el("button", {
            class: "icon-action danger", "aria-label": "Eliminar tarea",
            onclick: () => { this.tasks = this.tasks.filter((item) => item !== task); this.save(); }
          }, icon("i-x"))));
      }
    }
  };

  /* ------------------------------------------------------------------ *
   * Diagnostics
   * ------------------------------------------------------------------ */
  const DiagnosticsView = {
    async load() {
      const grid = $("#diag-grid");
      const summary = $("#diag-summary");
      summary.innerHTML = '<p class="empty">Comprobando módulos…</p>';
      try {
        const report = await api("/v1/diagnostics");
        state.diagnostics = report;
        const counts = report.counts || {};
        setDiagnosticsBadge(report.status);
        summary.innerHTML = "";
        summary.append(
          el("div", { class: "status-led " + report.status }),
          el("div", {}, el("div", { class: "big", text: report.status.toUpperCase() }),
            el("div", { class: "label", text: `Última comprobación: ${clock(report.checkedAt)}` })),
          el("div", { class: "counts" },
            ...["ok", "degraded", "unavailable", "error"].map((key) =>
              el("span", {}, el("b", { text: String(counts[key] || 0) }), ` ${key}`))));
        grid.innerHTML = "";
        for (const module of report.modules) {
          const details = el("details", {},
            el("summary", { text: "Ver datos de la comprobación" }),
            el("pre", { text: JSON.stringify(module.data || {}, null, 2) }));
          grid.append(el("div", { class: "diag-card" },
            el("header", {}, el("span", { class: "status-led " + module.status }), el("h3", { text: module.module })),
            el("p", { text: module.detail || "Sin detalle." }),
            details));
        }
      } catch (error) {
        summary.innerHTML = "";
        summary.append(el("p", { class: "empty", text: `No se pudo ejecutar el diagnóstico: ${error.message}` }));
      }
    }
  };

  /* ------------------------------------------------------------------ *
   * Settings
   * ------------------------------------------------------------------ */
  const SettingsView = {
    loaded: false,

    async load() {
      $("#api-base").value = connection.base;
      $("#api-token").value = connection.token;
      if (!this.loaded) {
        this.loaded = true;
        await Promise.all([this.loadVoice(), this.loadModels(), this.loadPrivacy()]);
      } else {
        await this.loadPrivacy();
      }
    },

    async loadVoice() {
      try {
        const data = await api("/v1/voice");
        Voice.apply(data.settings || {});
        const settings = Voice.settings;
        $("#voice-name").value = settings.voiceName || "LEYRA";
        $("#voice-rate").value = settings.rate;
        $("#voice-pitch").value = settings.pitch;
        $("#voice-rate-out").textContent = Number(settings.rate).toFixed(2);
        $("#voice-pitch-out").textContent = Number(settings.pitch).toFixed(2);
        $("#voice-pauses").checked = Boolean(settings.expressivePauses);
        $("#voice-autospeak").checked = Boolean(settings.autoSpeak);
        $("#voice-barge").checked = Boolean(settings.bargeIn);
        const languageSelect = $("#voice-language");
        languageSelect.innerHTML = "";
        for (const language of data.languages || ["es-MX"]) {
          languageSelect.append(el("option", { value: language, text: language, selected: language === settings.language }));
        }
        languageSelect.value = settings.language;
        const styleSelect = $("#voice-style");
        styleSelect.innerHTML = "";
        for (const style of data.styles || ["calida"]) {
          styleSelect.append(el("option", { value: style, text: style }));
        }
        styleSelect.value = settings.style;
        Voice.loadVoices();
      } catch (error) {
        $("#voice-feedback").className = "form-feedback error";
        $("#voice-feedback").textContent = "No se pudo leer la configuración de voz del servidor; se usarán los valores locales.";
      }
    },

    async loadModels() {
      const box = $("#models-summary");
      try {
        const data = await api("/v1/models");
        state.models = data.models || [];
        state.providers = data.providers || [];
        box.innerHTML = "";
        for (const provider of state.providers) {
          box.append(el("div", { class: "level-row" },
            el("span", { class: `badge-pill ${provider.configured ? "ok" : "err"}`, text: provider.configured ? "configurado" : "sin clave" }),
            el("span", { text: provider.label }),
            el("span", { style: "font-family:var(--mono);font-size:10px;color:var(--muted)", text: provider.keyEnv })));
        }
        const configured = state.models.filter((model) => model.configured);
        box.append(el("p", { class: "form-feedback", text: configured.length
          ? `Modelos disponibles: ${configured.map((model) => model.id).join(", ")}.`
          : "Ningún proveedor tiene credenciales: el chat responderá con un aviso hasta que configures una clave en el servidor." }));
        this.populateModelSelect();
      } catch (error) {
        box.innerHTML = "";
        box.append(el("p", { class: "empty", text: `No se pudieron cargar los modelos: ${error.message}` }));
      }
    },

    populateModelSelect() {
      const select = $("#model-select");
      if (!select) return;
      const current = select.value;
      select.innerHTML = "";
      select.append(el("option", { value: "", text: "Modelo automático" }));
      for (const model of state.models) {
        select.append(el("option", {
          value: model.id,
          text: `${model.label}${model.configured ? "" : " · sin credenciales"}`,
          disabled: !model.configured
        }));
      }
      select.value = current;
    },

    async loadPrivacy() {
      const box = $("#privacy-summary");
      try {
        const [memory, conversations] = await Promise.all([api("/v1/memory?limit=5"), api("/v1/conversations?limit=1")]);
        box.innerHTML = "";
        box.append(
          el("div", { class: "level-row" }, el("span", { text: "Recuerdos guardados:" }), el("b", { text: String(memory.count) })),
          el("div", { class: "level-row" }, el("span", { text: "Cifrado en reposo:" }), el("span", { class: "badge-pill warn", text: "no activo" })),
          el("p", { class: "form-feedback", text: "La memoria usa procedencia, deduplicación y permite exportación y borrado. Activa cifrado de disco en el servidor mientras el cifrado interno no esté implementado." })
        );
        if (memory.memories?.length) {
          const list = el("div", { class: "list" });
          for (const item of memory.memories) {
            list.append(el("div", { class: "list-item" },
              el("div", { class: "grow" },
                el("h3", {}, el("span", { class: "badge-pill info", text: item.category }), item.provenance),
                el("p", { text: item.text }),
                el("div", { class: "meta" }, el("span", { text: timeAgo(item.updatedAt) }))),
              el("button", {
                class: "icon-action danger", "aria-label": "Borrar recuerdo",
                onclick: async () => {
                  try {
                    await api(`/v1/memory/${item.id}`, { method: "DELETE" });
                    await this.loadPrivacy();
                  } catch (error) { toast("No se pudo borrar el recuerdo.", "error", error.message); }
                }
              }, icon("i-x"))));
          }
          box.append(list);
        }
      } catch (error) {
        box.innerHTML = "";
        box.append(el("p", { class: "empty", text: `No se pudo leer la memoria: ${error.message}` }));
      }
    }
  };

  /* ------------------------------------------------------------------ *
   * Event wiring
   * ------------------------------------------------------------------ */
  function bindNavigation() {
    $("#new-chat").addEventListener("click", () => Chat.reset());
    $("#rail-toggle").addEventListener("click", () => $("#rail").classList.add("is-open"));
    $("#rail-close").addEventListener("click", () => $("#rail").classList.remove("is-open"));
    $("#rail").addEventListener("click", (event) => {
      if (event.target.closest(".rail-link, .rail-pin")) $("#rail").classList.remove("is-open");
    });
    $("#status-card").addEventListener("click", () => {
      $("#quick-api-base").value = connection.base;
      $("#quick-api-token").value = connection.token;
      $("#quick-settings").showModal();
    });
    $("#quick-save").addEventListener("click", () => {
      connection.base = $("#quick-api-base").value.trim().replace(/\/+$/, "");
      connection.token = $("#quick-api-token").value.trim();
      persist(CONN_KEY, connection);
      setTimeout(() => checkHealth(true), 120);
    });
    $("#open-profile").addEventListener("click", () => showRoute("settings"));
    $("#btn-settings").addEventListener("click", () => showRoute("settings"));
    $("#btn-theme").addEventListener("click", () => {
      const order = ["dark", "space", "light"];
      prefs.theme = order[(order.indexOf(prefs.theme) + 1) % order.length];
      savePrefs();
      toast(`Tema: ${prefs.theme === "dark" ? "oscuro" : prefs.theme === "space" ? "negro espacial" : "claro"}`);
    });
    $("#btn-voice-mode").addEventListener("click", () => Voice.openMode());
  }

  function bindComposer() {
    const input = $("#message-input");
    const form = $("#composer");

    const resize = () => {
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight, 240)}px`;
      $("#char-count").textContent = `${input.value.length} / 20000`;
    };
    input.addEventListener("input", resize);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (state.busy) return;
        Chat.send(input.value).then(() => resize());
      }
    });

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (state.busy) { Chat.stop(); return; }
      Chat.send(input.value).then(() => resize());
    });

    $("#btn-tools").addEventListener("click", (event) => {
      const pressed = event.currentTarget.getAttribute("aria-pressed") === "true";
      event.currentTarget.setAttribute("aria-pressed", pressed ? "false" : "true");
    });
    $("#btn-reasoning").addEventListener("click", (event) => {
      const pressed = event.currentTarget.getAttribute("aria-pressed") === "true";
      event.currentTarget.setAttribute("aria-pressed", pressed ? "false" : "true");
      setCoreState(pressed ? "idle" : "reasoning");
      setTimeout(() => { if (!state.busy) setCoreState("idle"); }, 900);
    });
    $("#agent-select").addEventListener("change", (event) => {
      state.pendingAgent = event.target.value;
      if (event.target.value) toast(`Agente «${AGENTS.find((agent) => agent.id === event.target.value)?.name}» activo.`);
    });

    $("#btn-attach").addEventListener("click", () => $("#file-input").click());
    $("#btn-image").addEventListener("click", () => $("#image-input").click());
    $("#file-input").addEventListener("change", (event) => {
      for (const file of Array.from(event.target.files || [])) uploadFile(file);
      event.target.value = "";
    });
    $("#image-input").addEventListener("change", (event) => {
      for (const file of Array.from(event.target.files || [])) addImage(file);
      event.target.value = "";
    });

    ["dragenter", "dragover"].forEach((name) => form.addEventListener(name, (event) => {
      event.preventDefault();
      form.classList.add("drag-over");
    }));
    ["dragleave", "drop"].forEach((name) => form.addEventListener(name, (event) => {
      event.preventDefault();
      form.classList.remove("drag-over");
    }));
    form.addEventListener("drop", (event) => {
      for (const file of Array.from(event.dataTransfer?.files || [])) {
        if (file.type.startsWith("image/")) addImage(file);
        else uploadFile(file);
      }
    });
    input.addEventListener("paste", (event) => {
      for (const item of Array.from(event.clipboardData?.items || [])) {
        if (item.type.startsWith("image/")) {
          const file = item.getAsFile();
          if (file) addImage(file);
        }
      }
    });

    $("#btn-mic").addEventListener("click", () => Voice.toggleDictation());
    $("#btn-send").addEventListener("click", (event) => {
      if (!state.busy) return;
      event.preventDefault();
      Chat.stop();
    });
    $("#btn-send").setAttribute("aria-label", "Enviar mensaje");
  }

  function bindSuggestionsAndMisc() {
    $("#suggestions").addEventListener("click", (event) => {
      const button = event.target.closest("[data-prompt]");
      if (!button) return;
      const input = $("#message-input");
      input.value = button.dataset.prompt;
      input.dispatchEvent(new Event("input"));
      Chat.send(button.dataset.prompt);
    });
    $("#voice-close").addEventListener("click", () => Voice.closeMode());
    $("#voice-listen").addEventListener("click", () => {
      if (Voice.listening) { Voice.stopListening(); return; }
      if (Voice.speaking) { Voice.stop(); return; }
      Voice.listenOnce();
    });
    $("#voice-interrupt").addEventListener("click", () => {
      if (state.busy) Chat.stop();
      if (Voice.speaking) Voice.stop();
      Voice.stopListening();
      setCoreState("interrupted");
    });
    $("#history-search").addEventListener("input", debounce((event) => HistoryView.load(event.target.value), 260));
    $("#new-project").addEventListener("click", () => ProjectsView.create());
    $("#library-upload").addEventListener("click", () => LibraryView.upload());
    $("#tools-refresh").addEventListener("click", () => ToolsView.load());
    $("#apps-refresh").addEventListener("click", () => AppsView.load());
    $("#apps-import").addEventListener("click", () => AppsView.importConnector());
    $("#apps-search").addEventListener("input", debounce(() => AppsView.renderCatalog(), 180));
    $("#diagnostics-refresh").addEventListener("click", () => DiagnosticsView.load());
    $("#integration-resolve").addEventListener("click", () => AppsView.resolve(false));
    $("#integration-execute").addEventListener("click", async () => {
      const preview = await api("/v1/apps/resolve", { method: "POST", body: { instruction: $("#integration-instruction").value.trim() } }).catch(() => null);
      const needsConfirmation = preview?.plan?.requiresConfirmation;
      if (needsConfirmation) {
        const ok = window.confirm("Esta acción envía datos fuera de LEYRA. ¿Confirmas la ejecución para esta llamada?");
        if (!ok) return;
      }
      AppsView.resolve(true);
    });

    $("#apps-tabs").addEventListener("click", (event) => {
      const tab = event.target.closest(".tab");
      if (!tab) return;
      $$("#apps-tabs .tab").forEach((node) => node.classList.toggle("is-active", node === tab));
      $$(".tab-panel").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === tab.dataset.tab));
    });

    $("#task-form").addEventListener("submit", (event) => {
      event.preventDefault();
      TasksView.add($("#task-title").value, $("#task-priority").value);
      $("#task-title").value = "";
    });

    document.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        Chat.reset();
      }
      if (event.key === "Escape") {
        if (!$("#voice-overlay").hidden) Voice.closeMode();
        $("#rail").classList.remove("is-open");
      }
    });

    const settingsBind = (id, key) => {
      const node = document.getElementById(id);
      if (!node) return;
      node.addEventListener("change", () => {
        prefs[key] = node.value;
        savePrefs();
      });
    };
    settingsBind("pref-theme", "theme");
    settingsBind("pref-accent", "accent");
    settingsBind("pref-motion", "motion");
    settingsBind("pref-glass", "glass");
    settingsBind("pref-density", "density");

    $("#connection-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      connection.base = $("#api-base").value.trim().replace(/\/+$/, "");
      connection.token = $("#api-token").value.trim();
      persist(CONN_KEY, connection);
      const ok = await checkHealth(true);
      const feedback = $("#connection-feedback");
      feedback.className = `form-feedback ${ok ? "success" : "error"}`;
      feedback.textContent = ok ? "Conexión correcta." : "No se pudo conectar. Revisa la URL, CORS y el token.";
      if (ok) await SettingsView.loadModels();
    });
    $("#connection-test").addEventListener("click", () => {
      connection.base = $("#api-base").value.trim().replace(/\/+$/, "");
      connection.token = $("#api-token").value.trim();
      persist(CONN_KEY, connection);
      checkHealth(true);
    });

    $("#voice-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = {
        voiceName: $("#voice-name").value.trim() || "LEYRA",
        voiceId: $("#voice-select").value || "",
        language: $("#voice-language").value,
        rate: Number($("#voice-rate").value),
        pitch: Number($("#voice-pitch").value),
        style: $("#voice-style").value,
        expressivePauses: $("#voice-pauses").checked,
        autoSpeak: $("#voice-autospeak").checked,
        bargeIn: $("#voice-barge").checked
      };
      try {
        const data = await api("/v1/voice", { method: "PUT", body: payload });
        Voice.apply(data.settings);
        $("#voice-feedback").className = "form-feedback success";
        $("#voice-feedback").textContent = "Voz guardada en el servidor.";
        toast("Configuración de voz guardada.", "success");
      } catch (error) {
        $("#voice-feedback").className = "form-feedback error";
        $("#voice-feedback").textContent = error.message;
      }
    });
    $("#voice-rate").addEventListener("input", (event) => { $("#voice-rate-out").textContent = Number(event.target.value).toFixed(2); });
    $("#voice-pitch").addEventListener("input", (event) => { $("#voice-pitch-out").textContent = Number(event.target.value).toFixed(2); });
    $("#voice-language").addEventListener("change", (event) => { Voice.settings.language = event.target.value; Voice.loadVoices(); });
    $("#voice-test").addEventListener("click", () => {
      Voice.settings.rate = Number($("#voice-rate").value);
      Voice.settings.pitch = Number($("#voice-pitch").value);
      Voice.settings.language = $("#voice-language").value;
      Voice.speak(`Hola, soy ${$("#voice-name").value || "LEYRA"}. Así suena mi voz con la configuración actual.`);
    });

    $("#memory-export").addEventListener("click", async () => {
      try {
        const data = await api("/v1/memory/export");
        downloadText(`leyra-memoria-${Date.now()}.json`, JSON.stringify(data, null, 2), "application/json");
      } catch (error) { toast("No se pudo exportar la memoria.", "error", error.message); }
    });
    $("#memory-purge").addEventListener("click", async () => {
      if (!window.confirm("¿Borrar todos los recuerdos guardados? Esta acción no se puede deshacer.")) return;
      try {
        const data = await api("/v1/memory?limit=500");
        for (const item of data.memories || []) await api(`/v1/memory/${item.id}`, { method: "DELETE" });
        toast("Memoria borrada.", "success");
        await SettingsView.loadPrivacy();
      } catch (error) { toast("No se pudo borrar la memoria.", "error", error.message); }
    });

    // Copy buttons inside rendered code blocks
    document.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-copy]");
      if (!button) return;
      const code = document.getElementById(button.dataset.copy);
      if (!code) return;
      await copyText(code.textContent || "");
      button.textContent = "Copiado";
      setTimeout(() => { button.textContent = "Copiar"; }, 1500);
    });
  }

  /* ------------------------------------------------------------------ *
   * Boot
   * ------------------------------------------------------------------ */
  async function boot() {
    applyPrefs();
    syncPrefControls();
    Particles.start();
    Voice.init();
    AgentsView.render();
    TasksView.render();
    bindNavigation();
    bindComposer();
    bindSuggestionsAndMisc();

    const health = await checkHealth();
    if (health) {
      await Promise.all([
        SettingsView.loadModels().catch(() => null),
        loadPinnedRail(),
        refreshBadges()
      ]);
    }

    const { route, param } = parseHash();
    showRoute(route, param);

    setInterval(() => { checkHealth(); }, 60000);
    setInterval(() => { if (!state.busy && !Voice.speaking && core.state !== "offline") setCoreState("idle"); }, 30000);
  }

  function setDiagnosticsBadge(status) {
    const badge = $("#diag-dot");
    if (!badge) return;
    badge.textContent = ({ ok: "OK", degraded: "!", unavailable: "—", error: "×" })[status] || "—";
    badge.className = `badge dot-badge ${status}`;
  }

  async function refreshBadges() {
    try {
      const data = await api("/v1/tools");
      state.tools = data.tools || [];
      const ready = state.tools.filter((tool) => tool.available).length;
      $("#tools-count").textContent = `${ready}/${state.tools.length}`;
    } catch { /* the badge simply stays unknown */ }
    try {
      const data = await api("/v1/apps");
      state.apps = data;
      $("#apps-count").textContent = String((data.linked || []).filter((link) => link.enabled).length);
    } catch { /* ignored */ }
    try {
      const report = await api("/v1/diagnostics");
      state.diagnostics = report;
      setDiagnosticsBadge(report.status);
    } catch { /* ignored */ }
  }

  async function loadPinnedRail() {
    try {
      const data = await api("/v1/conversations?limit=100");
      HistoryView.items = data.conversations || [];
      HistoryView.renderPinned();
    } catch { /* silent: the rail simply stays without pinned items */ }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
