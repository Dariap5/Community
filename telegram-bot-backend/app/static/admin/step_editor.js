import { loadDraftSnapshot, clearDraftSnapshot, markInitialized, markSaved, applyDraftSnapshot, setServerSnapshot, setSaving, setStatus, subscribe, updateState, State } from "./step_editor/state.js";
import { loadFunnel, loadProducts, loadStep, loadTracks, saveStep, sendTestToAdmin, extractApiMessage } from "./step_editor/api.js";
import { renderFullEditor, renderLiveEditor, wireEditorControls } from "./step_editor/render.js";
import { showToast } from "./step_editor/utils.js";

async function init() {
    const data = window.__STEP_DATA__ || {};
    if (!data.funnelId || !data.stepId) {
        showToast("Не найдены funnelId / stepId для редактора", "error");
        return;
    }

    updateState({
        funnelId: data.funnelId,
        stepId: data.stepId,
        status: { tone: "neutral", message: "Загрузка шага…" },
    }, { persistDraft: false }, );

    wireEditorControls({
        handleSave: saveCurrentStep,
        handleTest: sendCurrentStepToTest,
    });

    subscribe(() => renderLiveEditor());

    await loadFreshEditor();
    markInitialized();
    renderFullEditor();

    window.addEventListener("beforeunload", (event) => {
        if (State.isDirty) {
            event.preventDefault();
            event.returnValue = "";
        }
    });
}

async function loadFreshEditor() {
    updateState({ loading: true, status: { tone: "neutral", message: "Загрузка данных…" } }, { persistDraft: false });

    try {
        const funnelPromise = loadFunnel(window.__STEP_DATA__.funnelId);
        const stepPromise = loadStep(window.__STEP_DATA__.funnelId, window.__STEP_DATA__.stepId);
        const productsPromise = loadProducts();
        const tracksPromise = loadTracks();

        const funnel = await funnelPromise;
        const step = await stepPromise;
        const products = await productsPromise.catch(() => []);
        const tracks = await tracksPromise.catch(() => []);

        setServerSnapshot({ funnel: funnel, step: step, lookups: { products: products, tracks: tracks } });

        const draft = loadDraftSnapshot();
        if (draft) {
            const restoreDraft = window.confirm("Найден локальный черновик шага. Восстановить его?");
            if (restoreDraft) {
                applyDraftSnapshot(draft);
            } else {
                clearDraftSnapshot();
            }
        }

        updateState({ loading: false, status: { tone: "success", message: "Шаг загружен" } }, { persistDraft: false });
    } catch (error) {
        const message = error && error.message ? error.message : "Не удалось загрузить редактор";
        updateState({ loading: false, status: { tone: "error", message: message } }, { persistDraft: false });
        showToast(message, "error");
    }
}

async function saveCurrentStep() {
    if (State.saving) return;

    setSaving(true);
    setStatus("Сохранение…", "warning");

    try {
        const payload = {
            name: State.stepMeta.name,
            step_key: State.stepMeta.step_key,
            is_active: State.stepMeta.is_active,
            config: State.config,
        };
        const saved = await saveStep(State.funnelId, State.stepId, payload);
        updateState({
            stepMeta: {
                name: saved.name,
                step_key: saved.step_key,
                is_active: saved.is_active,
                order: saved.order,
            },
            config: saved.config,
        }, { persistDraft: false }, );
        markSaved();
        showToast("Сохранено", "success");
    } catch (error) {
        setSaving(false);
        const message = extractApiMessage(error && error.payload ? error.payload : null, error && error.message ? error.message : "Ошибка сохранения");
        setStatus(message, "error");
        showToast(message, "error");
    }
}

async function sendCurrentStepToTest() {
    if (State.isDirty) {
        const shouldSave = window.confirm("Есть несохранённые изменения. Сохранить шаг перед тестом?");
        if (!shouldSave) {
            return;
        }
        await saveCurrentStep();
        if (State.isDirty) {
            return;
        }
    }

    try {
        await sendTestToAdmin(State.funnelId, State.stepId, State.emulation);
        setStatus("Тест отправлен", "success");
        showToast("Тест отправлен в Telegram", "success");
    } catch (error) {
        const message = extractApiMessage(error && error.payload ? error.payload : null, error && error.message ? error.message : "Не удалось отправить тест");
        setStatus(message, "error");
        showToast(message, "error");
    }
}

if (typeof window !== "undefined") {
    init();
}