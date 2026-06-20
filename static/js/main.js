document.addEventListener("DOMContentLoaded", () => {
    const pad = (value) => String(value).padStart(2, "0");
    const formatElapsed = (startText) => {
        if (!startText) return "00:00";
        const start = new Date(startText.replace(" ", "T"));
        if (Number.isNaN(start.getTime())) return "00:00";
        const diffSeconds = Math.max(0, Math.floor((Date.now() - start.getTime()) / 1000));
        const hours = Math.floor(diffSeconds / 3600);
        const minutes = Math.floor((diffSeconds % 3600) / 60);
        return `${pad(hours)}:${pad(minutes)}`;
    };

    const activeStart = document.body.dataset.activeStart;
    const timerTargets = [document.getElementById("activeShiftTimer"), ...document.querySelectorAll(".live-duration")].filter(Boolean);
    const refreshTimers = () => timerTargets.forEach((target) => target.textContent = formatElapsed(activeStart));
    if (activeStart && timerTargets.length) {
        refreshTimers();
        setInterval(refreshTimers, 30000);
    }

    document.querySelectorAll(".delete-form").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!confirm("Opravdu chcete tento záznam smazat?")) event.preventDefault();
        });
    });

    const discordModalElement = document.getElementById("discordModal");
    const discordText = document.getElementById("discordMessageText");
    const clipboardStatus = document.getElementById("clipboardStatus");
    const manualCopyBtn = document.getElementById("manualCopyBtn");
    const afterEndRedirect = document.getElementById("afterEndRedirect");
    const discordModal = discordModalElement ? new bootstrap.Modal(discordModalElement) : null;

    async function copyDiscordMessage(text, successMessage, failureMessage) {
        discordText.value = text;
        try {
            await navigator.clipboard.writeText(text);
            clipboardStatus.textContent = successMessage;
        } catch (error) {
            clipboardStatus.textContent = failureMessage;
        }
        discordModal?.show();
    }

    document.getElementById("endShiftBtn")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
            const response = await fetch(button.dataset.endUrl, { method: "POST", headers: { "X-Requested-With": "fetch" } });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.message || "Směnu se nepodařilo ukončit.");
            if (afterEndRedirect) afterEndRedirect.href = data.redirect_url;
            await copyDiscordMessage(data.message, "Discord zpráva byla zkopírována do schránky.", "Automatické kopírování selhalo. Použijte tlačítko Zkopírovat ručně.");
        } catch (error) {
            alert(error.message);
            button.disabled = false;
        }
    });

    manualCopyBtn?.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(discordText.value);
            clipboardStatus.textContent = "Discord zpráva byla zkopírována ručně.";
        } catch (error) {
            discordText.select();
            clipboardStatus.textContent = "Kopírování stále selhává. Označte text a zkopírujte ho klávesami Ctrl+C.";
        }
    });

    document.querySelectorAll(".show-discord").forEach((button) => {
        button.addEventListener("click", () => {
            discordText.value = button.dataset.message;
            clipboardStatus.textContent = "Uložená Discord zpráva.";
            discordModal?.show();
        });
    });

    const addItemBtn = document.getElementById("addItemBtn");
    const itemsContainer = document.getElementById("itemsContainer");
    const itemTemplate = document.getElementById("itemTemplate");
    const totalPrice = document.getElementById("totalPrice");
    const totalWeight = document.getElementById("totalWeight");

    function rowTotals(row) {
        const quantity = parseFloat(row.querySelector(".quantity-input")?.value || "0") || 0;
        const price = parseFloat(row.querySelector(".price-input")?.value || "0") || 0;
        const weight = parseFloat(row.querySelector(".weight-input")?.value || "0") || 0;
        const linePrice = quantity * price;
        const lineWeight = quantity * weight;
        const total = row.querySelector(".item-total");
        if (total) total.textContent = `Řádek: $${linePrice.toFixed(2)} | ${lineWeight.toFixed(0)}g`;
        return { linePrice, lineWeight };
    }

    function recalculatePurchase() {
        if (!itemsContainer) return;
        let price = 0;
        let weight = 0;
        itemsContainer.querySelectorAll(".item-row").forEach((row) => {
            const totals = rowTotals(row);
            price += totals.linePrice;
            weight += totals.lineWeight;
        });
        if (totalPrice) totalPrice.textContent = `$${price.toFixed(2)}`;
        if (totalWeight) totalWeight.textContent = `${weight.toFixed(0)}g`;
    }

    function fillCatalogDefaults(select) {
        const option = select.selectedOptions[0];
        const row = select.closest(".item-row");
        if (!option || !row) return;
        const priceInput = row.querySelector(".price-input");
        const weightInput = row.querySelector(".weight-input");
        if (priceInput) priceInput.value = option.dataset.price || 0;
        if (weightInput) weightInput.value = option.dataset.weight || 0;
        recalculatePurchase();
    }

    if (addItemBtn && itemsContainer && itemTemplate) {
        addItemBtn.addEventListener("click", () => {
            itemsContainer.appendChild(itemTemplate.content.cloneNode(true));
            recalculatePurchase();
        });
        itemsContainer.addEventListener("click", (event) => {
            if (event.target.classList.contains("remove-item")) {
                const rows = itemsContainer.querySelectorAll(".item-row");
                if (rows.length > 1) event.target.closest(".item-row").remove();
                recalculatePurchase();
            }
        });
        itemsContainer.addEventListener("input", recalculatePurchase);
        itemsContainer.addEventListener("change", (event) => {
            if (event.target.classList.contains("item-select")) fillCatalogDefaults(event.target);
            recalculatePurchase();
        });
        recalculatePurchase();
    }
});
