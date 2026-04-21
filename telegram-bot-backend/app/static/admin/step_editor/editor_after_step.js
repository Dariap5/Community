import { State, updateState } from "./state.js";
import { arrayToCsv, csvToArray, escapeHtml } from "./utils.js";

export function renderAfterStepSection(container, context) {
    if (!container) return;

    const steps = context && Array.isArray(context.steps) ? context.steps : [];
    const config = State.config || { after_step: { add_tags: [], next_step: "auto", dozhim_if_no_click_hours: null } };

    container.innerHTML = `
        <div class="se-section-card overflow-hidden">
            <div class="border-b border-slate-200 px-5 py-4">
                <h2 class="text-lg font-semibold text-slate-900">После шага</h2>
                <p class="text-sm text-slate-500">Действия после отправки последнего сообщения и завершения блока кнопок.</p>
            </div>

            <div class="grid gap-4 p-5 md:grid-cols-2">
                <label class="block md:col-span-2">
                    <span class="se-label">Теги после шага</span>
                    <input data-role="after-tags" class="se-input" type="text" value="${escapeHtml(arrayToCsv(config.after_step.add_tags || []))}" placeholder="tag_1, tag_2" />
                </label>

                <label class="block">
                    <span class="se-label">Следующий шаг</span>
                    <select data-role="next-step" class="se-select">
                        ${nextStepOptions(steps, config.after_step.next_step || "auto", State.stepMeta ? State.stepMeta.step_key : "")}
                    </select>
                </label>

                <label class="block">
                    <span class="se-label">Дожим, если нет клика, часы</span>
                    <input data-role="dozhim-hours" class="se-input" type="number" min="0" step="1" value="${config.after_step.dozhim_if_no_click_hours == null ? "" : String(config.after_step.dozhim_if_no_click_hours)}" placeholder="не задано" />
                    <p class="se-help mt-2">Если заполнено, шаг будет ждать указанные часы и затем запускать дожимный сценарий.</p>
                </label>
            </div>
        </div>
    `;

    bindAfterStepEvents(container);
}

function bindAfterStepEvents(container) {
    const tagsInput = container.querySelector('[data-role="after-tags"]');
    const nextStepInput = container.querySelector('[data-role="next-step"]');
    const dozhimInput = container.querySelector('[data-role="dozhim-hours"]');

    const sync = () => {
        const nextConfig = JSON.parse(JSON.stringify(State.config || {}));
        const dozhimValue = dozhimInput && dozhimInput.value !== "" ? Number(dozhimInput.value) : null;
        nextConfig.after_step = {
            add_tags: csvToArray(tagsInput ? tagsInput.value : ""),
            next_step: nextStepInput ? nextStepInput.value : "auto",
            dozhim_if_no_click_hours: dozhimValue == null || isNaN(dozhimValue) ? null : Math.max(0, dozhimValue),
        };
        updateState({ config: nextConfig });
    };

    if (tagsInput) tagsInput.addEventListener("input", sync);
    if (nextStepInput) nextStepInput.addEventListener("change", sync);
    if (dozhimInput) dozhimInput.addEventListener("input", sync);
}

function nextStepOptions(steps, selected, currentStepKey) {
    const options = [
        `<option value="auto" ${selected === "auto" ? "selected" : ""}>Авто</option>`,
        `<option value="end" ${selected === "end" ? "selected" : ""}>Завершить</option>`,
    ];

    (steps || []).forEach((step) => {
        const label = `${step.order}. ${step.name} · ${step.step_key}`;
        const value = step.step_key;
        const isCurrent = value === currentStepKey;
        options.push(`<option value="${value}" ${value === selected ? "selected" : ""}>${label}${isCurrent ? " (текущий)" : ""}</option>`);
    });

    return options.join("");
}