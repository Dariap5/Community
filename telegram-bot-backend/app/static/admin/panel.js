const state = {
    currentStepId: null,
    currentStep: null,
    settingsMap: {},
    dragMessageId: null,
    dragButtonId: null,
};

function setStepEditorStatus(text, isError = false) {
    const el = document.getElementById("stepEditorStatus");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("text-red-700", isError);
    el.classList.toggle("text-slate-600", !isError);
}

async function api(path, options = {}) {
    const response = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
    }
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
        return response.json();
    }
    return response.text();
}

function bindTabs() {
    const buttons = document.querySelectorAll(".tab-btn");
    buttons.forEach((btn) => {
        btn.addEventListener("click", async() => {
            const tab = btn.dataset.tab;
            buttons.forEach((b) => b.classList.remove("bg-slate-900", "text-white"));
            btn.classList.add("bg-slate-900", "text-white");

            document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.add("hidden"));
            document.getElementById(`tab-${tab}`).classList.remove("hidden");

            if (tab === "funnels") await loadFunnels();
            if (tab === "products") await loadProducts();
            if (tab === "tracks") await loadTracks();
            if (tab === "analytics") await loadAnalytics();
            if (tab === "settings") await loadSettings();
        });
    });
}

function renderCard(title, body, controls = "") {
    return `<div class="border rounded-xl p-3 bg-slate-50"><h3 class="font-semibold mb-2">${title}</h3><div class="text-sm text-slate-700 space-y-1">${body}</div><div class="mt-3 flex gap-2 flex-wrap">${controls}</div></div>`;
}

async function loadFunnels() {
    const data = await api("/admin/api/funnels");
    const root = document.getElementById("funnelsGrid");
    root.innerHTML = "";

    for (const funnel of data.items) {
        const counts = (funnel.step_counts || [])
            .map((x) => `Шаг ${x.step_order}: <b>${x.users}</b>`)
            .join("<br />");

        const controls = `
      <button class="btn-funnel-toggle px-2 py-1 rounded border text-xs" data-id="${funnel.id}" data-enabled="${funnel.is_enabled}">
        ${funnel.is_enabled ? "Активна" : "Выключена"}
      </button>
      <button class="btn-funnel-copy px-2 py-1 rounded border text-xs" data-id="${funnel.id}">Копировать</button>
      <button class="btn-funnel-archive px-2 py-1 rounded border text-xs text-red-700" data-id="${funnel.id}">Архивировать</button>
      <button class="btn-funnel-steps px-2 py-1 rounded bg-slate-900 text-white text-xs" data-id="${funnel.id}">Редактировать шаги</button>
    `;

        const card = document.createElement("div");
        card.innerHTML = renderCard(
            `${funnel.name}`,
            `Статус: ${funnel.is_archived ? "Архив" : funnel.is_enabled ? "Активна" : "Выключена"}<br/>${counts}`,
            controls,
        );
        root.appendChild(card.firstElementChild);
    }

    root.querySelectorAll(".btn-funnel-toggle").forEach((btn) => {
        btn.addEventListener("click", async() => {
            const id = Number(btn.dataset.id);
            const enabled = btn.dataset.enabled === "true";
            await api(`/admin/api/funnels/${id}`, {
                method: "PATCH",
                body: JSON.stringify({ is_enabled: !enabled }),
            });
            await loadFunnels();
        });
    });

    root.querySelectorAll(".btn-funnel-copy").forEach((btn) => {
        btn.addEventListener("click", async() => {
            await api(`/admin/api/funnels/${Number(btn.dataset.id)}/copy`, { method: "POST" });
            await loadFunnels();
        });
    });

    root.querySelectorAll(".btn-funnel-archive").forEach((btn) => {
        btn.addEventListener("click", async() => {
            if (!confirm("Подтвердите архивирование воронки")) return;
            await api(`/admin/api/funnels/${Number(btn.dataset.id)}/archive`, { method: "POST" });
            await loadFunnels();
        });
    });

    root.querySelectorAll(".btn-funnel-steps").forEach((btn) => {
        btn.addEventListener("click", async() => {
            const funnelId = Number(btn.dataset.id);
            const steps = await api(`/admin/api/funnels/${funnelId}/steps`);
            alert(`Шагов в воронке: ${steps.items.length}. Для редактирования укажите step_id в разделе "Редактор шага".`);
        });
    });
}

async function loadStep() {
    const stepId = Number(document.getElementById("stepIdInput").value || "0");
    if (!stepId) return;
    try {
        const step = await api(`/admin/api/steps/${stepId}`);
        state.currentStepId = stepId;
        state.currentStep = step;

        const metaEl = document.getElementById("loadedStepMeta");
        if (metaEl) {
            metaEl.textContent = `Загружен шаг #${step.id} (воронка ${step.funnel_id}, порядок ${step.step_order}, key: ${step.step_key || "-"})`;
        }

        const enabledToggle = document.getElementById("stepEnabledToggle");
        if (enabledToggle) {
            enabledToggle.checked = Boolean(step.is_enabled);
        }

        const messagesData = await api(`/admin/api/steps/${stepId}/messages`);
        const messagesRoot = document.getElementById("messagesList");
        const messageTypes = ["text", "photo", "document", "video", "video_note", "voice"];
        const parseModes = ["HTML", "Markdown"];

        messagesRoot.innerHTML = messagesData.items
            .map(
                (m) => `
      <div class="border rounded-lg p-2 text-sm" draggable="true" data-message-id="${m.id}">
        <div class="font-medium">#${m.message_order} 
          <select class="msg-type border rounded p-1" data-id="${m.id}">
            ${messageTypes.map(t => `<option ${t === m.message_type ? 'selected' : ''}>${t}</option>`).join('')}
          </select>
        </div>
        <textarea class="w-full mt-1 border rounded p-1 msg-text" data-id="${m.id}" placeholder="Текст сообщения">${m.content_text || ""}</textarea>
        <div class="grid grid-cols-4 gap-2 mt-1">
          <input class="border rounded p-1 msg-file" data-id="${m.id}" value="${m.content_file || ""}" placeholder="file id" />
          <input class="border rounded p-1 msg-caption" data-id="${m.id}" value="${m.caption || ""}" placeholder="caption" />
          <select class="border rounded p-1 msg-parse" data-id="${m.id}">
            ${parseModes.map(p => `<option ${p === m.parse_mode ? 'selected' : ''}>${p}</option>`).join('')}
          </select>
          <div class="grid grid-cols-2 gap-1">
            <input class="border rounded p-1 msg-delay" data-id="${m.id}" value="${m.delay_after_seconds}" type="number" min="0" placeholder="delay" />
            <button class="msg-del border rounded text-red-700 text-xs">Del</button>
          </div>
        </div>
      </div>`,
            )
            .join("");

        if (!messagesData.items.length) {
            messagesRoot.innerHTML = '<div class="text-xs text-slate-500">Субсообщений пока нет. Нажмите "Добавить".</div>';
        }

        const buttonsData = await api(`/admin/api/steps/${stepId}/buttons`);
        const buttonsRoot = document.getElementById("buttonsList");
        const buttonTypes = ["url", "callback", "payment"];
        
        buttonsRoot.innerHTML = buttonsData.items
            .map(
                (b) => `
      <div class="border rounded-lg p-2 text-sm" draggable="true" data-button-id="${b.id}">
        <input class="w-full border rounded p-1 btn-text" data-id="${b.id}" value="${b.text}" placeholder="Текст кнопки" />
        <div class="grid grid-cols-3 gap-2 mt-1">
          <select class="border rounded p-1 btn-type" data-id="${b.id}">
            ${buttonTypes.map(t => `<option ${t === b.button_type ? 'selected' : ''}>${t}</option>`).join('')}
          </select>
          <input class="border rounded p-1 btn-value" data-id="${b.id}" value="${b.value}" placeholder="URL/callback" />
          <button class="btn-del border rounded text-red-700 text-xs">Del</button>
        </div>
      </div>`,
            )
            .join("");

        if (!buttonsData.items.length) {
            buttonsRoot.innerHTML = '<div class="text-xs text-slate-500">Кнопок пока нет. Нажмите "Добавить".</div>';
        }

        setStepEditorStatus(`Шаг ${stepId} загружен`);

        bindStepAutosave();
        bindDnDReorder();
    } catch (error) {
        setStepEditorStatus(`Ошибка загрузки шага: ${String(error.message || error)}`, true);
        alert(`Не удалось загрузить шаг: ${String(error.message || error)}`);
    }
}

function bindDnDReorder() {
    const messageCards = Array.from(document.querySelectorAll("[data-message-id]"));
    messageCards.forEach((card) => {
        card.addEventListener("dragstart", () => {
            state.dragMessageId = Number(card.dataset.messageId);
        });
        card.addEventListener("dragover", (e) => e.preventDefault());
        card.addEventListener("drop", async() => {
            if (!state.dragMessageId) return;
            const target = Number(card.dataset.messageId);
            const ids = messageCards.map((n) => Number(n.dataset.messageId));
            const from = ids.indexOf(state.dragMessageId);
            const to = ids.indexOf(target);
            if (from >= 0 && to >= 0 && from !== to) {
                ids.splice(from, 1);
                ids.splice(to, 0, state.dragMessageId);
                await api("/admin/api/messages/reorder", { method: "POST", body: JSON.stringify({ ids }) });
                await loadStep();
            }
            state.dragMessageId = null;
        });
    });

    const buttonCards = Array.from(document.querySelectorAll("[data-button-id]"));
    buttonCards.forEach((card) => {
        card.addEventListener("dragstart", () => {
            state.dragButtonId = Number(card.dataset.buttonId);
        });
        card.addEventListener("dragover", (e) => e.preventDefault());
        card.addEventListener("drop", async() => {
            if (!state.dragButtonId) return;
            const target = Number(card.dataset.buttonId);
            const ids = buttonCards.map((n) => Number(n.dataset.buttonId));
            const from = ids.indexOf(state.dragButtonId);
            const to = ids.indexOf(target);
            if (from >= 0 && to >= 0 && from !== to) {
                ids.splice(from, 1);
                ids.splice(to, 0, state.dragButtonId);
                await api("/admin/api/buttons/reorder", { method: "POST", body: JSON.stringify({ ids }) });
                await loadStep();
            }
            state.dragButtonId = null;
        });
    });
}

function bindStepAutosave() {
    // Message text, file, caption, delay, parse mode, type auto-save
    document.querySelectorAll(".msg-text, .msg-file, .msg-delay, .msg-caption, .msg-parse, .msg-type").forEach((el) => {
        el.addEventListener("blur", async() => {
            const id = Number(el.dataset.id);
            const box = el.closest("[data-message-id]");
            const text = box.querySelector(".msg-text").value;
            const file = box.querySelector(".msg-file").value;
            const delay = Number(box.querySelector(".msg-delay").value || "0");
            const caption = box.querySelector(".msg-caption").value;
            const parse_mode = box.querySelector(".msg-parse").value;
            const message_type = box.querySelector(".msg-type").value;
            
            try {
                await api(`/admin/api/messages/${id}`, {
                    method: "PATCH",
                    body: JSON.stringify({ 
                        content_text: text, 
                        content_file: file, 
                        delay_after_seconds: delay,
                        caption: caption,
                        parse_mode: parse_mode,
                        message_type: message_type,
                    }),
                });
            } catch (error) {
                setStepEditorStatus(`Ошибка сохранения: ${String(error.message || error)}`, true);
            }
        });
    });

    document.querySelectorAll(".msg-del").forEach((el) => {
        el.addEventListener("click", async() => {
            if (!confirm("Удалить субсообщение?")) return;
            await api(`/admin/api/messages/${Number(el.closest("[data-message-id]").dataset.messageId)}`, { method: "DELETE" });
            await loadStep();
        });
    });

    // Button fields auto-save
    document.querySelectorAll(".btn-text, .btn-type, .btn-value").forEach((el) => {
        el.addEventListener("blur", async() => {
            const id = Number(el.dataset.id);
            const box = el.closest(".border");
            const text = box.querySelector(".btn-text").value;
            const button_type = box.querySelector(".btn-type").value;
            const value = box.querySelector(".btn-value").value;
            try {
                await api(`/admin/api/buttons/${id}`, {
                    method: "PATCH",
                    body: JSON.stringify({ text, button_type, value }),
                });
            } catch (error) {
                setStepEditorStatus(`Ошибка сохранения кнопки: ${String(error.message || error)}`, true);
            }
        });
    });

    document.querySelectorAll(".btn-del").forEach((el) => {
        el.addEventListener("click", async() => {
            if (!confirm("Удалить кнопку?")) return;
            await api(`/admin/api/buttons/${Number(el.closest("[data-button-id]").dataset.buttonId)}`, { method: "DELETE" });
            await loadStep();
        });
    });
}

async function loadProducts() {
    const data = await api("/admin/api/products");
    const root = document.getElementById("productsList");
    root.innerHTML = data.items
        .map(
            (p) => `
      <div class="border rounded-xl p-3 text-sm">
        <div class="flex justify-between"><b>${p.name}</b><span>${p.price} ₽</span></div>
        <div class="text-slate-600">${p.description || ""}</div>
        <div class="grid md:grid-cols-2 gap-2 mt-2">
          <input class="border rounded p-2 prod-name" data-id="${p.id}" value="${p.name}" />
          <input class="border rounded p-2 prod-price" data-id="${p.id}" value="${p.price}" />
          <input class="border rounded p-2 prod-pay" data-id="${p.id}" value="${p.payment_url || ""}" />
          <input class="border rounded p-2 prod-access" data-id="${p.id}" value="${p.access_payload || ""}" />
        </div>
        <div class="mt-2 flex gap-2">
          <button class="prod-save px-2 py-1 rounded border" data-id="${p.id}">Сохранить</button>
          <button class="prod-archive px-2 py-1 rounded border text-red-700" data-id="${p.id}">Архивировать</button>
        </div>
      </div>`,
        )
        .join("");

    root.querySelectorAll(".prod-save").forEach((btn) => {
        btn.addEventListener("click", async() => {
            const id = Number(btn.dataset.id);
            const box = btn.closest(".border");
            await api(`/admin/api/products/${id}`, {
                method: "PATCH",
                body: JSON.stringify({
                    name: box.querySelector(".prod-name").value,
                    price: Number(box.querySelector(".prod-price").value || "0"),
                    payment_url: box.querySelector(".prod-pay").value,
                    access_payload: box.querySelector(".prod-access").value,
                }),
            });
            await loadProducts();
        });
    });

    root.querySelectorAll(".prod-archive").forEach((btn) => {
        btn.addEventListener("click", async() => {
            if (!confirm("Архивировать продукт?")) return;
            await api(`/admin/api/products/${Number(btn.dataset.id)}/archive`, { method: "POST" });
            await loadProducts();
        });
    });
}

async function loadTracks() {
    const data = await api("/admin/api/tracks");
    const root = document.getElementById("tracksList");
    root.innerHTML = data.items
        .map(
            (t) => `
      <div class="border rounded-xl p-3 text-sm">
        <div class="flex items-center justify-between">
          <input class="track-title border rounded p-2 w-full" data-id="${t.id}" value="${t.title}" />
          <button class="track-del ml-2 px-2 py-1 border rounded text-red-700" data-id="${t.id}">Удалить</button>
        </div>
        <textarea class="track-payload mt-2 w-full border rounded p-2 h-24" data-id="${t.id}">${JSON.stringify(t.messages_payload || [], null, 2)}</textarea>
        <button class="track-save mt-2 px-2 py-1 border rounded" data-id="${t.id}">Сохранить</button>
      </div>`,
        )
        .join("");

    root.querySelectorAll(".track-save").forEach((btn) => {
        btn.addEventListener("click", async() => {
            const id = Number(btn.dataset.id);
            const box = btn.closest(".border");
            let payload = [];
            try {
                payload = JSON.parse(box.querySelector(".track-payload").value || "[]");
            } catch {
                alert("messages_payload должен быть валидным JSON");
                return;
            }
            await api(`/admin/api/tracks/${id}`, {
                method: "PATCH",
                body: JSON.stringify({ title: box.querySelector(".track-title").value, messages_payload: payload }),
            });
            await loadTracks();
        });
    });

    root.querySelectorAll(".track-del").forEach((btn) => {
        btn.addEventListener("click", async() => {
            if (!confirm("Удалить трек?")) return;
            await api(`/admin/api/tracks/${Number(btn.dataset.id)}`, { method: "DELETE" });
            await loadTracks();
        });
    });
}

async function loadUsers() {
    const q = document.getElementById("usersSearch").value;
    const tag = document.getElementById("usersTagFilter").value;
    const step = document.getElementById("usersStepFilter").value;
    const paidOnly = document.getElementById("usersPaidOnly").checked;

    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (tag) params.set("tag", tag);
    if (step) params.set("step_id", step);
    if (paidOnly) params.set("paid_only", "true");

    const data = await api(`/admin/api/users?${params.toString()}`);
    const root = document.getElementById("usersTable");
    root.innerHTML = `
    <table class="w-full text-sm border-collapse">
      <thead><tr class="bg-slate-50"><th class="p-2 text-left">ID</th><th class="p-2 text-left">Имя</th><th class="p-2 text-left">Username</th><th class="p-2 text-left">Источник</th><th class="p-2 text-left">Теги</th></tr></thead>
      <tbody>
        ${data.items
          .map(
            (u) => `<tr class="border-t cursor-pointer user-row" data-id="${u.id}">
              <td class="p-2">${u.telegram_id}</td>
              <td class="p-2">${u.first_name || ""}</td>
              <td class="p-2">${u.username || ""}</td>
              <td class="p-2">${u.source_deeplink || ""}</td>
              <td class="p-2">${(u.tags || []).join(", ")}</td>
            </tr>`,
          )
          .join("")}
      </tbody>
    </table>
  `;

  root.querySelectorAll(".user-row").forEach((row) => {
    row.addEventListener("click", async () => {
      const card = await api(`/admin/api/users/${Number(row.dataset.id)}`);
      renderUserCard(card);
    });
  });
}

function renderUserCard(data) {
  const root = document.getElementById("userCard");
  root.innerHTML = `
    <div class="space-y-2">
      <div><b>${data.user.first_name || ""}</b> (@${data.user.username || "-"})</div>
      <div>Telegram ID: ${data.user.telegram_id}</div>
      <div>Теги: ${data.tags.join(", ") || "-"}</div>
      <div>Покупки: ${data.purchases.map((p) => `${p.product} (${p.status})`).join(", ") || "-"}</div>
      <div>Текущий шаг: ${data.funnel_state.current_step_id || "-"}</div>
    </div>
  `;
}

async function loadAnalytics() {
  const data = await api("/admin/api/analytics");
  document.getElementById("analyticsFunnels").innerHTML = data.funnels
    .map(
      (f) => `
      <div class="border rounded-xl p-3">
        <h3 class="font-semibold mb-2">${f.name}</h3>
        <div class="text-sm space-y-1">
          ${f.steps
            .map((s) => `Шаг ${s.step_order}: ${s.reached} пользователей${s.conversion == null ? "" : `, конверсия ${s.conversion}%`}`)
            .join("<br />")}
        </div>
      </div>`,
    )
    .join("");

  document.getElementById("analyticsButtons").innerHTML = `
    <h3 class="font-semibold">CTR кнопок</h3>
    <div class="text-sm">${data.buttons.map((b) => `${b.text}: ${b.clicks}`).join("<br />")}</div>
  `;

  document.getElementById("analyticsFinance").innerHTML = `
    <h3 class="font-semibold">Финансы</h3>
    <div class="text-sm">${data.finance
      .map((f) => `${f.product}: выручка ${f.revenue} ₽, покупок ${f.purchases}, средний чек ${f.avg_check} ₽`)
      .join("<br />")}</div>
  `;
}

async function loadSettings() {
  const data = await api("/admin/api/settings");
  const root = document.getElementById("settingsForm");

  const keys = [
    "deeplink_guide",
    "deeplink_product",
    "support_chat_id",
    "calendly_url",
    "offer_content",
    "privacy_content",
    "payment_api_key",
    "payment_webhook_secret",
    "bot_token",
    "admin_test_telegram_id",
  ];

  state.settingsMap = {};
  for (const item of data.items) state.settingsMap[item.key] = item.value_text || "";

  root.innerHTML = keys
    .map(
      (key) => `
      <label class="text-sm font-medium">
        ${key}
        <textarea data-key="${key}" class="settings-input mt-1 w-full border rounded-lg px-3 py-2 h-20">${state.settingsMap[key] || ""}</textarea>
      </label>
    `,
    )
    .join("");

  root.querySelectorAll(".settings-input").forEach((input) => {
    input.addEventListener("blur", async () => {
      await api("/admin/api/settings", {
        method: "POST",
        body: JSON.stringify({ key: input.dataset.key, value_text: input.value }),
      });
    });
  });
}

function bindGlobalActions() {
  document.getElementById("newFunnelBtn").addEventListener("click", async () => {
    await api("/admin/api/funnels", { method: "POST", body: JSON.stringify({ name: "Новая воронка" }) });
    await loadFunnels();
  });

  document.getElementById("loadStepBtn").addEventListener("click", loadStep);

  document.getElementById("createStepBtn").addEventListener("click", async () => {
    const funnelId = Number(document.getElementById("newStepFunnelId").value || "0");
    const stepOrder = Number(document.getElementById("newStepOrder").value || "1");
    const stepKey = document.getElementById("newStepKey").value.trim() || null;
    if (!funnelId) {
      setStepEditorStatus("Укажите funnel_id для создания шага", true);
      return;
    }

    try {
      const created = await api("/admin/api/steps", {
        method: "POST",
        body: JSON.stringify({
          funnel_id: funnelId,
          step_order: stepOrder,
          step_key: stepKey,
          is_enabled: true,
          delay_unit: "seconds",
          delay_before_seconds: 0,
          trigger_conditions: {},
        }),
      });
      document.getElementById("stepIdInput").value = String(created.id);
      setStepEditorStatus(`Шаг создан: ID ${created.id}`);
      await loadStep();
    } catch (error) {
      setStepEditorStatus(`Ошибка создания шага: ${String(error.message || error)}`, true);
    }
  });

  document.getElementById("saveStepStateBtn").addEventListener("click", async () => {
    if (!state.currentStepId) {
      setStepEditorStatus("Сначала загрузите шаг", true);
      return;
    }
    const isEnabled = document.getElementById("stepEnabledToggle").checked;
    try {
      await api(`/admin/api/steps/${state.currentStepId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_enabled: isEnabled }),
      });
      setStepEditorStatus(`Статус шага сохранен: ${isEnabled ? "активен" : "выключен"}`);
    } catch (error) {
      setStepEditorStatus(`Ошибка сохранения статуса шага: ${String(error.message || error)}`, true);
    }
  });

  document.getElementById("newMessageBtn").addEventListener("click", async () => {
    if (!state.currentStepId) return alert("Сначала загрузите шаг");
    await api("/admin/api/messages", {
      method: "POST",
      body: JSON.stringify({ step_id: state.currentStepId, message_order: 999, message_type: "text", content_text: "" }),
    });
    await loadStep();
  });

  document.getElementById("newButtonBtn").addEventListener("click", async () => {
    if (!state.currentStepId) return alert("Сначала загрузите шаг");
    await api("/admin/api/buttons", {
      method: "POST",
      body: JSON.stringify({ step_id: state.currentStepId, text: "Кнопка", button_type: "url", value: "https://example.com" }),
    });
    await loadStep();
  });

  document.getElementById("sendStepTestBtn").addEventListener("click", async () => {
    if (!state.currentStepId) return alert("Сначала загрузите шаг");
    try {
      await api(`/admin/api/steps/${state.currentStepId}/send-test`, { method: "POST" });
      setStepEditorStatus("Тест-отправка выполнена (сообщение отправлено вам в Telegram)");
      alert("Тест-отправка выполнена! Проверьте Telegram - сообщение должно содержать все кнопки точно как в боте.");
    } catch (error) {
      setStepEditorStatus(`Тест-отправка не выполнена: ${String(error.message || error)}`, true);
      alert(`Ошибка тест-отправки: ${String(error.message || error)}`);
    }
  });

  document.getElementById("newProductBtn").addEventListener("click", async () => {
    await api("/admin/api/products", { method: "POST", body: JSON.stringify({ name: "Новый продукт", price: 0 }) });
    await loadProducts();
  });

  document.getElementById("newTrackBtn").addEventListener("click", async () => {
    await api("/admin/api/tracks", { method: "POST", body: JSON.stringify({ title: "Новый трек", messages_payload: [] }) });
    await loadTracks();
  });

  document.getElementById("usersLoadBtn").addEventListener("click", loadUsers);

  document.getElementById("usersExportBtn").addEventListener("click", () => {
    const tag = document.getElementById("usersTagFilter").value;
    const qp = tag ? `?tag=${encodeURIComponent(tag)}` : "";
    window.open(`/admin/api/users/export${qp}`, "_blank");
  });

  document.getElementById("broadcastPreviewBtn").addEventListener("click", async () => {
    const tags = document
      .getElementById("broadcastTags")
      .value.split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const preview = await api("/admin/api/broadcasts/preview", {
      method: "POST",
      body: JSON.stringify({ segment_tags: tags, segment_logic: "OR" }),
    });
    alert(`Получателей: ${preview.audience_count}`);
  });

  document.getElementById("broadcastSendBtn").addEventListener("click", async () => {
    if (!confirm("Подтвердите отправку рассылки")) return;
    const tags = document
      .getElementById("broadcastTags")
      .value.split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const content_text = document.getElementById("broadcastText").value;
    const result = await api("/admin/api/broadcasts/send", {
      method: "POST",
      body: JSON.stringify({
        title: "Рассылка из панели",
        segment_tags: tags,
        segment_logic: "OR",
        content_type: "text",
        content_text,
      }),
    });
    alert(`Поставлено в очередь. Получателей: ${result.audience_count}`);
  });

  document.getElementById("logoutBtn").addEventListener("click", async () => {
    await api("/admin/logout", { method: "POST" });
    window.location.href = "/admin/login";
  });

  // HTML editor with Telegram-compatible preview
  const htmlEditor = document.getElementById("htmlEditor");
  const htmlPreview = document.getElementById("htmlPreview");
  
  function updatePreview() {
    const html = htmlEditor.value;
    // Sanitize to Telegram-supported tags only
    const sanitized = html
      .replace(/<[^/][^>]*>/g, (tag) => {
        const allowed = ["<b>", "<i>", "<u>", "<s>", "<a ", "<code>", "<blockquote>", "<em>", "<strong>"];
        return allowed.some(t => tag.startsWith(t)) ? tag : "";
      })
      .replace(/<\/[^>]*>/g, (tag) => {
        const allowed = ["</b>", "</i>", "</u>", "</s>", "</a>", "</code>", "</blockquote>", "</em>", "</strong>"];
        return allowed.includes(tag) ? tag : "";
      });
    
    htmlPreview.innerHTML = sanitized || "<em class='text-slate-400'>Пусто</em>";
    
    if (sanitized !== html) {
      htmlPreview.className = "min-h-40 border-2 border-yellow-400 rounded-lg p-3 bg-yellow-50";
      htmlPreview.innerHTML += '<div class="text-xs text-yellow-700 mt-2">⚠️ Некоторые теги удалены - Telegram не их поддерживает. Поддержка: &lt;b&gt;, &lt;i&gt;, &lt;u&gt;, &lt;s&gt;, &lt;a&gt;, &lt;code&gt;, &lt;blockquote&gt;</div>';
    } else {
      htmlPreview.className = "min-h-40 border rounded-lg p-3 bg-slate-50";
    }
  }
  
  htmlEditor.addEventListener("input", updatePreview);

  document.getElementById("themeToggle").addEventListener("click", () => {
    document.body.classList.toggle("bg-slate-900");
    document.body.classList.toggle("text-slate-100");
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  bindTabs();
  bindGlobalActions();
  await loadFunnels();
});