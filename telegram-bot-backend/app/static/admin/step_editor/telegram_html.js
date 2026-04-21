import { escapeHtml } from "./utils.js";

const ALLOWED_TAGS = new Set(["b", "strong", "i", "em", "u", "s", "code", "pre", "a", "blockquote", "br"]);

export function sanitizeTelegramHTML(text, parseMode) {
    if (parseMode === undefined) parseMode = "HTML";
    if (parseMode === "Markdown") {
        return sanitizeHtml(markdownToHtml(text));
    }
    return sanitizeHtml(text == null ? "" : String(text));
}

function sanitizeHtml(html) {
    const template = document.createElement("template");
    template.innerHTML = `<div>${html}</div>`;
    const root = template.content.firstElementChild;
    if (!root) {
        return "";
    }

    const container = document.createElement("div");
    Array.from(root.childNodes).forEach((node) => {
        container.appendChild(sanitizeNode(node));
    });
    return container.innerHTML.replace(/\n/g, "<br>");
}

function sanitizeNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
        return document.createTextNode(node.textContent || "");
    }

    if (node.nodeType !== Node.ELEMENT_NODE) {
        return document.createTextNode("");
    }

    const tag = node.tagName.toLowerCase();
    if (!ALLOWED_TAGS.has(tag)) {
        const fragment = document.createDocumentFragment();
        Array.from(node.childNodes).forEach((child) => {
            fragment.appendChild(sanitizeNode(child));
        });
        return fragment;
    }

    if (tag === "br") {
        return document.createElement("br");
    }

    const element = document.createElement(tag);
    if (tag === "a") {
        const href = node.getAttribute("href") || "";
        if (isSafeHref(href)) {
            element.setAttribute("href", href);
        }
        element.setAttribute("target", "_blank");
        element.setAttribute("rel", "noreferrer noopener");
    }

    Array.from(node.childNodes).forEach((child) => {
        element.appendChild(sanitizeNode(child));
    });
    return element;
}

function isSafeHref(href) {
    try {
        const url = new URL(href, window.location.origin);
        return ["http:", "https:", "tg:"].includes(url.protocol);
    } catch {
        return false;
    }
}

function markdownToHtml(text) {
    return escapeHtml(text == null ? "" : String(text))
        .replace(/\r\n/g, "\n")
        .replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>")
        .replace(/\*([^*\n]+)\*/g, "<b>$1</b>")
        .replace(/__([^_\n]+)__/g, "<i>$1</i>")
        .replace(/_([^_\n]+)_/g, "<i>$1</i>")
        .replace(/~~([^~\n]+)~~/g, "<s>$1</s>")
        .replace(/`([^`\n]+)`/g, "<code>$1</code>")
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
        .replace(/\n/g, "<br>");
}