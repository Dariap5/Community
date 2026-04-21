import { State, updateState } from "./state.js";
import { arrayToCsv, csvToArray, escapeHtml } from "./utils.js";

export function renderSettingsSection(container, context) {
    if (!container) return;

    const config = State.config || {
        delay_before: { value: 0, unit: "seconds" },
        trigger_condition: { type: "always", tags: [] },
        wait_for_payment: false,
        linked_product_id: null,
    };
    const lookups = context && context.lookups ? context.lookups : { products: [] };

    container.innerHTML = `
        <div class="se-section-card overflow-hidden">
            <div class="border-b border-slate-200 px-5 py-4">
                <h2 class="text-lg font-semibold text-slate-900">Настройки шага</h2>
                <p class="text-sm text-slate-500">Задержка перед стартом, триггер, ожидание оплаты и связанный продукт.</p>
            </div>

            <div class="grid gap-4 p-5 md:grid-cols-2">
                <label class="block">
                    <span class="se-label">Delay before</span>
                    <div class="grid grid-cols-[1fr_140px] gap-3">
                        <input data-role="delay-value" class="se-input" type="number" min="0" step="1" value="${escapeHtml(String(config.delay_before.value || 0))}" />
                        <select data-role="delay-unit" class="se-select">
                            ${delayUnitOptions(config.delay_before.unit || "seconds")}
                        </select>
                    </div>
                </label>

                <label class="block">
                    <span class="se-label">Trigger condition</span>
                    <select data-role="trigger-type" class="se-select">
                        ${triggerTypeOptions(config.trigger_condition.type || "always")}
                    </select>
                </label>

                <label class="block md:col-span-2">
                    <span class="se-label">Trigger tags</span>
                    <input data-role="trigger-tags" class="se-input" type="text" value="${escapeHtml(arrayToCsv(config.trigger_condition.tags || []))}" placeholder="vip, warm_lead, ..." />
                    <p class="se-help mt-2">Теги можно перечислять через запятую. Для trigger condition они интерпретируются как AND/NOT AND в зависимости от выбранного типа.</p>
                </label>

                <label class="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                    <input data-role="wait-payment" type="checkbox" class="h-5 w-5 rounded border-slate-300 text-slate-900 focus:ring-slate-400" ${config.wait_for_payment ? "checked" : ""} />
                    <div>
                        <div class="text-sm font-semibold text-slate-900">Ждать оплату</div>
                        <div class="text-xs text-slate-500">Шаг не перейдёт дальше, пока оплата не подтверждена.</div>
                    </div>
                </label>

                <label class="block">
                    <span class="se-label">Связанный продукт</span>
                    <select data-role="linked-product" class="se-select" ${config.wait_for_payment ? "" : "disabled"}>
                        ${productOptions(lookups.products || [], config.linked_product_id)}
                    </select>
                    <p class="se-help mt-2">Если шаг ждёт оплату, здесь укажи продукт, с которым он связан.</p>
                </label>
            </div>
        </div>
    `;

    bindSettingsEvents(container);
}

function bindSettingsEvents(container) {
    const delayValue = container.querySelector('[data-role="delay-value"]');
    const delayUnit = container.querySelector('[data-role="delay-unit"]');
    const triggerType = container.querySelector('[data-role="trigger-type"]');
    const triggerTags = container.querySelector('[data-role="trigger-tags"]');
    const waitPayment = container.querySelector('[data-role="wait-payment"]');
    const linkedProduct = container.querySelector('[data-role="linked-product"]');

    const sync = () => {
        const nextConfig = JSON.parse(JSON.stringify(State.config || {}));
        const delayValueNumber = delayValue && delayValue.value !== "" ? Number(delayValue.value) : 0;
        nextConfig.delay_before = {
            value: isNaN(delayValueNumber) ? 0 : Math.max(0, delayValueNumber),
            unit: delayUnit ? delayUnit.value : "seconds",
        };
        nextConfig.trigger_condition = {
            type: triggerType ? triggerType.value : "always",
            tags: csvToArray(triggerTags ? triggerTags.value : ""),
        };
        nextConfig.wait_for_payment = Boolean(waitPayment && waitPayment.checked);
        nextConfig.linked_product_id = waitPayment && waitPayment.checked && linkedProduct && linkedProduct.value ? linkedProduct.value : null;
        updateState({ config: nextConfig });
        if (linkedProduct) {
            linkedProduct.disabled = !(waitPayment && waitPayment.checked);
        }
    };

    if (delayValue) delayValue.addEventListener("input", sync);
    if (delayUnit) delayUnit.addEventListener("change", sync);
    if (triggerType) triggerType.addEventListener("change", sync);
    if (triggerTags) triggerTags.addEventListener("input", sync);
    if (waitPayment) waitPayment.addEventListener("change", sync);
    if (linkedProduct) linkedProduct.addEventListener("change", sync);
}

function delayUnitOptions(selected) {
    return ["seconds", "minutes", "hours", "days"]
        .map((unit) => `<option value="${unit}" ${unit === selected ? "selected" : ""}>${unitLabel(unit)}</option>`)
        .join("");
}

function unitLabel(unit) {
    const labels = { seconds: "секунды", minutes: "минуты", hours: "часы", days: "дни" };
    return labels[unit] || unit;
}

function triggerTypeOptions(selected) {
    const options = [
        ["always", "Всегда"],
        ["has_tags", "Есть теги"],
        ["not_has_tags", "Нет тегов"],
    ];
    return options.map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`).join("");
}

function productOptions(products, selected) {
    const items = [`<option value="">Без продукта</option>`];
    (products || []).forEach((product) => {
                items.push(`<option value="${product.id}" ${String(product.id) === String(selected) ? "selected" : ""}>${product.name}${product.price != null ? ` · ${product.price}` : ""}</option>`);
    });
    return items.join("");
}