const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("video-input");
const selectedFile = document.getElementById("selected-file");
const form = document.getElementById("converter-form");
const statusEl = document.getElementById("status");
const convertBtn = document.getElementById("convert-btn");
const formatSelect = document.getElementById("format-select");
const customFormatWrap = document.getElementById("custom-format-wrap");
const customFormatInput = document.getElementById("custom-format");
const outputFormatInput = document.getElementById("output-format");
const progressPanel = document.getElementById("progress-panel");
const progressFill = document.getElementById("progress-fill");
const progressSummary = document.getElementById("progress-summary");
const remainingCountEl = document.getElementById("remaining-count");
const etaTextEl = document.getElementById("eta-text");
const resultsPanel = document.getElementById("results-panel");
const resultsList = document.getElementById("results-list");
const bulkDownloadSelect = document.getElementById("bulk-download-select");

let pollingTimerId = null;
let activeJobId = null;
let activeZipUrl = null;

function setStatus(message, tone = "") {
    statusEl.textContent = message;
    statusEl.classList.remove("error", "success");
    if (tone) {
        statusEl.classList.add(tone);
    }
}

function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) {
        return "--";
    }
    const value = Math.max(0, Number(seconds));
    const mins = Math.floor(value / 60);
    const secs = value % 60;
    if (mins > 0) {
        return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
}

function clearPolling() {
    if (pollingTimerId) {
        window.clearInterval(pollingTimerId);
        pollingTimerId = null;
    }
}

function resetResultsUi() {
    progressPanel.classList.add("hidden");
    resultsPanel.classList.add("hidden");
    resultsList.innerHTML = "";
    progressFill.style.width = "0%";
    progressSummary.textContent = "0% complete";
    remainingCountEl.textContent = "Remaining: 0";
    etaTextEl.textContent = "ETA: --";
    bulkDownloadSelect.value = "none";
    activeZipUrl = null;
}

function renderResults(files) {
    resultsList.innerHTML = "";
    files.forEach((file) => {
        const row = document.createElement("li");
        row.className = "result-item";

        const left = document.createElement("div");
        left.className = "result-left";

        const original = document.createElement("p");
        original.className = "result-original";
        original.textContent = file.original_name;

        const meta = document.createElement("p");
        meta.className = "result-meta";
        if (file.status === "completed") {
            meta.textContent = `Ready: ${file.output_name}`;
        } else if (file.status === "failed") {
            meta.textContent = `Failed: ${file.error || "Conversion error"}`;
        } else if (file.status === "processing") {
            meta.textContent = "Converting...";
        } else {
            meta.textContent = "Queued";
        }

        left.appendChild(original);
        left.appendChild(meta);

        const right = document.createElement("div");
        right.className = "result-right";
        if (file.status === "completed" && file.download_url) {
            const link = document.createElement("a");
            link.className = "download-link";
            link.href = file.download_url;
            link.textContent = "[DL] Download";
            right.appendChild(link);
        }

        row.appendChild(left);
        row.appendChild(right);
        resultsList.appendChild(row);
    });

    resultsPanel.classList.remove("hidden");
}

function updateProgressUi(payload) {
    progressPanel.classList.remove("hidden");

    const progress = payload.progress_percent || 0;
    progressFill.style.width = `${progress}%`;
    progressSummary.textContent = `${progress}% complete (${payload.completed}/${payload.total} done, ${payload.failed} failed)`;
    remainingCountEl.textContent = `Remaining: ${payload.remaining}`;
    etaTextEl.textContent = `ETA: ${formatDuration(payload.eta_seconds)}`;

    activeZipUrl = payload.zip_url;
    renderResults(payload.files || []);
}

async function pollJobStatus(statusUrl) {
    try {
        const response = await fetch(statusUrl, { method: "GET" });
        if (!response.ok) {
            setStatus("Could not fetch conversion progress.", "error");
            clearPolling();
            convertBtn.disabled = false;
            return;
        }

        const payload = await response.json();
        updateProgressUi(payload);

        if (payload.status === "completed") {
            setStatus("All conversions completed. Use the list below to download files.", "success");
            clearPolling();
            convertBtn.disabled = false;
        } else if (payload.status === "completed_with_errors") {
            setStatus("Conversion finished with some errors. Check file list below.", "error");
            clearPolling();
            convertBtn.disabled = false;
        } else if (payload.status === "failed") {
            setStatus("Conversion failed for all files.", "error");
            clearPolling();
            convertBtn.disabled = false;
        }
    } catch (error) {
        setStatus("Network error while checking progress.", "error");
        clearPolling();
        convertBtn.disabled = false;
    }
}

function updateSelectedFileLabel() {
    const files = fileInput.files;
    if (!files || !files.length) {
        selectedFile.textContent = "No file selected";
        return;
    }

    if (files.length === 1) {
        const file = files[0];
        selectedFile.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
        return;
    }

    const totalKb = Array.from(files).reduce((sum, file) => sum + Math.round(file.size / 1024), 0);
    selectedFile.textContent = `${files.length} files selected (${totalKb} KB total)`;
}

function toggleCustomFormat() {
    const isCustom = formatSelect.value === "custom";
    customFormatWrap.classList.toggle("hidden", !isCustom);

    if (isCustom) {
        customFormatInput.setAttribute("required", "required");
        outputFormatInput.value = customFormatInput.value.trim().toLowerCase();
    } else {
        customFormatInput.removeAttribute("required");
        outputFormatInput.value = formatSelect.value;
    }
}

function getCookie(name) {
    const cookieValue = document.cookie
        .split(";")
        .map((item) => item.trim())
        .find((item) => item.startsWith(`${name}=`));
    return cookieValue ? decodeURIComponent(cookieValue.split("=")[1]) : "";
}

["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.add("is-dragging");
    });
});

["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.remove("is-dragging");
    });
});

dropZone.addEventListener("drop", (event) => {
    const files = event.dataTransfer && event.dataTransfer.files;
    if (!files || !files.length) {
        return;
    }

    const dataTransfer = new DataTransfer();
    Array.from(files).forEach((file) => {
        dataTransfer.items.add(file);
    });
    fileInput.files = dataTransfer.files;
    updateSelectedFileLabel();
});

fileInput.addEventListener("change", updateSelectedFileLabel);
formatSelect.addEventListener("change", toggleCustomFormat);
customFormatInput.addEventListener("input", () => {
    outputFormatInput.value = customFormatInput.value.trim().toLowerCase();
});

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!fileInput.files || !fileInput.files.length) {
        setStatus("Choose one or more videos first.", "error");
        return;
    }

    toggleCustomFormat();

    const format = outputFormatInput.value.replace(/^\./, "").trim().toLowerCase();
    if (!/^[a-z0-9]{2,10}$/.test(format)) {
        setStatus("Enter a valid format using letters and numbers only.", "error");
        return;
    }

    outputFormatInput.value = format;

    const fileCount = fileInput.files.length;

    clearPolling();
    resetResultsUi();
    convertBtn.disabled = true;
    setStatus(`Starting conversion job for ${fileCount} video${fileCount > 1 ? "s" : ""}...`);

    const formData = new FormData(form);

    try {
        const response = await fetch(form.action, {
            method: "POST",
            body: formData,
            headers: {
                "X-CSRFToken": getCookie("csrftoken"),
            },
        });

        if (!response.ok) {
            let errorMessage = "Conversion failed.";
            try {
                const data = await response.json();
                if (data.error) {
                    errorMessage = data.error;
                }
            } catch {
                // Keep default message.
            }
            setStatus(errorMessage, "error");
            return;
        }

        const startPayload = await response.json();
        activeJobId = startPayload.job_id;
        setStatus("Conversion in progress. You can track remaining files and ETA below.");

        const statusUrl = startPayload.status_url;
        await pollJobStatus(statusUrl);
        pollingTimerId = window.setInterval(() => {
            pollJobStatus(statusUrl);
        }, 1500);
    } catch (error) {
        setStatus("Network error while converting. Try again.", "error");
        convertBtn.disabled = false;
    }
});

bulkDownloadSelect.addEventListener("change", () => {
    if (bulkDownloadSelect.value === "zip" && activeZipUrl && activeJobId) {
        window.location.href = activeZipUrl;
    }
    bulkDownloadSelect.value = "none";
});

toggleCustomFormat();
updateSelectedFileLabel();
resetResultsUi();
