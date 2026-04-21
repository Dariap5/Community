import { State, updateState, setSaving, setStatus } from "./state.js";
import { createBlock, normalizeStepConfig } from "./utils.js";
import { renderSettingsSection } from "./editor_settings.js";
import { renderAfterStepSection } from "./editor_after_step.js";
import { renderBlocksList } from "./editor_blocks.js";
import { renderPreview } from "./preview.js";

let controlsBound = false;

function getElements() {
    return {
        breadcrumbFunnel: document.getElementById("step-breadcrumb-funnel"),
        breadcrumbStep: document.getElementById("step-breadcrumb-step"),
        statusBox: document.getElementById("editor-status"),
        statusText: document.getElementById("editor-status-text"),
        saveButton: document.getElementById("btn-save"),
        testButton: document.getElementById("btn-test"),
        nameInput: document.getElementById("step-name"),
        keyInput: document.getElementById("step-key"),
        activeInput: document.getElementById("step-active"),
        emulationSelect: document.getElementById("emulation-select"),
        settingsRoot: document.getElementById("step-settings-section"),
        afterStepRoot: document.getElementById("after-step-section"),
        blocksRoot: document.getElementById("blocks-list"),
        previewRoot: document.getElementById("preview-root"),
        addBlockButton: document.getElementById("btn-add-block"),
        addBlockModal: document.getElementById("add-block-modal"),
        addBlockCancel: document.getElementById("add-block-cancel"),
    };
}

function getContext() {
    return {
        requestFullRender: renderFullEditor,
        lookups: State.lookups || { products: [], tracks: [] },
        steps: State.funnel && Array.isArray(State.funnel.steps) ? State.funnel.steps : [],
    };
}

export function wireEditorControls(handlers) {
    if (controlsBound) return;
    controlsBound = true;
    const safeHandlers = handlers || {};
    const elements = getElements();

    if (elements.nameInput) {
        elements.nameInput.addEventListener("input", () => {
            updateState({ stepMeta: {...State.stepMeta, name: elements.nameInput.value } });
        });
    }

    if (elements.keyInput) {
        elements.keyInput.addEventListener("input", () => {
            updateState({ stepMeta: {...State.stepMeta, step_key: elements.keyInput.value } });
        });
    }

    if (elements.activeInput) {
        elements.activeInput.addEventListener("change", () => {
            updateState({ stepMeta: {...State.stepMeta, is_active: elements.activeInput.checked } });
        });
    }

    if (elements.emulationSelect) {
        elements.emulationSelect.addEventListener("change", () => {
            updateState({ emulation: elements.emulationSelect.value }, { persistDraft: true });
        });
    }

    if (elements.saveButton) {
        elements.saveButton.addEventListener("click", () => {
            if (safeHandlers.handleSave) safeHandlers.handleSave();
        });
    }

    if (elements.testButton) {
        elements.testButton.addEventListener("click", () => {
            if (safeHandlers.handleTest) safeHandlers.handleTest();
        });
    }

    if (elements.addBlockButton && elements.addBlockModal) {
        elements.addBlockButton.addEventListener("click", () => elements.addBlockModal.showModal());
    }

    if (elements.addBlockCancel && elements.addBlockModal) {
        elements.addBlockCancel.addEventListener("click", () => elements.addBlockModal.close());
    }

    if (elements.addBlockModal) {
        Array.from(elements.addBlockModal.querySelectorAll("[data-block-type]")).forEach((button) => {
            button.addEventListener("click", () => {
                const type = button.getAttribute("data-block-type") || "text";
                const nextConfig = JSON.parse(JSON.stringify(State.config || {}));
                const blocks = Array.isArray(nextConfig.blocks) ? nextConfig.blocks : [];
                blocks.push(createBlock(type));
                nextConfig.blocks = blocks;
                updateState({ config: normalizeStepConfig(nextConfig) });
                elements.addBlockModal.close();
                renderFullEditor();
            });
        });
    }

    window.addEventListener("keydown", (event) => {
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
            event.preventDefault();
            if (safeHandlers.handleSave) safeHandlers.handleSave();
        }
    });
}

export function renderFullEditor() {
    renderStaticHeader();
    renderMetaInputs();
    renderSettingsSection(getElements().settingsRoot, getContext());
    renderBlocksList(getElements().blocksRoot, getContext());
    renderAfterStepSection(getElements().afterStepRoot, getContext());
    renderPreview(getElements().previewRoot);
    renderLiveEditor();
}

export function renderLiveEditor() {
    const elements = getElements();
    if (!elements.statusBox || !elements.statusText || !elements.saveButton || !elements.testButton || !elements.emulationSelect) {
        return;
    }

    if (elements.emulationSelect.value !== State.emulation) {
        elements.emulationSelect.value = State.emulation;
    }

    elements.saveButton.disabled = !State.isDirty || State.saving || State.loading;
    elements.saveButton.textContent = State.saving ? "Сохранение…" : (State.isDirty ? "Сохранить" : "Сохранено");
    elements.testButton.disabled = State.loading || State.saving;

    const tone = State.status && State.status.tone ? State.status.tone : (State.isDirty ? "warning" : "neutral");
    elements.statusBox.setAttribute("data-tone", tone);
    elements.statusText.textContent = State.status && State.status.message ? State.status.message : (State.loading ? "Загрузка…" : (State.isDirty ? "Есть несохранённые изменения" : "Готово к редактированию"));

    document.title = State.stepMeta && State.stepMeta.name ? `${State.stepMeta.name} — Step Editor` : "Редактор шага";
}

function renderStaticHeader() {
    const elements = getElements();
    if (elements.breadcrumbFunnel) {
        elements.breadcrumbFunnel.textContent = State.funnel && State.funnel.name ? State.funnel.name : "Воронка";
    }
    if (elements.breadcrumbStep) {
        elements.breadcrumbStep.textContent = State.stepMeta && State.stepMeta.name ? State.stepMeta.name : "Шаг";
    }
}

function renderMetaInputs() {
    const elements = getElements();
    if (elements.nameInput && elements.nameInput.value !== State.stepMeta.name) {
        elements.nameInput.value = State.stepMeta.name || "";
    }
    if (elements.keyInput && elements.keyInput.value !== State.stepMeta.step_key) {
        elements.keyInput.value = State.stepMeta.step_key || "";
    }
    if (elements.activeInput && elements.activeInput.checked !== Boolean(State.stepMeta.is_active)) {
        elements.activeInput.checked = Boolean(State.stepMeta.is_active);
    }
}