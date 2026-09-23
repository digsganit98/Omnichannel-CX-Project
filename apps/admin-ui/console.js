// ═══════════════════════════════════════════════════════════════════════════
// The agent console - the page an admin lands on after signing in.
//
// Three views over the SAME endpoints the classic workspace uses:
//   My work     one case at a time. The ticket lanes are the same judgement the
//               Service Desk board makes (sdCaseState in app.js): a pending draft is
//               "To approve", an unanswered or re-opened case is "To reply", and a case
//               we answered and are now waiting on is "Waiting on customers".
//   All conversations  every conversation as one stream, each with a progress bar.
//   AI activity what the AI resolved on its own (tickets that stayed `logged`).
//   AI performance  the AI-performance numbers, derived in the browser from tickets, reply
//               drafts and the LLM usage summary. No endpoint computes them yet.
//
// Every button that says "send" really sends: it calls /admin/reply-drafts/{id}/send or
// /admin/conversations/{id}/reply, exactly the calls the classic workspace makes.
//
// Nothing here calls an LLM. The case summary and suggested actions (which do) stay in
// the classic workspace, one click away from each case.
// ═══════════════════════════════════════════════════════════════════════════
(function () {
'use strict';

var ICON = {
  whatsapp: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M4 20l1.3-4A8 8 0 1112 20a8 8 0 01-4-1z"/></svg>',
  email: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>',
  web_chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4z"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
  bulb: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6M10 21h4M12 3a6 6 0 00-3.5 10.9c.6.4 1 1.1 1 1.8V16h5v-.3c0-.7.4-1.4 1-1.8A6 6 0 0012 3z"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/></svg>',
  work: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v14H4z"/><path d="M4 13h4l2 3h4l2-3h4"/></svg>',
  ai: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 4v4M9.5 13h.01M14.5 13h.01"/></svg>',
  team: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 19V11M12 19V5M19 19v-5"/></svg>',
  desk: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v16"/></svg>',
  chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19h16M7 15l4-5 3 3 5-7"/></svg>',
  gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 00-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 00-2-1.2L14 3h-4l-.6 2.6a7 7 0 00-2 1.2l-2.3-.9-2 3.4 2 1.5A7 7 0 005 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.3-.9c.6.5 1.3.9 2 1.2L10 21h4l.6-2.6c.7-.3 1.4-.7 2-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"/></svg>',
  classic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/></svg>',
  out: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10"/></svg>'
};
var CH = {
  whatsapp: { label: 'WhatsApp', live: true },
  web_chat: { label: 'Web chat', live: true },
  email:    { label: 'Email', live: false },
  offer:    { label: 'WhatsApp & email', live: false }
};
function chMeta(c) { return CH[c] || { label: c ? String(c) : 'Unknown channel', live: false }; }

// The hold reason in words a person reads without a decoder. Codes are the ones
// review_gate.py writes (reason_code / ticket_decision.reason); the raw code stays visible
// in Details.
var WHY = {
  handoff_human_requested: 'The customer asked to speak to a person.',
  customer_requested_human: 'The customer asked to speak to a person.',
  handoff_service_failure_asserted: 'The customer says we\'ve let them down before, so a person should reply.',
  handoff_emergency: 'This looks time-critical, so a person should take it now.',
  handoff_distress: 'The customer seems distressed, so a person should reply.',
  handoff_approval_needed: 'The customer is asking for a decision that needs your approval.',
  approval_required: 'The customer is asking for a decision that needs your approval.',
  manual_review_required: 'This case needs a manual check.',
  no_live_banking_data: 'The AI couldn\'t confirm live account data.',
  high_urgency: 'Marked urgent, so a person should check before it goes out.',
  low_intent_confidence: 'The AI wasn\'t sure what the customer was asking.',
  repeated_unresolved_query: 'The customer has asked this before without a fix.',
  repeat_customer_new_issue: 'A returning customer with a new issue.',
  knowledge_not_found: 'The AI had no article that covers this question.',
  low_retrieval_confidence: 'The AI wasn\'t sure its answer was complete.',
  secondary_intent_manual_review: 'There\'s a second issue in the message that needs a person.',
  critical_escalation: 'A critical case, so a person should handle it.',
  assisted_resolution_required: 'The AI couldn\'t fetch everything the customer asked for.',
  L3: 'A critical case, so a person should handle it.',
  L2: 'The AI couldn\'t fetch everything the customer asked for.'
};
var WHY_SHORT = {
  low_retrieval_confidence: 'Unsure its answer was complete', knowledge_not_found: 'No article covered it',
  handoff_human_requested: 'Customer asked for a person', customer_requested_human: 'Customer asked for a person',
  approval_required: 'Needed an approval', handoff_approval_needed: 'Needed an approval',
  no_live_banking_data: 'Couldn\'t confirm live data', assisted_resolution_required: 'Couldn\'t fetch everything',
  L2: 'Couldn\'t fetch everything', L3: 'Critical case', critical_escalation: 'Critical case',
  handoff_service_failure_asserted: 'Customer said we failed them', handoff_emergency: 'Time-critical',
  handoff_distress: 'Customer in distress', low_intent_confidence: 'Unsure what was asked'
};
function codeOf(s) { return String(s || '').split(':')[0].trim(); }

// ── plumbing ────────────────────────────────────────────────────────────────
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
function $(s, r) { return (r || root).querySelector(s); }
function $$(s, r) { return Array.prototype.slice.call((r || root).querySelectorAll(s)); }
function me() { try { return JSON.parse(sessionStorage.getItem('cx-admin-user') || 'null') || {}; } catch (e) { return {}; } }
function actor() { return me().username || 'admin'; }
function firstName(n) { return String(n || '').split(/[\s._@-]/)[0] || n; }
function cap(s) { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1); }
function intentLabel(k) { return cap(String(k || 'general enquiry').replace(/_/g, ' ').replace(/\b(kyc|emi|upi|neft|otp)\b/gi, function (w) { return w.toUpperCase(); })); }
function ts(iso) { var t = iso ? new Date(iso).getTime() : NaN; return isNaN(t) ? null : t; }
function minsUntil(iso) { var t = ts(iso); return t == null ? null : Math.round((t - Date.now()) / 60000); }
function isToday(iso) { var t = ts(iso); if (t == null) return false; var d = new Date(t), n = new Date(); return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate(); }
function ago(iso) {
  var t = ts(iso); if (t == null) return '';
  var m = Math.round((Date.now() - t) / 60000);
  if (m < 1) return 'just now'; if (m < 60) return m + ' min ago';
  if (m < 1440) return Math.round(m / 60) + ' h ago';
  return Math.round(m / 1440) + ' d ago';
}
function fmtMin(m) { m = Math.abs(m); if (m >= 2880) return Math.round(m / 1440) + ' days'; var h = Math.floor(m / 60), mm = m % 60; return h ? (h + ' h' + (mm ? ' ' + mm + ' min' : '')) : (mm + ' min'); }
function median(a) { if (!a.length) return null; a = a.slice().sort(function (x, y) { return x - y; }); var i = Math.floor(a.length / 2); return a.length % 2 ? a[i] : (a[i - 1] + a[i]) / 2; }
function nameOf(c) {
  var dn = c && c.display_name;
  if (!dn || dn === 'None' || dn === 'null' || String(dn).indexOf('@') !== -1) return 'Unverified customer';
  return dn;
}

function headers() {
  var h = {}, t = sessionStorage.getItem('cx-admin-jwt') || '', k = sessionStorage.getItem('cx-admin-key') || '';
  if (t) h.Authorization = 'Bearer ' + t;
  if (k) h['x-admin-key'] = k;
  return h;
}
async function api(path, opts) {
  opts = opts || {};
  var h = Object.assign({}, headers(), opts.headers || {});
  if (opts.body) h['content-type'] = 'application/json';
  var r = await fetch(path, Object.assign({}, opts, { headers: h }));
  var data = await r.json().catch(function () { return {}; });
  if (!r.ok) { var e = new Error(data.detail || (r.status + ' ' + r.statusText)); e.status = r.status; throw e; }
  return data;
}
// Same four outcomes app.js's deliveryToast distinguishes: three of them report "sent" and
// only delivery_mode says whether anything actually left the building.
function deliveryText(delivery, who) {
  switch ((delivery || {}).delivery_mode) {
    case 'delivered':   return 'Delivered to ' + who + '.';
    case 'portal':      return 'Posted. ' + who + ' sees it in the web chat.';
    case 'logged_only': return 'Not sent: logged locally only. ' + who + ' did not receive this.';
    case 'failed':      return 'Delivery failed. The provider rejected it.';
    default:            return 'Sent to ' + who + '.';
  }
}

// ── state ───────────────────────────────────────────────────────────────────
var root = null, pollTimer = null, running = false;
var S = { view: 'work', cur: null, aiTab: 'resolved', teamTab: 'overview', period: '7d', topic: null, busy: false, closing: false, err: null, loaded: false };
var D = { convs: [], tickets: [], drafts: [], agents: [], llm: {}, detail: {} };
var skips = {}, skipSeq = 0;
try { var sv = sessionStorage.getItem('cx2-view'); if (sv === 'work' || sv === 'all' || sv === 'ai' || sv === 'team') S.view = sv; } catch (e) {}

function serviceable(t) { return t && (t.status === 'open' || t.status === 'in_progress'); }
function convById(id) { for (var i = 0; i < D.convs.length; i++) if (D.convs[i].conversation_id === id) return D.convs[i]; return {}; }
function ticketById(id) { for (var i = 0; i < D.tickets.length; i++) if (D.tickets[i].ticket_id === id) return D.tickets[i]; return null; }
function pendingDrafts() { return D.drafts.filter(function (d) { return d.status === 'pending'; }); }

// ── the work list ───────────────────────────────────────────────────────────
function workItems() {
  var pend = pendingDrafts(), byTicket = {}, used = {};
  pend.forEach(function (d) { if (d.ticket_id && !byTicket[d.ticket_id]) byTicket[d.ticket_id] = d; });
  var out = [];
  D.tickets.filter(serviceable).forEach(function (t) {
    var c = convById(t.conversation_id), d = byTicket[t.ticket_id] || null, stage, note = '';
    var contacts = t.contacts || [], last = contacts[contacts.length - 1];
    var promise = t.follow_up_due_at ? minsUntil(t.follow_up_due_at) : null;
    if (d) { stage = 'approve'; used[d.draft_id] = true; }
    else if (!t.first_response_at) stage = 'reply';
    else if (promise != null && promise < 0) { stage = 'reply'; note = 'You promised an update, and it\'s now due.'; }
    else if (last && last.direction === 'inbound') { stage = 'reply'; note = 'They wrote back after your last reply.'; }
    else stage = 'waiting';
    var due = !t.first_response_at && t.sla_due_at ? minsUntil(t.sla_due_at) : promise;
    out.push({ key: t.ticket_id, t: t, c: c, d: d, stage: stage, note: note, due: due, promise: promise,
      ch: (d && d.channel) || c.last_channel || 'web_chat', name: nameOf(c), topic: t.title || intentLabel(t.intent) });
  });
  // A pending draft whose ticket isn't open: an approved offer or suggested follow-up.
  pend.forEach(function (d) {
    if (used[d.draft_id]) return;
    var c = convById(d.conversation_id), t = d.ticket_id ? ticketById(d.ticket_id) : null;
    out.push({ key: 'd:' + d.draft_id, t: t, c: c, d: d, stage: 'approve', note: '', due: null, promise: null, ch: d.channel || c.last_channel,
      name: nameOf(c), topic: d.channel === 'offer' ? 'An approved offer, ready to send' : (t && t.title) || 'A follow-up you approved' });
  });
  return out;
}
function order(a, b) {
  var as = skips[a.key] || 0, bs = skips[b.key] || 0;
  if (!!as !== !!bs) return as ? 1 : -1;
  if (as && bs) return as - bs;
  var ao = a.due != null && a.due < 0, bo = b.due != null && b.due < 0;
  if (ao !== bo) return ao ? -1 : 1;
  var al = chMeta(a.ch).live, bl = chMeta(b.ch).live;
  if (al !== bl) return al ? -1 : 1;
  var ad = a.due == null ? 1e9 : a.due, bd = b.due == null ? 1e9 : b.due;
  return ad - bd;
}
function todo() { return workItems().filter(function (i) { return i.stage !== 'waiting'; }).sort(order); }
function current() {
  var all = workItems(), hit = null;
  for (var i = 0; i < all.length; i++) if (all[i].key === S.cur) hit = all[i];
  if (!hit) { hit = todo()[0] || null; S.cur = hit ? hit.key : null; }
  return hit;
}
function whyText(i) {
  var d = i.d;
  if (d && d.channel === 'offer') return 'An offer someone approved. Check the wording, then send it.';
  if (d && (d.provider === 'nudge_reply' || d.provider === 'follow_up_nudge')) return 'A follow-up someone approved. Fill in any [bracket] before sending.';
  var code = codeOf((d && d.reason_code) || (i.t && i.t.escalation_reason));
  return WHY[code] || (d && d.hold_reason) || (i.t && i.t.escalation_reason) || 'This case needs a person.';
}
function dueHTML(i) {
  if (i.stage === 'waiting') {
    if (i.promise != null) return '<span class="due">Update due in ' + fmtMin(i.promise) + '</span>';
    return '<span class="due">Their turn</span>';
  }
  if (i.due == null) return '';
  if (i.due < 0) return '<span class="due over">Overdue ' + fmtMin(i.due) + '</span>';
  return '<span class="due' + (i.due < 60 ? ' is-soon' : '') + '">Due in ' + fmtMin(i.due) + '</span>';
}
function detailFor(convId) { var e = D.detail[convId]; return e ? e.data : null; }
function ticketTurns(i) {
  var det = detailFor(i.c.conversation_id); if (!det) return null;
  var turns = det.turns || [], tid = i.t && i.t.ticket_id;
  var mine = tid ? turns.filter(function (x) { return x.ticket_id === tid; }) : [];
  return mine.length ? mine : turns.slice(-12);
}
function lastInbound(i) {
  var turns = ticketTurns(i);
  if (turns) { for (var k = turns.length - 1; k >= 0; k--) if (turns[k].direction === 'inbound') return turns[k]; }
  return null;
}
async function ensureDetail(convId) {
  if (!convId) return;
  var c = convById(convId), e = D.detail[convId];
  if (e && (e.at === c.updated_at || e.loading)) return;
  D.detail[convId] = { at: c.updated_at, loading: true, data: e ? e.data : null };
  try { D.detail[convId] = { at: c.updated_at, data: await api('/admin/conversations/' + encodeURIComponent(convId)) }; }
  catch (err) { D.detail[convId] = { at: c.updated_at, data: e ? e.data : null, failed: true }; }
  if (running && !midTask()) render();
}

// ── data loading ────────────────────────────────────────────────────────────
var PERIOD_DAYS = { '24h': 1, '7d': 7, '30d': 30 };
async function load() {
  try {
    var base = await Promise.all([api('/admin/conversations'), api('/admin/tickets'), api('/admin/reply-drafts?status=')]);
    D.convs = base[0] || []; D.tickets = base[1] || []; D.drafts = base[2] || [];
    S.err = null; S.loaded = true;
    if (S.view === 'team') await loadTeam();
  } catch (err) {
    S.err = err; S.loaded = true;
  }
}
async function loadTeam() {
  var n = PERIOD_DAYS[S.period];
  var r = await Promise.all([
    api('/admin/agents').catch(function () { return []; }),
    api('/admin/llm-observability/summary?days=' + n).catch(function () { return null; }),
    api('/admin/llm-observability/summary?days=' + (2 * n)).catch(function () { return null; })
  ]);
  D.agents = r[0] || [];
  D.llm[S.period] = { cur: r[1], both: r[2] };
}
function midTask() {
  if (!root) return true;
  var ta = $('#cxReply'), i = S.view === 'work' ? current() : null;
  var initial = i && i.d && i.stage === 'approve' ? (i.d.draft_text || '') : '';
  if (ta && ta.value !== initial) return true;
  if (document.activeElement && root.contains(document.activeElement) && /TEXTAREA|INPUT/.test(document.activeElement.tagName)) return true;
  if ($('details.more[open]') || $('.item[open]')) return true;
  return S.busy;
}
async function refresh(force) { await load(); if (force || !midTask()) render(); }
function poll() { if (running && !document.hidden) refresh(false); }

// ── shell ───────────────────────────────────────────────────────────────────
// The sidebar is its own element (#cxSide), not part of the console: it stays on screen for
// the classic pages too (showStage 'app'), so every signed-in page shares one navigation.
// Grouped by the job, not by which file renders the page:
//   Review & respond    everything a person reads and answers, including who owns a case
//   Cost & performance  how the AI and the team are doing, and what it costs
//   System              setup, rarely visited
// Ganit's mark, the same file the favicon and the landing page use. Only the square mark
// exists in the repo; a full Ganit wordmark would replace this <img> one-for-one.
var WORDMARK = '<div class="brand"><img class="brand-logo" src="/admin-ui/assets/ganit-logo.png?v=1" alt="Ganit"></div>';
var FLOW_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="6" height="10" rx="2"/><rect x="15" y="7" width="6" height="10" rx="2"/><path d="M9 12h6"/></svg>';
var WHERE = { stage: 'console', page: null };
function sideHTML() {
  var u = me(), nm = u.username || 'Admin';
  return '<aside class="side">' + WORDMARK +
    '<nav class="nav" aria-label="Review and respond"><div class="nav-h">Review &amp; respond</div>' +
      '<button data-go="work" title="Cases waiting for a person to approve, reply or follow up">' + ICON.work + 'My work<span class="ct" id="cxNavWork"></span></button>' +
      '<button data-go="all" title="Every conversation in order, with where each one stands">' + ICON.classic + 'All conversations</button>' +
      '<button data-classic="servicedesk" title="Every ticket: who owns it, what is breaching, reassign">' + ICON.desk + 'Assign &amp; track</button>' +
    '</nav>' +
    '<nav class="nav nav-more" aria-label="Cost and performance"><div class="nav-h">Cost &amp; performance</div>' +
      '<button data-go="team" title="How much the AI resolves, how often people edit it, team workload">' + ICON.team + 'AI performance</button>' +
      '<button data-go="ai" title="What the AI answered today, and what it is answering now">' + ICON.ai + 'AI activity<span class="ct" id="cxNavAi"></span></button>' +
      '<button data-classic="analytics" title="LLM spend, channel and intent reports, and the audit trail">' + ICON.chart + 'Cost &amp; reports</button>' +
    '</nav>' +
    '<nav class="nav nav-more" aria-label="System"><div class="nav-h">System</div>' +
      '<button data-classic="connectors" title="WhatsApp, email and CRM connectors, and model settings">' + ICON.gear + 'Configuration</button>' +
      '<button data-flow title="A diagram of the AI pipeline">' + FLOW_ICON + 'Workflow</button>' +
    '</nav>' +
    '<div class="side-foot"><button class="me" data-classic="profile" title="My profile"><span class="avatar">' + esc(nm.slice(0, 2).toUpperCase()) + '</span><span>' + esc(nm) + '<small>' + esc(u.email || 'My profile') + '</small></span></button>' +
      '<button class="icon-btn" data-logout title="Sign out" aria-label="Sign out">' + ICON.out + '</button></div>' +
  '</aside>' +
  '<nav class="mobile-nav" aria-label="Sections"><div class="seg">' +
    '<button data-go="work">My work</button><button data-go="team">Performance</button><button data-go="ai">AI activity</button>' +
  '</div></nav>';
}
function shell() {
  return '<div class="bg" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>' +
    '<div class="cx-main"><div class="mobile-top">' + WORDMARK + '<button class="icon-btn" data-logout aria-label="Sign out">' + ICON.out + '</button></div><main id="cxMain"></main></div>' +
    '<div class="cx-toast" id="cxToast" role="status" hidden></div>';
}
function sideHost() {
  var el = document.getElementById('cxSide');
  if (!el) {
    el = document.createElement('div'); el.id = 'cxSide'; el.className = 'cx2'; el.hidden = true;
    document.body.appendChild(el);
    el.addEventListener('click', function (e) {
      var g = e.target.closest('[data-go]');
      if (g) {
        var v = g.getAttribute('data-go');
        if (WHERE.stage === 'console') go(v);
        else { S.view = v; try { sessionStorage.setItem('cx2-view', v); } catch (x) {} if (window.goToHub) window.goToHub(); }
        return;
      }
      var c = e.target.closest('[data-classic]'); if (c) { openClassic(c.getAttribute('data-classic')); return; }
      if (e.target.closest('[data-flow]')) { if (window.openFlowModal) window.openFlowModal(); return; }
      if (e.target.closest('[data-logout]')) { if (window.doLogout) window.doLogout(); }
    });
  }
  return el;
}
function markSide() {
  var el = document.getElementById('cxSide'); if (!el) return;
  $$('[data-go]', el).forEach(function (b) {
    var on = WHERE.stage === 'console' && b.getAttribute('data-go') === S.view;
    if (b.closest('.nav')) { if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); }
    else b.setAttribute('aria-pressed', on);
  });
  $$('[data-classic]', el).forEach(function (b) {
    var on = WHERE.stage === 'app' && b.getAttribute('data-classic') === WHERE.page;
    if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  var w = document.getElementById('cxNavWork'), a = document.getElementById('cxNavAi');
  if (S.loaded && !S.err) {
    if (w) w.textContent = todo().length || '';
    if (a) a.textContent = D.tickets.filter(function (t) { return t.status === 'logged' && isToday(t.created_at); }).length || '';
  }
}
// The host element outlives sign-out (reset() only empties it), so its listeners are bound
// once - binding on every start() would send every click twice after a second sign-in.
function bindShell() {
  if (root._cx2Bound) return;
  root._cx2Bound = true;
  root.addEventListener('click', function (e) {
    var g = e.target.closest('[data-go]'); if (g) { go(g.getAttribute('data-go')); return; }
    var c = e.target.closest('[data-classic]'); if (c) { openClassic(c.getAttribute('data-classic')); return; }
    if (e.target.closest('[data-logout]')) { if (window.doLogout) window.doLogout(); }
  });
  root.addEventListener('keydown', onKey);
}
function openClassic(page, convId) {
  if (convId) { try { sessionStorage.setItem('cx-conv', convId); } catch (e) {} }
  if (window.enterSection) window.enterSection(page);
  if (convId && page === 'inbox' && window.loadConversations) window.loadConversations();
}
function go(v) {
  S.view = v; S.closing = false;
  try { sessionStorage.setItem('cx2-view', v); } catch (e) {}
  render(); root.scrollTop = 0;
  if (v === 'team') loadTeam().then(function () { if (S.view === 'team') render(); });
}
function hero(inner) { return '<section class="hero"><div class="hero-in">' + inner + '</div></section>'; }
function render() {
  if (!root) return;
  markSide();
  // The Agent Workspace's panel may be sitting in this view (see cxLendContext in app.js).
  // Move it home before innerHTML replaces the view, or its nodes would be discarded.
  if (window.cxReturnContext) window.cxReturnContext();
  var m = $('#cxMain');
  if (!S.loaded) { m.innerHTML = hero('<div><div class="eyebrow">Loading</div><h1>Getting your work ready…</h1></div>') + '<div class="wrap"></div>'; return; }
  if (S.err) {
    var expired = S.err.status === 401;
    m.innerHTML = hero('<div><div class="eyebrow">Something went wrong</div><h1>' + (expired ? 'Your session has ended.' : 'Couldn\'t load your work.') + '</h1><p>' + esc(expired ? 'Sign in again to carry on.' : S.err.message) + '</p></div>') +
      '<div class="wrap"><div class="panel"><button class="btn btn-primary" ' + (expired ? 'data-logout' : 'id="cxRetry"') + '>' + (expired ? 'Sign in again' : 'Try again') + '</button></div></div>';
    var rb = $('#cxRetry'); if (rb) rb.addEventListener('click', function () { S.loaded = false; render(); refresh(true); });
    return;
  }
  if (S.view === 'work') { m.innerHTML = workHTML(); bindWork(); }
  else if (S.view === 'all') { m.innerHTML = allHTML(); bindAll(); }
  else if (S.view === 'ai') { m.innerHTML = aiHTML(); bindAI(); }
  else { m.innerHTML = teamHTML(); bindTeam(); }
}

// ── MY WORK ─────────────────────────────────────────────────────────────────
function greeting() { var h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'; }
function todayLabel() { try { return new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }); } catch (e) { return 'Today'; } }
function decisionMins() {
  var a = D.drafts.filter(function (d) { return d.decided_at && d.status !== 'pending'; })
    .map(function (d) { return (ts(d.decided_at) - ts(d.created_at)) / 60000; }).filter(function (x) { return x >= 0 && x < 720; });
  return median(a);
}
function ring(done, total) {
  var r = 46, c = 2 * Math.PI * r, p = total ? done / total : 1;
  return '<div class="ring"><svg viewBox="0 0 112 112" aria-hidden="true"><defs><linearGradient id="cxRg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8f86ff"/><stop offset="1" stop-color="#4a3bf0"/></linearGradient></defs>' +
    '<circle cx="56" cy="56" r="' + r + '" fill="none" stroke="var(--line)" stroke-width="12"/>' +
    '<circle cx="56" cy="56" r="' + r + '" fill="none" stroke="url(#cxRg)" stroke-width="12" stroke-linecap="round" stroke-dasharray="' + c.toFixed(2) + '" stroke-dashoffset="' + (c * (1 - p)).toFixed(2) + '"/></svg>' +
    '<div class="rv"><b>' + done + ' of ' + total + '</b>handled by people today</div></div>';
}
function workHTML() {
  var list = todo(), i = current(), n = list.length;
  var done = D.drafts.filter(function (d) { return d.status !== 'pending' && isToday(d.decided_at); }).length +
    D.tickets.filter(function (t) { return t.status === 'closed' && isToday(t.updated_at); }).length;
  var aiToday = D.tickets.filter(function (t) { return t.status === 'logged' && isToday(t.created_at); }).length;
  var per = decisionMins(), mins = per != null ? Math.max(5, Math.round(n * Math.max(per, 1) / 5) * 5) : null;
  var line = n ? (n === 1 ? 'One conversation needs you' : n + ' conversations need you') + (mins ? ', about ' + mins + ' minutes at the team\'s usual pace.' : '.') + ' The AI is taking care of the rest.'
    : 'Nothing needs you right now. The AI is taking care of everything.';
  if (i) ensureDetail(i.c.conversation_id);
  var top = hero('<div class="hero-row"><div class="grow"><div class="eyebrow">' + esc(todayLabel()) + '</div><h1>' + greeting() + ', ' + esc(cap(firstName(me().username || 'there'))) + '.</h1><p>' + line + '</p></div>' + '<div class="hero-stats">' + ring(done, done + n) + '<button class="hstat" data-go="ai"><b class="num">' + aiToday + '</b><span>resolved by the AI today</span></button></div></div>');
  if (!i) return top + '<div class="wrap">' + queueHTML(null) + '<div class="focus caught">' + ICON.check + '<h2>You\'re all caught up</h2><p>New conversations that need a person will appear here on their own.</p></div>' + '</div>';
  // Case on the left, everything about the customer on the right: the sentiment readout,
  // customer context, open tickets and the case review are the Agent Workspace's own panel.
  return top + '<div class="wrap">' + queueHTML(i) + '<div class="work"><div>' + focusHTML(i) + '</div>' +
    '<aside class="ctx-col" aria-label="About this customer"><div class="glass ctx-sent"><div class="ctx-h">How they feel</div><div id="cxSentMount"></div></div>' +
    '<div class="ctx-mount" id="cxCtxMount"></div></aside></div></div>';
}
function focusHTML(i) {
  var kind = { approve: 'To approve', reply: 'To reply', waiting: 'Waiting on customer' }[i.stage];
  var inb = lastInbound(i), sent = inb && inb.metadata && inb.metadata.sentiment;
  var msg = inb ? inb.text : (i.c.last_message || '');
  var sub = '<span class="ch">' + (ICON[i.ch] || '') + esc(chMeta(i.ch).label) + '</span><span class="dot-sep">·</span><span>' + esc(i.topic) + '</span>' +
    (sent === 'negative' ? '<span class="dot-sep">·</span><span class="upset">Upset</span>' : '');
  var body = '', dis = S.busy ? ' disabled' : '';
  if (i.stage === 'approve') {
    body = '<div><div class="block-lbl">Suggested reply<span class="edited" id="cxEdMark" hidden>Edited</span></div><textarea id="cxReply" aria-label="Suggested reply">' + esc(i.d.draft_text || '') + '</textarea></div>' +
      '<div class="f-actions"><button class="btn btn-primary" id="cxSend"' + dis + '>Approve &amp; send</button><button class="btn" id="cxEdit"' + dis + '>Edit</button><button class="btn btn-quiet" id="cxDiscard"' + dis + '>Not right</button><span class="grow"></span><button class="btn btn-quiet" id="cxSkip"' + dis + '>Skip for now</button></div>';
  } else if (i.stage === 'reply') {
    body = (i.note ? '<p class="note">' + esc(i.note) + '</p>' : '') +
      '<div><div class="block-lbl">Your reply</div><textarea id="cxReply" class="plain" aria-label="Your reply" placeholder="Hi ' + esc(firstName(i.name)) + ', …"></textarea></div>' +
      '<div class="f-actions"><button class="btn btn-primary" id="cxSend"' + dis + '>Send on ' + esc(chMeta(i.ch).label) + '</button><span class="grow"></span><button class="btn btn-quiet" id="cxSkip"' + dis + '>Skip for now</button></div>';
  } else {
    body = '<p class="why">' + ICON.info + '<span>' + (i.promise != null ? 'You promised them an update within ' + fmtMin(i.promise) + '.' : 'You\'ve replied. It\'s their turn.') + '</span></p>' +
      '<div><div class="block-lbl">Write to them</div><textarea id="cxReply" class="plain" aria-label="Message" placeholder="Hi ' + esc(firstName(i.name)) + ', …"></textarea></div>' +
      '<div class="f-actions"><button class="btn btn-primary" id="cxSend"' + dis + '>Send on ' + esc(chMeta(i.ch).label) + '</button><button class="btn" id="cxClose"' + dis + '>Close case…</button></div>' +
      (S.closing ? '<div class="close-row"><input id="cxCloseWhy" type="text" placeholder="Why is it resolved? (required)" aria-label="Reason for closing"><button class="btn btn-primary btn-sm" id="cxCloseGo"' + dis + '>Close case</button><button class="btn btn-quiet btn-sm" id="cxCloseCancel">Cancel</button></div>' : '');
  }
  var d = i.d, t = i.t;
  var conf = d && (d.retrieval_confidence != null || d.intent_confidence != null) ? '<div class="kv-list"><h4>How sure the AI was</h4>' +
    confRow('Knowledge match', d.retrieval_confidence) + confRow('Understood the question', d.intent_confidence) + '</div>' : '';
  var turns = ticketTurns(i);
  var more = '<details class="more"><summary>Details and full conversation</summary><div class="more-body">' +
    '<div class="kv-list"><h4>Case</h4>' +
      (d && d.hold_reason ? '<div>' + esc(d.hold_reason) + '</div>' : '') +
      kv('Reason code', '<span class="code">' + esc((d && d.reason_code) || (t && t.escalation_reason) || '—') + '</span>') +
      (t ? kv('Ticket', '<span class="code">' + esc(t.ticket_id) + '</span>') + kv('Priority', esc(cap(t.priority))) + kv('Team', esc(t.assigned_team || '—')) + kv('Owner', esc(t.assigned_to || 'Unassigned')) : '') +
    '</div>' + conf +
    '<div class="kv-list"><h4>More</h4><button class="link" data-classic-conv="' + esc(i.c.conversation_id) + '">Open this conversation in the Agent Workspace</button></div>' +
    '<div class="thread"><div class="kv-list"><h4>Conversation</h4></div>' +
      (turns ? (turns.length ? turns.map(bubble).join('') : '<p class="note">No messages yet.</p>') : '<p class="note">Loading…</p>') + '</div>' +
    '</div></details>';
  return '<article class="focus" aria-labelledby="cxFocusName">' +
    '<div class="f-top"><span class="eyebrow">Up next · ' + kind + '</span>' + dueHTML(i) + '</div>' +
    '<div><h2 id="cxFocusName">' + esc(i.name) + '</h2><div class="f-sub">' + sub + '</div></div>' +
    (i.stage !== 'waiting' ? '<p class="why">' + ICON.info + '<span>' + esc(whyText(i)) + '</span></p>' : '') +
    (msg ? '<div><blockquote class="cx-cust">' + esc(msg) + '</blockquote><div class="cx-cust-by">' + esc(firstName(i.name)) + (inb ? ' · ' + ago(inb.created_at) : '') + '</div></div>' : '') +
    body + '<div class="keys"><kbd>Ctrl</kbd> + <kbd>Enter</kbd> sends · <kbd>S</kbd> skips</div>' + more + '</article>';
}
function kv(k, v) { return '<div class="kv"><span>' + k + '</span><b>' + v + '</b></div>'; }
function confRow(label, v) {
  if (v == null) return '';
  var p = Math.round(v * 100);
  return kv(label, '<span class="num">' + p + '%</span>') + '<div class="conf-row"><div class="bar"><i class="' + (v < 0.5 ? 'lo' : '') + '" style="width:' + p + '%"></i></div></div>';
}
function bubble(x) {
  var holding = /support agent will help you with this shortly/i.test(x.text || '');
  var human = x.metadata && /manual_agent_reply|agent_composed_reply/.test(x.metadata.source || '');
  var cls = x.direction === 'inbound' ? 'c' : holding ? 'o hold' : 'o';
  var who = x.direction === 'inbound' ? 'Customer' : holding ? 'AI Agent · automatic holding reply' : human ? 'Agent' : 'AI Agent';
  return '<div class="cx-msg ' + cls + '"><div class="bub">' + esc(x.text) + '</div><div class="by">' + who + ' · ' + esc(chMeta(x.channel).label) + ' · ' + ago(x.created_at) + '</div></div>';
}
function queueHTML(cur) {
  var all = workItems().sort(order);
  if (!all.length) return '';
  function chip(i) {
    return '<button class="q-chip" data-pick="' + esc(i.key) + '" aria-current="' + (cur && cur.key === i.key) + '"><span class="n">' + esc(i.name) + '</span><span class="tp">' + esc(i.topic) + '</span>' + dueHTML(i) + '</button>';
  }
  var ap = all.filter(function (i) { return i.stage === 'approve'; }), rp = all.filter(function (i) { return i.stage === 'reply'; }), wt = all.filter(function (i) { return i.stage === 'waiting'; });
  function sec(title, pip, items, waiting) {
    if (!items.length) return '';
    var open = !waiting || S.showWaiting;
    return '<div class="qs-sec"><' + (waiting ? 'button class="qs-lbl" data-toggle-waiting aria-expanded="' + open + '"' : 'span class="qs-lbl"') + '><i class="pip" style="background:' + pip + '"></i>' + title + ' <b>' + items.length + '</b></' + (waiting ? 'button' : 'span') + '>' +
      (open ? items.map(chip).join('') : '') + '</div>';
  }
  return '<section class="qstrip glass" aria-label="Your queue"><div class="qs-scroll">' +
    sec('To approve', '#6d5dfc', ap) + sec('To reply', '#f0a36b', rp) + sec('Waiting', '#b3b9c5', wt, true) +
  '</div></section>';
}
function bindWork() {
  var i = current();
  $$('[data-pick]').forEach(function (b) { b.addEventListener('click', function () { S.cur = b.getAttribute('data-pick'); S.closing = false; render(); if (window.innerWidth < 1100) { var f = $('.focus'); if (f) f.scrollIntoView({ behavior: 'smooth', block: 'start' }); } }); });
  $$('[data-classic-conv]').forEach(function (b) { b.addEventListener('click', function () { openClassic('inbox', b.getAttribute('data-classic-conv')); }); });
  $$('[data-toggle-waiting]').forEach(function (b) { b.addEventListener('click', function () { S.showWaiting = !S.showWaiting; render(); }); });
  if (!i) return;
  if (window.cxLendContext && i.c.conversation_id) window.cxLendContext($('#cxCtxMount'), $('#cxSentMount'), i.c.conversation_id, i.t && i.t.ticket_id);
  var ta = $('#cxReply');
  if (ta && i.stage === 'approve') ta.addEventListener('input', function () { var m = $('#cxEdMark'); if (m) m.hidden = ta.value.trim() === (i.d.draft_text || '').trim(); });
  on('#cxSend', function () { if (i.stage === 'approve') approve(i, ta.value); else sendOwn(i, ta.value); });
  on('#cxEdit', function () { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); });
  on('#cxDiscard', function () { discard(i); });
  on('#cxSkip', function () { skip(i); });
  on('#cxClose', function () { S.closing = true; render(); var r = $('#cxCloseWhy'); if (r) r.focus(); });
  on('#cxCloseCancel', function () { S.closing = false; render(); });
  on('#cxCloseGo', function () { closeCase(i, ($('#cxCloseWhy') || {}).value || ''); });
}
function on(sel, fn) { var el = $(sel); if (el) el.addEventListener('click', fn); }

// ── actions: every one of these is real ─────────────────────────────────────
var toastT = null;
function toast(msg, kind) {
  var el = $('#cxToast'); if (!el) return;
  el.textContent = msg; el.className = 'cx-toast' + (kind ? ' ' + kind : ''); el.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(function () { el.hidden = true; }, 5000);
}
// Buttons are disabled in place rather than by re-rendering, so a failed send leaves the
// agent's edited text exactly where it was.
async function act(fn) {
  if (S.busy) return;
  S.busy = true;
  var btns = $$('.focus button, .item-body button').filter(function (b) { return !b.disabled; });
  btns.forEach(function (b) { b.disabled = true; });
  try { await fn(); }
  catch (err) {
    S.busy = false; btns.forEach(function (b) { b.disabled = false; });
    toast('That didn\'t go through: ' + err.message, 'bad');
    return;
  }
  S.busy = false;
  if (window.cxContextStale) window.cxContextStale();
  await refresh(true);
}
function approve(i, text) {
  text = (text || '').trim();
  if (!text) { toast('The reply is empty.', 'bad'); return; }
  act(async function () {
    var res = await api('/admin/reply-drafts/' + encodeURIComponent(i.d.draft_id) + '/send', { method: 'POST', body: JSON.stringify({ text: text, actor: actor() }) });
    S.cur = null;
    var mode = (res && res.delivery || {}).delivery_mode;
    toast(deliveryText(res && res.delivery, firstName(i.name)), mode === 'logged_only' || mode === 'failed' ? 'bad' : '');
  });
}
function discard(i) {
  act(async function () {
    await api('/admin/reply-drafts/' + encodeURIComponent(i.d.draft_id) + '/discard', { method: 'POST', body: JSON.stringify({ actor: actor() }) });
    skips[i.key] = ++skipSeq; S.cur = null;
    toast('Draft set aside. ' + firstName(i.name) + ' is now under To reply.');
  });
}
function sendOwn(i, text, convId) {
  text = (text || '').trim();
  if (!text) { toast('Write a reply first.', 'bad'); var ta = $('#cxReply'); if (ta) ta.focus(); return; }
  act(async function () {
    var res = await api('/admin/conversations/' + encodeURIComponent(convId || i.c.conversation_id) + '/reply', { method: 'POST', body: JSON.stringify({ text: text, actor: actor() }) });
    S.cur = null;
    var mode = (res && res.delivery || {}).delivery_mode;
    toast(deliveryText(res && res.delivery, firstName(i.name)), mode === 'logged_only' || mode === 'failed' ? 'bad' : '');
  });
}
function closeCase(i, reason) {
  reason = (reason || '').trim();
  if (!reason) { toast('Add a short reason first.', 'bad'); var r = $('#cxCloseWhy'); if (r) r.focus(); return; }
  act(async function () {
    await api('/admin/tickets/' + encodeURIComponent(i.t.ticket_id) + '/close', { method: 'POST', body: JSON.stringify({ reason: reason, actor: actor() }) });
    S.closing = false; S.cur = null; toast('Case closed.');
  });
}
function skip(i) { skips[i.key] = ++skipSeq; S.cur = null; S.closing = false; render(); toast(firstName(i.name) + ' moved to the end of your queue.'); }
function onKey(e) {
  if (S.view !== 'work') return;
  var tag = (document.activeElement && document.activeElement.tagName) || '';
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { var s = $('#cxSend'); if (s && !s.disabled) { e.preventDefault(); s.click(); } return; }
  if (/TEXTAREA|INPUT/.test(tag)) { if (e.key === 'Escape') document.activeElement.blur(); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  var i = current(); if (!i) return;
  var k = e.key.toLowerCase();
  if (k === 's' && i.stage !== 'waiting') { e.preventDefault(); skip(i); }
  else if (k === 'e') { var ta = $('#cxReply'); if (ta) { e.preventDefault(); ta.focus(); } }
}

// ── ALL CONVERSATIONS ───────────────────────────────────────────────────────
// Every conversation as one stream, newest first, grouped by day. Each carries a progress
// bar for where its case stands on the way to resolution. The stages are the same
// judgement My work makes (workItems): a held draft, a reply we owe, a reply we sent and
// are waiting on, or finished - by the AI (`logged`) or by a person (`closed`).
var STAGES = {
  new:     { pct: 6,   label: 'Received',                    tone: 'muted', step: 0 },
  reply:   { pct: 20,  label: 'Needs a reply',               tone: 'warm',  step: 0 },
  approve: { pct: 33.3, label: 'AI draft waiting for approval', tone: 'warm', step: 1 },
  waiting: { pct: 66.7, label: 'Replied · waiting on customer', tone: 'accent', step: 2 },
  logged:  { pct: 100, label: 'Answered by the AI',          tone: 'ai',    step: 3 },
  closed:  { pct: 100, label: 'Resolved by a person',        tone: 'ok',    step: 3 }
};
var STEP_NAMES = ['Received', 'Drafted', 'Replied', 'Resolved'];
function ticketStage(t, items) {
  if (!t) return 'new';
  if (t.status === 'logged') return 'logged';
  if (t.status === 'closed') return 'closed';
  for (var k = 0; k < items.length; k++) if (items[k].key === t.ticket_id) return items[k].stage;
  return 'reply';
}
function convRows() {
  var items = workItems(), byConv = {};
  D.tickets.forEach(function (t) { (byConv[t.conversation_id] = byConv[t.conversation_id] || []).push(t); });
  return D.convs.map(function (c) {
    var tks = (byConv[c.conversation_id] || []).slice().sort(function (a, b) { return ts(b.created_at) - ts(a.created_at); });
    // The case shown is the one that still needs someone; otherwise the newest.
    var cur = tks.filter(serviceable)[0] || tks[0] || null;
    var stage = ticketStage(cur, items);
    var item = null; for (var k = 0; k < items.length; k++) if (cur && items[k].key === cur.ticket_id) item = items[k];
    return { c: c, tickets: tks, cur: cur, stage: stage, item: item, name: nameOf(c),
      topic: cur ? (cur.title || intentLabel(cur.intent)) : 'New conversation',
      when: c.updated_at, items: items };
  // A conversation nobody has written in yet (no message, no case) is not shown: before the
  // portal fix, merely opening the customer portal created one of these.
  }).filter(function (r) { return r.tickets.length || r.c.last_message; })
    .sort(function (a, b) { return ts(b.when) - ts(a.when); });
}
function convFilterMatch(r) {
  var f = S.convFilter || 'all';
  if (f === 'needs') return r.stage === 'reply' || r.stage === 'approve';
  if (f === 'waiting') return r.stage === 'waiting';
  if (f === 'ai') return r.stage === 'logged';
  if (f === 'closed') return r.stage === 'closed';
  return true;
}
function convSearchMatch(r) {
  var q = (S.convQ || '').trim().toLowerCase(); if (!q) return true;
  return (r.name + ' ' + r.topic + ' ' + (r.c.last_message || '')).toLowerCase().indexOf(q) !== -1;
}
function dayLabel(iso) {
  var t = ts(iso); if (t == null) return 'Earlier';
  var d = new Date(t), n = new Date(); n.setHours(0, 0, 0, 0);
  var diff = Math.round((n.getTime() - new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) / 86400000);
  if (diff <= 0) return 'Today'; if (diff === 1) return 'Yesterday';
  try { return d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }); } catch (e) { return d.toDateString(); }
}
function progressHTML(stage, small) {
  var s = STAGES[stage] || STAGES.new;
  var dots = small ? '' : '<div class="pg-steps">' + STEP_NAMES.map(function (n, k) {
    var label = (k === 3 && stage === 'logged') ? 'Answered by AI' : n;
    return '<span class="' + (k <= s.step ? 'on' : '') + '">' + label + '</span>';
  }).join('') + '</div>';
  return '<div class="pg' + (small ? ' pg-sm' : '') + '" role="img" aria-label="' + esc(s.label) + ', ' + s.pct + '% of the way">' +
    '<div class="pg-track"><i class="pg-fill tone-' + s.tone + '" style="width:' + s.pct + '%"></i></div>' + dots + '</div>';
}
function dayBarHTML(rows) {
  var today = rows.filter(function (r) { return dayLabel(r.when) === 'Today'; });
  var n = { ai: 0, ok: 0, prog: 0, needs: 0 };
  today.forEach(function (r) {
    if (r.stage === 'logged') n.ai++; else if (r.stage === 'closed') n.ok++;
    else if (r.stage === 'reply' || r.stage === 'approve') n.needs++; else n.prog++;
  });
  var tot = today.length;
  if (!tot) return '<p class="note">No conversations yet today.</p>';
  var seg = function (v, cls, lbl) { return v ? '<i class="ds ' + cls + '" style="flex:' + v + '" title="' + lbl + ': ' + v + '"></i>' : ''; };
  return '<div class="daybar"><div class="daybar-h"><b>' + (n.ai + n.ok) + ' of ' + tot + '</b> conversations resolved today</div>' +
    '<div class="daybar-track">' + seg(n.ai, 'tone-ai', 'Answered by the AI') + seg(n.ok, 'tone-ok', 'Resolved by a person') + seg(n.prog, 'tone-accent', 'In progress') + seg(n.needs, 'tone-warm', 'Needs you') + '</div>' +
    '<div class="daybar-l"><span><i class="tone-ai"></i>AI resolved <b>' + n.ai + '</b></span><span><i class="tone-ok"></i>People resolved <b>' + n.ok + '</b></span><span><i class="tone-accent"></i>In progress <b>' + n.prog + '</b></span><span><i class="tone-warm"></i>Need you <b>' + n.needs + '</b></span></div></div>';
}
function allHTML() {
  var rows = convRows();
  var filters = [['all', 'All'], ['needs', 'Needs you'], ['waiting', 'Waiting on customer'], ['ai', 'Answered by AI'], ['closed', 'Resolved']];
  var count = function (f) { var keep = S.convFilter; S.convFilter = f; var n = rows.filter(convFilterMatch).length; S.convFilter = keep; return n; };
  var top = hero('<div class="hero-row"><div class="grow"><div class="eyebrow">All conversations</div><h1>Every conversation, in order</h1><p>Where each one stands, newest first. Open one to see its history and reply.</p></div>' +
      '<button class="btn" id="cxKg">Knowledge graph</button></div>' + dayBarHTML(rows) +
    '<div class="hero-row"><div class="seg" role="group" aria-label="Filter">' + filters.map(function (f) {
      return '<button data-cf="' + f[0] + '" aria-pressed="' + ((S.convFilter || 'all') === f[0]) + '">' + f[1] + ' <span class="muted">' + count(f[0]) + '</span></button>';
    }).join('') + '</div><span class="grow"></span><input class="cv-search" id="cxConvQ" type="search" placeholder="Search name, topic or message" aria-label="Search conversations" value="' + esc(S.convQ || '') + '"></div>');
  return top + '<div class="wrap"><div id="cxAllList">' + convListHTML(rows) + '</div></div>';
}
function convListHTML(rows) {
  var shown = rows.filter(convFilterMatch).filter(convSearchMatch);
  if (!shown.length) return '<div class="panel caught">' + ICON.check + '<p>' + (rows.length ? 'Nothing matches this filter.' : 'No conversations yet. They appear here as customers write in.') + '</p></div>';
  var out = '', last = null;
  shown.forEach(function (r, k) {
    var day = dayLabel(r.when);
    if (day !== last) { out += (last ? '</div>' : '') + '<div class="cv-day"><div class="cv-day-h">' + esc(day) + '</div>'; last = day; }
    out += convCardHTML(r, k);
  });
  return out + '</div>';
}
function convCardHTML(r, k) {
  var s = STAGES[r.stage] || STAGES.new, open = S.openConv === r.c.conversation_id;
  var initials = r.name.split(/\s+/).map(function (w) { return w.charAt(0); }).join('').slice(0, 2).toUpperCase();
  var more = r.tickets.length > 1 ? '<span class="muted"> · ' + r.tickets.length + ' requests</span>' : '';
  return '<article class="cv-card' + (open ? ' open' : '') + '" style="--i:' + Math.min(k, 12) + '">' +
    '<button class="cv-head" data-open-conv="' + esc(r.c.conversation_id) + '" aria-expanded="' + open + '">' +
      '<span class="cv-av">' + esc(initials) + '</span>' +
      '<span class="cv-main"><span class="cv-top"><b>' + esc(r.name) + '</b><span class="ch">' + (ICON[r.c.last_channel] || '') + esc(chMeta(r.c.last_channel).label) + '</span><span class="cv-when">' + ago(r.when) + '</span></span>' +
        '<span class="cv-topic">' + esc(r.topic) + more + '</span>' +
        '<span class="cv-msg">' + esc(r.c.last_message || 'No messages yet') + '</span>' +
        '<span class="cv-stage tone-t-' + s.tone + '">' + esc(s.label) + '</span>' + progressHTML(r.stage) + '</span>' +
    '</button>' + (open ? convOpenHTML(r) : '') + '</article>';
}
function convOpenHTML(r) {
  var det = detailFor(r.c.conversation_id);
  var hist = r.tickets.length ? '<div class="cv-sec"><div class="ctx-h">History</div>' + r.tickets.map(function (t) {
    var st = ticketStage(t, r.items), sd = STAGES[st];
    return '<div class="cv-hist"><span class="cv-hist-t">' + esc(t.title || intentLabel(t.intent)) + '</span><span class="cv-hist-s tone-t-' + sd.tone + '">' + esc(sd.label) + '</span><span class="cv-hist-d">' + ago(t.created_at) + '</span>' + progressHTML(st, true) + '</div>';
  }).join('') + '</div>' : '';
  var thread = '<div class="cv-sec"><div class="ctx-h">Conversation</div><div class="thread">' +
    (det ? ((det.turns || []).slice(-12).map(bubble).join('') || '<p class="note">No messages yet.</p>') : '<p class="note">Loading…</p>') + '</div></div>';
  var needs = r.stage === 'reply' || r.stage === 'approve';
  var act = needs && r.item
    ? '<div class="f-actions"><button class="btn btn-primary" data-to-work="' + esc(r.item.key) + '">' + (r.stage === 'approve' ? 'Review the AI draft' : 'Reply in My work') + '</button><button class="btn btn-quiet" data-classic-conv="' + esc(r.c.conversation_id) + '">Open classic view</button></div>'
    : '<div class="take"><textarea id="cxReply" class="plain" rows="3" aria-label="Message to ' + esc(r.name) + '" placeholder="Write to ' + esc(firstName(r.name)) + '…"></textarea>' +
      '<div class="f-actions"><button class="btn btn-primary" data-conv-send="' + esc(r.c.conversation_id) + '">Send on ' + esc(chMeta(r.c.last_channel).label) + '</button><button class="btn btn-quiet" data-classic-conv="' + esc(r.c.conversation_id) + '">Open classic view</button></div></div>';
  return '<div class="cv-open">' + hist + thread + act + '</div>';
}
function bindAll() {
  on('#cxKg', function () { if (window.openLiveGraphModal) window.openLiveGraphModal(); });
  $$('[data-cf]').forEach(function (b) { b.addEventListener('click', function () { S.convFilter = b.getAttribute('data-cf'); render(); }); });
  var q = $('#cxConvQ');
  if (q) q.addEventListener('input', function () { S.convQ = q.value; var list = $('#cxAllList'); if (list) { list.innerHTML = convListHTML(convRows()); bindConvList(); } });
  bindConvList();
}
function bindConvList() {
  $$('[data-open-conv]').forEach(function (b) { b.addEventListener('click', function () {
    var id = b.getAttribute('data-open-conv');
    S.openConv = S.openConv === id ? null : id;
    if (S.openConv) ensureDetail(S.openConv);
    render();
  }); });
  $$('[data-to-work]').forEach(function (b) { b.addEventListener('click', function () { S.cur = b.getAttribute('data-to-work'); go('work'); }); });
  $$('[data-classic-conv]').forEach(function (b) { b.addEventListener('click', function () { openClassic('inbox', b.getAttribute('data-classic-conv')); }); });
  $$('[data-conv-send]').forEach(function (b) { b.addEventListener('click', function () {
    var id = b.getAttribute('data-conv-send'), c = convById(id), ta = $('#cxReply');
    sendOwn({ name: nameOf(c), c: c }, ta ? ta.value : '', id);
  }); });
}

// ── AI AGENT ────────────────────────────────────────────────────────────────
function aiLists() {
  var resolved = D.tickets.filter(function (t) { return t.status === 'logged' && isToday(t.created_at); });
  var byConv = {};
  D.tickets.forEach(function (t) { var p = byConv[t.conversation_id]; if (!p || ts(t.created_at) > ts(p.created_at)) byConv[t.conversation_id] = t; });
  var live = D.convs.filter(function (c) {
    var t = byConv[c.conversation_id], m = ts(c.updated_at);
    return c.status !== 'closed' && m != null && Date.now() - m < 15 * 60000 && t && t.status === 'logged';
  });
  var handed = workItems();
  return { resolved: resolved, live: live, handed: handed };
}
function aiHTML() {
  var L = aiLists();
  var tabs = [['resolved', 'Resolved on its own today', L.resolved.length], ['active', 'In conversation now', L.live.length], ['handed', 'With people now', L.handed.length]];
  var top = hero('<div><div class="eyebrow">AI activity</div><h1>What the AI handled today</h1><p>These stay out of your queue unless a person is needed.</p></div>' +
    '<div class="stat-tabs" role="group" aria-label="Filter">' + tabs.map(function (x) { return '<button class="stat-tab" data-ait="' + x[0] + '" aria-pressed="' + (S.aiTab === x[0]) + '"><b class="num">' + x[2] + '</b><span>' + x[1] + '</span></button>'; }).join('') + '</div>');
  var rows = '', empty = '';
  if (S.aiTab === 'resolved') {
    rows = L.resolved.map(function (t) { var c = convById(t.conversation_id); return aiItem(c, t, t.title || intentLabel(t.intent), intentLabel(t.intent), '<span class="state is-ok">Resolved</span>', t.created_at); }).join('');
    empty = 'Nothing yet today. Resolved conversations will collect here.';
  } else if (S.aiTab === 'active') {
    rows = L.live.map(function (c) { return aiItem(c, null, c.last_message || '', intentLabel(c.last_intent), '<span class="state live">Replying</span>', c.updated_at); }).join('');
    empty = 'The AI isn\'t in a live conversation right now.';
  } else {
    var lbl = { approve: 'Waiting for approval', reply: 'Waiting for a reply', waiting: 'Waiting on customer' };
    rows = L.handed.map(function (i) {
      return '<div class="item"><button class="item-row" data-open-work="' + esc(i.key) + '"><div class="who"><b>' + esc(i.name) + '</b><span>' + esc(chMeta(i.ch).label) + '</span></div><div class="qa"><div class="q">' + esc(i.topic) + '</div><div class="a">' + esc(whyText(i)) + '</div></div><span class="state">' + lbl[i.stage] + '</span></button></div>';
    }).join('');
    empty = 'Nobody is needed right now.';
  }
  var note = { resolved: 'Open one to read it, or reply to the customer yourself.', active: 'Live right now. Open one to read along or step in.', handed: 'Choose one to open it in My work.' }[S.aiTab];
  return top + '<div class="wrap">' + (rows ? '<div class="list">' + rows + '</div><p class="note">' + note + '</p>' : '<div class="panel caught">' + ICON.check + '<p>' + empty + '</p></div>') + '</div>';
}
function aiItem(c, t, q, a, state, at) {
  return '<details class="item" data-conv="' + esc(c.conversation_id || '') + '" data-ticket="' + esc(t ? t.ticket_id : '') + '"><summary><div class="who"><b>' + esc(nameOf(c)) + '</b><span>' + esc(chMeta(c.last_channel).label) + ' · ' + ago(at) + '</span></div><div class="qa"><div class="q">' + esc(q) + '</div><div class="a">' + esc(a) + '</div></div>' + state + '</summary><div class="item-body"><p class="note">Loading…</p></div></details>';
}
function fillAiItem(el) {
  var convId = el.getAttribute('data-conv'), tid = el.getAttribute('data-ticket'), body = $('.item-body', el);
  var det = detailFor(convId);
  if (!det) { ensureDetail(convId).then(function () { if (el.open && document.contains(el)) fillAiItem(el); }); return; }
  var turns = det.turns || [], mine = tid ? turns.filter(function (x) { return x.ticket_id === tid; }) : [];
  if (!mine.length) mine = turns.slice(-8);
  var c = convById(convId);
  body.innerHTML = '<div class="thread">' + mine.map(bubble).join('') + '</div>' +
    '<div class="take"><textarea class="plain" rows="3" aria-label="Reply to ' + esc(nameOf(c)) + '" placeholder="Step in: write to ' + esc(firstName(nameOf(c))) + '…"></textarea>' +
    '<div class="f-actions"><button class="btn btn-primary btn-sm" data-take="' + esc(convId) + '">Send on ' + esc(chMeta(c.last_channel).label) + '</button><button class="btn btn-quiet btn-sm" data-classic-conv="' + esc(convId) + '">Open in classic workspace</button></div></div>';
  $$('[data-take]', body).forEach(function (b) { b.addEventListener('click', function () { var ta = $('textarea', body); sendOwn({ name: nameOf(c), c: c }, ta.value, convId); }); });
  $$('[data-classic-conv]', body).forEach(function (b) { b.addEventListener('click', function () { openClassic('inbox', convId); }); });
}
function bindAI() {
  $$('[data-ait]').forEach(function (b) { b.addEventListener('click', function () { S.aiTab = b.getAttribute('data-ait'); render(); }); });
  $$('details.item').forEach(function (d) { d.addEventListener('toggle', function () { if (d.open) fillAiItem(d); }); });
  $$('[data-open-work]').forEach(function (b) { b.addEventListener('click', function () { S.cur = b.getAttribute('data-open-work'); go('work'); }); });
}

// ── TEAM & AI: every number derived here from tickets, drafts and LLM usage ───
function windowOf(period, back) {
  var ms = PERIOD_DAYS[period] * 86400000, end = Date.now() - (back ? ms : 0);
  return { start: end - ms, end: end };
}
function inWin(iso, w) { var t = ts(iso); return t != null && t >= w.start && t < w.end; }
function isAsIs(d) { return (d.sent_text || '').trim() === (d.draft_text || '').trim(); }
function metrics(period, back) {
  var w = windowOf(period, back);
  var tk = D.tickets.filter(function (t) { return inWin(t.created_at, w); });
  var dr = D.drafts.filter(function (d) { return inWin(d.created_at, w) && d.channel !== 'offer'; });
  var auto = tk.filter(function (t) { return t.status === 'logged'; }).length, person = tk.length - auto;
  var sent = dr.filter(function (d) { return d.status === 'sent'; });
  var asis = sent.filter(isAsIs).length, edited = sent.length - asis, disc = dr.filter(function (d) { return d.status === 'discarded'; }).length;
  var pending = dr.filter(function (d) { return d.status === 'pending'; }).length, decided = asis + edited + disc;
  var reasons = {};
  dr.forEach(function (d) { var k = codeOf(d.reason_code) || 'other'; reasons[k] = (reasons[k] || 0) + 1; });
  return { w: w, tickets: tk, drafts: dr, inbound: tk.length, auto: auto, person: person, asis: asis, edited: edited, disc: disc, pending: pending, decided: decided, reasons: reasons,
    autoP: tk.length ? auto / tk.length * 100 : null, personP: tk.length ? person / tk.length * 100 : null, asisP: decided ? asis / decided * 100 : null };
}
function costOf(period) {
  var l = D.llm[period]; if (!l || !l.cur) return { cur: null, prev: null };
  var cur = (l.cur.totals || {}).estimated_cost_usd, both = l.both ? (l.both.totals || {}).estimated_cost_usd : null;
  return { cur: cur == null ? null : cur, prev: both == null || cur == null ? null : Math.max(0, both - cur) };
}
function change(cur, prev, goodUp, pts) {
  if (cur == null || prev == null) return '';
  var d = cur - prev; if (Math.abs(d) < (pts ? 0.05 : 1e-9)) return 'no change';
  if (!pts && !prev) return '';
  var good = goodUp ? d > 0 : d < 0, txt = pts ? Math.abs(d).toFixed(1) + ' points' : Math.abs(d / prev * 100).toFixed(0) + '%';
  return '<span class="' + (good ? 'good' : 'bad') + '">' + (d > 0 ? 'up ' : 'down ') + txt + '</span>';
}
function pctTxt(v) { return v == null ? '—' : v.toFixed(0) + '%'; }
var PERIOD_TXT = { '24h': ['in the last 24 hours', 'the 24 hours before'], '7d': ['this week', 'the previous 7 days'], '30d': ['this month', 'the previous 30 days'] };
function teamHTML() {
  var tabs = [['overview', 'Overview'], ['topics', 'Topics'], ['team', 'People']];
  var controls = '<div class="hero-row"><div class="seg" role="group" aria-label="Section">' + tabs.map(function (x) { return '<button data-tt="' + x[0] + '" aria-pressed="' + (S.teamTab === x[0]) + '">' + x[1] + '</button>'; }).join('') + '</div><span class="grow"></span>' +
    '<div class="seg" role="group" aria-label="Period">' + [['24h', '24 hours'], ['7d', '7 days'], ['30d', '30 days']].map(function (x) { return '<button data-p="' + x[0] + '" aria-pressed="' + (S.period === x[0]) + '">' + x[1] + '</button>'; }).join('') + '</div></div>';
  var m = metrics(S.period, false), pm = metrics(S.period, true), pt = PERIOD_TXT[S.period];
  var top, body;
  if (S.teamTab === 'overview') {
    var cost = costOf(S.period), resolvedN = m.auto + m.asis + m.edited, prevResolved = pm.auto + pm.asis + pm.edited;
    var cpr = cost.cur != null && resolvedN ? cost.cur / resolvedN : null, pcpr = cost.prev != null && prevResolved ? cost.prev / prevResolved : null;
    var chg = change(m.autoP, pm.autoP, true, true).replace(/<[^>]+>/g, '');
    top = hero(controls + '<div><div class="eyebrow">AI performance · ' + pt[0] + '</div>' +
      (m.inbound ? '<p class="big">The AI resolved <em>' + pctTxt(m.autoP) + '</em> of conversations on its own.</p><p>' + m.auto + ' of ' + m.inbound + (chg ? ', ' + chg + ' on ' + pt[1] : '') + '.</p>'
        : '<p class="big">No conversations ' + pt[0] + ' yet.</p><p>Numbers appear here as soon as customers write in.</p>') + '</div>' +
      '<div class="tiles">' +
      '<div class="htile"><span class="k">Needed a person</span><span class="v num">' + pctTxt(m.personP) + '</span><span class="d">' + m.person + ' conversation' + (m.person === 1 ? '' : 's') + (change(m.personP, pm.personP, false, true) ? ' · ' + change(m.personP, pm.personP, false, true) : '') + '</span></div>' +
      '<div class="htile"><span class="k">AI drafts sent without changes</span><span class="v num">' + pctTxt(m.asisP) + '</span><span class="d">of ' + m.decided + ' reviewed' + (change(m.asisP, pm.asisP, true, true) ? ' · ' + change(m.asisP, pm.asisP, true, true) : '') + '</span></div>' +
      '<div class="htile"><span class="k">Cost per resolution</span><span class="v num">' + (cpr == null ? '—' : '$' + cpr.toFixed(4)) + '</span><span class="d">LLM spend' + (cost.cur != null ? ' $' + cost.cur.toFixed(2) : '') + (change(cpr, pcpr, false, false) ? ' · ' + change(cpr, pcpr, false, false) : '') + '</span></div></div>');
    body = overviewHTML(m);
  } else {
    var ttl = { topics: ['Where people step in', 'Topics where the AI hands over or its drafts get rewritten, ' + pt[0] + '.'], team: ['People and the AI, side by side', 'Who is holding what right now, and what each resolved ' + pt[0] + '.'] }[S.teamTab];
    top = hero(controls + '<div><div class="eyebrow">AI performance</div><h1>' + ttl[0] + '</h1><p>' + ttl[1] + '</p></div>');
    body = S.teamTab === 'topics' ? topicsHTML(m) : peopleHTML(m);
  }
  return top + '<div class="wrap">' + body + '</div>';
}
function topicRows(m) {
  var byTicket = {}; m.tickets.forEach(function (t) { byTicket[t.ticket_id] = t; });
  var rows = {};
  function row(k) { return rows[k] || (rows[k] = { k: k, auto: 0, asis: 0, edit: 0, disc: 0, other: 0 }); }
  m.tickets.forEach(function (t) { if (t.status === 'logged') row(t.intent).auto++; });
  var drafted = {};
  m.drafts.forEach(function (d) {
    var t = byTicket[d.ticket_id] || ticketById(d.ticket_id); if (!t) return;
    drafted[t.ticket_id] = true;
    if (d.status === 'sent') { if (isAsIs(d)) row(t.intent).asis++; else row(t.intent).edit++; }
    else if (d.status === 'discarded') row(t.intent).disc++;
  });
  m.tickets.forEach(function (t) { if (t.status !== 'logged' && !drafted[t.ticket_id]) row(t.intent).other++; });
  return Object.keys(rows).map(function (k) { var r = rows[k]; r.tot = r.auto + r.asis + r.edit + r.disc + r.other; r.touch = r.tot ? (r.tot - r.auto) / r.tot : 0; return r; })
    .filter(function (r) { return r.tot > 0; }).sort(function (a, b) { return b.touch - a.touch || b.tot - a.tot; });
}
function insightHTML(m) {
  var best = null;
  topicRows(m).forEach(function (r) { var rev = r.asis + r.edit + r.disc; if (rev >= 3 && (!best || r.edit / rev > best.edit / (best.asis + best.edit + best.disc))) best = r; });
  if (!best || !best.edit) return '';
  var rev = best.asis + best.edit + best.disc;
  return '<div class="insight"><span class="ic">' + ICON.bulb + '</span><div><h3>One thing worth a look</h3><p>People rewrote ' + best.edit + ' of ' + rev + ' AI drafts about ' + esc(intentLabel(best.k).toLowerCase()) + '. The knowledge behind those answers may be missing something.</p></div><button class="btn" data-topic="' + esc(best.k) + '">See the edits</button></div>';
}
function overviewHTML(m) {
  if (!m.inbound && !m.drafts.length) return '<div class="panel caught">' + ICON.check + '<p>Nothing to measure in this period yet.</p></div>';
  function segB(v, tot, color, label, light) { if (!v || !tot) return ''; var w = v / tot * 100; return '<div class="seg-b' + (light ? ' light' : '') + '" style="flex:0 0 calc(' + w.toFixed(3) + '% - 2px);background:' + color + '" title="' + label + ': ' + v + '">' + (w > 14 ? label : '') + '</div>'; }
  var held = m.asis + m.edited + m.disc + m.pending, autoW = m.inbound ? m.auto / m.inbound * 100 : 0;
  var funnel = '<div class="panel"><h3>Where conversations end up</h3><p class="cap">What the AI answered alone, and what people did with its drafts</p>' +
    '<div class="fn-row"><span class="fn-lbl">All</span><div class="fn-bar">' + segB(m.auto, m.inbound, 'var(--viz-ai)', 'Answered by AI') + segB(m.person, m.inbound, 'var(--viz-held)', 'Person') + '</div></div>' +
    (held ? '<div class="fn-link" style="clip-path:polygon(' + autoW.toFixed(2) + '% 0,100% 0,100% 100%,0 100%)"></div>' +
    '<div class="fn-row"><span class="fn-lbl">AI drafts held</span><div class="fn-bar">' + segB(m.asis, held, 'var(--viz-asis)', 'Sent as-is', true) + segB(m.edited, held, 'var(--viz-edit)', 'Edited') + segB(m.disc, held, 'var(--viz-disc)', 'Replaced') + segB(m.pending, held, 'var(--viz-pend)', 'Waiting') + '</div></div>' : '') +
    '<div class="legend">' + [['var(--viz-ai)', 'Answered by AI', m.auto], ['var(--viz-held)', 'Needed a person', m.person], ['var(--viz-asis)', 'Draft sent as-is', m.asis], ['var(--viz-edit)', 'Draft edited', m.edited], ['var(--viz-disc)', 'Draft replaced', m.disc], ['var(--viz-pend)', 'Waiting now', m.pending]]
      .filter(function (x) { return x[2]; }).map(function (x) { return '<span><i style="background:' + x[0] + '"></i>' + x[1] + ' <b>' + x[2] + '</b></span>'; }).join('') + '</div></div>';
  var rs = Object.keys(m.reasons).map(function (k) { return [k, WHY_SHORT[k] || intentLabel(k), m.reasons[k]]; }).sort(function (a, b) { return b[2] - a[2]; });
  if (rs.length > 5) { var rest = rs.slice(4).reduce(function (s, r) { return s + r[2]; }, 0); rs = rs.slice(0, 4).concat([['other', 'Other reasons', rest]]); }
  var max = rs.length ? rs[0][2] : 1;
  var reasons = '<div class="panel"><h3>Why the AI asked for help</h3><p class="cap">' + m.drafts.length + ' held draft' + (m.drafts.length === 1 ? '' : 's') + '</p>' +
    (rs.length ? '<div class="rbars">' + rs.map(function (r) { return '<div class="rbar"><div class="l"><span>' + esc(r[1]) + '</span><b>' + r[2] + '</b></div><div class="track"><i style="width:' + (r[2] / max * 100).toFixed(1) + '%"></i></div></div>'; }).join('') + '</div>' : '<p class="note">No drafts were held.</p>') + '</div>';
  var trend = '<div class="panel"><h3>Over time</h3><p class="cap" id="cxColCap"></p><div class="chart" id="cxColChart"></div><div class="legend" style="margin-left:0"><span><i style="background:var(--viz-ai)"></i>Answered by AI</span><span><i style="background:var(--viz-held)"></i>Needed a person</span></div></div>';
  return insightHTML(m) + '<div class="two">' + funnel + reasons + '</div>' + trend;
}
function topicsHTML(m) {
  var rows = topicRows(m);
  if (!rows.length) return '<div class="panel caught">' + ICON.check + '<p>No conversations in this period yet.</p></div>';
  if (!S.topic || !rows.some(function (r) { return r.k === S.topic; })) S.topic = rows[0].k;
  var list = '<div class="panel"><h3>How often people step in, by topic</h3><p class="cap">Choose a topic to see what people changed.</p><div class="topics">' + rows.map(function (r) {
    var segs = [[r.auto, 'var(--viz-ai)'], [r.asis, 'var(--viz-asis)'], [r.edit, 'var(--viz-edit)'], [r.disc, 'var(--viz-disc)'], [r.other, 'var(--viz-held)']].filter(function (s) { return s[0] > 0; }).map(function (s) { return '<i style="flex:' + s[0] + ';background:' + s[1] + '"></i>'; }).join('');
    return '<button class="topic" data-topic="' + esc(r.k) + '" aria-pressed="' + (S.topic === r.k) + '"><span class="tn">' + esc(intentLabel(r.k)) + '<small>' + r.tot + ' conversation' + (r.tot === 1 ? '' : 's') + '</small></span><span class="stack" title="Answered by AI ' + r.auto + ' · sent as-is ' + r.asis + ' · edited ' + r.edit + ' · replaced ' + r.disc + ' · handled by a person ' + r.other + '">' + segs + '</span><span class="pc">' + (r.touch * 100).toFixed(0) + '%</span></button>';
  }).join('') + '</div><div class="legend" style="margin-left:12px"><span><i style="background:var(--viz-ai)"></i>Answered by AI</span><span><i style="background:var(--viz-asis)"></i>Sent as-is</span><span><i style="background:var(--viz-edit)"></i>Edited</span><span><i style="background:var(--viz-disc)"></i>Replaced</span><span><i style="background:var(--viz-held)"></i>Person, no draft</span><span class="muted">Right: share that needed a person</span></div></div>';
  var edits = m.drafts.filter(function (d) { var t = ticketById(d.ticket_id); return t && t.intent === S.topic && d.status === 'sent' && !isAsIs(d); })
    .sort(function (a, b) { return ts(b.decided_at) - ts(a.decided_at); });
  var diff = '<div class="panel" id="cxDiffCard"><h3>What people changed · ' + esc(intentLabel(S.topic)) + '</h3>' +
    (edits.length ? '<p class="cap">The latest of ' + edits.length + ' edited draft' + (edits.length === 1 ? '' : 's') + '. Struck-through text is the AI\'s, highlighted text is the person\'s.</p><div class="diff">' + wordDiff(edits[0].draft_text || '', edits[0].sent_text || '') + '</div>'
      : '<p class="cap" style="margin:0">Nobody edited an AI draft on this topic in this period.</p>') + '</div>';
  return '<div class="two">' + list + '<div>' + diff + '</div></div>';
}
// Real people only. /admin/agents also returns the Service Desk's routing bench - twelve
// seeded rows (scripts/seed_service_desk_agents.py) that exist so tickets have somewhere to
// route and that nobody can sign in as. The seed's own rule tells them apart: every seeded
// agent has a team, every real account is left team-less (is_operator). Each person's
// numbers are what they actually did in the period, read from the records their actions
// wrote: drafts they decided, cases they closed, replies they sent.
function peopleHTML(m) {
  var w = m.w, meName = actor();
  var real = (D.agents || []).filter(function (a) { return a.is_operator; });
  if (!real.some(function (a) { return a.username === meName; }) && meName !== 'admin') real.unshift({ username: meName, is_operator: true, open_count: 0 });
  var bench = (D.agents || []).filter(function (a) { return !a.is_operator; });
  var benchOpen = bench.reduce(function (n, a) { return n + (a.open_count || 0); }, 0);
  var aiRow = '<tr class="ai"><td><span class="ai-tag">AI</span>AI Agent<span class="sub">All channels</span></td><td><span class="muted">Always on</span></td><td class="ar num">' + m.auto + '</td><td class="ar num">—</td><td class="ar num">Seconds</td></tr>';
  var rows = real.map(function (a) {
    var decided = m.drafts.filter(function (d) { return d.decided_by === a.username && d.status !== 'pending' && inWin(d.decided_at, w); });
    var closed = D.tickets.filter(function (t) { return t.closed_by === a.username && t.status === 'closed' && inWin(t.updated_at, w); }).length;
    var sentAsIs = decided.filter(function (d) { return d.status === 'sent' && isAsIs(d); }).length;
    var mine = D.tickets.filter(function (t) { return t.assigned_to === a.username; });
    var fr = median(mine.filter(function (t) { return t.first_response_at && inWin(t.created_at, w); }).map(function (t) { return (ts(t.first_response_at) - ts(t.created_at)) / 60000; }).filter(function (x) { return x >= 0; }));
    var away = a.availability === 'away', you = a.username === meName;
    return '<tr><td><span class="pdot ' + (away ? 'away' : 'is-on') + '"></span>' + esc(a.username) + (you ? ' <span class="muted">(you)</span>' : '') +
      '<span class="sub">' + (away ? 'Away' : 'Active') + (a.breaching ? ' · <span class="upset">' + a.breaching + ' overdue</span>' : '') + '</span></td>' +
      '<td class="num">' + (a.open_count || 0) + ' open</td>' +
      '<td class="ar num">' + (decided.length + closed) + '</td>' +
      '<td class="ar num">' + (decided.length ? Math.round(sentAsIs / decided.length * 100) + '%' : '—') + '</td>' +
      '<td class="ar num">' + (fr == null ? '—' : fmtMin(Math.round(fr))) + '</td></tr>';
  }).join('');
  var empty = real.length ? '' : '<tr><td colspan="5" class="muted">No one has signed in to this workspace yet.</td></tr>';
  return '<div class="panel"><div class="table-scroll"><table class="people"><thead><tr><th>Who</th><th>Open now</th><th class="ar">Handled</th><th class="ar">AI drafts sent as-is</th><th class="ar">Typical first reply</th></tr></thead><tbody>' + aiRow + rows + empty + '</tbody></table></div></div>' +
    '<p class="note">Handled counts drafts a person approved or replaced and cases they closed in this period. People who can sign in are listed' +
    (bench.length ? '; ' + (bench.length === 1 ? 'one routing-bench agent is' : bench.length + ' routing-bench agents are') + ' not' + (benchOpen ? ' (holding ' + benchOpen + ' open case' + (benchOpen === 1 ? '' : 's') + ', see Assign &amp; track)' : '') : '') + '.</p>';
}
function bindTeam() {
  $$('[data-tt]').forEach(function (b) { b.addEventListener('click', function () { S.teamTab = b.getAttribute('data-tt'); render(); }); });
  $$('[data-p]').forEach(function (b) { b.addEventListener('click', function () { S.period = b.getAttribute('data-p'); render(); loadTeam().then(function () { if (S.view === 'team') render(); }); }); });
  $$('[data-topic]').forEach(function (b) { b.addEventListener('click', function () { S.topic = b.getAttribute('data-topic'); S.teamTab = 'topics'; render(); var d = $('#cxDiffCard'); if (d && window.innerWidth < 1100) d.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }); });
  if (S.teamTab === 'overview') drawColumns();
}
function drawColumns() {
  var box = $('#cxColChart'); if (!box) return;
  var w = windowOf(S.period, false), hourly = S.period === '24h', n = hourly ? 24 : PERIOD_DAYS[S.period], step = hourly ? 3600000 : 86400000;
  var start = hourly ? w.end - 24 * step : (function () { var d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime() - (n - 1) * step; })();
  var auto = [], held = [], labels = [], MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  for (var i = 0; i < n; i++) { auto.push(0); held.push(0); var d = new Date(start + i * step); labels.push(hourly ? String(d.getHours()).padStart(2, '0') + ':00' : d.getDate() + ' ' + MON[d.getMonth()]); }
  D.tickets.forEach(function (t) { var x = ts(t.created_at); if (x == null || x < start) return; var k = Math.floor((x - start) / step); if (k < 0 || k >= n) return; if (t.status === 'logged') auto[k]++; else held[k]++; });
  var W = Math.max(300, box.clientWidth || 700), H = 190, pl = 36, pr = 4, pt = 8, pb = 24;
  var max = Math.max(1, Math.max.apply(null, auto.map(function (a, k) { return a + held[k]; })));
  var st = Math.pow(10, Math.floor(Math.log10(max))); if (Math.ceil(max / st) <= 3 && st > 1) st /= 2; st = Math.max(1, st); var ymax = Math.ceil(max / st) * st;
  var cw = (W - pl - pr) / n, bw = Math.max(3, Math.min(28, cw * 0.55));
  function y(v) { return pt + (H - pt - pb) * (1 - v / ymax); }
  var g = ''; for (var v = 0; v <= ymax; v += st) g += '<line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="var(--grid)"/><text x="' + (pl - 8) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + v + '</text>';
  var every = n > 14 ? Math.ceil(n / 7) : (n > 8 ? 4 : 1), bars = '';
  for (var j = 0; j < n; j++) {
    var x = pl + cw * j + (cw - bw) / 2, ya = y(auto[j]), yh = y(auto[j] + held[j]), hh = held[j] ? ya - 2 - yh : 0, r = Math.max(0, Math.min(4, bw / 2, hh));
    bars += '<g class="col" data-i="' + j + '"><rect x="' + (pl + cw * j) + '" y="' + pt + '" width="' + cw + '" height="' + (H - pt - pb) + '" fill="transparent"/>' +
      (auto[j] ? '<rect x="' + x + '" y="' + ya + '" width="' + bw + '" height="' + Math.max(0, y(0) - ya) + '" fill="var(--viz-ai)"/>' : '') +
      (hh > 0 ? '<path d="M' + x + ',' + (ya - 2) + ' V' + (yh + r) + ' q0,-' + r + ' ' + r + ',-' + r + ' H' + (x + bw - r) + ' q' + r + ',0 ' + r + ',' + r + ' V' + (ya - 2) + ' Z" fill="var(--viz-held)"/>' : '');
    if (j % every === 0 || j === n - 1) bars += '<text x="' + (x + bw / 2) + '" y="' + (H - 6) + '" text-anchor="middle">' + labels[j] + '</text>';
    bars += '</g>';
  }
  box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Conversations answered by AI and by people per ' + (hourly ? 'hour' : 'day') + '">' + g + bars + '</svg><div class="tip" hidden></div>';
  var cap = $('#cxColCap'); if (cap) cap.textContent = (hourly ? 'Per hour' : 'Per day') + '. Hover a column for numbers.';
  var tip = $('.tip', box);
  $$('.col', box).forEach(function (c) {
    c.addEventListener('mousemove', function () {
      var k = +c.getAttribute('data-i'), rect = box.getBoundingClientRect(), sx = rect.width / W;
      tip.innerHTML = '<b>' + labels[k] + '</b><div><i style="background:var(--viz-ai)"></i>Answered by AI ' + auto[k] + '</div><div><i style="background:var(--viz-held)"></i>Needed a person ' + held[k] + '</div>';
      tip.hidden = false; tip.style.left = Math.min(rect.width - 80, Math.max(80, (pl + cw * (k + 0.5)) * sx)) + 'px'; tip.style.top = (y(auto[k] + held[k]) * sx - 8) + 'px';
    });
    c.addEventListener('mouseleave', function () { tip.hidden = true; });
  });
}
function wordDiff(a, b) {
  var A = a.split(/\s+/).filter(Boolean), B = b.split(/\s+/).filter(Boolean);
  if (A.length * B.length > 250000) return '<ins>' + esc(b) + '</ins>';
  var m = A.length, n = B.length, L = [], i, j;
  for (i = 0; i <= m; i++) L.push(new Array(n + 1).fill(0));
  for (i = m - 1; i >= 0; i--) for (j = n - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  var out = []; i = 0; j = 0;
  while (i < m && j < n) { if (A[i] === B[j]) { out.push(esc(A[i])); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) { out.push('<del>' + esc(A[i]) + '</del>'); i++; } else { out.push('<ins>' + esc(B[j]) + '</ins>'); j++; } }
  while (i < m) out.push('<del>' + esc(A[i++]) + '</del>'); while (j < n) out.push('<ins>' + esc(B[j++]) + '</ins>');
  return out.join(' ');
}
var rz; window.addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(function () { if (running && S.view === 'team' && S.teamTab === 'overview') drawColumns(); }, 150); });

// ── lifecycle, driven by app.js showStage('console') ────────────────────────
window.CX2 = {
  start: function () {
    var host = document.getElementById('cx2Root'); if (!host) return;
    if (!root) { root = host; root.innerHTML = shell(); bindShell(); }
    WHERE.stage = 'console';
    running = true; render(); refresh(true);
    if (S.view === 'team') loadTeam().then(function () { if (S.view === 'team') render(); });
    clearInterval(pollTimer); pollTimer = setInterval(poll, 15000);
  },
  stop: function () { running = false; clearInterval(pollTimer); pollTimer = null; },
  reset: function () {
    if (root) { root.innerHTML = ''; } root = null; S.cur = null; S.loaded = false; D.detail = {}; skips = {};
    var side = document.getElementById('cxSide'); if (side) { side.innerHTML = ''; side.hidden = true; }
  },
  // Called by showStage for every stage: the shared sidebar shows on the two signed-in
  // stages (the console and the classic pages) and nowhere else.
  side: function (stage) {
    var signedIn = stage === 'console' || stage === 'app', el = sideHost();
    document.body.classList.toggle('cx-signed-in', signedIn);
    el.hidden = !signedIn;
    if (!signedIn) return;
    if (!el.firstChild) el.innerHTML = sideHTML();
    WHERE.stage = stage;
    markSide();
  },
  // Called by switchPage, so the sidebar follows a classic page change made from inside it
  // (for example Service Desk opening a case in the Agent Workspace).
  onPage: function (name) { WHERE.page = name; markSide(); }
};
document.addEventListener('visibilitychange', function () { if (running && !document.hidden) refresh(false); });
})();
