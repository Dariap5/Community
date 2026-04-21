async function requestJson(path, options) {
    const requestOptions = options || {};
    const response = await fetch(path, {
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
            ...(requestOptions.headers || {}),
        },
        method: requestOptions.method || "GET",
        body: requestOptions.body === undefined ? undefined : JSON.stringify(requestOptions.body),
    });

    const contentType = response.headers.get("content-type") || "";
    let payload = null;
    if (contentType.indexOf("application/json") !== -1) {
        try {
            payload = await response.json();
        } catch {
            payload = null;
        }
    } else {
        const text = await response.text();
        payload = text ? { raw: text } : null;
    }

    if (!response.ok) {
        const error = new Error(extractApiMessage(payload, `HTTP ${response.status}`));
        error.payload = payload;
        error.status = response.status;
        throw error;
    }

    return payload;
}

export function extractApiMessage(payload, fallback) {
    const fallbackMessage = fallback || "Не удалось выполнить запрос";
    if (!payload) return fallbackMessage;
    if (typeof payload === "string") return payload;
    if (payload.error && payload.error.message) return payload.error.message;
    if (payload.detail && typeof payload.detail === "object" && payload.detail.message) return payload.detail.message;
    if (payload.detail && typeof payload.detail === "string") return payload.detail;
    if (payload.message) return payload.message;
    if (payload.raw) return payload.raw;
    return fallbackMessage;
}

export async function loadFunnel(funnelId) {
    return requestJson(`/api/funnels/${funnelId}`);
}

export async function loadStep(funnelId, stepId) {
    return requestJson(`/api/funnels/${funnelId}/steps/${stepId}`);
}

export async function loadProducts() {
    const payload = await requestJson("/admin/api/products");
    return payload && payload.items ? payload.items : [];
}

export async function loadTracks() {
    const payload = await requestJson("/admin/api/tracks");
    return payload && payload.items ? payload.items : [];
}

export async function saveStep(funnelId, stepId, data) {
    return requestJson(`/api/funnels/${funnelId}/steps/${stepId}`, {
        method: "PUT",
        body: data,
    });
}

export async function sendTestToAdmin(funnelId, stepId, emulation) {
    return requestJson(`/api/funnels/${funnelId}/steps/${stepId}/test`, {
        method: "POST",
        body: { emulation },
    });
}