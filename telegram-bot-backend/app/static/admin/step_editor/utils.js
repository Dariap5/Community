export const EMULATION_OPTIONS = [
    { value: "new", label: "Новый пользователь", tags: [] },
    { value: "bought_product_1", label: "Купил продукт 1", tags: ["купил_продукт_1", "получил_гайд"] },
    { value: "bought_community", label: "Купил комьюнити", tags: ["купил_продукт_1", "купил_комьюнити"] },
];

const MESSAGE_TYPES = ["text", "photo", "document", "video", "video_note", "voice"];
const BUTTON_ACTIONS = [
    { value: "url", label: "Открыть ссылку", valueType: "text", placeholder: "https://example.com" },
    { value: "pay_product", label: "Оплатить продукт", valueType: "select_product", placeholder: "Выбери продукт" },
    { value: "goto_step", label: "Перейти на шаг", valueType: "select_step", placeholder: "Выбери шаг" },
    { value: "add_tag", label: "Добавить тег", valueType: "text", placeholder: "vip" },
    { value: "open_track", label: "Открыть трек", valueType: "select_track", placeholder: "Выбери трек" },
    { value: "signal", label: "Отправить сигнал", valueType: "text", placeholder: "signal_name" },
];

export function cloneValue(value) {
    return value == null ? value : JSON.parse(JSON.stringify(value));
}

export function generateId() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        return crypto.randomUUID();
    }
    return `id_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function safeText(value) {
    return String(value == null ? "" : value).trim();
}

export function csvToArray(value) {
    return String(value == null ? "" : value)
        .split(/[\n,;]/)
        .map((item) => item.trim())
        .filter(Boolean);
}

export function arrayToCsv(items) {
    return (items || []).map((item) => String(item).trim()).filter(Boolean).join(", ");
}

export function escapeHtml(value) {
    const element = document.createElement("div");
    element.textContent = String(value == null ? "" : value);
    return element.innerHTML;
}

export function formatDelay(value, unit) {
    const amount = Number(value) || 0;
    const suffixMap = {
        seconds: "сек",
        minutes: "мин",
        hours: "час",
        days: "дн",
    };
    return `${amount} ${suffixMap[unit] || unit}`;
}

export function getEmulationTags(value) {
    const option = EMULATION_OPTIONS.find((item) => item.value === value);
    return option ? option.tags : [];
}

export function getBlockIcon(type) {
    const icons = {
        text: "📝",
        photo: "🖼",
        document: "📎",
        video: "🎥",
        video_note: "⭕",
        voice: "🎙",
        buttons: "▢",
    };
    return icons[type] || "•";
}

export function getBlockTitle(type) {
    const labels = {
        text: "Текст",
        photo: "Фото",
        document: "Документ",
        video: "Видео",
        video_note: "Кружочек",
        voice: "Голосовое",
        buttons: "Кнопки",
    };
    return labels[type] || type;
}

export function getActionDefinition(type) {
    return BUTTON_ACTIONS.find((item) => item.value === type) || BUTTON_ACTIONS[0];
}

export function normalizeVisibleIf(visibleIf) {
    const source = visibleIf && typeof visibleIf === "object" ? visibleIf : {};
    const hasTags = Array.isArray(source.has_tags) ? source.has_tags.map((item) => safeText(item)).filter(Boolean) : [];
    const notHasTags = Array.isArray(source.not_has_tags) ? source.not_has_tags.map((item) => safeText(item)).filter(Boolean) : [];
    return {
        has_tags: hasTags,
        not_has_tags: notHasTags,
    };
}

export function normalizeButtonAction(action) {
    const source = action && typeof action === "object" ? action : {};
    const type = BUTTON_ACTIONS.some((item) => item.value === source.type) ? source.type : "url";
    return {
        type,
        value: safeText(source.value),
    };
}

export function normalizeButton(button) {
    const source = button && typeof button === "object" ? button : {};
    return {
        id: source.id || generateId(),
        text: safeText(source.text) || "Кнопка",
        action: normalizeButtonAction(source.action),
        visible_if: normalizeVisibleIf(source.visible_if),
    };
}

function normalizeMessageBlock(block) {
    const source = block && typeof block === "object" ? block : {};
    const type = MESSAGE_TYPES.includes(source.type) ? source.type : "text";
    return {
        id: source.id || generateId(),
        type,
        content_text: source.content_text == null ? "" : source.content_text,
        file_id: source.file_id == null ? "" : source.file_id,
        parse_mode: source.parse_mode === "Markdown" ? "Markdown" : "HTML",
        delay_after: Number.isFinite(Number(source.delay_after)) ? Math.max(0, Number(source.delay_after)) : 0,
    };
}

function normalizeButtonsBlock(block) {
    const source = block && typeof block === "object" ? block : {};
    return {
        id: source.id || generateId(),
        type: "buttons",
        buttons: Array.isArray(source.buttons) ? source.buttons.map(normalizeButton) : [],
    };
}

export function normalizeBlock(block) {
    if (!block || typeof block !== "object") {
        return normalizeMessageBlock({ type: "text" });
    }
    return block.type === "buttons" ? normalizeButtonsBlock(block) : normalizeMessageBlock(block);
}

export function normalizeStepConfig(config) {
    const source = cloneValue(config) || {};
    const blocks = Array.isArray(source.blocks) ? source.blocks.map(normalizeBlock) : [];
    const delayBefore = source.delay_before && typeof source.delay_before === "object" ? source.delay_before : {};
    const triggerCondition = source.trigger_condition && typeof source.trigger_condition === "object" ? source.trigger_condition : {};
    const afterStep = source.after_step && typeof source.after_step === "object" ? source.after_step : {};

    return {
        delay_before: {
            value: Number(delayBefore.value) >= 0 ? Number(delayBefore.value) : 0,
            unit: ["seconds", "minutes", "hours", "days"].includes(delayBefore.unit) ? delayBefore.unit : "seconds",
        },
        trigger_condition: {
            type: ["always", "has_tags", "not_has_tags"].includes(triggerCondition.type) ? triggerCondition.type : "always",
            tags: Array.isArray(triggerCondition.tags) ? triggerCondition.tags.map((item) => safeText(item)).filter(Boolean) : [],
        },
        wait_for_payment: Boolean(source.wait_for_payment),
        linked_product_id: source.linked_product_id || null,
        blocks,
        after_step: {
            add_tags: Array.isArray(afterStep.add_tags) ? afterStep.add_tags.map((item) => safeText(item)).filter(Boolean) : [],
            next_step: safeText(afterStep.next_step) || "auto",
            dozhim_if_no_click_hours: afterStep.dozhim_if_no_click_hours == null || afterStep.dozhim_if_no_click_hours === "" ?
                null :
                Number(afterStep.dozhim_if_no_click_hours),
        },
    };
}

export function createButtonAction(type) {
    const defaults = {
        url: "https://example.com",
        pay_product: "",
        goto_step: "",
        add_tag: "",
        open_track: "",
        signal: "",
    };
    return {
        type: BUTTON_ACTIONS.some((item) => item.value === type) ? type : "url",
        value: defaults[type] == null ? "" : defaults[type],
    };
}

export function createButton(type = "url") {
    return {
        id: generateId(),
        text: "Новая кнопка",
        action: createButtonAction(type),
        visible_if: { has_tags: [], not_has_tags: [] },
    };
}

export function createBlock(type = "text") {
    const blockId = generateId();
    if (type === "buttons") {
        return { id: blockId, type: "buttons", buttons: [] };
    }
    return {
        id: blockId,
        type: MESSAGE_TYPES.includes(type) ? type : "text",
        content_text: "",
        file_id: "",
        parse_mode: "HTML",
        delay_after: 0,
    };
}

export function convertBlockType(block, type) {
    const source = block && typeof block === "object" ? block : {};
    if (type === "buttons") {
        return {
            id: source.id || generateId(),
            type: "buttons",
            buttons: Array.isArray(source.buttons) ? source.buttons.map(normalizeButton) : [],
        };
    }
    return {
        id: source.id || generateId(),
        type: MESSAGE_TYPES.includes(type) ? type : "text",
        content_text: source.content_text == null ? "" : source.content_text,
        file_id: source.file_id == null ? "" : source.file_id,
        parse_mode: source.parse_mode === "Markdown" ? "Markdown" : "HTML",
        delay_after: Number.isFinite(Number(source.delay_after)) ? Math.max(0, Number(source.delay_after)) : 0,
    };
}

export function duplicateBlock(block) {
    const copy = cloneValue(normalizeBlock(block));
    copy.id = generateId();
    if (copy.type === "buttons") {
        copy.buttons = copy.buttons.map((button) => ({ id: generateId(), text: button.text, action: button.action, visible_if: button.visible_if }));
    }
    return copy;
}

export function showToast(message, tone) {
    const root = document.getElementById("toast-root");
    if (!root) return;

    const palette = {
        info: "bg-slate-900 text-white",
        success: "bg-emerald-600 text-white",
        warning: "bg-amber-500 text-white",
        error: "bg-rose-600 text-white",
    };

    const toast = document.createElement("div");
    toast.className = `pointer-events-auto rounded-2xl px-4 py-3 shadow-2xl ring-1 ring-black/5 ${palette[tone || "info"] || palette.info}`;
    toast.textContent = message;
    root.appendChild(toast);

    window.setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(-4px)";
        toast.style.transition = "opacity 180ms ease, transform 180ms ease";
    }, 2600);

    window.setTimeout(() => toast.remove(), 3100);
}