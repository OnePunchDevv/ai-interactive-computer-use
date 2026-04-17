"use strict";

const API = "/api/v1";

let sessions = [];
let activeSessionId = null;
let eventSource = null;
let isAgentRunning = false;

const sessionList      = document.getElementById("session-list");
const btnNewSession    = document.getElementById("btn-new-session");
const vncPlaceholder   = document.getElementById("vnc-placeholder");
const vncFrame         = document.getElementById("vnc-frame");
const emptyState       = document.getElementById("empty-state");
const chatUi           = document.getElementById("chat-ui");
const chatMessages     = document.getElementById("chat-messages");
const chatSessionTitle = document.getElementById("chat-session-title");
const chatStatusDot    = document.getElementById("chat-status-dot");
const chatStatusLabel  = document.getElementById("chat-status-label");
const msgInput         = document.getElementById("msg-input");
const btnSend          = document.getElementById("btn-send");

async function apiFetch(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.status === 204 ? null : res.json();
}

async function loadSessions() {
  const data = await apiFetch("/sessions");
  sessions = data.sessions;
  renderSessionList();
}

async function createSession() {
  const title = `Session ${new Date().toLocaleTimeString()}`;
  const session = await apiFetch("/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
  sessions.unshift(session);
  renderSessionList();
  selectSession(session.id);
}

async function deleteSession(id, e) {
  e.stopPropagation();
  if (!confirm("Delete this session and all its history?")) return;
  await apiFetch(`/sessions/${id}`, { method: "DELETE" });
  sessions = sessions.filter(s => s.id !== id);
  if (activeSessionId === id) {
    activeSessionId = null;
    closeEventSource();
    showEmptyState();
  }
  renderSessionList();
}

function renderSessionList() {
  sessionList.innerHTML = "";
  sessions.forEach(s => {
    const el = document.createElement("div");
    el.className = "session-item" + (s.id === activeSessionId ? " active" : "");
    el.dataset.id = s.id;

    const dot = `<span class="status-dot ${s.status}"></span>`;
    const time = new Date(s.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    el.innerHTML = `
      <div class="session-title">${escHtml(s.title)}</div>
      <div class="session-meta">${dot}<span>${s.status}</span><span>·</span><span>${time}</span></div>
      <button class="btn-delete-session" title="Delete session">×</button>
    `;
    el.querySelector(".btn-delete-session").addEventListener("click", e => deleteSession(s.id, e));
    el.addEventListener("click", () => selectSession(s.id));
    sessionList.appendChild(el);
  });
}

async function selectSession(id) {
  if (activeSessionId === id) return;
  activeSessionId = id;
  closeEventSource();
  renderSessionList();
  showChatUi();

  const session = sessions.find(s => s.id === id);
  if (!session) return;

  chatSessionTitle.textContent = session.title;
  setStatus(session.status);

  await loadVnc(id);

  chatMessages.innerHTML = "";
  const { messages } = await apiFetch(`/sessions/${id}/messages`);
  messages.forEach(appendMessageFromDb);

  openEventSource(id);
  setInputEnabled(session.status === "idle");
}

async function loadVnc(sessionId) {
  try {
    const info = await apiFetch(`/sessions/${sessionId}/vnc`);
    if (!info.novnc_url) {
      vncFrame.style.display = "none";
      vncPlaceholder.style.display = "flex";
      vncPlaceholder.textContent = "VNC not available for this session";
      return;
    }
    vncPlaceholder.style.display = "flex";
    vncPlaceholder.textContent = "Starting desktop…";
    vncFrame.style.display = "none";

    let loaded = false;
    const cleanup = () => {
      vncFrame.removeEventListener("load", handleLoad);
      vncFrame.removeEventListener("error", handleError);
    };
    const handleLoad = () => {
      loaded = true;
      vncFrame.style.display = "block";
      vncPlaceholder.style.display = "none";
      cleanup();
    };
    const handleError = () => {
      cleanup();
      if (!loaded) {
        vncPlaceholder.textContent = "Desktop unavailable — check container logs";
      }
    };

    vncFrame.addEventListener("load", handleLoad);
    vncFrame.addEventListener("error", handleError);
    vncFrame.src = info.novnc_url + (info.novnc_url.includes("?") ? "&" : "?") + "t=" + Date.now();
    setTimeout(() => {
      if (!loaded && activeSessionId === sessionId) {
        vncPlaceholder.textContent = "Starting desktop…";
      }
    }, 3000);
  } catch {
    vncFrame.style.display = "none";
    vncPlaceholder.style.display = "flex";
    vncPlaceholder.textContent = "Could not load VNC info";
  }
}

function openEventSource(sessionId) {
  closeEventSource();
  eventSource = new EventSource(`${API}/sessions/${sessionId}/stream`);

  eventSource.onmessage = e => {
    try {
      handleSseEvent(JSON.parse(e.data));
    } catch {
      // ignore malformed events
    }
  };

  eventSource.onerror = () => {
    console.warn("SSE connection lost — browser will reconnect");
  };
}

function closeEventSource() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function handleSseEvent(event) {
  switch (event.event) {
    case "text_delta":
      appendOrMergeAssistantText(event.data.text || "");
      break;
    case "tool_use":
      appendToolUse(event.data);
      break;
    case "tool_result":
      appendToolResult(event.data);
      break;
    case "status":
      setStatus(event.data.status);
      updateSessionStatus(event.data.status);
      if (event.data.status === "running") {
        setInputEnabled(false);
        showTypingIndicator();
      } else {
        removeTypingIndicator();
        setInputEnabled(true);
      }
      break;
    case "error":
      appendErrorMessage(event.data.message || "Unknown error");
      setInputEnabled(true);
      break;
    case "done":
      removeTypingIndicator();
      setInputEnabled(true);
      break;
  }
  scrollToBottom();
}

async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text || !activeSessionId || isAgentRunning) return;

  appendUserMessage(text);
  msgInput.value = "";
  autoResizeTextarea();
  setInputEnabled(false);

  try {
    await apiFetch(`/sessions/${activeSessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content: text }),
    });
  } catch (err) {
    appendErrorMessage(err.message);
    setInputEnabled(true);
  }
}

// Merge consecutive text_delta events into one bubble instead of creating a new element each time
let _lastAssistantEl = null;

function appendUserMessage(text) {
  _lastAssistantEl = null;
  const el = document.createElement("div");
  el.className = "msg msg-user";
  el.innerHTML = `<div class="msg-role">You</div><div>${escHtml(text)}</div>`;
  chatMessages.appendChild(el);
  scrollToBottom();
}

function appendOrMergeAssistantText(text) {
  if (_lastAssistantEl && _lastAssistantEl.dataset.type === "assistant-text") {
    _lastAssistantEl.querySelector(".msg-body").textContent += text;
  } else {
    _lastAssistantEl = document.createElement("div");
    _lastAssistantEl.className = "msg msg-assistant";
    _lastAssistantEl.dataset.type = "assistant-text";
    _lastAssistantEl.innerHTML = `<div class="msg-role">Agent</div><div class="msg-body">${escHtml(text)}</div>`;
    chatMessages.appendChild(_lastAssistantEl);
  }
  scrollToBottom();
}

function appendToolUse(data) {
  _lastAssistantEl = null;
  const el = document.createElement("div");
  el.className = "msg msg-tool-use";
  const inputStr = data.input ? JSON.stringify(data.input, null, 2) : "";
  el.innerHTML = `
    <span class="tool-badge">⚙ ${escHtml(data.tool || "tool")}</span>
    <div class="msg-role">Tool Call</div>
    <pre style="white-space:pre-wrap;overflow:hidden">${escHtml(inputStr)}</pre>
  `;
  chatMessages.appendChild(el);
  scrollToBottom();
}

function appendToolResult(data) {
  _lastAssistantEl = null;
  const el = document.createElement("div");
  el.className = "msg msg-tool-result";
  const content = data.error
    ? `<span style="color:var(--error)">Error: ${escHtml(data.error)}</span>`
    : data.output
      ? `<pre style="white-space:pre-wrap;overflow:hidden">${escHtml(data.output.slice(0, 800))}</pre>`
      : data.has_screenshot
        ? `<em style="color:var(--muted)">Screenshot captured</em>`
        : `<em style="color:var(--muted)">(empty result)</em>`;
  el.innerHTML = `<div class="msg-role">Tool Result</div>${content}`;
  chatMessages.appendChild(el);
  scrollToBottom();
}

function appendErrorMessage(msg) {
  _lastAssistantEl = null;
  const el = document.createElement("div");
  el.className = "msg msg-error";
  el.innerHTML = `<div class="msg-role">Error</div><div>${escHtml(msg)}</div>`;
  chatMessages.appendChild(el);
  scrollToBottom();
}

function appendMessageFromDb(msg) {
  switch (msg.role) {
    case "user":        appendUserMessage(msg.text_preview || ""); break;
    case "assistant":   appendOrMergeAssistantText(msg.text_preview || ""); break;
    case "tool_use":    appendToolUse({ tool: msg.content?.name, input: msg.content?.input }); break;
    case "tool_result": appendToolResult({
      output: msg.content?.output,
      error: msg.content?.error,
      has_screenshot: msg.content?.has_image,
    }); break;
  }
}

let _typingEl = null;

function showTypingIndicator() {
  if (_typingEl) return;
  _typingEl = document.createElement("div");
  _typingEl.className = "typing-indicator";
  _typingEl.innerHTML = "<span></span><span></span><span></span>";
  chatMessages.appendChild(_typingEl);
  scrollToBottom();
}

function removeTypingIndicator() {
  if (_typingEl) {
    _typingEl.remove();
    _typingEl = null;
  }
}

function showEmptyState() {
  emptyState.style.display = "flex";
  chatUi.style.display = "none";
  vncFrame.style.display = "none";
  vncPlaceholder.style.display = "flex";
  vncPlaceholder.textContent = "Select a session to view its desktop";
}

function showChatUi() {
  emptyState.style.display = "none";
  chatUi.style.display = "flex";
}

function setInputEnabled(enabled) {
  isAgentRunning = !enabled;
  msgInput.disabled = !enabled;
  btnSend.disabled = !enabled;
  if (enabled) msgInput.focus();
}

function setStatus(status) {
  chatStatusDot.className = `status-dot ${status}`;
  chatStatusLabel.textContent = status;
}

function updateSessionStatus(status) {
  const session = sessions.find(s => s.id === activeSessionId);
  if (session) {
    session.status = status;
    renderSessionList();
  }
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escHtml(str) {
  const d = document.createElement("div");
  d.textContent = String(str);
  return d.innerHTML;
}

function autoResizeTextarea() {
  msgInput.style.height = "auto";
  msgInput.style.height = Math.min(msgInput.scrollHeight, 120) + "px";
}

btnNewSession.addEventListener("click", createSession);
btnSend.addEventListener("click", sendMessage);
msgInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
msgInput.addEventListener("input", autoResizeTextarea);

(async () => {
  await loadSessions();
  if (sessions.length > 0) selectSession(sessions[0].id);
})();
