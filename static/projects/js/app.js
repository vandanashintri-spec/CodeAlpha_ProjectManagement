const menuToggle = document.getElementById("menu-toggle");
const sidebar = document.getElementById("sidebar");

if (menuToggle && sidebar) {
    menuToggle.addEventListener("click", () => {
        const isOpen = sidebar.classList.toggle("is-open");
        menuToggle.setAttribute("aria-expanded", String(isOpen));
    });
}

const boardMessage = document.querySelector("[data-board-message]");
let draggedCard = null;

function refreshColumn(column) {
    const list = column.querySelector(".task-list");
    const cards = list.querySelectorAll("[data-task-card]");
    column.querySelector(".column-count").textContent = cards.length;
    const emptyState = list.querySelector(".column-empty");
    if (cards.length && emptyState) {
        emptyState.remove();
    } else if (!cards.length && !emptyState) {
        const empty = document.createElement("div");
        empty.className = "column-empty";
        empty.textContent = "No tasks here yet.";
        list.appendChild(empty);
    }
}

function moveCard(card, status) {
    const destination = document.querySelector(`[data-column-status="${status}"]`);
    const source = card.closest("[data-board-column]");
    if (!destination || !source) {
        return;
    }
    const previousStatus = card.dataset.status;
    destination.querySelector(".task-list").appendChild(card);
    card.dataset.status = status;
    card.querySelector("[data-status-form] select").value = status;
    refreshColumn(source);
    if (source !== destination) {
        refreshColumn(destination);
    }
    const progressPanel = document.querySelector("[data-total-tasks]");
    if (progressPanel && source !== destination) {
        const total = Number(progressPanel.dataset.totalTasks);
        const completedElement = progressPanel.querySelector("[data-completed-count]");
        const progressElement = progressPanel.querySelector("[data-project-progress]");
        const progressBar = progressPanel.querySelector("[data-progress-bar]");
        let completed = Number(completedElement.textContent);
        if (previousStatus === "completed") {
            completed -= 1;
        }
        if (status === "completed") {
            completed += 1;
        }
        const progress = total ? Math.round((completed * 100) / total) : 0;
        completedElement.textContent = completed;
        progressElement.textContent = progress;
        progressBar.style.width = progress + "%";
    }
}

async function saveTaskStatus(form, status) {
    const card = form.closest("[data-task-card]");
    const select = form.querySelector("select[name='status']");
    const previousStatus = card.dataset.status;
    if (status === previousStatus) {
        return;
    }
    select.disabled = true;
    if (boardMessage) {
        boardMessage.textContent = "Updating task status…";
        boardMessage.classList.remove("has-error");
    }
    try {
        const body = new FormData(form);
        body.set("status", status);
        const response = await fetch(form.action, {
            method: "POST",
            body,
            credentials: "same-origin",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": form.querySelector("[name='csrfmiddlewaretoken']").value,
            },
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || "You do not have permission to change this task.");
        }
        moveCard(card, result.status);
        if (boardMessage) {
            boardMessage.textContent = "Task moved to " + result.label + ".";
        }
    } catch (error) {
        select.value = previousStatus;
        if (boardMessage) {
            boardMessage.textContent = error.message || "Could not update the task. Please try again.";
            boardMessage.classList.add("has-error");
        }
    } finally {
        select.disabled = false;
    }
}

document.querySelectorAll("[data-status-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        saveTaskStatus(form, form.querySelector("select[name='status']").value);
    });
    form.querySelector("select[name='status']").addEventListener("change", (event) => {
        saveTaskStatus(form, event.target.value);
    });
});

document.querySelectorAll("[data-task-card]").forEach((card) => {
    card.addEventListener("dragstart", (event) => {
        draggedCard = card;
        card.classList.add("is-dragging");
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", card.dataset.status);
    });
    card.addEventListener("dragend", () => {
        card.classList.remove("is-dragging");
        draggedCard = null;
        document.querySelectorAll("[data-board-column]").forEach((column) => {
            column.classList.remove("drag-target");
        });
    });
});

document.querySelectorAll("[data-board-column]").forEach((column) => {
    column.addEventListener("dragover", (event) => {
        if (draggedCard) {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
            column.classList.add("drag-target");
        }
    });
    column.addEventListener("dragleave", (event) => {
        if (!column.contains(event.relatedTarget)) {
            column.classList.remove("drag-target");
        }
    });
    column.addEventListener("drop", (event) => {
        event.preventDefault();
        column.classList.remove("drag-target");
        if (draggedCard) {
            const form = draggedCard.querySelector("[data-status-form]");
            saveTaskStatus(form, column.dataset.columnStatus);
        }
    });
});
