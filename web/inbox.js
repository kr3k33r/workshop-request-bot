const $ = (id) => document.getElementById(id);
const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character],
  );
let session = localStorage.getItem("request-bot-session");
if (!session) {
  session = crypto.randomUUID();
  localStorage.setItem("request-bot-session", session);
}
let busy = false;
let pending = null;
let leads = [];
let statuses = {};

async function api(path, payload) {
  const response = await fetch(
    path,
    payload
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      : {},
  );
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "Не удалось выполнить запрос.");
  return data;
}

function renderConversation(data) {
  $("history").replaceChildren();
  for (const message of data.history) {
    const element = document.createElement("div");
    element.className = "bubble " + message.role;
    element.textContent = message.text;
    $("history").append(element);
  }
  $("history").scrollTop = $("history").scrollHeight;
  $("choices").replaceChildren();
  for (const label of data.buttons) {
    const button = document.createElement("button");
    button.textContent = label;
    button.onclick = () => send(label);
    $("choices").append(button);
  }
  $("message").placeholder = {
    service: "Выберите технику выше…",
    description: "Например: не сливает воду, ошибка E20",
    contact: "Телефон, email или @username",
    preferred: "Когда удобно? До 100 символов",
    review: "Проверьте данные и подтвердите",
    done: "Заявка сохранена",
  }[data.step];
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

function setBusy(value) {
  busy = value;
  $("send").disabled = value;
  $("restart").disabled = value;
  $("choices")
    .querySelectorAll("button")
    .forEach((button) => {
      button.disabled = value;
    });
}

async function send(text) {
  if (busy || !text.trim()) return;
  showError("");
  setBusy(true);
  if (!pending || pending.text !== text)
    pending = { session, text, request_id: crypto.randomUUID() };
  try {
    const data = await api("/api/message", pending);
    pending = null;
    renderConversation(data);
    $("message").value = "";
    await refresh();
  } catch (error) {
    showError("Не удалось отправить: " + error.message + " Повторите то же сообщение.");
  } finally {
    setBusy(false);
  }
}

async function refresh() {
  const data = await api("/api/leads");
  leads = data.leads;
  statuses = data.statuses;
  renderLeads();
}

function renderLeads() {
  const filtered = leads.filter(
    (lead) =>
      ($("channel-filter").value === "all" || lead.channel === $("channel-filter").value) &&
      ($("status-filter").value === "all" || lead.status === $("status-filter").value),
  );
  $("count").textContent = filtered.length;
  $("leads").innerHTML = filtered.length
    ? filtered
        .map(
          (lead) => `<article class="lead-card">
    <div class="lead-top"><span>№ ${escapeHTML(lead.id)} · ${new Date(lead.created).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</span><span>${escapeHTML(statuses[lead.status])}</span></div>
    <h3>${escapeHTML(lead.service)}</h3><p>${escapeHTML(lead.description)}</p>
    <div class="lead-meta"><span>↗ ${escapeHTML(lead.contact)}</span><span>◷ ${escapeHTML(lead.preferred)}</span><span>${lead.channel === "telegram" ? "Telegram" : "Браузер"}</span></div>
    <label class="lead-status-label">Статус<select data-id="${escapeHTML(lead.id)}">${Object.entries(
      statuses,
    )
      .map(
        ([key, label]) =>
          `<option value="${key}"${lead.status === key ? " selected" : ""}>${label}</option>`,
      )
      .join("")}</select></label>
    ${lead.channel === "telegram" ? `<small class="delivery-status">${lead.notified ? "Уведомление владельцу отправлено" : "Уведомление ожидает подключения Telegram"}</small>` : ""}
    </article>`,
        )
        .join("")
    : '<div class="empty"><strong>Пока нет обращений</strong>Пройдите диалог и подтвердите заявку или измените фильтр.</div>';
  $("leads")
    .querySelectorAll("select")
    .forEach((select) => {
      select.onchange = async () => {
        select.disabled = true;
        try {
          await api("/api/status", { id: select.dataset.id, status: select.value });
          await refresh();
        } catch (error) {
          showError(error.message);
          renderLeads();
        }
      };
    });
}

async function load() {
  setBusy(true);
  try {
    renderConversation(await api("/api/session?id=" + encodeURIComponent(session)));
    await refresh();
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

$("chat-form").onsubmit = (event) => {
  event.preventDefault();
  send($("message").value);
};
$("restart").onclick = () => send("/start");
$("refresh").onclick = () => refresh().catch((error) => showError(error.message));
$("channel-filter").onchange = renderLeads;
$("status-filter").onchange = renderLeads;
load();
