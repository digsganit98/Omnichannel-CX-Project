const $ = (selector) => document.querySelector(selector);
const state = { tickets: [], selectedTicketId: null };

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
    <tr data-ticket-id="${escapeHtml(ticket.ticket_id)}">
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
  }
}

async function updateTicketStatus() {
  try {
    await api(`/admin/tickets/${encodeURIComponent(state.selectedTicketId)}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: $("#ticket-status").value }),
    });
    showFlash("Ticket status updated.");
    await loadDashboard();
  } catch (error) {
    showFlash(error.message, true);
  }
}

async function addTicketComment() {
  const comment = $("#ticket-comment").value.trim();
  if (!comment) return showFlash("Enter a ticket comment first.", true);
  try {
    await api(`/admin/tickets/${encodeURIComponent(state.selectedTicketId)}/comments`, {
      method: "POST",
      body: JSON.stringify({ comment, actor: "admin-ui" }),
    });
    showFlash("Ticket comment added.");
    await loadDashboard();
  } catch (error) {
    showFlash(error.message, true);
  }
}

async function syncTicket() {
  try {
    await api(`/admin/tickets/${encodeURIComponent(state.selectedTicketId)}/sync`, { method: "POST" });
    showFlash("Ticket CRM sync attempted.");
    await loadDashboard();
  } catch (error) {
    showFlash(error.message, true);
  }
}

async function simulateInbound(event) {
  event.preventDefault();
  const signature = $("#test-signature").value.trim();
  sessionStorage.setItem("cx-test-signature", signature);
  try {
    const result = await api("/test/whatsapp/inbound-simulate", {
      method: "POST",
      headers: { "x-test-whatsapp-signature": signature },
      body: JSON.stringify({
        from: $("#sim-phone").value.trim(),
        text: $("#sim-message").value.trim(),
      }),
    });
    $("#simulate-result").textContent = JSON.stringify(result, null, 2);
    showFlash("Simulated WhatsApp flow completed.");
    await loadDashboard();
  } catch (error) {
    $("#simulate-result").textContent = error.message;
    showFlash(error.message, true);
  }
}

$("#save-key").addEventListener("click", () => {
  sessionStorage.setItem("cx-admin-key", adminKey());
  loadDashboard();
});
$("#refresh").addEventListener("click", loadDashboard);
$("#simulate-form").addEventListener("submit", simulateInbound);
$("#tickets-body").addEventListener("click", (event) => {
  const row = event.target.closest("[data-ticket-id]");
  if (row) loadTicket(row.dataset.ticketId);
});

$("#admin-key").value = sessionStorage.getItem("cx-admin-key") || "";
$("#test-signature").value = sessionStorage.getItem("cx-test-signature") || "";
if (adminKey()) loadDashboard();
