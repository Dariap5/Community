export function enableDragDrop(container, options = {}) {
    const itemSelector = options.itemSelector || ".drag-item";
    const handleSelector = options.handleSelector || "[data-drag-handle]";
    const idKey = options.idKey || "itemId";
    const onReorder = options.onReorder || (() => {});
    let draggedItem = null;

    container.addEventListener("dragstart", (event) => {
        const item = event.target.closest(itemSelector);
        if (!item || !event.target.closest(handleSelector)) {
            return;
        }

        draggedItem = item;
        item.dataset.dragging = "true";
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", item.dataset[idKey] || "");
    });

    container.addEventListener("dragover", (event) => {
        if (!draggedItem) return;
        event.preventDefault();

        const afterElement = getDragAfterElement(container, event.clientY, itemSelector, draggedItem);
        const target = afterElement || null;
        if (target === null) {
            container.appendChild(draggedItem);
        } else {
            container.insertBefore(draggedItem, target);
        }
    });

    container.addEventListener("dragend", () => {
        if (!draggedItem) return;
        draggedItem.dataset.dragging = "false";
        draggedItem = null;
        onReorder(Array.from(container.querySelectorAll(itemSelector)).map((item) => item.dataset[idKey]).filter(Boolean));
    });
}

function getDragAfterElement(container, y, itemSelector, draggedItem) {
    const items = [...container.querySelectorAll(itemSelector)].filter((item) => item !== draggedItem);
    return items.reduce(
        (closest, child) => {
            const box = child.getBoundingClientRect();
            const offset = y - box.top - box.height / 2;
            if (offset < 0 && offset > closest.offset) {
                return { offset, element: child };
            }
            return closest;
        }, { offset: Number.NEGATIVE_INFINITY, element: null },
    ).element;
}