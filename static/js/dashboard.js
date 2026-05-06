let callRunning = false;

// ============================
// START AUTO CALL
// ============================
document.getElementById("startBtn").onclick = function () {

    fetch("/start_auto_call", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            showToast("Auto Calling Started", "success");
            callRunning = true;
        })
        .catch(err => console.error(err));
};


// ============================
// PAUSE
// ============================
document.getElementById("pauseBtn").onclick = function () {

    fetch("/pause_calling", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            showToast("Auto Calling Paused", "warning");
        });
};


// ============================
// RESUME
// ============================
document.getElementById("resumeBtn").onclick = function () {

    fetch("/resume_calling", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            showToast("Auto Calling Resumed", "success");
        });
};


// ============================
// CUT CALL
// ============================
document.getElementById("cutBtn").onclick = function () {

    fetch("/cut_call", { method: "POST" })
        .then(res => res.json())
        .then(data => {
            showToast("Call Ended", "warning");
        });
};


// ============================
// LIVE STATUS
// ============================
function loadCallStatus() {

    fetch("/call_status_ui")
        .then(res => res.json())
        .then(data => {
            document.getElementById("callStatus").innerText = data.status;
        });
}

setInterval(loadCallStatus, 2000);


// ============================
// LIVE TIMER (SERVER BASED)
// ============================
function updateTimerFromServer() {

    fetch("/call_timer")
        .then(res => res.json())
        .then(data => {

            let seconds = data.seconds;

            let min = Math.floor(seconds / 60);
            let sec = seconds % 60;

            document.getElementById("timer").innerText =
                `${String(min).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
        });
}

setInterval(updateTimerFromServer, 1000);


// ============================
// LIVE TRANSCRIPT
// ============================
function loadLatestMessages() {

    fetch("/latest_messages")
        .then(res => res.json())
        .then(data => {
            document.getElementById("userText").innerText = data.user || "--";
            document.getElementById("agentText").innerText = data.agent || "--";
            document.getElementById("leadScore").innerText = data.lead_score || "--";
        });
}

setInterval(loadLatestMessages, 2000);


// ============================
// LOAD CLIENTS TABLE
// ============================
function loadClients() {

    fetch("/get_clients")
        .then(res => res.json())
        .then(data => {

            const table = document.getElementById("clientTable");
            const thead = table.querySelector("thead");
            const tbody = table.querySelector("tbody");

            thead.innerHTML = "";
            tbody.innerHTML = "";

            if (!data.columns || data.columns.length === 0) {
                tbody.innerHTML = "<tr><td>No Clients Found</td></tr>";
                return;
            }

            // HEADER
            let headerRow = "<tr>";
            data.columns.forEach(col => {
                headerRow += `<th>${col}</th>`;
            });
            headerRow += "<th>Status</th></tr>";
            thead.innerHTML = headerRow;

            // ROWS
            data.clients.forEach((client, index) => {

                let row = "<tr>";

                data.columns.forEach(col => {

                    if (col.toLowerCase().includes("mobile")) {
                        row += `
                            <td>
                                <a href="#" 
                                   onclick="callSpecific('${client[col]}')"
                                   style="color:#facc15; font-weight:600;">
                                   ${client[col]}
                                </a>
                            </td>
                        `;
                    } else {
                        row += `<td>${client[col] || ""}</td>`;
                    }
                });

                let status =
                    index < data.current_index ? "Completed" :
                    index === data.current_index ? "Calling" :
                    "Pending";

                row += `<td>${status}</td></tr>`;

                tbody.innerHTML += row;
            });

        });
}

setInterval(loadClients, 5000);
loadClients();


// ============================
// CALL SPECIFIC
// ============================
function callSpecific(phone) {

    fetch("/call_specific", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ phone: phone })
    })
    .then(res => res.json())
    .then(data => {

        if (data.status === "Calling") {
            showToast("Calling " + phone, "success");
        } else {
            showToast("Error calling number", "warning");
        }

    });
}


// ============================
// TOAST MESSAGE
// ============================
function showToast(message, type="success") {

    let toast = document.getElementById("toast");

    if (!toast) return;

    toast.innerText = message;
    toast.className = "toast show " + type;

    setTimeout(() => {
        toast.className = "toast";
    }, 3000);
}



document.getElementById("leadScore").onclick = function () {

    fetch("/last_lead_details")
        .then(res => res.json())
        .then(data => {

            if (data.status !== "Success") {
                showToast("No data available", "warning");
                return;
            }

            const detailsBox = document.getElementById("leadDetails");
            detailsBox.innerHTML = "";

            const clientData = data.data;

            for (let key in clientData) {
                detailsBox.innerHTML += `
                    <p><strong>${key}:</strong> ${clientData[key]}</p>
                `;
            }

            document.getElementById("leadModal").style.display = "flex";
        });
};

// ============================
// UPLOAD CSV
// ============================
async function uploadCSV() {

    const fileInput = document.getElementById("csvFile");

    if (!fileInput.files.length) {
        showToast("Please select CSV file", "warning");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {

        showToast("Uploading CSV...", "success");

        const response = await fetch("/upload_csv", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        showToast(data.status, "success");

        // reload clients instantly
        loadClients();

    } catch (err) {
        console.error(err);
        showToast("CSV upload failed", "warning");
    }
}


// ============================
// DELETE ALL CLIENTS
// ============================
async function deleteAllClients() {

    const confirmDelete = confirm(
        "Are you sure you want to delete all clients?"
    );

    if (!confirmDelete) return;

    try {

        const response = await fetch("/delete_all_clients", {
            method: "DELETE"
        });

        const data = await response.json();

        showToast(data.status, "warning");

        loadClients();

    } catch (err) {
        console.error(err);
        showToast("Delete failed", "warning");
    }
}

async function loadTerminalLogs() {

    try {

        const response = await fetch("/terminal_logs");
        const data = await response.json();

        const terminal = document.getElementById("liveTerminal");

        terminal.innerHTML = data.logs.join("\n");

        // auto scroll
        terminal.scrollTop = terminal.scrollHeight;

    } catch(err) {
        console.error(err);
    }
}

setInterval(loadTerminalLogs, 1000);

function closeLeadModal() {
    document.getElementById("leadModal").style.display = "none";
}

