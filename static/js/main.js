document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".delete-form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!confirm("Opravdu chcete tento záznam smazat?")) {
                event.preventDefault();
            }
        });
    });

    const addItemBtn = document.getElementById("addItemBtn");
    const itemsContainer = document.getElementById("itemsContainer");
    const itemTemplate = document.getElementById("itemTemplate");

    if (addItemBtn && itemsContainer && itemTemplate) {
        addItemBtn.addEventListener("click", () => {
            itemsContainer.appendChild(itemTemplate.content.cloneNode(true));
        });

        itemsContainer.addEventListener("click", (event) => {
            if (event.target.classList.contains("remove-item")) {
                const rows = itemsContainer.querySelectorAll(".item-row");
                if (rows.length > 1) {
                    event.target.closest(".item-row").remove();
                }
            }
        });
    }

    const durationInputs = document.querySelectorAll(".duration-input");
    const durationPreview = document.getElementById("durationPreview");

    function updateDurationPreview() {
        const start = document.querySelector('input[name="time_from"]')?.value;
        const end = document.querySelector('input[name="time_to"]')?.value;
        if (!start || !end || !durationPreview) return;

        const startDate = new Date(`2000-01-01T${start}:00`);
        const endDate = new Date(`2000-01-01T${end}:00`);
        const diff = (endDate - startDate) / 3600000;
        durationPreview.value = diff > 0 ? `${diff.toFixed(2)} hodin` : "Čas do musí být větší než čas od";
    }

    durationInputs.forEach((input) => input.addEventListener("input", updateDurationPreview));
});
