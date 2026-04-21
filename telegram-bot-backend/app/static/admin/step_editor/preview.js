import { State } from "./state.js";
import { arrayToCsv, escapeHtml, formatDelay, getBlockIcon, getBlockTitle, getEmulationTags } from "./utils.js";
import { sanitizeTelegramHTML } from "./telegram_html.js";

export function renderPreview(container) {
    if (!container) return;

    const config = State.config || { blocks: [], delay_before: { value: 0, unit: "seconds" }, trigger_condition: { type: "always", tags: [] }, after_step: { add_tags: [], next_step: "auto", dozhim_if_no_click_hours: null } };
    const blocks = Array.isArray(config.blocks) ? config.blocks : [];
    const messageBlocks = blocks.filter((block) => block.type !== "buttons");
    const buttonBlocks = blocks.filter((block) => block.type === "buttons");
    const emulatedTags = getEmulationTags(State.emulation);

    container.innerHTML = "";

    const info = document.createElement("div");
    info.className = "se-telegram-card se-scroll p-4 text-xs text-slate-300";
    info.innerHTML = [
        chip(`Delay before: ${formatDelay(config.delay_before?.value || 0, config.delay_before?.unit || "seconds")}`),
        chip(`Trigger: ${describeTrigger(config.trigger_condition)}`),
        chip(`After step: ${describeAfterStep(config.after_step)}`),
    ].join("");
    container.appendChild(info);

    const chat = document.createElement("div");
    chat.className = "se-telegram-shell se-scroll space-y-3 p-4";

    if (!messageBlocks.length && !buttonBlocks.length) {
        const placeholder = document.createElement("div");
        placeholder.className = "se-preview-placeholder flex items-center justify-center px-5 py-10 text-center text-sm leading-6";
        placeholder.innerHTML = "Добавь первый блок, чтобы увидеть Telegram-preview здесь.";
        chat.appendChild(placeholder);
        container.appendChild(chat);
        return;
    }

    const renderedBubbles = [];
    messageBlocks.forEach((block) => {
        const bubble = renderMessageBubble(block);
        renderedBubbles.push(bubble);
        chat.appendChild(bubble);
    });

    if (buttonBlocks.length > 1) {
        const warning = document.createElement("div");
        warning.className = "se-chip se-chip-dark self-start";
        warning.textContent = "В шаге найдено несколько блоков кнопок, движок использует первый.";
        chat.appendChild(warning);
    }

    if (buttonBlocks.length > 0) {
        const buttonsBlock = buttonBlocks[0];
        const buttons = renderButtons(buttonsBlock, emulatedTags);

        if (renderedBubbles.length > 0) {
            renderedBubbles[renderedBubbles.length - 1].appendChild(buttons);
        } else {
            const standalone = document.createElement("div");
            standalone.className = "se-telegram-bubble px-4 py-4";
            standalone.appendChild(buttons);
            chat.appendChild(standalone);
        }
    }

    container.appendChild(chat);
}

function renderMessageBubble(block) {
    const bubble = document.createElement("article");
    bubble.className = "se-telegram-bubble space-y-3 px-4 py-4";
    bubble.dataset.blockType = block.type;

    const topRow = document.createElement("div");
    topRow.className = "flex items-center justify-between gap-3 text-xs text-slate-300/80";
    topRow.innerHTML = `
        <span class="se-chip se-chip-dark">${getBlockIcon(block.type)} ${getBlockTitle(block.type)}</span>
        <span>${block.delay_after ? `+ ${formatDelay(block.delay_after, "seconds")}` : "без задержки"}</span>
    `;
    bubble.appendChild(topRow);

    if (block.type === "text") {
        const body = document.createElement("div");
        body.className = "text-[15px] leading-6 text-slate-100";
        body.innerHTML = sanitizeTelegramHTML(block.content_text || "", block.parse_mode || "HTML");
        bubble.appendChild(body);
    }

    if (block.type === "photo" || block.type === "video" || block.type === "document" || block.type === "voice") {
        const frame = document.createElement("div");
        frame.className = "rounded-2xl border border-white/10 bg-white/5 p-4";
        frame.innerHTML = renderMediaPlaceholder(block);
        bubble.appendChild(frame);

        if (block.content_text) {
            const caption = document.createElement("div");
            caption.className = "text-[15px] leading-6 text-slate-100";
            caption.innerHTML = sanitizeTelegramHTML(block.content_text, block.parse_mode || "HTML");
            bubble.appendChild(caption);
        }
    }

    if (block.type === "video_note") {
        const frame = document.createElement("div");
        frame.className = "flex items-center justify-center rounded-full border border-white/10 bg-white/5 p-7 text-4xl";
        frame.textContent = "⭕";
        bubble.appendChild(frame);
    }

    return bubble;
}

function renderMediaPlaceholder(block) {
    const labelMap = {
        photo: "Фото",
        video: "Видео",
        document: "Документ",
        voice: "Голосовое",
    };
    return `
        <div class="flex items-center gap-3">
            <div class="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/10 text-2xl">${getBlockIcon(block.type)}</div>
            <div class="space-y-1">
                <div class="text-sm font-semibold text-slate-100">${labelMap[block.type] || getBlockTitle(block.type)}</div>
                <div class="text-xs text-slate-300/70">file_id: ${escapeHtml(block.file_id || "—")}</div>
            </div>
        </div>
    `;
}

function renderButtons(block, userTags) {
    const wrapper = document.createElement("div");
    wrapper.className = "mt-3 space-y-2";

    const visibleButtons = (block.buttons || []).filter((button) => {
        const visibleIf = button.visible_if || { has_tags: [], not_has_tags: [] };
        if (visibleIf.has_tags?.length && !visibleIf.has_tags.every((tag) => userTags.includes(tag))) {
            return false;
        }
        if (visibleIf.not_has_tags?.length && visibleIf.not_has_tags.some((tag) => userTags.includes(tag))) {
            return false;
        }
        return true;
    });

    if (!visibleButtons.length) {
        const empty = document.createElement("div");
        empty.className = "se-chip se-chip-dark";
        empty.textContent = "В этой эмуляции кнопок нет";
        wrapper.appendChild(empty);
        return wrapper;
    }

    visibleButtons.forEach((button) => {
        const el = document.createElement("div");
        el.className = "se-telegram-button space-y-1";
        el.innerHTML = `
            <div>${escapeHtml(button.text)}</div>
            <div class="text-[11px] font-medium text-white/70">${escapeHtml(describeButtonAction(button.action?.type || "url", button.action?.value || ""))}</div>
        `;
        wrapper.appendChild(el);
    });

    return wrapper;
}

function chip(text) {
    return `<span class="se-chip se-chip-dark mr-2 mb-2">${escapeHtml(text)}</span>`;
}

function describeTrigger(trigger) {
    if (!trigger) return "always";
    if (trigger.type === "always") return "always";
    if (trigger.type === "has_tags") return `has tags: ${arrayToCsv(trigger.tags || [])}`;
    if (trigger.type === "not_has_tags") return `not has: ${arrayToCsv(trigger.tags || [])}`;
    return trigger.type;
}

function describeAfterStep(afterStep) {
    if (!afterStep) return "auto";
    const tags = arrayToCsv(afterStep.add_tags || []);
    const click = afterStep.dozhim_if_no_click_hours == null ? "" : ` · dozhim ${afterStep.dozhim_if_no_click_hours}h`;
    return `${afterStep.next_step || "auto"}${tags ? ` · +${tags}` : ""}${click}`;
}

function describeButtonAction(type, value) {
    const labels = {
        url: value || "URL",
        pay_product: value ? `product ${value}` : "product",
        goto_step: value ? `goto ${value}` : "goto step",
        add_tag: value ? `add tag ${value}` : "tag",
        open_track: value ? `track ${value}` : "track",
        signal: value ? `signal ${value}` : "signal",
    };
    return labels[type] || type;
}