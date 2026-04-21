import { State, updateState } from "./state.js";
import { arrayToCsv, cloneValue, createButton, csvToArray, escapeHtml, generateId, getActionDefinition, normalizeButton, normalizeStepConfig } from "./utils.js";
import { enableDragDrop } from "./drag_drop.js";

export function renderButtonsEditor(container, block, context) {
    if (!container) return;

    const currentBlock = findButtonBlock(block.id);
    const buttons = currentBlock && Array.isArray(currentBlock.buttons) ? currentBlock.buttons : [];
    const safeContext = context || { lookups: { products: [], tracks: [] }, steps: [], requestFullRender: function() {} };

    container.innerHTML = `
        <div class="space-y-3">
            <p class="se-help rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-900">
                Кнопки прикрепляются к последнему сообщению шага. Если сообщений нет, движок отправит пустую текстовую оболочку с кнопками.
            </p>
            <div class="space-y-3" data-role="buttons-list"></div>
            <button type="button" class="se-button-secondary w-full" data-role="add-button">+ Добавить кнопку</button>
        </div>
    `;

    const list = container.querySelector('[data-role="buttons-list"]');
    (buttons || []).forEach((button) => {
        list.appendChild(renderButtonRow(currentBlock.id, button, safeContext));
    });

    const addButton = container.querySelector('[data-role="add-button"]');
    if (addButton) {
        addButton.addEventListener("click", () => {
            const nextButtons = readButtonsFromDom(list);
            nextButtons.push(createButton());
            updateButtonsBlock(currentBlock.id, nextButtons);
            safeContext.requestFullRender();
        });
    }

    enableDragDrop(list, {
        itemSelector: ".se-button-row",
        handleSelector: "[data-drag-handle]",
        idKey: "buttonId",
        onReorder: (orderedIds) => {
            const byId = new Map(readButtonsFromDom(list).map((button) => [button.id, button]));
            const nextButtons = orderedIds.map((id) => byId.get(id)).filter(Boolean);
            updateButtonsBlock(currentBlock.id, nextButtons);
            safeContext.requestFullRender();
        },
    });
}

function renderButtonRow(blockId, button, context) {
    const row = document.createElement("div");
    row.className = "se-button-row p-4";
    row.dataset.buttonId = button.id || generateId();
    row.setAttribute("draggable", "true");

    row.innerHTML = `
        <div class="flex items-start gap-3">
            <div class="pt-2 text-lg leading-none se-drag-handle" data-drag-handle>⋮⋮</div>
            <div class="flex-1 space-y-4">
                <div class="grid gap-3 md:grid-cols-[1.1fr_1fr_auto]">
                    <label class="block">
                        <span class="se-label">Текст кнопки</span>
                        <input data-role="button-text" class="se-input" type="text" maxlength="64" value="${escapeHtml(button.text || "")}" placeholder="Нажми меня" />
                    </label>
                    <label class="block">
                        <span class="se-label">Действие</span>
                        <select data-role="action-type" class="se-select">${actionTypeOptions(button.action && button.action.type ? button.action.type : "url")}</select>
                    </label>
                    <div class="flex items-end gap-2">
                        <button type="button" class="se-button-ghost h-[54px] px-4" data-role="duplicate-button">Дублировать</button>
                        <button type="button" class="se-button-ghost h-[54px] px-4 text-rose-600" data-role="delete-button">Удалить</button>
                    </div>
                </div>

                <div class="grid gap-3 md:grid-cols-[1fr_1fr]">
                    <div class="space-y-2">
                        <span class="se-label">Значение действия</span>
                        <div data-role="action-value"></div>
                    </div>
                    <div class="space-y-2 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                        <div class="text-sm font-semibold text-slate-900">Visible if</div>
                        <label class="block">
                            <span class="se-label">Has tags</span>
                            <input data-role="has-tags" class="se-input" type="text" value="${escapeHtml(arrayToCsv(button.visible_if && button.visible_if.has_tags ? button.visible_if.has_tags : []))}" placeholder="vip, paid" />
                        </label>
                        <label class="block mt-3">
                            <span class="se-label">Not has tags</span>
                            <input data-role="not-has-tags" class="se-input" type="text" value="${escapeHtml(arrayToCsv(button.visible_if && button.visible_if.not_has_tags ? button.visible_if.not_has_tags : []))}" placeholder="blocked, inactive" />
                        </label>
                    </div>
                </div>
            </div>
        </div>
    `;

    const actionValueHost = row.querySelector('[data-role="action-value"]');
    renderActionValueField(actionValueHost, blockId, button, context);
    bindButtonRowEvents(row, blockId, context);
    return row;
}

function renderActionValueField(host, blockId, button, context) {
    if (!host) return;

    const actionType = button.action && button.action.type ? button.action.type : "url";
    const definition = getActionDefinition(actionType);

    if (definition.valueType === "select_product") {
        host.innerHTML = `<select data-role="action-value-field" class="se-select">${productOptions(context.lookups && context.lookups.products ? context.lookups.products : [], button.action && button.action.value ? button.action.value : "")}</select>`;
        return;
    }

    if (definition.valueType === "select_step") {
        host.innerHTML = `<select data-role="action-value-field" class="se-select">${stepOptions(context.steps || [], button.action && button.action.value ? button.action.value : "")}</select>`;
        return;
    }

    if (definition.valueType === "select_track") {
        host.innerHTML = `<select data-role="action-value-field" class="se-select">${trackOptions(context.lookups && context.lookups.tracks ? context.lookups.tracks : [], button.action && button.action.value ? button.action.value : "")}</select>`;
        return;
    }

    host.innerHTML = `
        <input
            data-role="action-value-field"
            class="se-input"
            type="text"
            value="${escapeHtml(button.action && button.action.value ? button.action.value : "")}" 
            placeholder="${escapeHtml(definition.placeholder || "Значение")}" 
        />
    `;
}

function bindButtonRowEvents(row, blockId, context) {
    const textInput = row.querySelector('[data-role="button-text"]');
    const actionType = row.querySelector('[data-role="action-type"]');
    const valueHost = row.querySelector('[data-role="action-value"]');
    const hasTags = row.querySelector('[data-role="has-tags"]');
    const notHasTags = row.querySelector('[data-role="not-has-tags"]');
    const deleteButton = row.querySelector('[data-role="delete-button"]');
    const duplicateButton = row.querySelector('[data-role="duplicate-button"]');

    const syncButtons = () => {
        const nextButtons = readButtonsFromDom(row.parentElement);
        updateButtonsBlock(blockId, nextButtons);
    };

    const rerenderValueField = () => {
        const currentButton = readButtonRow(row);
        renderActionValueField(valueHost, blockId, currentButton, context);
        const valueField = row.querySelector('[data-role="action-value-field"]');
        if (valueField) {
            valueField.addEventListener("input", syncButtons);
            valueField.addEventListener("change", syncButtons);
        }
    };

    if (textInput) textInput.addEventListener("input", syncButtons);
    if (actionType) actionType.addEventListener("change", () => {
        rerenderValueField();
        syncButtons();
    });
    if (hasTags) hasTags.addEventListener("input", syncButtons);
    if (notHasTags) notHasTags.addEventListener("input", syncButtons);
    if (deleteButton) deleteButton.addEventListener("click", () => {
        const nextButtons = readButtonsFromDom(row.parentElement).filter((item) => item.id !== row.dataset.buttonId);
        updateButtonsBlock(blockId, nextButtons);
        context.requestFullRender();
    });
    if (duplicateButton) duplicateButton.addEventListener("click", () => {
        const nextButtons = readButtonsFromDom(row.parentElement);
        const current = readButtonRow(row);
        const index = nextButtons.findIndex((item) => item.id === current.id);
        const duplicate = normalizeButton({
            id: generateId(),
            text: current.text,
            action: current.action,
            visible_if: current.visible_if,
        });
        nextButtons.splice(index + 1, 0, duplicate);
        updateButtonsBlock(blockId, nextButtons);
        context.requestFullRender();
    });

    const valueField = row.querySelector('[data-role="action-value-field"]');
    if (valueField) {
        valueField.addEventListener("input", syncButtons);
        valueField.addEventListener("change", syncButtons);
    }
}

function readButtonsFromDom(list) {
    return Array.from(list ? list.querySelectorAll(".se-button-row") : []).map(readButtonRow).filter(Boolean);
}

function readButtonRow(row) {
    const actionType = row.querySelector('[data-role="action-type"]');
    const valueField = row.querySelector('[data-role="action-value-field"]');
    const hasTagsField = row.querySelector('[data-role="has-tags"]');
    const notHasTagsField = row.querySelector('[data-role="not-has-tags"]');

    return normalizeButton({
        id: row.dataset.buttonId,
        text: row.querySelector('[data-role="button-text"]') ? row.querySelector('[data-role="button-text"]').value : "Кнопка",
        action: {
            type: actionType ? actionType.value : "url",
            value: valueField ? valueField.value : "",
        },
        visible_if: {
            has_tags: csvToArray(hasTagsField ? hasTagsField.value : ""),
            not_has_tags: csvToArray(notHasTagsField ? notHasTagsField.value : ""),
        },
    });
}

function updateButtonsBlock(blockId, nextButtons) {
    const nextConfig = JSON.parse(JSON.stringify(State.config || {}));
    const blocks = Array.isArray(nextConfig.blocks) ? nextConfig.blocks : [];
    const blockIndex = blocks.findIndex((item) => item.id === blockId);
    if (blockIndex === -1) return;
    blocks[blockIndex].buttons = nextButtons.map(normalizeButton);
    nextConfig.blocks = blocks;
    updateState({ config: normalizeStepConfig(nextConfig) });
}

function findButtonBlock(blockId) {
    const blocks = State.config && Array.isArray(State.config.blocks) ? State.config.blocks : [];
    return blocks.find((block) => block.id === blockId) || null;
}

function actionTypeOptions(selected) {
    return [
            ["url", "URL"],
            ["pay_product", "Оплата продукта"],
            ["goto_step", "Переход на шаг"],
            ["add_tag", "Добавить тег"],
            ["open_track", "Открыть трек"],
            ["signal", "Сигнал"],
        ]
        .map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`)
        .join("");
}

function productOptions(products, selected) {
    const items = ['<option value="">Без продукта</option>'];
    (products || []).forEach((product) => {
        items.push(`<option value="${product.id}" ${String(product.id) === String(selected) ? "selected" : ""}>${escapeHtml(product.name || "")}</option>`);
    });
    return items.join("");
}

function stepOptions(steps, selected) {
    const items = ['<option value="">Без шага</option>'];
    (steps || []).forEach((step) => {
        items.push(`<option value="${escapeHtml(step.step_key || "")}" ${step.step_key === selected ? "selected" : ""}>${escapeHtml((step.order || 0) + ". " + (step.name || ""))}</option>`);
    });
    return items.join("");
}

function trackOptions(tracks, selected) {
    const items = ['<option value="">Без трека</option>'];
    (tracks || []).forEach((track) => {
        const title = track.title || track.name || "";
        items.push(`<option value="${track.id}" ${String(track.id) === String(selected) ? "selected" : ""}>${escapeHtml(title)}</option>`);
    });
    return items.join("");
}