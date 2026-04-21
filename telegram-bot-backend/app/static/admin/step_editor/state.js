import { cloneValue, normalizeStepConfig, safeText } from "./utils.js";

export const State = {
    funnelId: null,
    stepId: null,
    funnel: null,
    lookups: {
        products: [],
        tracks: [],
    },
    stepMeta: {
        name: "",
        step_key: "",
        is_active: true,
        order: 0,
    },
    originalMeta: null,
    config: normalizeStepConfig({}),
    originalConfig: normalizeStepConfig({}),
    emulation: "new",
    loading: true,
    saving: false,
    initialized: false,
    isDirty: false,
    status: {
        tone: "neutral",
        message: "",
    },
};

const subscribers = new Set();

function emit() {
    subscribers.forEach((subscriber) => subscriber(State));
}

function draftKey() {
    return `step-editor:draft:${State.funnelId}:${State.stepId}`;
}

function normalizeMeta(meta) {
    const source = meta && typeof meta === "object" ? meta : {};
    return {
        name: safeText(source.name),
        step_key: safeText(source.step_key),
        is_active: source.is_active !== false,
        order: Number.isFinite(Number(source.order)) ? Number(source.order) : 0,
    };
}

function normalizeLookups(lookups) {
    const source = lookups && typeof lookups === "object" ? lookups : {};
    return {
        products: Array.isArray(source.products) ? cloneValue(source.products) : [],
        tracks: Array.isArray(source.tracks) ? cloneValue(source.tracks) : [],
    };
}

function recomputeDirty() {
    if (!State.originalConfig || !State.originalMeta) {
        State.isDirty = false;
        return;
    }

    const currentMeta = normalizeMeta(State.stepMeta);
    const originalMeta = normalizeMeta(State.originalMeta);
    State.isDirty =
        JSON.stringify(State.config) !== JSON.stringify(State.originalConfig) ||
        JSON.stringify(currentMeta) !== JSON.stringify(originalMeta);
}

function persistDraft() {
    try {
        if (!State.funnelId || !State.stepId) return;
        localStorage.setItem(
            draftKey(),
            JSON.stringify({
                config: State.config,
                stepMeta: State.stepMeta,
                emulation: State.emulation,
            }),
        );
    } catch {
        // ignore storage failures
    }
}

export function subscribe(listener) {
    subscribers.add(listener);
    return () => subscribers.delete(listener);
}

export function loadDraftSnapshot() {
    try {
        const raw = localStorage.getItem(draftKey());
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
}

export function clearDraftSnapshot() {
    try {
        localStorage.removeItem(draftKey());
    } catch {
        // ignore
    }
}

export function updateState(patch, options) {
    const safeOptions = options || {};
    Object.assign(State, patch);
    recomputeDirty();
    if (State.initialized && safeOptions.persistDraft !== false) {
        persistDraft();
    }
    emit();
}

export function setServerSnapshot(payload) {
    const source = payload && typeof payload === "object" ? payload : {};
    State.funnel = cloneValue(source.funnel);
    State.lookups = normalizeLookups(source.lookups);
    State.stepMeta = normalizeMeta(source.step);
    State.originalMeta = cloneValue(State.stepMeta);
    State.config = normalizeStepConfig(source.step ? source.step.config : {});
    State.originalConfig = cloneValue(State.config);
    State.loading = false;
    State.isDirty = false;
    State.status = { tone: "neutral", message: "" };
    emit();
}

export function applyDraftSnapshot(snapshot) {
    if (!snapshot) return;
    if (snapshot.config) {
        State.config = normalizeStepConfig(snapshot.config);
    }
    if (snapshot.stepMeta) {
        State.stepMeta = normalizeMeta(snapshot.stepMeta);
    }
    if (snapshot.emulation) {
        State.emulation = snapshot.emulation;
    }
    recomputeDirty();
    emit();
    if (State.initialized) {
        persistDraft();
    }
}

export function markInitialized() {
    State.initialized = true;
    recomputeDirty();
    if (State.isDirty) {
        persistDraft();
    } else {
        clearDraftSnapshot();
    }
    emit();
}

export function setSaving(isSaving) {
    State.saving = isSaving;
    emit();
}

export function setStatus(message, tone) {
    State.status = {
        message: message || "",
        tone: tone || "neutral",
    };
    emit();
}

export function markSaved() {
    State.originalConfig = cloneValue(State.config);
    State.originalMeta = cloneValue(State.stepMeta);
    State.isDirty = false;
    State.saving = false;
    State.status = { tone: "success", message: "Сохранено" };
    clearDraftSnapshot();
    emit();
}