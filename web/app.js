(() => {
  "use strict";

  const API_BASE_KEY = "mily.web.apiBase";
  const DEFAULT_MODEL = "gpt-6-astra";
  const $ = (id) => document.getElementById(id);
  const state = { messages: [], busy: false, toastTimer: null };
  const ui = {
    conversation: $("conversation"), welcome: $("welcome"), messages: $("messages"),
    form: $("chat-form"), input: $("message-input"), send: $("send-button"),
    count: $("char-count"), dialog: $("settings-dialog"), settingsForm: $("settings-form"),
    apiBase: $("api-base"), feedback: $("settings-feedback"), dot: $("status-dot"),
    topDot: $("top-status-dot"), label: $("connection-label"), detail: $("connection-detail"),
    topStatus: $("top-status"), toast: $("toast")
  };

  function apiBase() {
    return (localStorage.getItem(API_BASE_KEY) || "").trim().replace(/\/+$/, "");
  }

  function endpoint(path) {
    return apiBase() + path;
  }

  function setConnection(online, label, detail) {
    for (const dot of [ui.dot, ui.topDot]) {
      dot.classList.toggle("online", online === true);
      dot.classList.toggle("offline", online === false);
    }
    ui.label.textContent = label;
    ui.detail.textContent = detail;
    ui.topStatus.textContent = label;
  }

  function toast(message) {
    ui.toast.textContent = message;
    ui.toast.classList.add("visible");
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => ui.toast.classList.remove("visible"), 2600);
  }

  async function checkConnection(showFeedback = false) {
    setConnection(null, "Comprobando…", "Consultando el backend");
    try {
      const response = await fetch(endpoint("/health"), { method: "GET", headers: { Accept: "application/json" }, signal: AbortSignal.timeout(7000) });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      if (data.ok === false) throw new Error("El backend reportó un estado no saludable");
      const model = typeof data.model === "string" ? data.model : "modelo configurado";
      setConnection(true, "Servidor disponible", model);
      if (showFeedback) {
        ui.feedback.className = "settings-feedback success";
        ui.feedback.textContent = "Conexión correcta. El servidor respondió a /health.";
      }
      return true;
    } catch (error) {
      setConnection(false, "Sin conexión", "Revisa la URL y el servidor");
      if (showFeedback) {
        ui.feedback.className = "settings-feedback error";
        ui.feedback.textContent = "No se pudo conectar. Comprueba la URL, CORS y que el backend esté activo.";
      }
      return false;
    }
  }

  function addMessage(role, text, options = {}) {
    ui.welcome.hidden = true;
    const row = document.createElement("article");
    row.className = "message" + (role === "user" ? " user" : "") + (options.error ? " error" : "");
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = role === "user" ? "TÚ" : "M";
    const body = document.createElement("div");
    body.className = "message-body";
    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.textContent = role === "user" ? "TÚ" : options.error ? "MILY · AVISO" : "MILY";
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    body.append(meta, paragraph);
    row.append(avatar, body);
    ui.messages.append(row);
    ui.conversation.scrollTop = ui.conversation.scrollHeight;
    return row;
  }

  function addTyping() {
    ui.welcome.hidden = true;
    const row = document.createElement("article");
    row.className = "message";
    row.setAttribute("aria-label", "MILY está pensando");
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "M";
    const body = document.createElement("div");
    body.className = "message-body";
    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.textContent = "MILY · PROCESANDO";
    const dots = document.createElement("div");
    dots.className = "typing";
    dots.innerHTML = "<span></span><span></span><span></span>";
    body.append(meta, dots);
    row.append(avatar, body);
    ui.messages.append(row);
    ui.conversation.scrollTop = ui.conversation.scrollHeight;
    return row;
  }

  function setBusy(busy) {
    state.busy = busy;
    ui.send.disabled = busy;
    ui.input.disabled = busy;
    ui.send.setAttribute("aria-label", busy ? "Esperando respuesta" : "Enviar mensaje");
  }

  async function sendMessage(raw) {
    const text = raw.trim();
    if (!text || state.busy) return;
    state.messages.push({ role: "user", content: text });
    addMessage("user", text);
    ui.input.value = "";
    resizeInput();
    updateCount();
    setBusy(true);
    const typing = addTyping();

    try {
      const response = await fetch(endpoint("/v1/mily/responses"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          model: DEFAULT_MODEL,
          instructions: "Eres MILY, una asistente útil, clara y segura. Responde en el idioma del usuario. No afirmes haber ejecutado acciones que no realizaste.",
          input: state.messages.slice(-20),
          temperature: 0.7,
          maxOutputTokens: 2048
        }),
        signal: AbortSignal.timeout(90000)
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "El servidor respondió con HTTP " + response.status);
      const answer = typeof data.outputText === "string" ? data.outputText : (typeof data.text === "string" ? data.text : "");
      if (!answer.trim()) throw new Error("El servidor respondió, pero no devolvió texto.");
      state.messages.push({ role: "assistant", content: answer });
      addMessage("assistant", answer);
      setConnection(true, "Servidor disponible", typeof data.route === "string" ? data.route : "Respuesta recibida");
    } catch (error) {
      addMessage("assistant", "No pude completar la solicitud. " + (error && error.message ? error.message : "Comprueba el servidor y vuelve a intentarlo."), { error: true });
      setConnection(false, "Error de conexión", "La solicitud no se completó");
    } finally {
      typing.remove();
      setBusy(false);
      ui.input.focus();
    }
  }

  function resizeInput() {
    ui.input.style.height = "auto";
    ui.input.style.height = Math.min(ui.input.scrollHeight, 160) + "px";
  }

  function updateCount() {
    ui.count.textContent = ui.input.value.length + " / 12000";
  }

  function openSettings() {
    ui.apiBase.value = apiBase();
    ui.feedback.textContent = "";
    ui.feedback.className = "settings-feedback";
    ui.dialog.showModal();
  }

  ui.form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(ui.input.value);
  });
  ui.input.addEventListener("input", () => { resizeInput(); updateCount(); });
  ui.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      ui.form.requestSubmit();
    }
  });
  $("new-chat").addEventListener("click", () => {
    state.messages = [];
    ui.messages.replaceChildren();
    ui.welcome.hidden = false;
    ui.input.value = "";
    resizeInput();
    updateCount();
    toast("Conversación nueva");
  });
  $("open-settings").addEventListener("click", openSettings);
  $("top-settings").addEventListener("click", openSettings);
  $("close-settings").addEventListener("click", () => ui.dialog.close());
  $("test-connection").addEventListener("click", async () => {
    const previous = apiBase();
    const candidate = ui.apiBase.value.trim().replace(/\/+$/, "");
    try {
      if (candidate) new URL(candidate);
    } catch (_) {
      ui.feedback.className = "settings-feedback error";
      ui.feedback.textContent = "Introduce una URL válida, incluyendo https:// o http://.";
      return;
    }
    localStorage.setItem(API_BASE_KEY, candidate);
    const ok = await checkConnection(true);
    if (!ok && !candidate) {
      localStorage.setItem(API_BASE_KEY, previous);
    }
  });
  ui.settingsForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const candidate = ui.apiBase.value.trim().replace(/\/+$/, "");
    try {
      if (candidate) new URL(candidate);
    } catch (_) {
      ui.feedback.className = "settings-feedback error";
      ui.feedback.textContent = "Introduce una URL válida, incluyendo https:// o http://.";
      return;
    }
    localStorage.setItem(API_BASE_KEY, candidate);
    ui.dialog.close();
    checkConnection();
    toast("Ajustes guardados");
  });
  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => sendMessage(button.dataset.prompt || ""));
  });

  checkConnection();
})();