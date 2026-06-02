const $ = (selector) => document.querySelector(selector);
const state = { tickets: [], selectedTicketId: null, simulationStartedAt: null, simulationTimer: null };

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showFlash(message = "", isError = false) {
  const flash = $("#flash");
  flash.textContent = message;
  flash.style.color = isError ? "#a33924" : "#176b57";
}

function setBusy(button, busy, busyText = "Working...") {
  if (!button) return;
  if (!button.dataset.idleText) button.dataset.idleText = button.textContent;
  button.disabled = busy;
  button.classList.toggle("is-busy", busy);
  button.textContent = busy ? busyText : button.dataset.idleText;
}

function setSimulationStatus(message = "", stateName = "") {
  const status = $("#simulate-status");
  status.textContent = message;
  status.className = `processing ${stateName || "hidden"}`;
}

function startSimulation(button, channel) {
  clearInterval(state.simulationTimer);
  state.simulationStartedAt = Date.now();
  setBusy(button, true, "Processing message...");
  $("#simulate-summary").className = "simulation-summary hidden";
  $("#simulate-result").textContent = "Waiting for the orchestration response...";
  const update = () => {
    const elapsed = Math.floor((Date.now() - state.simulationStartedAt) / 1000);
    setSimulationStatus(
      `${channel} message submitted ${elapsed}s ago. Running identity resolution, AI classification, retrieval, and ticket workflow...`,
      "active",
    );
  };
  update();
  state.simulationTimer = setInterval(update, 1000);
}

function finishSimulation(button, result, channel) {
  clearInterval(state.simulationTimer);
  state.simulationTimer = null;
  const elapsed = ((Date.now() - state.simulationStartedAt) / 1000).toFixed(1);
  const summary = $("#simulate-summary");
  summary.className = "simulation-summary success";
  summary.innerHTML = `
    <strong>${escapeHtml(channel)} message processed successfully</strong>
    <span>Intent: ${escapeHtml(result.intent)} | Resolution: ${result.resolved ? "resolved" : "ticket follow-up required"}</span>
    <span>Outbound: ${escapeHtml(result.outbound_status)} | Ticket: ${escapeHtml(result.ticket_id || "none")} | Time: ${escapeHtml(elapsed)}s</span>
  `;
  $("#simulate-result").textContent = JSON.stringify(result, null, 2);
  setSimulationStatus("Completed. The inbound message was persisted and the outbound reply was sent.", "success");
  setBusy(button, false);
  showFlash(`${channel} simulation completed.`);
  loadDashboard();
}

function failSimulation(button, error) {
  clearInterval(state.simulationTimer);
  state.simulationTimer = null;
  $("#simulate-result").textContent = error.message;
  setSimulationStatus(`Simulation failed: ${error.message}`, "error");
  setBusy(button, false);
  showFlash(error.message, true);
}

function adminKey() {
  return $("#admin-key").value.trim();
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (adminKey()) headers["x-admin-key"] = adminKey();
  if (options.body) headers["content-type"] = "application/json";

  const response = await fetch(path, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function renderCrm(status) {
  $("#crm-provider").textContent = status.provider || "disabled";
  $("#crm-detail").textContent = status.configured
    ? "Configured and available for ticket synchronization."
    : "Local ticket persistence is active. External CRM sync is not configured.";
}

function renderTickets(tickets) {
  state.tickets = tickets;
  $("#ticket-total").textContent = `${tickets.length} ticket${tickets.length === 1 ? "" : "s"}`;
  $("#ticket-detail").textContent = tickets.length
    ? `${tickets.filter((ticket) => ticket.status !== "resolved").length} ticket(s) still active.`
    : "No tickets have been escalated.";

  const body = $("#tickets-body");
  if (!tickets.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">No tickets found.</td></tr>';
    return;
  }

  body.innerHTML = tickets.map((ticket) => `
    <tr data-ticket-id="${escapeHtml(ticket.ticket_id)}" class="${ticket.ticket_id === state.selectedTicketId ? "selected" : ""}">
      <td><strong>${escapeHtml(ticket.ticket_id)}</strong><br><span class="muted">${escapeHtml(ticket.assigned_team)}</span></td>
      <td><span class="pill">${escapeHtml(ticket.status)}</span></td>
      <td>${escapeHtml(ticket.priority)}</td>
      <td>${escapeHtml(ticket.intent)}</td>
      <td>${escapeHtml(ticket.sla_due_at || "Not set")}</td>
      <td>${escapeHtml(ticket.crm_sync_status || "not_configured")}</td>
    </tr>
  `).join("");
}

function renderAudit(events) {
  const container = $("#audit-events");
  if (!events.length) {
    container.innerHTML = '<p class="empty">No audit events found.</p>';
    return;
  }
  container.innerHTML = events.slice(-40).reverse().map((event) => `
    <div class="timeline-item">
      <strong>${escapeHtml(event.event_type)}</strong>
      <span>${escapeHtml(event.created_at)} · ${escapeHtml(event.channel || "system")}</span>
      <br><span class="muted">${escapeHtml(event.ticket_id || event.message_id || event.correlation_id || "")}</span>
    </div>
  `).join("");
}

function renderTicket(ticket, events) {
  const externalLink = /^https?:\/\//.test(ticket.external_ticket_url || "")
    ? `<a href="${escapeHtml(ticket.external_ticket_url)}" target="_blank" rel="noopener">Open external ticket</a>`
    : "Local ticket only";
  $("#ticket-detail-panel").innerHTML = `
    <h2>${escapeHtml(ticket.ticket_id)}</h2>
    <div class="detail-grid">
      <div><strong>Status</strong>${escapeHtml(ticket.status)}</div>
      <div><strong>Priority</strong>${escapeHtml(ticket.priority)}</div>
      <div><strong>Intent</strong>${escapeHtml(ticket.intent)}</div>
      <div><strong>CRM sync</strong>${escapeHtml(ticket.crm_sync_status || "not_configured")}</div>
      <div><strong>Approval</strong>${escapeHtml(ticket.approval_status || "not_required")}</div>
      <div><strong>SLA due</strong>${escapeHtml(ticket.sla_due_at || "Not set")}</div>
    </div>
    <p>${escapeHtml(ticket.description)}</p>
    <p class="muted">${externalLink}</p>
    <div class="actions">
      <label>Status
        <select id="ticket-status">
          ${["open", "in_progress", "resolved"].map((value) =>
            `<option value="${value}" ${ticket.status === value ? "selected" : ""}>${value}</option>`
          ).join("")}
        </select>
      </label>
      <button id="update-status" type="button">Update status</button>
      <label>Internal / CRM comment
        <textarea id="ticket-comment" rows="3" placeholder="Add an operational note"></textarea>
      </label>
      <button id="add-comment" type="button">Add comment</button>
      <button id="sync-ticket" type="button" class="secondary">Sync ticket to CRM</button>
    </div>
    <h2>Ticket events</h2>
    <div class="timeline">
      ${events.slice().reverse().map((event) => `
        <div class="timeline-item">
          <strong>${escapeHtml(event.event_type)}</strong>
          <span>${escapeHtml(event.created_at)}</span>
        </div>
      `).join("") || '<p class="empty">No ticket events recorded.</p>'}
    </div>
  `;

  $("#update-status").addEventListener("click", updateTicketStatus);
  $("#add-comment").addEventListener("click", addTicketComment);
  $("#sync-ticket").addEventListener("click", syncTicket);
}

async function loadTicket(ticketId) {
  state.selectedTicketId = ticketId;
  document.querySelectorAll("[data-ticket-id]").forEach((row) => {
    row.classList.toggle("selected", row.dataset.ticketId === ticketId);
  });
  $("#ticket-detail-panel").innerHTML = '<p class="loading-line">Loading ticket details...</p>';
  try {
    const [ticket, events] = await Promise.all([
      api(`/admin/tickets/${encodeURIComponent(ticketId)}`),
      api(`/admin/tickets/${encodeURIComponent(ticketId)}/events`),
    ]);
    renderTicket(ticket, events);
  } catch (error) {
    showFlash(error.message, true);
  }
}

async function loadDashboard() {
  if (!adminKey()) {
    showFlash("Enter ADMIN_API_KEY to load the operations dashboard.", true);
    return;
  }
  const button = $("#refresh");
  setBusy(button, true, "Refreshing...");
  try {
    const [crm, tickets, audit] = await Promise.all([
      api("/admin/crm/status"),
      api("/admin/tickets"),
      api("/admin/audit-events"),
    ]);
    renderCrm(crm);
    renderTickets(tickets);
    renderAudit(audit);
    showFlash("Dashboard refreshed.");
    if (state.selectedTicketId) await loadTicket(state.selectedTicketId);
  } catch (error) {
    showFlash(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function updateTicketStatus() {
  const button = $("#update-status");
  setBusy(button, true, "Updating...");
  try {
    await api(`/admin/tickets/${encodeURIComponent(state.selectedTicketId)}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: $("#ticket-status").value }),
    });
    showFlash("Ticket status updated.");
    await loadDashboard();
  } catch (error) {
    showFlash(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function addTicketComment() {
  const comment = $("#ticket-comment").value.trim();
  if (!comment) return showFlash("Enter a ticket comment first.", true);
  const button = $("#add-comment");
  setBusy(button, true, "Adding...");
  try {
    await api(`/admin/tickets/${encodeURIComponent(state.selectedTicketId)}/comments`, {
      method: "POST",
      body: JSON.stringify({ comment, actor: "admin-ui" }),
    });
    showFlash("Ticket comment added.");
    await loadDashboard();
  } catch (error) {
    showFlash(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function syncTicket() {
  const button = $("#sync-ticket");
  setBusy(button, true, "Syncing...");
  try {
    await api(`/admin/tickets/${encodeURIComponent(state.selectedTicketId)}/sync`, { method: "POST" });
    showFlash("Ticket CRM sync attempted.");
    await loadDashboard();
  } catch (error) {
    showFlash(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function simulateInbound(event) {
  event.preventDefault();
  const signature = $("#test-signature").value.trim();
  const button = $("#simulate-submit");
  sessionStorage.setItem("cx-test-signature", signature);
  startSimulation(button, "WhatsApp");
  try {
    const result = await api("/test/whatsapp/inbound-simulate", {
      method: "POST",
      headers: { "x-test-whatsapp-signature": signature },
      body: JSON.stringify({
        from: $("#sim-phone").value.trim(),
        text: $("#sim-message").value.trim(),
      }),
    });
    finishSimulation(button, result, "WhatsApp");
  } catch (error) {
    failSimulation(button, error);
  }
}

async function simulateEmailInbound(event) {
  event.preventDefault();
  const secret = $("#email-secret").value.trim();
  const button = $("#email-simulate-submit");
  sessionStorage.setItem("cx-email-secret", secret);
  startSimulation(button, "Email");
  try {
    const result = await api("/integrations/email/webhook", {
      method: "POST",
      headers: { "x-email-webhook-secret": secret },
      body: JSON.stringify({
        from_email: $("#sim-email").value.trim(),
        subject: $("#sim-email-subject").value.trim(),
        body: $("#sim-email-message").value.trim(),
      }),
    });
    finishSimulation(button, result, "Email");
  } catch (error) {
    failSimulation(button, error);
  }
}

function selectChannel(channel) {
  document.querySelectorAll(".channel-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.channel === channel);
  });
  $("#whatsapp-simulate-form").classList.toggle("hidden", channel !== "whatsapp");
  $("#email-simulate-form").classList.toggle("hidden", channel !== "email");
}

$("#save-key").addEventListener("click", () => {
  sessionStorage.setItem("cx-admin-key", adminKey());
  const button = $("#save-key");
  setBusy(button, true, "Connecting...");
  loadDashboard().finally(() => setBusy(button, false));
});
$("#refresh").addEventListener("click", loadDashboard);
$("#whatsapp-simulate-form").addEventListener("submit", simulateInbound);
$("#email-simulate-form").addEventListener("submit", simulateEmailInbound);
document.querySelectorAll(".channel-tab").forEach((tab) => {
  tab.addEventListener("click", () => selectChannel(tab.dataset.channel));
});
$("#tickets-body").addEventListener("click", (event) => {
  const row = event.target.closest("[data-ticket-id]");
  if (row) loadTicket(row.dataset.ticketId);
});

$("#admin-key").value = sessionStorage.getItem("cx-admin-key") || "";
$("#test-signature").value = sessionStorage.getItem("cx-test-signature") || "";
$("#email-secret").value = sessionStorage.getItem("cx-email-secret") || "";
if (adminKey()) loadDashboard();
