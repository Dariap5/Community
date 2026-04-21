import { State, updateState } from "./state.js";
import { convertBlockType, createBlock, duplicateBlock, escapeHtml, getBlockIcon, getBlockTitle, normalizeBlock, normalizeStepConfig } from "./utils.js";
import { enableDragDrop } from "./drag_drop.js";
import { renderButtonsEditor } from "./buttons_editor.js";

export function renderBlocksList(container, context) {
    if (!container) return;

    const blocks = State.config && Array.isArray(State.config.blocks) ? State.config.blocks : [];
    const safeContext = context || { requestFullRender: function() {} };
    container.innerHTML = "";

    if (!blocks.length) {
        const empty = document.createElement("div");
        empty.className = "se-section-card border-dashed border-slate-300 bg-slate-50 p-6 text-center";
        empty.innerHTML = `
            <div class="text-3xl">🧱</div>
            <div class="mt-2 text-sm font-semibold text-slate-900">Пока нет блоков</div>
            <div class="mt-1 text-sm text-slate-500">Добавь первый текст, медиа или блок кнопок.</div>
        `;
        container.appendChild(empty);
    }

    blocks.forEach((block, index) => {
        container.appendChild(createBlockCard(block, index, safeContext));
    });

    if (blocks.length) {
        enableDragDrop(container, {
            itemSelector: ".se-block-card",
            handleSelector: "[data-drag-handle]",
            idKey: "blockId",
            onReorder: (orderedIds) => {
                const byId = new Map(blocks.map((item) => [item.id, item]));
                const nextConfig = JSON.parse(JSON.stringify(State.config || {}));
                nextConfig.blocks = orderedIds.map((id) => byId.get(id)).filter(Boolean).map(normalizeBlock);
                updateState({ config: normalizeStepConfig(nextConfig) });
                safeContext.requestFullRender();
            },
        });
    }
}

function createBlockCard(block, index, context) {
    const card = document.createElement("article");
    card.className = "se-block-card se-scroll";
    card.dataset.blockId = block.id;
    card.setAttribute("draggable", "true");

    card.innerHTML = `
        <div class="border-b border-slate-200 px-5 py-4">
            <div class="flex flex-wrap items-start justify-between gap-4">
                <div class="flex items-start gap-3">
                    <div class="pt-1 text-lg leading-none se-drag-handle" data-drag-handle>⋮⋮</div>
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="se-chip">${getBlockIcon(block.type)} ${getBlockTitle(block.type)}</span>
                            <span class="text-sm text-slate-500">Блок ${index + 1}</span>
                        </div>
                        <p class="mt-2 text-sm text-slate-500">Перетащи за ручку, чтобы изменить порядок отправки.</p>
                    </div>
                </div>

                <div class="flex flex-wrap items-center gap-2">
                    <label class="block min-w-[180px]">
                        <span class="se-label">Тип блока</span>
                        <select data-role="block-type" class="se-select">${blockTypeOptions(block.type)}</select>
                    </label>
                    <button type="button" class="se-button-ghost h-[54px] px-4" data-role="duplicate-block">Дублировать</button>
                    <button type="button" class="se-button-ghost h-[54px] px-4 text-rose-600" data-role="delete-block">Удалить</button>
                </div>
            </div>
        </div>
        <div class="space-y-4 p-5">
            ${renderBlockBody(block)}
        </div>
    `;

    bindBlockEvents(card, block, context);
    return card;
}

function renderBlockBody(block) {
    if (block.type === "buttons") {
        return '<div data-role="buttons-host"></div>';
    }

    const isVideoNote = block.type === "video_note";
    const needsFileId = block.type === "photo" || block.type === "document" || block.type === "video" || block.type === "voice" || isVideoNote;

    return `
        <div class="grid gap-4 lg:grid-cols-2">
            <label class="block lg:col-span-2">
                <span class="se-label">${block.type === "text" ? "Текст сообщения" : "Caption / content"}</span>
                <textarea data-role="content-text" class="se-input min-h-[120px] resize-y">${escapeHtml(block.content_text || "")}</textarea>
            </label>

            ${needsFileId ? `
                <label class="block lg:col-span-2">
                    <span class="se-label">File ID</span>
                    <input data-role="file-id" class="se-input" type="text" value="${escapeHtml(block.file_id || "")}" placeholder="Telegram file_id" />
                </label>
            ` : ""}

            <label class="block">
                <span class="se-label">Parse mode</span>
                <select data-role="parse-mode" class="se-select">
                    <option value="HTML" ${block.parse_mode !== "Markdown" ? "selected" : ""}>HTML</option>
                    <option value="Markdown" ${block.parse_mode === "Markdown" ? "selected" : ""}>Markdown</option>
                </select>
            </label>

            <label class="block">
                <span class="se-label">Delay after, seconds</span>
                <input data-role="delay-after" class="se-input" type="number" min="0" step="1" value="${block.delay_after == null ? 0 : block.delay_after}" />
            </label>
        </div>
    `;
}

function bindBlockEvents(card, block, context) {
    const blockType = card.querySelector('[data-role="block-type"]');
    const deleteButton = card.querySelector('[data-role="delete-block"]');
    const duplicateButton = card.querySelector('[data-role="duplicate-block"]');

    if (blockType) {
        blockType.addEventListener("change", () => {
            replaceBlock(block.id, convertBlockType(block, blockType.value));
            context.requestFullRender();
        });
    }

    if (deleteButton) {
        deleteButton.addEventListener("click", () => {
            const nextConfig = JSON.parse(JSON.stringify(State.config || {}));
            nextConfig.blocks = (nextConfig.blocks || []).filter((item) => item.id !== block.id);
            updateState({ config: normalizeStepConfig(nextConfig) });
            context.requestFullRender();
        });
    }

    if (duplicateButton) {
        duplicateButton.addEventListener("click", () => {
            const nextConfig = JSON.parse(JSON.stringify(State.config || {}));
            const blocks = Array.isArray(nextConfig.blocks) ? nextConfig.blocks : [];
            const blockIndex = blocks.findIndex((item) => item.id === block.id);
            if (blockIndex === -1) return;
            blocks.splice(blockIndex + 1, 0, duplicateBlock(block));
            nextConfig.blocks = blocks;
            updateState({ config: normalizeStepConfig(nextConfig) });
            context.requestFullRender();
        });
    }

    const contentText = card.querySelector('[data-role="content-text"]');
    const fileId = card.querySelector('[data-role="file-id"]');
    const parseMode = card.querySelector('[data-role="parse-mode"]');
    const delayAfter = card.querySelector('[data-role="delay-after"]');

    const syncMessageBlock = () => {
        patchBlock(block.id, {
            content_text: contentText ? contentText.value : "",
            file_id: fileId ? fileId.value : "",
            parse_mode: parseMode ? parseMode.value : "HTML",
            delay_after: delayAfter && delayAfter.value !== "" ? Math.max(0, Number(delayAfter.value)) : 0,
        });
    };

    if (contentText) contentText.addEventListener("input", syncMessageBlock);
    if (fileId) fileId.addEventListener("input", syncMessageBlock);
    if (parseMode) parseMode.addEventListener("change", syncMessageBlock);
    if (delayAfter) delayAfter.addEventListener("input", syncMessageBlock);

    const buttonsHost = card.querySelector('[data-role="buttons-host"]');
    if (buttonsHost) {
        renderButtonsEditor(buttonsHost, block, context);
    }
}

function patchBlock(blockId, patch) {
    const nextConfig = JSON.parse(JSON.stringify(State.config || {}));
    const blocks = Array.isArray(nextConfig.blocks) ? nextConfig.blocks : [];
    const blockIndex = blocks.findIndex((item) => item.id === blockId);
    if (blockIndex === -1) return;
    blocks[blockIndex] = { ...blocks[blockIndex], ...patch };
    nextConfig.blocks = blocks;
    updateState({ config: normalizeStepConfig(nextConfig) });
}

function replaceBlock(blockId, nextBlock) {
    const nextConfig = JSON.parse(JSON.stringify(State.config || {}));
    const blocks = Array.isArray(nextConfig.blocks) ? nextConfig.blocks : [];
    const blockIndex = blocks.findIndex((item) => item.id === blockId);
    if (blockIndex === -1) return;
    blocks[blockIndex] = nextBlock;
    nextConfig.blocks = blocks;
    updateState({ config: normalizeStepConfig(nextConfig) });
}

function blockTypeOptions(selected) {
    return [
        ["text", "Текст"],
        ["photo", "Фото"],
        ["document", "Документ"],
        ["video", "Видео"],
        ["video_note", "Кружочек"],
        ["voice", "Голосовое"],
        ["buttons", "Кнопки"],
    ]
        .map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`)
        .join("");
}