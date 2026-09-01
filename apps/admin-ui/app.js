(function () {
'use strict';

// ── Channel metadata ─────────────────────────────────────────────────────────
var CH = {
  whatsapp: { label:'WhatsApp', pill:'pwa', stripe:'cwa', bg:'#f0fdf4', bd:'#bbf7d0', clr:'#16a34a',
    svg:'<svg viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51C10.25 6.01 10.052 6 9.853 6c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413z"/><path d="M20.52 3.449C12.831-3.984.106 1.407.101 11.893c0 2.096.549 4.14 1.595 5.945L.057 24l6.335-1.652c1.746.943 3.71 1.444 5.71 1.447h.006c9.756 0 15.466-8.65 11.466-16.001a11.816 11.816 0 0 0-3.054-4.345z"/></svg>' },
  email:    { label:'Email', pill:'pem', stripe:'cem', bg:'#eff6ff', bd:'#bfdbfe', clr:'#2563eb',
    svg:'<svg viewBox="0 0 24 24"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>' },
  phone:    { label:'Phone', pill:'pcl', stripe:'ccl', bg:'#fffbeb', bd:'#fde68a', clr:'#d97706',
    svg:'<svg viewBox="0 0 24 24"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg>' },
  web_chat: { label:'Web Chat', pill:'pwc', stripe:'cwc', bg:'#f5f3ff', bd:'#ddd6fe', clr:'#6d28d9',
    svg:'<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>' },
};
function chMeta(ch) { return CH[(ch||'').toLowerCase()] || { label: ch||'?', pill:'pdef', stripe:'cdef', bg:'#f2f4f7', bd:'#e4e7ec', clr:'#98a2b3', svg:'' }; }

// ── Theme / sub-theme grouping ────────────────────────────────────────────────
// The conversation flow groups consecutive turns by THEME (the team an intent
// maps to) with a labelled divider, and marks SUB-THEME (the intent) shifts
// inside a theme with a lighter marker. Both are derived purely from the
// `intent` already on each turn — no backend/schema change. Mirrors
// INTENT_TO_TEAM in shared/constants/intents.py.
var INTENT_TO_TEAM = {
  account_balance_inquiry: 'retail_banking',
  transaction_dispute:     'fraud_and_disputes',
  fund_transfer:           'payments',
  loan_status:             'loans',
  loan_application:        'loans',
  loan_default_notice:     'collections',
  policy_status:           'insurance_operations',
  claim_status:            'claims',
  insurance_claim:         'claims',
  card_management:         'card_services',
  kyc_update:              'compliance',
  fraud_report:            'fraud_and_disputes',
  complaint:               'customer_care',
  ticket_status:           'customer_care',
  general_inquiry:         'customer_care',
  human_escalation:        'customer_care'
};
var TEAM_LABEL = {
  retail_banking:       'Retail Banking',
  payments:             'Payments',
  loans:                'Loans',
  collections:          'Collections',
  insurance_operations: 'Insurance Ops',
  claims:               'Claims',
  card_services:        'Card Services',
  compliance:           'Compliance',
  fraud_and_disputes:   'Fraud & Disputes',
  customer_care:        'Customer Care'
};
// A stable colour per theme so dividers are visually distinct. Uses the same
// token vocabulary as the rest of the flow view (border/bg/text triples).
var THEME_COLOR = {
  card_services:        { t:'var(--wc)',    bg:'var(--wc-bg)',   bd:'var(--wc-bd)' },
  loans:                { t:'#db2777',      bg:'#fdf2f8',        bd:'#fbcfe8' },
  collections:          { t:'#db2777',      bg:'#fdf2f8',        bd:'#fbcfe8' },
  fraud_and_disputes:   { t:'var(--amb-t)', bg:'var(--amb-bg)',  bd:'var(--amb-bd)' },
  retail_banking:       { t:'var(--grn-t)', bg:'var(--grn-bg)',  bd:'var(--grn-bd)' },
  payments:             { t:'var(--grn-t)', bg:'var(--grn-bg)',  bd:'var(--grn-bd)' },
  claims:               { t:'var(--blue-t)',bg:'var(--blue-bg)', bd:'var(--blue-bd)' },
  insurance_operations: { t:'var(--blue-t)',bg:'var(--blue-bg)', bd:'var(--blue-bd)' },
  compliance:           { t:'var(--t2)',    bg:'var(--surf2)',   bd:'var(--bdr)' },
  customer_care:        { t:'var(--t2)',    bg:'var(--surf2)',   bd:'var(--bdr)' },
  general:              { t:'var(--t3)',    bg:'var(--surf2)',   bd:'var(--bdr)' }
};
// System-event "intents" that aren't real customer topics — excluded from
// grouping and from node/row titles so they never surface as a theme.
var NON_TOPIC_INTENTS = { ticket_closure: 1 };
function topicOrEmpty(intent) { return NON_TOPIC_INTENTS[intent] ? '' : (intent || ''); }
// Prettify a raw intent key into a display label, e.g. "fraud_report" →
// "Fraud Report". Empty/unknown intent falls back to "General".
function intentLabel(intent) {
  var key = (intent || '').toLowerCase();
  if (!key) return 'General';
  return key.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
}
// Groups are keyed on the raw INTENT (finer-grained than team). Colour is still
// looked up via the intent's team, so related intents (e.g. Fraud Report &
// Transaction Dispute) share a colour family without merging into one group.
function themeOf(intent) {
  var key = (intent || '').toLowerCase();
  var team = INTENT_TO_TEAM[key] || 'general';
  var themeKey = key || 'general';
  return { theme: themeKey, themeLabel: intentLabel(key), color: THEME_COLOR[team] || THEME_COLOR.general };
}

// A bank-initiated offer has no customer intent of its own, so map its product
// to the intent whose theme it belongs to. This lets an offer be grouped by the
// app's existing intent→theme machinery: it joins the matching topic group when
// one exists, else forms its own themed group (never glued under an unrelated
// query). Products not listed fall back to 'general_inquiry'.
var OFFER_PRODUCT_INTENT = {
  term_insurance: 'policy_status',
  health_insurance: 'policy_status',
  insurance_policy: 'policy_status',
  credit_card: 'card_management',
  premium_card_upgrade: 'card_management',
  personal_loan_info: 'loan_status',
  fixed_deposit: 'account_balance_inquiry',
  fd_renewal: 'account_balance_inquiry',
  premium_account_tier: 'account_balance_inquiry',
  charge_waiver_account_upgrade: 'account_balance_inquiry'
};
function offerIntentOf(step) {
  var o = step.outbound;
  var product = o && o.metadata && o.metadata.product;
  return OFFER_PRODUCT_INTENT[(product || '').toLowerCase()] || 'general_inquiry';
}
// True for an admin-approved bank-initiated offer turn (Opportunities flow):
// an outbound turn tagged opportunity_offer with no paired customer message.
function isOfferStep(step) {
  var o = step.outbound;
  return !!(o && o.metadata && o.metadata.source === 'opportunity_offer' && !step.inbound);
}
// The draft_id shared by every delivery of ONE offer — its grouping key, the
// role ticket_id plays for a ticket (the same offer goes to WhatsApp + email as
// separate turns sharing this id).
function offerDraftId(step) {
  var o = step.outbound;
  return (o && o.metadata && o.metadata.draft_id) || null;
}

// ── Auth state ────────────────────────────────────────────────────────────────
var adminKey = sessionStorage.getItem('cx-admin-key') || '';
var adminToken = sessionStorage.getItem('cx-admin-jwt') || '';
var userToken = sessionStorage.getItem('cx-user-jwt') || '';
var currentUser = null;
var portalUser = null;

try {
  var savedUser = sessionStorage.getItem('cx-admin-user');
  if (savedUser) currentUser = JSON.parse(savedUser);
} catch(e) {}
try {
  var savedPortalUser = sessionStorage.getItem('cx-user-account');
  if (savedPortalUser) portalUser = JSON.parse(savedPortalUser);
} catch(e) {}

var state = { convs: [], selectedConvId: null, convDetail: null, simTimer: null, sseSource: null, pendingDrafts: {},
  // Open Tickets card expanded? Collapsed by default - the count in the header is the
  // signal; the rows are for acting on. Held here so the choice survives the poll
  // re-render, and shared across conversations (it is a display preference, not data).
  tktOpen: false,
  // Theme-group fold state. Keyed "<conversation_id>:<groupIndex>"; presence in
  // the Set = collapsed. Persists across the inbox poll re-render. `themeSeeded`
  // tracks which conversations have had their default (all-but-latest collapsed)
  // applied, so re-renders don't re-collapse groups the agent opened.
  collapsedThemes: {}, themeSeeded: {},
  // Conversation view mode per conversation_id: 'detailed' (spine, default) or
  // 'lineage' (compact 3-column history overview). Clicking a lineage row drills
  // back into 'detailed', focused on that request.
  convView: {},
  // Which single request the Detailed view is focused on, per conversation_id.
  // Value = a request key (ticket_id, or 'u<idx>' for an unticketed request).
  // Defaults to the latest request; a lineage row click sets it to that request.
  detailFocus: {} };
var rtTimers = [];

function isTokenExpired(token) {
  if (!token) return true;
  try {
    var parts = token.split('.');
    if (parts.length !== 3) return true;
    var payload = JSON.parse(atob(parts[1]));
    return (payload.exp || 0) < Math.floor(Date.now() / 1000);
  } catch(e) { return true; }
}

function adminHeaders() {
  var h = { 'x-admin-key': adminKey };
  if (adminToken) h['Authorization'] = 'Bearer ' + adminToken;
  return h;
}

async function api(path, opts) {
  opts = opts || {};
  var headers = Object.assign({}, adminHeaders(), opts.headers || {});
  if (opts.body) headers['content-type'] = 'application/json';
  var r = await fetch(path, Object.assign({}, opts, { headers: headers }));
  var data = await r.json().catch(function() { return {}; });
  if (!r.ok) throw new Error(data.detail || (r.status + ' ' + r.statusText));
  return data;
}

function toast(msg) {
  var el = document.getElementById('toastEl');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(function() { el.classList.remove('show'); }, 2400);
}

// ── Stage management ──────────────────────────────────────────────────────────
function showStage(stage) {
  document.getElementById('connectModal').classList.toggle('hidden', stage !== 'apikey');
  document.getElementById('authPage').classList.toggle('hidden', stage !== 'auth');
  document.getElementById('mainShell').style.display = stage === 'app' ? 'flex' : 'none';
  document.getElementById('userPortal').style.display = stage === 'user' ? 'flex' : 'none';
}

window.switchLoginMode = function(mode) {
  var isAdmin = mode === 'admin';
  document.getElementById('adminModeForm').style.display = isAdmin ? 'flex' : 'none';
  document.getElementById('userModeForm').style.display = isAdmin ? 'none' : 'flex';
  document.getElementById('modeAdminBtn').classList.toggle('active', isAdmin);
  document.getElementById('modeUserBtn').classList.toggle('active', !isAdmin);
  document.getElementById('connectErr').classList.remove('show');
  document.getElementById('userLoginErr').classList.remove('show');
};

window.switchCustomerAuth = function(tab) {
  var isLogin = tab === 'login';
  document.getElementById('customerLoginForm').style.display = isLogin ? 'flex' : 'none';
  document.getElementById('customerSignupForm').style.display = isLogin ? 'none' : 'flex';
  document.getElementById('customerLoginTab').classList.toggle('active', isLogin);
  document.getElementById('customerSignupTab').classList.toggle('active', !isLogin);
  document.getElementById('userLoginErr').classList.remove('show');
};

function onCustomerAuthSuccess(data) {
  userToken = data.token;
  portalUser = data.user;
  sessionStorage.setItem('cx-user-jwt', userToken);
  sessionStorage.setItem('cx-user-account', JSON.stringify(portalUser));
  showStage('user');
  bootUserPortal();
}

// ── STAGE 1: API Key ──────────────────────────────────────────────────────────
document.getElementById('connectBtn').addEventListener('click', async function() {
  var key = document.getElementById('adminKeyInput').value.trim();
  if (!key) return;
  var err = document.getElementById('connectErr');
  err.classList.remove('show');
  var btn = document.getElementById('connectBtn');
  btn.disabled = true; btn.textContent = 'Verifying…';
  try {
    var res = await fetch('/admin/auth/verify-key', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ api_key: key })
    });
    var data = await res.json().catch(function(){ return {}; });
    if (!res.ok) throw new Error(data.detail || 'Invalid key');
    adminKey = key;
    sessionStorage.setItem('cx-admin-key', key);
    showStage('auth');
  } catch(e) {
    adminKey = '';
    err.classList.add('show');
  } finally {
    btn.disabled = false; btn.textContent = 'Continue as Admin';
  }
});
document.getElementById('adminKeyInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') document.getElementById('connectBtn').click();
});

// ── STAGE 2: Auth (Login / Signup) ────────────────────────────────────────────
document.getElementById('userLoginBtn').addEventListener('click', async function() {
  var userId = document.getElementById('userIdInput').value.trim();
  var password = document.getElementById('userPasswordInput').value;
  var err = document.getElementById('userLoginErr');
  err.classList.remove('show');
  if (!userId || !password) {
    err.textContent = 'Please enter user ID and password.';
    err.classList.add('show');
    return;
  }
  var btn = document.getElementById('userLoginBtn');
  btn.disabled = true;
  btn.textContent = 'Logging in...';
  try {
    var res = await fetch('/user/auth/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ user_id: userId, password: password })
    });
    var data = await res.json().catch(function() { return {}; });
    if (!res.ok) throw new Error(data.detail || 'Login failed');
    onCustomerAuthSuccess(data);
  } catch(e) {
    err.textContent = e.message;
    err.classList.add('show');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Customer Login';
  }
});
document.getElementById('userPasswordInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') document.getElementById('userLoginBtn').click();
});

document.getElementById('customerSignupBtn').addEventListener('click', async function() {
  var userId = document.getElementById('customerSignupId').value.trim();
  var email = document.getElementById('customerSignupEmail').value.trim();
  var password = document.getElementById('customerSignupPassword').value;
  var confirm = document.getElementById('customerSignupConfirm').value;
  var err = document.getElementById('userLoginErr');
  err.classList.remove('show');
  if (!userId || !email || !password || !confirm) {
    err.textContent = 'All fields are required.';
    err.classList.add('show');
    return;
  }
  if (password !== confirm) {
    err.textContent = 'Passwords do not match.';
    err.classList.add('show');
    return;
  }
  var btn = document.getElementById('customerSignupBtn');
  btn.disabled = true;
  btn.textContent = 'Creating account...';
  try {
    var res = await fetch('/user/auth/signup', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ user_id: userId, email: email, password: password })
    });
    var data = await res.json().catch(function() { return {}; });
    if (!res.ok) throw new Error(data.detail || 'Signup failed');
    onCustomerAuthSuccess(data);
  } catch(e) {
    err.textContent = e.message;
    err.classList.add('show');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Create Customer Account';
  }
});

window.switchAuthTab = function(tab) {
  document.getElementById('loginForm').style.display = tab === 'login' ? 'block' : 'none';
  document.getElementById('signupForm').style.display = tab === 'signup' ? 'block' : 'none';
  document.getElementById('authTabLogin').classList.toggle('active', tab === 'login');
  document.getElementById('authTabSignup').classList.toggle('active', tab === 'signup');
  document.getElementById('authErr').classList.remove('show');
  document.getElementById('authErr').textContent = '';
};

function showAuthErr(msg) {
  var el = document.getElementById('authErr');
  el.textContent = msg;
  el.classList.add('show');
}

function onAuthSuccess(data) {
  adminToken = data.token;
  currentUser = data.user;
  sessionStorage.setItem('cx-admin-jwt', adminToken);
  sessionStorage.setItem('cx-admin-user', JSON.stringify(currentUser));
  updateRibbonUser();
  showStage('app');
  bootApp();
}

document.getElementById('loginBtn').addEventListener('click', async function() {
  var username = document.getElementById('loginUsername').value.trim();
  var password = document.getElementById('loginPassword').value;
  if (!username || !password) { showAuthErr('Please enter username and password.'); return; }
  var btn = document.getElementById('loginBtn');
  btn.disabled = true; btn.textContent = 'Logging in…';
  try {
    var data = await fetch('/admin/auth/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-admin-key': adminKey },
      body: JSON.stringify({ username: username, password: password })
    }).then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error(d.detail || 'Login failed'); return d; }); });
    onAuthSuccess(data);
  } catch(e) {
    showAuthErr(e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Login';
  }
});
document.getElementById('loginPassword').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') document.getElementById('loginBtn').click();
});

document.getElementById('signupBtn').addEventListener('click', async function() {
  var username = document.getElementById('signupUsername').value.trim();
  var email = document.getElementById('signupEmail').value.trim();
  var password = document.getElementById('signupPassword').value;
  var confirm = document.getElementById('signupConfirm').value;
  if (!username || !email || !password) { showAuthErr('All fields are required.'); return; }
  if (password !== confirm) { showAuthErr('Passwords do not match.'); return; }
  if (password.length < 6) { showAuthErr('Password must be at least 6 characters.'); return; }
  var btn = document.getElementById('signupBtn');
  btn.disabled = true; btn.textContent = 'Creating account…';
  try {
    var data = await fetch('/admin/auth/signup', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-admin-key': adminKey },
      body: JSON.stringify({ username: username, email: email, password: password })
    }).then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error(d.detail || 'Signup failed'); return d; }); });
    onAuthSuccess(data);
    toast('Account created — welcome, ' + data.user.username + '!');
  } catch(e) {
    showAuthErr(e.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Create account';
  }
});

// ── Logout ────────────────────────────────────────────────────────────────────
window.doLogout = function() {
  stopRealtime();
  if (state.sseSource) { state.sseSource.close(); state.sseSource = null; }
  adminToken = '';
  currentUser = null;
  sessionStorage.removeItem('cx-admin-jwt');
  sessionStorage.removeItem('cx-admin-user');
  document.getElementById('loginUsername').value = '';
  document.getElementById('loginPassword').value = '';
  document.getElementById('signupUsername').value = '';
  document.getElementById('signupEmail').value = '';
  document.getElementById('signupPassword').value = '';
  document.getElementById('signupConfirm').value = '';
  switchAuthTab('login');
  showStage('auth');
};

window.backToPortalSelection = function() {
  stopRealtime();
  if (state.sseSource) { state.sseSource.close(); state.sseSource = null; }
  adminKey = '';
  adminToken = '';
  currentUser = null;
  sessionStorage.removeItem('cx-admin-key');
  sessionStorage.removeItem('cx-admin-jwt');
  sessionStorage.removeItem('cx-admin-user');
  document.getElementById('adminKeyInput').value = '';
  switchLoginMode('admin');
  showStage('apikey');
};

function updateRibbonUser() {
  if (!currentUser) return;
  var nm = currentUser.username || 'Admin';
  var av = nm.slice(0,2).toUpperCase();
  document.getElementById('ribbonUserName').textContent = nm;
  document.getElementById('ribbonUserRole').textContent = currentUser.email || 'CX Operations';
  document.getElementById('ribbonUserAv').textContent = av;
}

// ── Page switching ────────────────────────────────────────────────────────────
var activePage = 'inbox';
window.switchPage = function(name) {
  document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
  document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.remove('active'); });
  document.getElementById('page-' + name).classList.add('active');
  var navEl = document.getElementById('nav-' + name);
  if (navEl) navEl.classList.add('active');
  activePage = name;
  if (name === 'analytics') loadAnalytics();
  if (name === 'connectors') loadConnectors();
  if (name === 'sim') loadAudit();
  if (name === 'settings') loadSettings();
};

// ── INBOX ─────────────────────────────────────────────────────────────────────
var activeFilter = 'all';
var activeChFilter = 'all';

function formatTime(iso) {
  if (!iso) return '';
  var d = new Date(iso);
  var now = new Date();
  var diff = (now - d) / 1000;
  if (diff < 60) return Math.round(diff) + 's ago';
  if (diff < 3600) return Math.round(diff/60) + 'm ago';
  if (diff < 86400) return Math.round(diff/3600) + 'h ago';
  return d.toLocaleDateString();
}

function inferNameFromEmail(email) {
  if (!email) return null;
  return email.split('@')[0].split(/[._-]/).map(function(w) {
    return w.charAt(0).toUpperCase() + w.slice(1);
  }).join(' ');
}

function customerLabel(conv) {
  var dn = conv.display_name;
  // Unregistered/unmatched sender: display_name is empty, junk, or a raw email.
  // Never fabricate a name from an email — show an honest "Unverified" instead.
  if (!dn || dn === 'None' || dn === 'null' || dn.indexOf('@') !== -1) return 'Unverified';
  return dn;
}

// DISPLAY-ONLY: unify every status label to one pair — Open / Closed.
// The whole app has two status vocabularies (ticket: open/in_progress/resolved;
// conversation: active/resolved), which read as confusing near-synonyms on screen.
// This maps the RAW value to a single user-facing word. It must ONLY wrap display
// text — never feed a class/branch/comparison; all logic keeps using the raw value.
// One word, stored and shown: a finished case is 'closed'. This used to translate the
// stored 'resolved' into "Closed" for display, which covered the six places the UI
// renders a status and nothing else - the case-summary LLM was handed the raw value and
// wrote "resolved" onto the agent's screen. The value itself is now the word.
function statusLabel(s) {
  var v = (s || '').toLowerCase();
  if (v === 'closed') return 'Closed';
  // "Logged", not "Open": the whole point of the status is that nothing is pending on a
  // person. Labelling it Open would tell an agent there is work here and would put the
  // word "Open" in front of a customer for a question already answered.
  if (v === 'logged') return 'Logged';
  return 'Open';
}

function urgencyToStatus(conv) {
  if (conv.status === 'closed') return 'closed';
  var convTkts = allTickets().filter(function(t) { return t.conversation_id === conv.conversation_id; });
  // Nothing serviceable left => nothing is waiting on a person, so the banner reads as
  // settled. Logging threads are ignored on BOTH sides of this test: they never keep a
  // conversation looking active, and a conversation made only of them is not "closed"
  // work either - it just has no open cases, which is what the banner says (Fix 121).
  var hasServiceable = convTkts.some(isServiceable);
  if (convTkts.length > 0 && !hasServiceable) return 'closed';
  return conv.status || 'open';
}

// Fetch all pending held drafts and index them by conversation_id (one card per conv;
// if multiple drafts exist for a conv we surface the most recent, which sorts first).
async function loadPendingDrafts() {
  try {
    var drafts = await api('/admin/reply-drafts?status=pending');
    var byConv = {};
    (drafts || []).forEach(function(d) {
      if (!byConv[d.conversation_id]) byConv[d.conversation_id] = d;
    });
    state.pendingDrafts = byConv;
  } catch(e) {
    state.pendingDrafts = state.pendingDrafts || {};
  }
}

window.loadConversations = async function() {
  try {
    var results = await Promise.all([api('/admin/conversations'), api('/admin/tickets'), loadPendingDrafts()]);
    var convs = results[0], tks = results[1];
    _allTickets.logged = tks.filter(function(t) { return t.status === 'logged'; });
    _allTickets.open   = tks.filter(isServiceable);
    _allTickets.closed = tks.filter(function(t) { return t.status === 'closed'; });
    var prevIds = state.convs.map(function(c){ return c.conversation_id; }).sort().join(',');
    var newIds = convs.map(function(c){ return c.conversation_id; }).sort().join(',');
    var hasNew = newIds !== prevIds;
    state.convs = convs;
    renderQueue();
    // Needs Review badge: number of conversations with a pending held draft
    var nrCount = Object.keys(state.pendingDrafts).length;
    var nrBadge = document.getElementById('reviewBadge');
    if (nrBadge) {
      if (nrCount > 0) { nrBadge.style.display='flex'; nrBadge.textContent = nrCount > 9 ? '9+' : nrCount; }
      else { nrBadge.style.display = 'none'; }
    }
    if (hasNew && state.selectedConvId) refreshSelectedConv();
  } catch(e) {
    document.getElementById('qlist').innerHTML = '<div style="padding:20px;text-align:center;color:var(--red-t);font-size:12px">' + escH(e.message) + '</div>';
  }
};

async function refreshSelectedConv() {
  if (!state.selectedConvId) return;
  if (state.convDetail && state.convDetail.status === 'closed') return;
  try {
    var detail = await api('/admin/conversations/' + encodeURIComponent(state.selectedConvId));
    var prevLen = (state.convDetail && state.convDetail.turns) ? state.convDetail.turns.length : 0;
    if (detail.turns && detail.turns.length !== prevLen) {
      state.convDetail = detail;
      renderCentre(detail);
      renderRight(detail, allTickets());
      loadCaseSummary(detail.conversation_id, false);
    }
  } catch(e) {}
}

function renderQueue() {
  var search = (document.getElementById('srchInput').value || '').toLowerCase();
  var list = document.getElementById('qlist');
  list.innerHTML = '';
  var filtered = state.convs.filter(function(c) {
    if (search && !customerLabel(c).toLowerCase().includes(search) && !(c.last_message||'').toLowerCase().includes(search)) return false;
    if (activeFilter === 'review' && !state.pendingDrafts[c.conversation_id]) return false;
    return true;
  });
  if (!filtered.length) {
    list.innerHTML = '<div style="padding:20px;text-align:center;color:var(--t3);font-size:12px">No conversations found</div>';
    return;
  }
  filtered.forEach(function(c) {
    var isOn = c.conversation_id === state.selectedConvId;
    var sts = urgencyToStatus(c);
    var ch = chMeta(c.last_channel);
    var div = document.createElement('div');
    div.className = 'qi' + (isOn ? ' on' : '') + (sts === 'closed' ? ' done' : '');
    div.innerHTML = '<div class="cs ' + ch.stripe + '"></div>'
      + '<div class="qb">'
      + '<div class="qr1"><span class="qn">' + escH(customerLabel(c)) + '</span><span class="qt">' + escH(formatTime(c.updated_at)) + '</span></div>'
      + '<div class="qp">' + escH((c.last_message || c.summary || 'No messages yet').slice(0,60)) + '</div>'
      + '<div class="qf">'
      + (c.last_channel ? '<span class="cp ' + ch.pill + '">' + ch.svg + ch.label + '</span>' : '<span class="cp pdef">Unknown</span>')
      + (state.pendingDrafts[c.conversation_id] ? '<span class="qi-review-dot" title="Held reply needs review"></span>' : '')
      + '</div></div>';
    div.addEventListener('click', function() { selectConv(c.conversation_id); });
    list.appendChild(div);
  });
}

async function selectConv(convId) {
  state.selectedConvId = convId;
  renderQueue();
  var msgsEl = document.getElementById('msgs');
  msgsEl.className = 'msgs';
  msgsEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--t3);font-size:12px">Loading…</div>';
  document.getElementById('compwrap').style.display = 'none';
  document.getElementById('resbanner').style.display = 'none';
  try {
    var cachedTickets = allTickets().length
      ? Promise.resolve(allTickets())
      : api('/admin/tickets');
    var results = await Promise.all([
      api('/admin/conversations/' + encodeURIComponent(convId)),
      cachedTickets,
      loadPendingDrafts()
    ]);
    var detail = results[0], tickets = results[1];
    state.convDetail = detail;
    renderCentre(detail);
    renderRight(detail, tickets);
    loadCaseSummary(detail.conversation_id, false);
  } catch(e) {
    msgsEl.className = 'msgs';
    msgsEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--red-t);font-size:12px">' + escH(e.message) + '</div>';
  }
}

var EMOTION_MAP = { critical:'Frustrated', high:'Frustrated', medium:'Concerned', low:'Positive' };
var EMOTION_CLS  = { critical:'fe-frustrated', high:'fe-frustrated', medium:'fe-concerned', low:'fe-positive' };

function renderCentre(conv) {
  var turns = conv.turns || [];
  var conv_meta = state.convs.find(function(c) { return c.conversation_id === conv.conversation_id; }) || conv;
  var nm = customerLabel(conv_meta);
  document.getElementById('convName').textContent = nm;
  // Clear the meta line + graph button on every switch: both are filled asynchronously
  // by renderRight, so without this the previous customer's details linger until the
  // graph call returns (or forever, if this customer resolves to no graph node).
  var _metaEl = document.getElementById('convMeta');
  if (_metaEl) _metaEl.innerHTML = '';

  // The banner reads "No open tickets", not "Conversation closed", because that is what
  // urgencyToStatus actually reports: it returns 'closed' either when the conversation is
  // closed OR when every ticket on it is closed while the conversation itself is still
  // active (see line ~509). The second case is the common one - a customer whose cases are
  // all settled but who is still in the queue - and calling that "conversation closed" told
  // the agent something the record did not say. Nothing here notifies the customer, so the
  // banner no longer claims that either.
  var isDone = urgencyToStatus(conv_meta) === 'closed';
  document.getElementById('resbanner').style.display = isDone ? 'flex' : 'none';
  // The compose box stays on a closed conversation. Closing is not the end of contact:
  // a customer writes back after a case is closed, and an agent who has just closed one
  // may still owe them a word - closing notifies nobody, which is why the banner above no
  // longer claims it does. Removing the only reply surface left the agent reading a
  // conversation they could not answer.
  document.getElementById('compwrap').style.display = 'block';

  // Channel filter bar
  // Counts here must match what the pane below actually renders, not raw DB turns: turns
  // sharing a ticket_id are merged into ONE visible exchange further down (a customer
  // question + the "we'll get back to you" holding ack + the eventual real reply all
  // collapse into one row) — counting raw turns.length previously overpromised ("shows 3"
  // while only 1 exchange was ever visible). Untracked turns (no ticket_id) each still
  // count individually since they're never merged.
  // Counts here are TURNS, and every turn belongs to exactly one channel, so the parts
  // sum to the total: 20 = 11 + 6 + 3. That is what a filter bar is for — pick a channel,
  // see how much of the conversation is on it.
  //
  // Requests deliberately are NOT counted here. A ticket that spans WhatsApp and email is
  // ONE request under "All" but appears under BOTH channel chips, so a request count makes
  // the chips stop summing (5 vs 2+3+2) and reads as an arithmetic error on screen.
  var seenChs = {};
  turns.forEach(function(t) { if (t.channel) seenChs[t.channel] = (seenChs[t.channel] || 0) + 1; });
  var bar = document.getElementById('chbar');
  bar.innerHTML = '<span class="chbar-label">Channel:</span>';
  var allBtn = document.createElement('button');
  allBtn.className = 'chfilt' + (activeChFilter === 'all' ? ' on' : '');
  allBtn.innerHTML = 'All channels <span class="ch-count">' + turns.length + '</span>';
  allBtn.addEventListener('click', function() { activeChFilter = 'all'; renderCentre(conv); });
  bar.appendChild(allBtn);
  Object.keys(seenChs).forEach(function(ch) {
    var btn = document.createElement('button');
    btn.className = 'chfilt' + (activeChFilter === ch ? ' on' : '');
    var cm = chMeta(ch);
    btn.innerHTML = cm.svg + cm.label + ' <span class="ch-count">' + seenChs[ch] + '</span>';
    if (activeChFilter === ch) btn.style.cssText = 'background:' + cm.clr + ';border-color:' + cm.clr + ';color:#fff';
    btn.addEventListener('click', function() { activeChFilter = ch; renderCentre(conv); });
    bar.appendChild(btn);
  });

  // View-mode toggle (Detailed spine ↔ Lineage overview). Separate tab strip so
  // it reads as a view switch, not another channel filter. Default = 'detailed'.
  var convViewKey = conv.conversation_id;
  var viewMode = state.convView[convViewKey] || 'detailed';
  var viewbar = document.getElementById('viewbar');
  if (viewbar) {
    viewbar.innerHTML = '';
    [['detailed', 'Detailed', 'M4 6h16M4 12h16M4 18h10'],
     ['lineage', 'Lineage', 'M4 5h4v4H4zM10 5h10v2H10zM4 11h4v4H4zM10 12h10v2H10zM4 17h4v4H4zM10 18h8v2h-8z']
    ].forEach(function(v) {
      var tab = document.createElement('button');
      tab.className = 'viewtab' + (viewMode === v[0] ? ' on' : '');
      tab.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13"><path d="' + v[2] + '"/></svg>' + v[1];
      tab.addEventListener('click', function() {
        state.convView[convViewKey] = v[0];
        renderCentre(conv);
      });
      viewbar.appendChild(tab);
    });
  }

  var filtered = turns.filter(function(t) { return activeChFilter === 'all' || t.channel === activeChFilter; });
  var box = document.getElementById('msgs');
  box.innerHTML = '';

  if (!filtered.length) {
    box.className = 'msgs';
    box.innerHTML = '<div class="empty-conv"><svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/></svg>No messages on this channel yet</div>';
    return;
  }

  box.className = 'flow-wrap';

  // Group turns into inbound+outbound pairs (flow steps)
  var steps = [];
  var pendingIn = null;
  filtered.forEach(function(t) {
    if (t.direction === 'inbound') {
      if (pendingIn) steps.push({ inbound: pendingIn, outbound: null });
      pendingIn = t;
    } else {
      steps.push({ inbound: pendingIn, outbound: t });
      pendingIn = null;
    }
  });
  if (pendingIn) steps.push({ inbound: pendingIn, outbound: null });

  steps.reverse();

  // Build a ticket-status lookup from the cached ticket lists.
  // Used below to drive per-turn status display.
  var convIsResolved = conv.status === 'closed';
  var tktStatusMap = {};
  allTickets().forEach(function(t) {
    tktStatusMap[t.ticket_id] = t.status;
  });

  // ── Theme grouping (ticket-first, then theme) ────────────────────────────
  // `steps` is newest-first (idx 0 = latest). Each step is an inbound+outbound
  // pair; in this data the classified `intent` usually lives on the OUTBOUND
  // turn, and a single request often spans multiple turns/steps that share ONE
  // `ticket_id` (e.g. a "Support Agent will help…" holding turn + the full
  // reply, sometimes with the intent flipping between them).
  //
  // Rules:
  //  1. A ticket is one unit — turns sharing a ticket_id are NEVER split by a
  //     divider, and a whole ticket run takes ONE theme (the first themed
  //     intent seen in that ticket), so an intent flip inside a ticket (e.g.
  //     KYC mis-labelled as fraud) can't change the theme mid-ticket.
  //  2. Empty-intent steps otherwise inherit the surrounding theme
  //     (carry-forward), and a leading empty step looks ahead to the first
  //     themed step.
  //  3. A new group starts only at a REAL boundary: the theme changed AND the
  //     step does not share a ticket with the previous step.
  // `ticket_closure` is a system event (auto-close on "thanks"), not a
  // customer topic — treat it as unthemed (via topicOrEmpty) so it never forms
  // its own group and instead inherits the intent of the ticket/turns around it.
  var rawIntent = steps.map(function(step) {
    // A bank-initiated offer carries no query intent; theme it by its product so
    // it groups with the matching topic (or forms its own themed group).
    if (isOfferStep(step)) return offerIntentOf(step);
    return topicOrEmpty((step.inbound && step.inbound.intent) || (step.outbound && step.outbound.intent) || '');
  });
  var stepTicket = steps.map(function(step) {
    return (step.inbound && step.inbound.ticket_id) || (step.outbound && step.outbound.ticket_id) || null;
  });
  // Per-ticket theme + intent: first themed intent seen for each ticket_id.
  // ticketIntent is used to label the sub-theme marker shown between two
  // different tickets inside the same theme group.
  var ticketTheme = {};
  var ticketIntent = {};
  // A ticket's subject comes from the TICKET, not from the first turn that happens to
  // carry its id. The ticket is created DURING the turn that opens it, so the opening
  // message is not tagged with the id - the first tagged turn is whatever came next.
  // On a real dispute that was "any update on my dispute?", so a transaction_dispute
  // case was headed TICKET STATUS: the follow-up question, not the matter.
  var _tk = allTickets();
  for (var ti = 0; ti < steps.length; ti++) {
    var tk = stepTicket[ti];
    if (!tk || ticketTheme[tk]) continue;
    var rec = null;
    for (var ri = 0; ri < _tk.length; ri++) {
      if (_tk[ri].ticket_id === tk) { rec = _tk[ri]; break; }
    }
    var subject = (rec && rec.intent) || rawIntent[ti];
    if (subject) {
      ticketTheme[tk] = themeOf(subject);
      ticketIntent[tk] = subject;
    }
  }
  var stepThemes = new Array(steps.length);
  var carried = null;
  for (var si = 0; si < steps.length; si++) {
    var tkt = stepTicket[si];
    if (tkt && ticketTheme[tkt]) {
      stepThemes[si] = ticketTheme[tkt];        // whole ticket = one theme
    } else if (rawIntent[si]) {
      stepThemes[si] = themeOf(rawIntent[si]);
    } else if (carried) {
      stepThemes[si] = carried;                 // inherit from previous themed step
    } else {
      // Leading empty step(s): look ahead to the first themed step.
      var ahead = null;
      for (var sj = si + 1; sj < steps.length; sj++) {
        if (stepTicket[sj] && ticketTheme[stepTicket[sj]]) { ahead = ticketTheme[stepTicket[sj]]; break; }
        if (rawIntent[sj]) { ahead = themeOf(rawIntent[sj]); break; }
      }
      stepThemes[si] = ahead || themeOf('');    // all-empty conversation → General
    }
    carried = stepThemes[si];
  }
  // An admin-approved offer turn (Opportunities flow) is bank-initiated and
  // unticketed. It is themed by its product (see offerIntentOf / rawIntent), so
  // it flows through the SAME theme-grouping as any other turn: it joins the
  // group of the matching topic when the customer discussed it, otherwise it
  // forms its own themed group — never glued under an unrelated preceding query.
  // (Supersedes the 2026-07-23 "offer is transparent, glue to prev" rule, which
  // made unrelated offers look like a continuation of whatever came before.)

  var groups = [];
  var prevTicket = null;
  // Which group each ticket already lives in. A customer interleaves topics —
  // opens a dispute, asks an unrelated loan question, then returns to the dispute —
  // and `prevTicket` alone only keeps a ticket together while its steps are
  // CONSECUTIVE. The intervening loan step reset it, so the returning dispute step
  // opened a THIRD group and the same ticket rendered as two separate rows in both
  // Detailed and Lineage, hiding the very continuity the backend had established.
  // Remembering the group per ticket sends a returning ticket back to its own group.
  var ticketGroup = {};
  steps.forEach(function(step, idx) {
    var th = stepThemes[idx];
    var tkt = stepTicket[idx];
    var prev = groups[groups.length - 1];
    var offer = isOfferStep(step);
    var item = { step: step, idx: idx, ticket: tkt, offer: offer };
    // A ticket seen before rejoins its original group, however many other topics
    // came in between.
    if (tkt && ticketGroup[tkt]) {
      ticketGroup[tkt].items.push(item);
      prevTicket = tkt;
      return;
    }
    // Same ticket as the previous step → always stay in the same group. An offer
    // is unticketed (tkt is null), so it can only join a group by matching theme.
    var sameTicket = tkt && prevTicket && tkt === prevTicket;
    var target;
    if (!prev || (prev.theme !== th.theme && !sameTicket)) {
      target = { theme: th.theme, themeLabel: th.themeLabel, color: th.color, items: [item] };
      groups.push(target);
    } else {
      prev.items.push(item);
      target = prev;
    }
    if (tkt && !ticketGroup[tkt]) ticketGroup[tkt] = target;
    prevTicket = tkt;
  });

  // Seed default fold state ONCE per conversation: latest group (index 0)
  // expanded, all older groups collapsed. Done only if not seeded yet, so a
  // poll re-render never re-collapses a group the agent manually opened.
  var convKey = conv.conversation_id;
  if (!state.themeSeeded[convKey]) {
    groups.forEach(function(g, gi) {
      if (gi > 0) state.collapsedThemes[convKey + ':' + gi] = true;
    });
    state.themeSeeded[convKey] = true;
  }

  // The AI holding message injected when a reply is held for human review
  // (mirrors HOLDING_MESSAGE in services/orchestration_service/graph.py). When a
  // request's final outbound is only this stub, we demote it to an "auto-ack"
  // pill rather than treating it as the substantive answer.
  var HOLDING_PREFIX = 'support agent will help you with this shortly';
  function isHolding(text) {
    return (text || '').trim().toLowerCase().indexOf(HOLDING_PREFIX) === 0;
  }

  // ── Merge a group's items into request UNITS ────────────────────────────
  // Consecutive items sharing a ticket_id collapse into one request node.
  // Unticketed items each become their own unit. Each unit summarises: the
  // customer's opening message, the FINAL substantive reply, whether a holding
  // "auto-ack" was sent, plus channel/emotion/status/time for the header.
  function buildUnits(items) {
    var units = [];
    var byKey = {};
    items.forEach(function(it) {
      // A unit's grouping key: ticket_id for a query/ticket, or — for a
      // bank-initiated offer (unticketed) — its draft_id. The same offer is
      // delivered to every push channel (WhatsApp + email) as separate turns
      // sharing one draft_id, so this key makes those deliveries collapse into
      // ONE unit (each channel = one exchange/dot), exactly the omnichannel
      // grouping a multi-channel ticket already gets.
      var key = it.offer ? offerDraftId(it.step) : it.ticket;
      // Matching on the PREVIOUS unit only kept a ticket together while its steps
      // were consecutive; a step from another ticket in between split one ticket
      // into two units. Keyed lookup merges every step of a ticket into one unit
      // no matter what interleaved — the unit still renders its exchanges in
      // chronological order below.
      if (key && byKey[key]) {
        byKey[key].items.push(it);
      } else {
        var unit = { key: key, ticket: it.offer ? null : it.ticket, items: [it] };
        units.push(unit);
        if (key) byKey[key] = unit;
      }
    });
    return units.map(function(u) {
      // `items` is newest-first; walk a CHRONOLOGICAL (oldest-first) copy so
      // exchanges read in the order they happened. A ticket can span several
      // exchanges (e.g. "Please transfer…" → holding → reply → "close it" →
      // "resolved"); each customer message + the reply(ies) that follow it become
      // one EXCHANGE sub-box inside the single ticket node.
      var chrono = u.items.slice().reverse();
      var exchanges = [];
      var cur = null;
      var lastTurn = null;
      // Each exchange carries its own `ref` (its latest turn) for a per-box time.
      function startExchange(inbound) { cur = { inbound: inbound, holdingText: null, reply: null, ref: inbound || null }; exchanges.push(cur); }
      chrono.forEach(function(it) {
        if (it.step.inbound) {
          startExchange(it.step.inbound);
          lastTurn = it.step.inbound;
        }
        if (it.step.outbound) {
          // A bank-initiated offer is its own exchange — it must not overwrite
          // the previous exchange's reply, and nothing pairs with it.
          if (it.offer) startExchange(null);
          else if (!cur) startExchange(null);  // reply with no preceding inbound in this unit
          if (isHolding(it.step.outbound.text)) cur.holdingText = it.step.outbound.text;
          else cur.reply = it.step.outbound;   // latest substantive reply for this exchange
          cur.ref = it.step.outbound;          // latest turn in this exchange
          lastTurn = it.step.outbound;
        }
      });
      var firstInbound = exchanges.length ? exchanges[0].inbound : null;
      return {
        ticket: u.ticket,
        idx: u.items[0].idx,            // latest step's idx (items are newest-first)
        exchanges: exchanges,           // ordered [{inbound, holdingText, reply, ref}]
        firstInbound: firstInbound,     // customer's original message (summary/collapsed)
        ref: lastTurn || firstInbound   // latest turn → node timestamp/status
      };
    });
  }

  // True when an exchange's outbound turn is an admin-approved cross-/up-sell
  // offer (sent via the Opportunities flow) — bank-initiated, no customer query.
  function isOfferTurn(t) {
    return !!(t && t.metadata && t.metadata.source === 'opportunity_offer');
  }

  // Renders one request unit for the DETAILED view: every customer→AI exchange
  // in the request as its own 3-column row (Customer Query · ticket/channel/
  // status/time · AI Agent Reply), stacked oldest→newest. All exchanges share
  // one ticket, so a multi-message ticket reads top-to-bottom in order.
  function renderUnit(u, themeColor) {
    function fmtTime(turn) {
      var dd = turn && turn.created_at ? new Date(turn.created_at) : null;
      return dd ? dd.toLocaleDateString([], {month:'short', day:'numeric', year:'numeric'})
                + ' · ' + dd.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) : '';
    }

    var tktStatus = u.ticket ? tktStatusMap[u.ticket] : null;
    var isLatestUnit = u.idx === 0;
    var nodeStatus;
    if (tktStatus === 'closed') nodeStatus = 'closed';
    // A logged thread is shown, not hidden: this view is the customer's story, and a
    // grouping id is precisely the thing that makes two messages one matter. It renders
    // as its own state so it never reads as work waiting on a person.
    else if (tktStatus === 'logged') nodeStatus = 'logged';
    else if (tktStatus === 'open' || tktStatus === 'in_progress') nodeStatus = 'active';
    else if (!isLatestUnit) nodeStatus = 'closed';
    else nodeStatus = convIsResolved ? 'closed' : (conv.status || 'active');
    var statusCls = nodeStatus === 'logged' ? 'fns-logged'
      : (nodeStatus === 'active' || nodeStatus === 'open' || nodeStatus === 'in_progress') ? 'fns-active' : 'fns-done';

    // Customer message text (strips a leading duplicated subject line).
    function custText(inbound) {
      if (!inbound) return '';
      var s = inbound.subject || '', b = inbound.text || '';
      if (s && b.startsWith(s)) b = b.slice(s.length).replace(/^\s+/, '');
      return b;
    }

    var exchanges = u.exchanges || [];
    // Left border = THEME colour (matches the theme header + the Lineage view),
    // not the channel colour. Mirrors renderLineageRow's fallback.
    var themeClr = (themeColor && themeColor.t) || 'var(--t3)';

    var el = document.createElement('div');
    el.className = 'det-unit';

    var rowsHtml = '';
    exchanges.forEach(function(ex) {
      var chn = chMeta((ex.inbound && ex.inbound.channel) || (ex.ref && ex.ref.channel) || '');
      var query = custText(ex.inbound);

      // Admin-approved offer (Opportunities flow): bank-initiated, no customer
      // query to pair with — render as an OFFER row, not a blank-query reply.
      if (!ex.inbound && ex.reply && isOfferTurn(ex.reply)) {
        var offTime = fmtTime(ex.ref);
        rowsHtml +=
            '<div class="det-row det-row--offer" style="--det-clr:' + themeClr + '">'
          +   '<div class="det-head">'
          +     '<span class="nba-badge nba-badge-upsell">Offer</span>'
          +     '<span class="cp ' + chn.pill + '" style="font-size:10px">' + chn.svg + chn.label + '</span>'
          +     (offTime ? '<span class="lin-time">' + escH(offTime) + '</span>' : '')
          +   '</div>'
          +   '<div class="det-q">'
          +     '<span class="det-lbl">Bank-initiated</span>'
          +     '<div class="det-q-text det-q-text--offer">Offer approved by admin &amp; sent to the customer</div>'
          +   '</div>'
          +   '<div class="det-r">'
          +     '<span class="det-lbl det-r-lbl">Offer Message</span>'
          +     '<div class="det-r-text">' + escH(ex.reply.text || '') + '</div>'
          +   '</div>'
          + '</div>';
        return;
      }

      // AI Agent Reply box: optional auto-sent (holding) line, then the reply.
      var replyInner;
      if (ex.reply) {
        var auto = ex.holdingText
          ? '<div class="det-auto">↳ Auto-sent: “' + escH(ex.holdingText.trim()) + '”</div>' : '';
        replyInner = auto + '<div class="det-r-text">' + escH(ex.reply.text || '') + '</div>';
      } else if (ex.holdingText) {
        replyInner = '<div class="det-auto">↳ Auto-sent: “' + escH(ex.holdingText.trim()) + '”</div>'
          + '<div class="det-r-text det-r-pending"><em>Awaiting agent reply…</em></div>';
      } else {
        replyInner = '<div class="det-r-text">—</div>';
      }

      var timeStr = fmtTime(ex.ref);
      // Per-exchange sentiment from that inbound message's urgency.
      var exUrg = ((ex.inbound && ex.inbound.urgency) || '').toLowerCase();
      var exEmotion = EMOTION_MAP[exUrg] || 'Neutral';
      var exEmotionCls = EMOTION_CLS[exUrg] || 'fe-neutral';
      // Blank on a turn the classifier never labelled (an outbound-only exchange); the
      // pill is then not drawn at all, rather than showing a made-up 'General'.
      var exIntentRaw = (ex.inbound && ex.inbound.intent) || (ex.reply && ex.reply.intent) || '';
      var exIntent = exIntentRaw ? intentLabel(exIntentRaw) : '';
      rowsHtml +=
          '<div class="det-row" style="--det-clr:' + themeClr + '">'
          // Metadata reads as a header across the top rather than a middle column: as a
          // column these five pills stacked into a tall empty gutter while the query and
          // reply were squeezed either side of it.
          // The header reads left-to-right in the same direction as the row beneath it.
          // LEFT describes the customer's message, which sits below-left: how it arrived,
          // how they sounded, what they wanted. RIGHT describes what the system did, below-
          // right: the case it opened or attached to, where that stands, when. Intent is the
          // pivot - the last thing read out of the message and the first thing that decides
          // the response - and it was missing entirely, so a row about a dispute and a row
          // about its follow-up looked identical.
        +   '<div class="det-head">'
        +     '<span class="cp ' + chn.pill + '" style="font-size:10px">' + chn.svg + chn.label + '</span>'
        +     '<span class="flow-emotion ' + exEmotionCls + '">' + escH(exEmotion) + '</span>'
        +     (exIntent ? '<span class="det-intent">' + escH(exIntent) + '</span>' : '')
        +     (u.ticket ? '<span class="lin-tkt">' + escH(u.ticket) + '</span>' : '<span class="lin-tkt lin-tkt--none">no ticket</span>')
        +     '<span class="flow-node-status ' + statusCls + '">' + escH(statusLabel(nodeStatus)) + '</span>'
        +     (timeStr ? '<span class="lin-time">' + escH(timeStr) + '</span>' : '')
        +   '</div>'
        +   '<div class="det-q">'
        +     '<span class="det-lbl">Customer Query</span>'
        +     '<div class="det-q-text">' + escH(query || '—') + '</div>'
        +   '</div>'
        +   '<div class="det-r">'
        +     '<span class="det-lbl det-r-lbl">AI Agent Reply</span>'
        +     replyInner
        +     // Only on a real answer. A holding message ("Support Agent will help you
              // shortly") explains nothing — the actual reply is still a pending draft, so
              // any retrieval shown against it would be unrelated to what the customer read.
              (ex.reply && ex.reply.turn_id && !isHolding(ex.reply.text)
                ? '<button class="det-why" type="button" data-turn="' + escH(ex.reply.turn_id) + '"'
                  + ' title="Show where this answer\'s information came from">Why this answer?</button>'
                : '')
        +   '</div>'
        + '</div>';
    });

    el.innerHTML = rowsHtml;
    Array.prototype.forEach.call(el.querySelectorAll('.det-why'), function(b) {
      b.onclick = function() { openWhyModal(b.getAttribute('data-turn')); };
    });

    if (state.highlightTicketId && u.ticket === state.highlightTicketId) {
      el.classList.add('flow-step--highlight');
    }
    return el;
  }

  // Renders one request unit as a LINEAGE TIMELINE-STRIP row. This is the
  // history-overview view: a scannable index of past requests. The row is a
  // small left section (ticket-id + status) beside a mini timeline — one dot per
  // customer→AI exchange, channel-coloured, oldest→newest, with channel + time
  // beneath each dot — then a one-line snippet of the opening message. The row's
  // left border follows the THEME colour (dots follow channel). Click drills into
  // the Detailed view for this request. Same `unit` shape as renderUnit, so the
  // two views never diverge on grouping.
  function renderLineageRow(u, themeColor) {
    var tktStatus = u.ticket ? tktStatusMap[u.ticket] : null;
    var isLatestUnit = u.idx === 0;
    var nodeStatus;
    if (tktStatus === 'closed') nodeStatus = 'closed';
    // A logged thread is shown, not hidden: this view is the customer's story, and a
    // grouping id is precisely the thing that makes two messages one matter. It renders
    // as its own state so it never reads as work waiting on a person.
    else if (tktStatus === 'logged') nodeStatus = 'logged';
    else if (tktStatus === 'open' || tktStatus === 'in_progress') nodeStatus = 'active';
    else if (!isLatestUnit) nodeStatus = 'closed';
    else nodeStatus = convIsResolved ? 'closed' : (conv.status || 'active');
    var statusCls = nodeStatus === 'logged' ? 'fns-logged'
      : (nodeStatus === 'active' || nodeStatus === 'open' || nodeStatus === 'in_progress') ? 'fns-active' : 'fns-done';

    function fmtTime(turn) {
      var dd = turn && turn.created_at ? new Date(turn.created_at) : null;
      return dd ? dd.toLocaleDateString([], {month:'short', day:'numeric'})
                + ' · ' + dd.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) : '';
    }

    // Bank-initiated offer unit (no customer inbound; outbound(s) from the
    // Opportunities flow) — labelled as an offer, not "Opened with —".
    var offerReply = null;
    if (!u.firstInbound) {
      (u.exchanges || []).forEach(function(ex) {
        if (!offerReply && ex.reply && isOfferTurn(ex.reply)) offerReply = ex.reply;
      });
    }

    // Opening customer message snippet (strips a leading duplicated subject).
    var query = '';
    if (u.firstInbound) {
      var s = u.firstInbound.subject || '', b = u.firstInbound.text || '';
      if (s && b.startsWith(s)) b = b.slice(s.length).replace(/^\s+/, '');
      query = b;
    }

    // One timeline entry per exchange (channel-coloured dot + channel + time).
    // An offer exchange (bank-initiated, inside the request that triggered it)
    // is labelled "Offer · <channel>" so the sales touchpoint is visible.
    var dotsHtml = (u.exchanges || []).map(function(ex) {
      var chn = chMeta((ex.inbound && ex.inbound.channel) || (ex.ref && ex.ref.channel) || '');
      var t = fmtTime(ex.ref || ex.inbound);
      var isOfferEx = !ex.inbound && isOfferTurn(ex.reply);
      return '<div class="tl-ex' + (isOfferEx ? ' tl-ex--offer' : '') + '" style="--ex-clr:' + chn.clr + '">'
        +   '<span class="tl-dot"></span>'
        +   '<span class="tl-ch">' + (isOfferEx ? 'Offer · ' : '') + escH(chn.label) + '</span>'
        +   (t ? '<span class="tl-time">' + escH(t) + '</span>' : '')
        + '</div>';
    }).join('');

    var tc = themeColor || { t:'var(--t3)' };

    var el = document.createElement('div');
    el.className = 'lin-row';
    el.setAttribute('role', 'button');
    el.setAttribute('tabindex', '0');
    el.style.setProperty('--lin-clr', tc.t);   // left border = theme colour
    var metaHtml = offerReply
      ? '<span class="nba-badge nba-badge-upsell">Offer</span>'
        + '<span class="flow-node-status fns-done">Sent</span>'
      : (u.ticket ? '<span class="lin-tkt">' + escH(u.ticket) + '</span>' : '<span class="lin-tkt lin-tkt--none">no ticket</span>')
        + '<span class="flow-node-status ' + statusCls + '">' + escH(statusLabel(nodeStatus)) + '</span>';
    var snipHtml = offerReply
      ? '<div class="lin-snip"><span class="lin-snip-lbl">Offer sent</span>' + escH(offerReply.text || '') + '</div>'
      : '<div class="lin-snip"><span class="lin-snip-lbl">Opened with</span>' + escH(query || '—') + '</div>';
    el.innerHTML =
        '<div class="lin-meta">' + metaHtml + '</div>'
      + '<div class="lin-main">'
      +   '<div class="tl"><div class="tl-line"></div><div class="tl-dots">' + dotsHtml + '</div></div>'
      +   snipHtml
      + '</div>';

    var drill = function() {
      // Focus the Detailed view on THIS request, then switch to it.
      state.detailFocus[convViewKey] = u.ticket || ('u' + u.idx);
      state.convView[convViewKey] = 'detailed';
      renderCentre(conv);
    };
    el.addEventListener('click', drill);
    el.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); drill(); }
    });
    return el;
  }

  // Stable per-request key (matches the lineage-row key convention).
  function unitKey(u) { return u.ticket || ('u' + u.idx); }

  // ── Detailed view = ONE request at a time ───────────────────────────────
  // Resolve which request the Detailed view shows: the stored focus if it still
  // exists in the current data, else the latest request (group 0, unit 0). The
  // latest sits first because steps are newest-first. In Lineage mode focusKey
  // is unused (all requests are listed).
  var focusKey = null;
  if (viewMode !== 'lineage') {
    var allKeys = [];
    var latestKey = null;
    groups.forEach(function(g) {
      buildUnits(g.items).forEach(function(u) {
        var k = unitKey(u);
        allKeys.push(k);
        if (latestKey === null) latestKey = k;   // first unit overall = latest request
      });
    });
    var stored = state.detailFocus[convViewKey];
    focusKey = (stored && allKeys.indexOf(stored) !== -1) ? stored : latestKey;
  }

  // Inbound turns visible in the CURRENT Detailed view (filled in below). A held
  // draft belongs to one specific question, so its card is only shown when that
  // question is the one being displayed.
  var shownInboundTurnIds = {};

  // ── Render theme groups with foldable headers ───────────────────────────
  groups.forEach(function(g, gi) {
    var groupKey = convKey + ':' + gi;
    // If we're navigating to a specific ticket, force-open the group that holds
    // it so the highlighted turn isn't hidden inside a collapsed group.
    if (state.highlightTicketId) {
      var hasHighlight = g.items.some(function(it) {
        var tid = (it.step.inbound && it.step.inbound.ticket_id) || (it.step.outbound && it.step.outbound.ticket_id) || null;
        return tid === state.highlightTicketId;
      });
      if (hasHighlight) delete state.collapsedThemes[groupKey];
    }
    var units = buildUnits(g.items);        // merged request units for this group

    // In Detailed mode, render ONLY the single focused request. Skip any group
    // that doesn't contain it; within the matching group, keep only that unit.
    var detailSingle = viewMode !== 'lineage';
    if (detailSingle) {
      units = units.filter(function(u) { return unitKey(u) === focusKey; });
      if (!units.length) return;   // focused request isn't in this group
      // Remember which inbound turns this focused request actually shows, so the
      // held-draft card below can tell whether ITS question is the one on screen.
      units.forEach(function(u) {
        (u.exchanges || []).forEach(function(ex) {
          if (ex.inbound && ex.inbound.turn_id) shownInboundTurnIds[ex.inbound.turn_id] = true;
        });
      });
    }

    var collapsed = !detailSingle && !!state.collapsedThemes[groupKey];

    var groupEl = document.createElement('div');
    groupEl.className = 'flow-theme-group' + (collapsed ? ' collapsed' : '');

    // Theme header (divider). In Lineage it's foldable (toggles the group); in
    // single-request Detailed it's a static label (nothing to fold to).
    var header = document.createElement('div');
    header.className = 'flow-theme-divider' + (detailSingle ? ' static' : '');
    if (!detailSingle) {
      header.setAttribute('role', 'button');
      header.setAttribute('tabindex', '0');
      header.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }
    header.style.cssText = '--th-t:' + g.color.t + ';--th-bg:' + g.color.bg + ';--th-bd:' + g.color.bd;
    header.innerHTML =
        '<span class="ftd-line"></span>'
      + '<span class="ftd-label">'
      +   (detailSingle ? '' : '<svg class="ftd-chev" viewBox="0 0 24 24" width="11" height="11"><path d="M8 5l8 7-8 7z"/></svg>')
      +   '<span class="ftd-dot"></span>'
      +   escH(g.themeLabel)
      + '</span>'
      + '<span class="ftd-line r"></span>';
    if (!detailSingle) {
      var toggle = function() {
        if (state.collapsedThemes[groupKey]) delete state.collapsedThemes[groupKey];
        else state.collapsedThemes[groupKey] = true;
        renderCentre(conv);
      };
      header.addEventListener('click', toggle);
      header.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
      });
    }
    // Detailed shows ONE request at a time (Fix 31), so this divider divides nothing -
    // and now that every row carries its own intent pill it just repeats the row beneath
    // it. Kept in Lineage, where it genuinely separates one request from the next.
    if (!detailSingle) groupEl.appendChild(header);

    // Group body — stacked exchange rows (detailed) or compact summary rows (lineage).
    var bodyEl = document.createElement('div');
    bodyEl.className = 'flow-theme-body ' + (viewMode === 'lineage' ? 'lineage' : 'detailed');

    // Each unit is a request; render it per the active view mode.
    units.forEach(function(u) {
      bodyEl.appendChild(viewMode === 'lineage'
        ? renderLineageRow(u, g.color)
        : renderUnit(u, g.color));
    });

    groupEl.appendChild(bodyEl);
    box.appendChild(groupEl);
  });

  // "Collapse/Expand all" toggle at the end of the channel-filter bar. Only
  // meaningful in Lineage (multiple foldable theme sections); Detailed shows a
  // single request. Collapses every THEME section and flips to "Expand all".
  if (groups.length && viewMode === 'lineage') {
    var allThemeKeys = groups.map(function(_, gi) { return convKey + ':' + gi; });
    var everyCollapsed = allThemeKeys.every(function(k) { return state.collapsedThemes[k]; });
    var caBtn = document.createElement('button');
    caBtn.className = 'chfilt chfilt-collapse';
    caBtn.innerHTML = (everyCollapsed
      ? '<svg viewBox="0 0 24 24" width="12" height="12"><path d="M7 10l5 5 5-5z"/></svg>Expand all'
      : '<svg viewBox="0 0 24 24" width="12" height="12"><path d="M7 14l5-5 5 5z"/></svg>Collapse all');
    caBtn.addEventListener('click', function() {
      allThemeKeys.forEach(function(k) {
        if (everyCollapsed) delete state.collapsedThemes[k];
        else state.collapsedThemes[k] = true;
      });
      renderCentre(conv);
    });
    bar.appendChild(caBtn);
  }

  // Scroll the highlighted turn into view and clear the pending highlight
  if (state.highlightTicketId) {
    var highlighted = box.querySelector('.flow-step--highlight');
    if (highlighted) {
      setTimeout(function() { highlighted.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 120);
    }
    state.highlightTicketId = null;
  }

  // Compose
  if (!isDone) {
    document.getElementById('cinput').placeholder = 'Reply to ' + nm + '…';
  }

  renderDraftCard(conv, viewMode, shownInboundTurnIds);
}

// Render the human-in-the-loop editable draft card if this conversation has a pending
// held reply. The AI's proposed answer is shown in an editable box; the agent can correct
// it and Send (delivers to the customer + persists the outbound turn), or Discard it.
// A confidence pill for the held-reply card: label + %, coloured by band
// (≥70 green, ≥40 amber, else red). Renders nothing when the score is absent
// (legacy drafts predate the feature).
function confPill(label, score) {
  if (score == null || isNaN(score)) return '';
  var pct = Math.round(Number(score) * 100);
  var cls = pct >= 70 ? 'conf-hi' : (pct >= 40 ? 'conf-mid' : 'conf-lo');
  return '<span class="conf-pill ' + cls + '" title="' + escH(label) + ' confidence: ' + pct + '%">'
    + escH(label) + ' ' + pct + '%</span>';
}

function renderDraftCard(conv, viewMode, shownInboundTurnIds) {
  var mount = document.getElementById('draftMount');
  if (!mount) return;
  var draft = state.pendingDrafts[conv.conversation_id];
  var compose = document.getElementById('compwrap');
  if (!draft) {
    mount.innerHTML = '';
    return;  // no draft: leave the compose box as renderCentre() set it
  }
  // A held draft answers ONE specific question, so it is only shown while that
  // question is the one on screen. The card used to be keyed on the conversation
  // alone, so it sat under whichever request the Detailed view happened to be
  // focused on — an agent could read "What is my credit card limit?" above a
  // proposed reply about a payment due date and send it against the wrong turn.
  //
  // Hidden in Lineage too: that view is an overview of every request, so no single
  // question is being displayed and there is nothing for the card to belong to.
  // An offer draft is bank-initiated and answers no question, so it keeps the old
  // conversation-level behaviour.
  var isOfferDraft = draft.channel === 'offer';
  if (!isOfferDraft) {
    var onDetailed = viewMode !== 'lineage';
    var shown = shownInboundTurnIds || {};
    var belongsHere = !!(draft.inbound_turn_id && shown[draft.inbound_turn_id]);
    if (!onDetailed || !belongsHere) {
      mount.innerHTML = '';
      // The compose box was hidden for the draft that is no longer shown; restore
      // it so the agent still has a reply surface on this request. Restored on closed
      // conversations too - see renderCentre: a closed case still gets replies.
      if (compose) {
        compose.style.display = 'block';
      }
      return;
    }
  }
  // A held draft IS the reply surface — hide the generic compose box so there is only one
  // (and the real one). renderCentre() runs before this and may have shown compwrap.
  if (compose) compose.style.display = 'none';
  // Offer drafts (channel="offer", from an approved cross-/up-sell opportunity)
  // are proactive outbound: sent to every push channel on record, not a reply.
  var isOffer = draft.channel === 'offer';
  var hdr = isOffer
    ? '<span>💡 Approved offer — edit &amp; send</span>'
    + '<span class="draft-reason">Delivers via WhatsApp + Email</span>'
    : '<span>✋ Held for review — edit &amp; send manually</span>'
    + '<span class="draft-reason">' + escH(draft.hold_reason || 'Escalated') + '</span>'
    + confPill('Retrieval', draft.retrieval_confidence)
    + confPill('Intent', draft.intent_confidence);
  mount.innerHTML =
    '<div class="draft-card' + (isOffer ? ' draft-card--offer' : '') + '" data-draft-id="' + escH(draft.draft_id) + '">'
    + '<div class="draft-hdr">' + hdr + '</div>'
    + '<div class="draft-body">'
    + '<div class="draft-label">' + (isOffer ? 'Offer message (editable)' : 'AI-proposed reply (editable)') + '</div>'
    + '<textarea class="draft-textarea" id="draftText">' + escH(draft.draft_text || '') + '</textarea>'
    + '<div class="draft-actions">'
    + '<button class="draft-send-btn" onclick="sendDraft(this)">' + (isOffer ? 'Send offer' : 'Send reply') + '</button>'
    + '<button class="draft-discard-btn" onclick="discardDraft(this)">Discard</button>'
    + '</div></div></div>';
}

window.sendDraft = function(btn) {
  var card = btn.closest('.draft-card');
  var draftId = card && card.getAttribute('data-draft-id');
  var text = (document.getElementById('draftText').value || '').trim();
  if (!draftId || !text) { toast('Reply text is required'); return; }
  card.querySelectorAll('button').forEach(function(b){ b.disabled = true; });
  api('/admin/reply-drafts/' + encodeURIComponent(draftId) + '/send', {
    method: 'POST',
    body: JSON.stringify({ text: text }),
  }).then(function() {
    toast('Reply sent to customer');
    if (state.convDetail) {
      delete state.pendingDrafts[state.convDetail.conversation_id];
      renderCentre(state.convDetail);  // clears the card + restores the compose box
    }
    refreshSelectedConv();
    loadConversations();
  }).catch(function(err) {
    toast('Failed: ' + err.message);
    card.querySelectorAll('button').forEach(function(b){ b.disabled = false; });
  });
};

window.discardDraft = function(btn) {
  var card = btn.closest('.draft-card');
  var draftId = card && card.getAttribute('data-draft-id');
  if (!draftId) return;
  card.querySelectorAll('button').forEach(function(b){ b.disabled = true; });
  api('/admin/reply-drafts/' + encodeURIComponent(draftId) + '/discard', {
    method: 'POST',
    body: JSON.stringify({}),
  }).then(function() {
    toast('Draft discarded');
    if (state.convDetail) {
      delete state.pendingDrafts[state.convDetail.conversation_id];
      renderCentre(state.convDetail);  // clears the card + restores the compose box
    }
    loadConversations();
  }).catch(function(err) {
    toast('Failed: ' + err.message);
    card.querySelectorAll('button').forEach(function(b){ b.disabled = false; });
  });
};

function renderRight(conv, tickets) {
  var conv_meta = state.convs.find(function(c) { return c.conversation_id === conv.conversation_id; }) || conv;

  var turns = conv.turns || [];

  var NEG_KW = ['angry','bad','terrible','frustrated','late','failed','problem','damaged','not received','not credited','charged twice','cancel','fraud','stolen','unauthorized','incorrect charge','overdue','default','claim rejected','policy lapsed','blocked account','money gone','wrong transfer','human agent','human representative'];
  var POS_KW = ['thanks','thank you','great','good','helpful','resolved','approved','credited','disbursed','processed','excellent','perfect','awesome'];
  function clientSentiment(text) {
    var t = (text || '').toLowerCase();
    if (NEG_KW.some(function(w){ return t.indexOf(w) !== -1; })) return 'negative';
    if (POS_KW.some(function(w){ return t.indexOf(w) !== -1; })) return 'positive';
    return 'neutral';
  }
  var inbound = turns.filter(function(t) { return t.direction === 'inbound'; });
  // Sentiment window: the last N customer messages (newest), so the panel
  // reflects how the customer feels NOW, not a lifetime average. Counts,
  // bar, and label are all computed from this same window.
  var SENT_WINDOW = 5;
  var recent = inbound.slice(-SENT_WINDOW);
  var sentCounts = { positive: 0, neutral: 0, negative: 0 };
  recent.forEach(function(t) {
    var s = (t.metadata && t.metadata.sentiment) ? t.metadata.sentiment.toLowerCase() : clientSentiment(t.text);
    if (sentCounts[s] !== undefined) sentCounts[s]++;  else sentCounts.neutral++;
  });
  var total = recent.length || 1;
  var negPct = Math.round((sentCounts.negative / total) * 100);
  var posPct = Math.round((sentCounts.positive / total) * 100);
  var neuPct = Math.max(0, 100 - negPct - posPct);
  var sentCount = recent.length || 1;
  var sentLbl, sentClr;
  if (negPct >= 60) {
    sentLbl = 'Very frustrated'; sentClr = '#dc2626';
  } else if (negPct >= 30) {
    sentLbl = 'Frustrated'; sentClr = 'var(--red-t)';
  } else if (posPct >= 55) {
    sentLbl = 'Positive'; sentClr = 'var(--grn-t)';
  } else {
    sentLbl = 'Neutral'; sentClr = 'var(--amb-t)';
  }


  // SERVICEABLE: the panel shows the agent what needs a person, so logging threads
  // stay out of it.
  var _snapTickets = (tickets || allTickets())
    .filter(function(t) { return t.conversation_id === conv.conversation_id && isServiceable(t); });

  var body = document.getElementById('rpbody');
  body.innerHTML = ''
    // Customer Context leads the panel: what is WRONG with this customer's records,
    // grouped into tabs by one LLM call. Rendered as a placeholder and filled
    // asynchronously so a slow or unavailable LLM never delays the rest of the panel.
    + '<div class="rpcard cctx-card" id="cctx-card">'
    + '<div class="cctx-head"><span class="rplbl">Customer context</span>'
    + '<button class="cctx-refresh" id="cctx-refresh" type="button" title="Regroup this customer\'s records">Refresh</button></div>'
    + '<div class="cctx-tabs" id="cctx-tabs"></div>'
    + '<div class="cctx-body" id="cctx-body"><span class="cctx-muted">Grouping records…</span></div>'
    + '</div>'
    // Sentiment before the case summary: it is a one-line read, so it answers "how is
    // this customer feeling" before the agent starts reading prose.
    + '<div class="rpcard"><div class="ssent-head"><span class="rplbl">Sentiment</span>'
    + '<span class="ssc" style="color:' + sentClr + '">' + escH(sentLbl) + '</span>'
    + '<span class="ssent-count">(last ' + sentCount + ' message' + (sentCount === 1 ? '' : 's') + ')</span></div>'
    + '<div class="sbar">'
    + '<div class="sbp" style="flex:' + posPct + '"></div>'
    + '<div class="sbu" style="flex:' + neuPct + '"></div>'
    + '<div class="sbn" style="flex:' + negPct + '"></div>'
    + '</div>'
    + '<div class="srow">'
    + '<span class="slbl" style="color:var(--grn-t)">' + posPct + '% positive</span>'
    + '<span class="slbl">' + neuPct + '% neutral</span>'
    + '<span class="slbl" style="color:var(--red-t)">' + negPct + '% negative</span>'
    + '</div></div>'
    // Rendered as a placeholder and filled asynchronously so a slow or unavailable LLM
    // never delays the rest of the panel.
    + '<div class="rpcard csum-card" id="csum-card">'
    + '<div class="csum-head"><span class="rplbl">Case summary</span>'
    + '<button class="csum-refresh" id="csum-refresh" type="button" title="Regenerate this summary">Refresh</button></div>'
    + '<div class="csum-body" id="csum-body"><span class="csum-muted">Summarising…</span></div>'
    + '</div>';

  // Async: fetch loans/claims count from Neo4j via customer graph endpoint
  var _snapCustId = conv_meta.customer_id;
  if (_snapCustId) {
    // Customer Context. renderRight rebuilds the panel HTML above, so the card needs
    // repainting on every render — but the payload is held client-side, so a repaint
    // reuses it and only a genuinely new customer costs a request.
    loadCustomerContext(_snapCustId, false);

    // The customer-360 graph is no longer offered here — the header now opens the two
    // system diagrams instead (Neo4j knowledge graph / LangGraph workflow), which do not
    // depend on which customer is selected. /graph-view is still live and still feeds the
    // "Why this answer" provenance panel.

    // Still called after the snapshot tiles were dropped: this is also what fills the
    // conversation header's name / id / email / phone line.
    api('/admin/customers/' + encodeURIComponent(_snapCustId) + '/graph').then(function(g) {
      // Contact details from the CUSTOMER RECORD, falling back to the channels they
      // have written in on. channel_identities lists channels USED, so a customer who
      // has only ever emailed had no whatsapp row and the header showed no phone -
      // while the bank held one in the graph. The fallback keeps unverified senders
      // (not in the graph) showing whatever address they wrote from.
      var ids = g.identifiers || [];
      var emailId = g.email || null, phoneId = g.phone || null;
      ids.forEach(function(id) {
        if (!emailId && id.channel === 'email') emailId = id.identifier;
        if (!phoneId && id.channel === 'whatsapp') phoneId = id.identifier;
      });

      // Use the REAL name from the Neo4j graph payload ONLY if present. Do NOT
      // overwrite the name already set by renderCentre/customerLabel (which reads
      // the SQLite display_name) — otherwise a missing g.name would clobber a
      // correct name. Never fabricate a name from the email.
      if (g.name && String(g.name).trim()) {
        var nameEl = document.getElementById('convName');
        if (nameEl) nameEl.textContent = String(g.name).trim();
      }
      // Email · phone beside the name. The internal cust_... key used to lead this line,
      // but it is a SQLite row id this app generates - random hex an agent cannot use,
      // look up, or quote to anyone. The identifier that means something is the CRN the
      // BFSI dataset is keyed on, and that belongs in the Profile tab with the rest of
      // the record. Email and phone stay: they are how an agent verifies who is writing.
      var metaEl = document.getElementById('convMeta');
      if (metaEl) {
        var parts = [];
        if (emailId) parts.push(escH(emailId));
        if (phoneId) parts.push(escH(phoneId));
        metaEl.innerHTML = parts.join('<span class="cmeta-sep">·</span>');
      }
    }).catch(function() {});
  }

  var _tickets = tickets || allTickets();
  var convTickets = _tickets.filter(function(t) {
    return t.conversation_id === conv.conversation_id && isServiceable(t);
  });
  if (convTickets.length) {
    var tktHtml = convTickets.map(function(t) {
      var isOpen = isServiceable(t);
      var stBg = t.status === 'closed' ? 'background:var(--grn-bg);border-color:var(--grn-bd);color:var(--grn-t)' :
                 isOpen ? 'background:var(--amb-bg);border-color:var(--amb-bd);color:var(--amb-t)' :
                 'background:var(--surf2);border-color:var(--bdr);color:var(--t3)';
      return '<div class="tkt-item tkt-item--clickable" onclick="goToConversation(\'' + escH(conv.conversation_id) + '\',\'' + escH(t.ticket_id) + '\')"><div class="tkt-head">'
        + '<span class="tkt-id">' + escH(t.ticket_id.slice(0,16)) + '</span>'
        + '<span class="tkt-st" style="' + stBg + '">' + escH(statusLabel(t.status)) + '</span>'
        + '</div><div class="tkt-desc">' + escH((t.title||t.intent||'').slice(0,60)) + '</div>'
        + '<div class="tkt-created">Created: ' + escH(fmtDateTime(t.created_at)) + '</div>'
        + (isOpen ? '<button class="tkt-resolve-btn" onclick="event.stopPropagation();resolveTicket(this,\'' + escH(t.ticket_id) + '\')">Close ticket</button>' : '')
        + '</div>';
    }).join('');
    // Collapsed by default: the COUNT is the at-a-glance signal an agent needs, and
    // each ticket row carries an id, a description, a date and a Resolve button, so
    // three open tickets otherwise own most of the panel.
    body.innerHTML += '<div class="rpcard tkt-card' + (state.tktOpen ? ' on' : '') + '" id="tkt-card">'
      + '<button class="tkt-toggle" id="tkt-toggle" type="button">'
      + '<span class="rplbl rplbl-tickets">Open Tickets (' + convTickets.length + ')</span>'
      + '<svg class="tkt-chev" width="10" height="10" viewBox="0 0 16 16" aria-hidden="true">'
      + '<path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="2"/></svg>'
      + '</button>'
      + '<div class="tkt-scroll">' + tktHtml + '</div></div>';
  }

  // Cross-sell / up-sell opportunities (LLM-selected, code-gated; admin
  // approves → editable offer draft → sent to WhatsApp + email).
  body.innerHTML += '<div class="rpcard" id="rpOppCard"><div class="rplbl rplbl-offers">Suggested Offers</div>'
    + '<div id="rpOppBody" style="font-size:11px;color:var(--t3)">Checking…</div></div>';
  api('/admin/agent-assist/opportunities?conversation_id=' + encodeURIComponent(conv.conversation_id))
    .then(function(result) { renderOpportunities(result); })
    .catch(function() {
      var el = document.getElementById('rpOppBody');
      if (el) el.textContent = 'Unavailable';
    });
}

function renderOpportunities(result) {
  var el = document.getElementById('rpOppBody');
  if (!el) return;
  if (result.suppressed) {
    el.innerHTML = '<span class="opp-suppressed">No offers right now — '
      + escH(result.suppressed) + '.</span>';
    return;
  }
  var opps = result.opportunities || [];
  if (!opps.length) {
    el.textContent = 'No offers right now.';
    return;
  }
  el.innerHTML = opps.map(function(o) {
    var isUp = o.action_type === 'up_sell';
    var badge = isUp
      ? '<span class="nba-badge nba-badge-upsell">Up-sell</span>'
      : '<span class="nba-badge nba-badge-crosssell">Cross-sell</span>';
    var meta = o.metadata || {};
    var basis = meta.basis ? '<div class="opp-basis">Why: ' + escH(meta.basis) + '</div>' : '';
    return '<div class="nba-item opp-item" data-rec-id="' + escH(o.recommendation_id) + '">'
      + badge
      + '<div class="nba-reason">' + escH(o.reason) + '</div>'
      + basis
      + '<div class="nba-actions">'
      + '<button class="nba-approve-btn" onclick="decideOpportunity(this,\'approved\')">Approve</button>'
      + '<button class="nba-dismiss-btn" onclick="decideOpportunity(this,\'dismissed\')">Dismiss</button>'
      + '</div></div>';
  }).join('');
}

// Approving an opportunity CREATES an editable offer draft (unlike operational
// NBA approvals, which only record the decision) — refresh the centre so the
// draft card appears immediately.
window.decideOpportunity = function(btn, status) {
  var item = btn.closest('.opp-item');
  var recId = item ? item.getAttribute('data-rec-id') : null;
  if (!recId) return;
  btn.parentElement.querySelectorAll('button').forEach(function(b) { b.disabled = true; });
  api('/admin/agent-assist/recommendations/' + encodeURIComponent(recId) + '/decision', {
    method: 'POST',
    body: JSON.stringify({ status: status }),
  }).then(function() {
    if (status === 'approved') {
      toast('Offer approved — review the draft & send');
      loadPendingDrafts().then(function() {
        if (state.convDetail) renderCentre(state.convDetail);
        // Keep the Needs Review badge + queue dot/filter in sync immediately — otherwise
        // the newly-created offer draft is invisible there until the next ~10s poll.
        renderQueue();
        var nrBadge = document.getElementById('reviewBadge');
        if (nrBadge) {
          var nrCount = Object.keys(state.pendingDrafts).length;
          if (nrCount > 0) { nrBadge.style.display = 'flex'; nrBadge.textContent = nrCount > 9 ? '9+' : nrCount; }
          else { nrBadge.style.display = 'none'; }
        }
      });
    } else {
      toast('Opportunity dismissed');
    }
    if (item) item.style.opacity = '0.4';
  }).catch(function(err) {
    toast('Failed: ' + err.message);
    btn.parentElement.querySelectorAll('button').forEach(function(b) { b.disabled = false; });
  });
};

// NOTE: the "Recommended actions" (NBA) card was removed (redundant with the
// Attrition band, Tickets panel SLA info, and the Opportunities card — and its
// Approve recorded a decision without executing anything). The backend NBA
// engine/endpoint remain for API consumers.

window.doSend = function() {
  var txt = document.getElementById('cinput').value.trim();
  if (!txt || !state.convDetail) return;
  toast('Reply queued (simulation mode) · ' + txt.slice(0,30));
  document.getElementById('cinput').value = '';
};

// ── Confirmation modal ────────────────────────────────────────────────────────
var _confirmCallback = null;

function showConfirm(opts) {
  var icon = opts.icon || '';
  var title = opts.title || 'Confirm';
  var msg = opts.msg || '';
  var okLabel = opts.okLabel || 'Confirm';
  var okColor = opts.okColor || 'var(--blue)';
  _confirmCallback = opts.onConfirm || null;
  document.getElementById('confirmIcon').innerHTML = icon;
  document.getElementById('confirmTitle').textContent = title;
  document.getElementById('confirmMsg').textContent = msg;
  var okBtn = document.getElementById('confirmOkBtn');
  okBtn.textContent = okLabel;
  okBtn.style.background = okColor;
  okBtn.style.borderColor = okColor;
  document.getElementById('confirmModal').classList.remove('hidden');
}

window.closeConfirm = function() {
  document.getElementById('confirmModal').classList.add('hidden');
  _confirmCallback = null;
};

window.confirmOk = async function() {
  document.getElementById('confirmModal').classList.add('hidden');
  if (_confirmCallback) {
    var cb = _confirmCallback;
    _confirmCallback = null;
    await cb();
  }
};

// Conversation-level Resolve/Escalate buttons were removed: resolution is per-ticket (see the
// per-ticket Resolve control in renderRight), and conversation "resolved" is derived from having
// no open tickets. The old Escalate was a non-functional UI stub (no backend action).

// Resolve a single ticket from the Tickets panel, then refresh so the conversation-resolved
// state is re-derived (a conversation is done only when it has no open tickets left).
window.resolveTicket = function(btn, ticketId) {
  if (!ticketId) return;
  var adminUser = currentUser ? currentUser.username : 'admin';
  btn.disabled = true;
  api('/admin/tickets/' + encodeURIComponent(ticketId) + '/status', {
    method: 'PATCH',
    body: JSON.stringify({ status: 'closed', actor: adminUser })
  }).then(function() {
    toast('Ticket ' + ticketId.slice(0,16) + ' resolved ✓');
    // Re-derive: loadConversations refreshes the _allTickets cache too.
    return loadConversations();
  }).then(function() {
    if (state.convDetail) {
      var all = allTickets();
      // SERVICEABLE: a logging thread is not outstanding work, so it must not keep a
      // conversation showing as active (mirrors the same rule in repository.append_turn).
      var stillOpen = all.some(function(t) {
        return t.conversation_id === state.convDetail.conversation_id && isServiceable(t);
      });
      state.convDetail.status = stillOpen ? 'active' : 'closed';
      state.convs.forEach(function(c) {
        if (c.conversation_id === state.convDetail.conversation_id) c.status = state.convDetail.status;
      });
      renderCentre(state.convDetail);
      renderRight(state.convDetail, all);
      renderQueue();
      // Resolving a ticket is not a new TURN, and the case summary is cached against
      // the newest turn id -- so without forcing it here the summary keeps listing the
      // ticket just resolved as open, contradicting the Open Tickets card beside it.
      loadCaseSummary(state.convDetail.conversation_id, true);
    }
  }).catch(function(e) {
    toast('Error: ' + e.message);
    btn.disabled = false;
  });
};

document.getElementById('ftags').addEventListener('click', function(e) {
  if (!e.target.dataset.f) return;
  activeFilter = e.target.dataset.f;
  document.querySelectorAll('.ftag').forEach(function(b) { b.classList.remove('on'); });
  e.target.classList.add('on');
  renderQueue();
});
document.getElementById('srchInput').addEventListener('input', function() { renderQueue(); });
document.getElementById('cinput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); window.doSend(); }
});

// ── ANALYTICS ────────────────────────────────────────────────────────────────
window.loadAnalytics = async function() {
  var spinner = document.getElementById('analyticsSpinner');
  if (spinner) spinner.classList.add('spinning');
  try {
    var results = await Promise.all([
      fetch('/analytics/overview', { headers: adminHeaders() }).then(function(r){return r.json();}),
      fetch('/analytics/channels', { headers: adminHeaders() }).then(function(r){return r.json();}),
      fetch('/analytics/intents',  { headers: adminHeaders() }).then(function(r){return r.json();}),
      fetch('/analytics/agents',   { headers: adminHeaders() }).then(function(r){return r.json();}),
      fetch('/admin/audit-events', { headers: adminHeaders() }).then(function(r){return r.json();}),
      fetch('/admin/llm-observability/summary?days=7', { headers: adminHeaders() }).then(function(r){return r.json();}),
      fetch('/analytics/sentiment', { headers: adminHeaders() }).then(function(r){return r.json();}),
      fetch('/analytics/solution-performance', { headers: adminHeaders() }).then(function(r){return r.json();}),
    ]);
    renderOverview(results[0]);
    renderChannelBars(results[1]);
    renderIntentBars(results[2]);
    renderAgentPanel(results[3]);
    renderFeedList(results[4], false);
    renderLlmUsagePanel(results[5]);
    renderModelVersionTable(results[5]);
    renderLlmTimeTrends(results[5]);
    renderSolutionStats(results[7]);
    renderSolutionCharts(results[7]);
  } catch(e) {
    console.error('Analytics load error:', e.message);
  } finally {
    if (spinner) spinner.classList.remove('spinning');
  }
};

function renderOverview(d) {
  var negPct = d.neg_sentiment_today_pct || 0;
  var yesterPct = d.neg_sentiment_yesterday_pct || 0;
  var negDelta = Math.round((negPct - yesterPct) * 10) / 10;
  var negDeltaLabel = (negDelta >= 0 ? '↑ +' : '↓ ') + negDelta + '% vs yesterday';
  var negDeltaClr = negDelta > 0 ? 'var(--red-t)' : 'var(--grn-t)';

  var frt = d.avg_resolution_minutes || 0;
  var frtLabel = frt >= 60 ? (frt / 60).toFixed(1) + ' hr' : frt.toFixed(1) + ' min';
  var frtDeltaLabel = '';
  var frtDeltaClr = 'var(--t1)';

  var cards = [
    { val: d.total_open, lbl: 'Open tickets', sub: d.total_conversations + ' total conversations', tone: 'amb', icon: '&#9873;', clr: d.total_open > 20 ? 'var(--amb-t)' : 'var(--t1)', subClr: '',
      tip: 'Count of tickets whose status is not resolved or closed. The live backlog across all conversations.' },
    { val: d.total_resolved, lbl: 'Closed', sub: d.total_customers + ' customers', tone: 'grn', icon: '&#10003;', clr: 'var(--grn-t)', subClr: '',
      tip: 'Count of tickets with status resolved or closed.' },
    { val: negPct.toFixed(0) + '%', lbl: 'Negative sentiment today', sub: negDeltaLabel, tone: 'red', icon: '&#9760;', clr: 'var(--red-t)', subClr: negDeltaClr,
      tip: 'Share of today\'s inbound messages classified negative (stored AI sentiment, falling back to keyword detection) ÷ today\'s inbound messages × 100. The delta compares against yesterday\'s same figure.' },
    { val: frtLabel, lbl: 'Avg resolution time today', sub: frtDeltaLabel, tone: 'blue', icon: '&#9201;', clr: 'var(--t1)', subClr: frtDeltaClr,
      tip: 'Average of (ticket updated_at − created_at) over tickets resolved/closed, in minutes (shown as hr when ≥60).' },
  ];
  document.getElementById('overviewGrid').innerHTML = renderKpiTiles(cards);
}

// Shared KPI-tile renderer — accent tone + icon + optional data-driven value colour + sub line.
// c.tip (optional) = a formula/explanation shown as a native hover tooltip on the whole tile,
// with a small "?" affordance so users know to hover.
function renderKpiTiles(cards) {
  return cards.map(function(c) {
    var valStyle = c.clr ? ' style="color:' + c.clr + '"' : '';
    var sub = c.sub ? '<div class="kpi-sub"' + (c.subClr ? ' style="color:' + c.subClr + '"' : '') + '>' + c.sub + '</div>' : '';
    var tipAttr = c.tip ? ' title="' + escH(c.tip) + '"' : '';
    var tipMark = c.tip ? '<span class="kpi-help" title="' + escH(c.tip) + '">?</span>' : '';
    return '<div class="kpi-tile kpi-' + (c.tone || 'blue') + (c.tip ? ' kpi-has-tip' : '') + '"' + tipAttr + '>'
      + tipMark
      + '<div class="kpi-icon">' + (c.icon || '') + '</div>'
      + '<div class="kpi-val"' + valStyle + '>' + c.val + '</div>'
      + '<div class="kpi-lbl">' + c.lbl + '</div>'
      + sub + '</div>';
  }).join('');
}

function renderBars(containerId, items, lk, vk, colorFn) {
  var el = document.getElementById(containerId);
  if (!items || !items.length) { el.innerHTML = '<div class="empty-state">No data yet</div>'; return; }
  var max = Math.max.apply(null, items.map(function(i){return i[vk];}));
  var COLORS = ['#2563eb','#16a34a','#d97706','#dc2626','#7c3aed','#0ea5e9','#ec4899','#f59e0b','#10b981','#6366f1'];
  el.innerHTML = items.map(function(item, idx) {
    var pct = max > 0 ? Math.round((item[vk]/max)*100) : 0;
    var clr = colorFn ? colorFn(item[lk], idx) : COLORS[idx % COLORS.length];
    // subtle gradient: base colour → a lighter tint of itself, for depth without new tokens
    var fill = 'linear-gradient(90deg,' + clr + ',' + clr + ' 55%,color-mix(in srgb,' + clr + ' 68%,#fff))';
    return '<div class="bar-row"><span class="bar-label" title="' + escH(item[lk]) + '">' + escH(String(item[lk])) + '</span>'
      + '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%;background:' + fill + '"></div></div>'
      + '<span class="bar-val">' + item[vk] + '</span></div>';
  }).join('');
}

function renderChannelBars(data) {
  var items = (data.channels || []).map(function(c){return {channel: c.channel, count: c.ticket_count};}).filter(function(c){return c.count>0;});
  renderBars('channelBars', items, 'channel', 'count', function(ch){ return chMeta(ch).clr; });
}
function renderIntentBars(data) {
  var items = (data.intents||[]).map(function(i){return {intent:i.intent.replace(/_/g,' '),count:i.count};});
  renderBars('intentBars', items, 'intent', 'count', null);
}

// Pipeline order: 1-3 fire on EVERY inbound message, 4-5 only when ticket matching is
// ambiguous, 6-8 when an agent opens a conversation. Anything unlisted sorts last.
var LLM_OP_ORDER = {
  ticket_action_detection: 1,
  intent_classification: 2,
  resolution_level_classification: 3,
  answer_generation: 4,
  ticket_referee: 5,
  ticket_refine_referee: 6,
  case_summary: 7,
  customer_context: 8,
  opportunity_generation: 9
};

// What each call is for, shown on hover. Names like "resolution level classification"
// say nothing on their own about when the call fires or what it decides.
var LLM_OP_PURPOSE = {
  ticket_action_detection:
    'Runs before intent, and only when keyword rules cannot decide: does this message mean the customer considers their issue resolved? A YES closes the open ticket.',
  intent_classification:
    'EVERY message. Classifies the message into one of ~20 BFSI intents, which decides whether the answer comes from the knowledge graph or the knowledge base.',
  resolution_level_classification:
    'EVERY message. Decides L1 / L2 / L3 — whether the query can be answered directly or must escalate into a ticket.',
  answer_generation:
    'EVERY message. Writes the customer-facing reply from whatever the retrieval step returned (graph records, ticket record, or KB passages).',
  ticket_referee:
    'Only when ticket matching is ambiguous: the message matches no open ticket but same-intent tickets exist. Picks the right one or says NEW. Any doubt forks a new ticket.',
  ticket_refine_referee:
    'Only when a vague ticket may need narrowing — e.g. a general dispute becoming a specific card dispute. Refines the existing ticket instead of forking a duplicate.',
  case_summary:
    'When an agent opens a conversation. Writes the situation and open items for someone picking the case up cold. Cached against the newest turn, so re-opening costs nothing.',
  customer_context:
    'When an agent opens a conversation. Sorts the customer’s records into the Risk / Holdings / Activity / Claims / Profile tabs. Cached against a fingerprint of the record.',
  opportunity_generation:
    'Evaluates cross-sell and up-sell offers for the Suggested Offers card. Code picks the candidate products; the LLM writes the pitch.'
};

// Stable colour per operation so the same op keeps its colour across the table + meters.
var LLM_OP_COLORS = ['--blue', '--pur', '--grn', '--amb', '--pnk', '--red'];
function llmOpColor(name, idx) {
  // deterministic by index so ordering (cost-desc) reads as a gentle palette walk
  return 'var(' + LLM_OP_COLORS[idx % LLM_OP_COLORS.length] + ')';
}

// A table cell that is a mini meter: a proportional bar + the value beside it.
// frac = 0..1 (share of the column max), color = css colour, valueLabel = printed text.
// The <td> stays a real table cell; the flex row lives on an inner wrapper so the
// four metric cells keep their own table columns.
function llmMeterCell(frac, color, valueLabel) {
  var pct = Math.max(2, Math.round((frac || 0) * 100));
  return '<td class="llm-meter-cell"><div class="llm-meter-wrap">'
    + '<div class="llm-meter"><div class="llm-meter-fill" style="width:' + pct + '%;background:' + color + '"></div></div>'
    + '<span class="llm-meter-val">' + valueLabel + '</span></div></td>';
}

function renderLlmUsagePanel(data) {
  var el = document.getElementById('llmUsagePanel');
  if (!el) return;
  var totals = (data && data.totals) || {};
  var calls = totals.calls || 0;
  if (!calls) {
    el.innerHTML = '<div class="empty-state">No LLM usage recorded yet</div>';
    return;
  }
  var cost = Number(totals.estimated_cost_usd || 0);
  var avg = Number(totals.avg_latency_ms || 0);
  var cards = [
    { val: Number(calls).toLocaleString(), lbl: 'LLM calls', tone: 'blue', icon: '&#9673;' },
    { val: (totals.total_tokens || 0).toLocaleString(), lbl: 'Tokens', tone: 'pur', icon: '&#9632;' },
    { val: '$' + cost.toFixed(6), lbl: 'Estimated cost', tone: 'grn', icon: '&#36;' },
    { val: avg.toFixed(0) + ' ms', lbl: 'Avg latency', tone: 'amb', icon: '&#9201;' },
  ];

  // Every metric column becomes its own meter (bar + value), each scaled to that column's
  // max across operations, coloured by the row's operation colour — so Calls, Token share,
  // Cost and Latency all read as mini bar charts, not bare numbers.
  var ops = (data.by_operation || []).slice();
  // Ordered by WHERE each call happens in the pipeline, not by cost. Cost order shuffles
  // as usage changes and tells you nothing about what the system does; this reads top to
  // bottom as the actual sequence: every message, then the conditional ones, then the
  // calls an agent triggers by opening a conversation.
  ops.sort(function(a, b) {
    return (LLM_OP_ORDER[a.operation] || 99) - (LLM_OP_ORDER[b.operation] || 99);
  });
  // Cost per call, alongside the total. The two rank the operations differently and both
  // matter: measured here, opportunity generation is the top TOTAL spender but one of the
  // cheapest per call (it just runs often), while customer context is the most expensive
  // per call by 7.6x. Total alone hides which operation is inherently costly.
  var avgCostOf = function(r) {
    var n = Number(r.calls || 0);
    return n ? Number(r.estimated_cost_usd || 0) / n : 0;
  };
  var maxTok   = ops.reduce(function(m, r){ return Math.max(m, Number(r.total_tokens || 0)); }, 0) || 1;
  var maxCalls = ops.reduce(function(m, r){ return Math.max(m, Number(r.calls || 0)); }, 0) || 1;
  var maxCost  = ops.reduce(function(m, r){ return Math.max(m, Number(r.estimated_cost_usd || 0)); }, 0) || 1;
  var maxAvgC  = ops.reduce(function(m, r){ return Math.max(m, avgCostOf(r)); }, 0) || 1;
  var maxLat   = ops.reduce(function(m, r){ return Math.max(m, Number(r.avg_latency_ms || 0)); }, 0) || 1;
  var opRows = ops.map(function(row, i) {
    var clr = llmOpColor(row.operation, i);
    var tok = Number(row.total_tokens || 0);
    var cl  = Number(row.calls || 0);
    var co  = Number(row.estimated_cost_usd || 0);
    var lat = Number(row.avg_latency_ms || 0);
    var purpose = LLM_OP_PURPOSE[row.operation] || '';
    return '<tr>'
      + '<td class="llm-op-cell"' + (purpose ? ' title="' + escH(purpose) + '"' : '') + '>'
        + '<span class="llm-op-dot" style="background:' + clr + '"></span>'
        + escH((row.operation || 'unknown').replace(/_/g, ' '))
        + (purpose ? '<span class="llm-op-q">?</span>' : '') + '</td>'
      + llmMeterCell(cl / maxCalls, clr, cl.toLocaleString())
      + llmMeterCell(tok / maxTok, clr, tok.toLocaleString())
      + llmMeterCell(co / maxCost, clr, '$' + co.toFixed(6))
      + llmMeterCell(avgCostOf(row) / maxAvgC, clr, '$' + avgCostOf(row).toFixed(6))
      + llmMeterCell(lat / maxLat, clr, lat.toFixed(0) + ' ms')
      + '</tr>';
  }).join('');

  el.innerHTML =
    '<div class="kpi-grid">'
    + cards.map(function(c) {
      return '<div class="kpi-tile kpi-' + c.tone + '">'
        + '<div class="kpi-icon">' + c.icon + '</div>'
        + '<div class="kpi-val">' + c.val + '</div>'
        + '<div class="kpi-lbl">' + c.lbl + '</div>'
        + '</div>';
    }).join('')
    + '</div>'
    + '<table class="mini-table llm-op-table"><thead><tr>'
      + '<th>Operation</th><th>Calls</th><th>Token share</th><th>Cost</th>'
      + '<th>Avg cost</th><th>Avg latency</th>'
      + '</tr></thead><tbody>'
    + (opRows || '<tr><td colspan="6">No operation breakdown yet</td></tr>')
    + '</tbody></table>';
}

// Render the short config version as a tag + decode it from the per-row config the backend
// stores alongside each call ("log it somewhere" — the tag is never a mystery). Falls back
// to plain text when no decoded config is present (e.g. legacy 'unknown' rows).
function llmVersionCell(row) {
  var v = row.model_version || 'unknown';
  var cfg = row.model_config || null;
  if (v === 'unknown' || !v) {
    return '<span class="llm-ver llm-ver-unknown">unknown</span>';
  }
  var decoded = '';
  if (cfg && typeof cfg === 'object') {
    var parts = [];
    if (cfg.temperature != null) parts.push('temp ' + cfg.temperature);
    if (cfg.max_tokens != null) parts.push('max ' + cfg.max_tokens); else parts.push('max —');
    if (cfg.top_p != null) parts.push('top_p ' + cfg.top_p); else parts.push('top_p —');
    decoded = '<span class="llm-ver-cfg">' + escH(parts.join(' · ')) + '</span>';
  }
  return '<span class="llm-ver">' + escH(v) + '</span>' + decoded;
}

// A version label for a by_model row: MODEL name as the heading with the version tag as an
// inline chip beside it, and the human-readable config on the line below. The tag is an id
// FOR the config shown — never a duplicate of it stacked above.
// One row per model + config, same six columns as the Operation table above so a number
// means the same thing in both. Was two separate strip panels (cost, latency) that each
// showed one metric and no call count, so a row backed by 7 calls looked as authoritative
// as one backed by 156.
function renderModelVersionTable(data) {
  var el = document.getElementById('modelVersionPanel');
  if (!el) return;
  // Configs with no successful call are not configs - they are settings that errored
  // (a rejected request records zero tokens and zero cost). Showing them as rows invites
  // comparing a real config against a mistake.
  var rows = ((data && data.by_model) || []).filter(function(r) {
    return Number(r.calls || 0) > 0 && Number(r.total_tokens || 0) > 0;
  });
  if (!rows.length) {
    el.innerHTML = '<div class="empty-state">No model usage recorded yet</div>';
    return;
  }

  var avgCostOf = function(r) {
    var n = Number(r.calls || 0);
    return n ? Number(r.estimated_cost_usd || 0) / n : 0;
  };
  var maxCalls = rows.reduce(function(m, r){ return Math.max(m, Number(r.calls || 0)); }, 0) || 1;
  var maxTok   = rows.reduce(function(m, r){ return Math.max(m, Number(r.total_tokens || 0)); }, 0) || 1;
  var maxCost  = rows.reduce(function(m, r){ return Math.max(m, Number(r.estimated_cost_usd || 0)); }, 0) || 1;
  var maxAvgC  = rows.reduce(function(m, r){ return Math.max(m, avgCostOf(r)); }, 0) || 1;
  var maxLat   = rows.reduce(function(m, r){ return Math.max(m, Number(r.avg_latency_ms || 0)); }, 0) || 1;

  var body = rows.map(function(row, i) {
    var clr = llmOpColor(row.model_version || row.model || 'unknown', i);
    var cl  = Number(row.calls || 0);
    var tok = Number(row.total_tokens || 0);
    var co  = Number(row.estimated_cost_usd || 0);
    var lat = Number(row.avg_latency_ms || 0);
    return '<tr>'
      + '<td class="llm-op-cell llm-op-cell--ver" title="' + escH(llmVerPurpose(row)) + '">'
        + '<span class="llm-op-dot" style="background:' + clr + '"></span>'
        + llmVerCellLabel(row) + '</td>'
      + llmMeterCell(cl / maxCalls, clr, cl.toLocaleString())
      + llmMeterCell(tok / maxTok, clr, tok.toLocaleString())
      + llmMeterCell(co / maxCost, clr, '$' + co.toFixed(6))
      + llmMeterCell(avgCostOf(row) / maxAvgC, clr, '$' + avgCostOf(row).toFixed(6))
      + llmMeterCell(lat / maxLat, clr, lat.toFixed(0) + ' ms')
      + '</tr>';
  }).join('');

  el.innerHTML = '<table class="mini-table llm-op-table"><thead><tr>'
    + '<th>Model / config</th><th>Calls</th><th>Token share</th><th>Cost</th>'
    + '<th>Avg cost</th><th>Avg latency</th>'
    + '</tr></thead><tbody>' + body + '</tbody></table>';
}

// What a config row means, built FROM the recorded config rather than from a hardcoded
// table — a version tag is a hash, so anything written by hand would go stale the moment
// a setting changes. Explains what the tag is and what each setting does.
function llmVerPurpose(row) {
  var out = '';
  // What this config is FOR: the pipeline steps that ran under it. A version tag is a
  // hash, so the operation list is the only thing that gives it meaning.
  var ops = (row.operations || '').split(',').filter(Boolean).sort();
  if (ops.length) {
    out += ops.length === 1
      ? 'Used by: ' + ops[0].replace(/_/g, ' ') + '\n\n'
      : 'Used by ' + ops.length + ' operations:\n'
        + ops.map(function(o){ return '  • ' + o.replace(/_/g, ' '); }).join('\n') + '\n\n';
  }
  var cfg = row.model_config || null;
  if (!cfg || typeof cfg !== 'object') {
    return (out + 'Settings were not recorded for these calls — they predate per-call '
      + 'config tracking.').trim();
  }
  out += 'Settings\n';
  if (cfg.temperature != null) {
    out += '  temperature ' + cfg.temperature + ' — how much the wording varies between '
      + 'runs; low keeps answers consistent\n';
  }
  out += cfg.max_tokens != null
    ? '  max tokens ' + cfg.max_tokens + ' — ceiling on one reply, set where a long '
      + 'structured answer would otherwise be cut off mid-document\n'
    : '  max tokens not set — the provider default applies\n';
  if (cfg.top_p != null) out += '  top_p ' + cfg.top_p + '\n';
  return out.trim();
}

// Model name + version tag + the decoded config, on one line for a table cell.
function llmVerCellLabel(row) {
  var v = row.model_version || 'unknown';
  var isUnknown = (v === 'unknown' || !v);
  var cfg = row.model_config || null;
  var sub;
  if (cfg && typeof cfg === 'object') {
    var parts = [];
    if (cfg.temperature != null) parts.push('temp ' + cfg.temperature);
    parts.push(cfg.max_tokens != null ? 'max ' + cfg.max_tokens : 'max —');
    parts.push(cfg.top_p != null ? 'top_p ' + cfg.top_p : 'top_p —');
    sub = escH(parts.join(' · '));
  } else {
    sub = 'config not recorded';  // legacy 'unknown' rows predate the version feature
  }
  return escH(row.model || 'unknown')
    + '<span class="llm-ver ' + (isUnknown ? 'llm-ver-unknown' : '') + '">' + escH(v) + '</span>'
    + '<span class="llm-op-q">?</span>'
    + '<span class="llm-ver-cfg">' + sub + '</span>';
}

// Two side-by-side hourly line charts (Cost | Tokens), one coloured line per model+version.
// Shared X-axis (hours, IST) and a shared colour legend above both. Interactive crosshair +
// tooltip driven in JS (native <title> was unreliable and only on the tiny dot).
var LLM_TL_COLORS = ['#2563eb', '#7c3aed', '#16a34a', '#d97706', '#db2777', '#dc2626', '#0ea5e9', '#65a30d'];
function renderLlmTimeTrends(data) {
  // Same filter as the model/config table: a config whose calls produced no tokens is a
  // rejected request, not a configuration. Left in, each one drew a lone dot on the axis
  // and took a colour in the legend.
  var series = ((data && data.time_series) || []).filter(function(r) {
    return Number(r.total_tokens || 0) > 0;
  });
  var legendEl = document.getElementById('llmTimeLegend');
  var costEl = document.getElementById('llmCostTrend');
  var tokEl = document.getElementById('llmTokenTrend');
  if (!costEl || !tokEl) return;
  if (!series.length) {
    if (legendEl) legendEl.innerHTML = '';
    costEl.innerHTML = tokEl.innerHTML = '<div class="empty-state">No time-series data yet</div>';
    return;
  }
  var hours = []; var hourSet = {};
  var keys = []; var keyIndex = {};
  series.forEach(function(r) {
    if (!hourSet[r.hour]) { hourSet[r.hour] = 1; hours.push(r.hour); }
    var key = (r.model || 'unknown') + ' · ' + (r.model_version || 'unknown');
    if (keyIndex[key] == null) { keyIndex[key] = keys.length; keys.push(key); }
  });
  hours.sort();
  var byKey = {};
  keys.forEach(function(k){ byKey[k] = {}; });
  series.forEach(function(r) {
    var key = (r.model || 'unknown') + ' · ' + (r.model_version || 'unknown');
    byKey[key][r.hour] = { cost: Number(r.estimated_cost_usd || 0), tok: Number(r.total_tokens || 0) };
  });
  if (legendEl) {
    legendEl.innerHTML = keys.map(function(k, i) {
      return '<span class="llm-tl-lg"><span class="llm-tl-sw" style="background:' + LLM_TL_COLORS[i % LLM_TL_COLORS.length] + '"></span>' + escH(k) + '</span>';
    }).join('');
  }
  _llmLineChart(costEl, hours, keys, byKey, 'cost', function(v){ return '$' + v.toFixed(6); });
  _llmLineChart(tokEl, hours, keys, byKey, 'tok', function(v){ return v.toLocaleString() + ' tokens'; });
}

// hour string is "YYYY-MM-DDTHH:00" already in IST (converted in SQL).
var _LLM_MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

// Axis tick. Only hours that HAD calls become points, so consecutive points can be days
// apart — showing the hour alone made three different days' "14:00" look like one hour
// and the axis appear to run backwards. The date is shown on the first point of each day.
function _llmHourTick(h, prev) {
  var hhmm = h.slice(11, 16);
  if (prev && prev.slice(0, 10) === h.slice(0, 10)) return hhmm;   // same day, hour only
  return _llmDayLabel(h) + '|' + hhmm;   // '|' splits it onto a second line
}

function _llmDayLabel(h) {
  var mon = _LLM_MON[parseInt(h.slice(5, 7), 10) - 1] || h.slice(5, 7);
  return parseInt(h.slice(8, 10), 10) + ' ' + mon;
}

// Tooltip header — always the full date, there is no neighbouring point for context.
function _llmHourLabel(h){ return _llmDayLabel(h) + ' ' + h.slice(11, 16); }

// Compact axis tick label (cost in $, tokens as k).
function _llmShort(v, metric) {
  if (metric === 'cost') return '$' + (v >= 0.01 ? v.toFixed(3) : v.toFixed(5));
  return v >= 1000 ? (v/1000).toFixed(v >= 10000 ? 0 : 1) + 'k' : Math.round(v);
}

// Render an interactive line chart into `host`. Uses a big viewBox (so text renders at true
// size), an area gradient under each line, a soft dashed grid, and a JS crosshair+tooltip.
function _llmLineChart(host, hours, keys, byKey, metric, fmt) {
  var W = 720, H = 300, mL = 64, mR = 18, mT = 16, mB = 46;
  var pw = W - mL - mR, ph = H - mT - mB;
  var maxV = 0;
  keys.forEach(function(k){ hours.forEach(function(h){ var d = byKey[k][h]; if (d) maxV = Math.max(maxV, d[metric]); }); });
  if (maxV <= 0) maxV = 1;
  maxV = maxV * 1.12; // headroom so the peak isn't glued to the top
  var n = hours.length;
  var X = function(i){ return n <= 1 ? mL + pw/2 : mL + pw*i/(n-1); };
  var Y = function(v){ return mT + ph - (ph*v/maxV); };
  var uid = 'g' + Math.random().toString(36).slice(2,7);
  var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" class="llm-tl-svg" preserveAspectRatio="xMidYMid meet">';
  s += '<defs>';
  keys.forEach(function(k, ki){
    var c = LLM_TL_COLORS[ki % LLM_TL_COLORS.length];
    s += '<linearGradient id="' + uid + '-' + ki + '" x1="0" y1="0" x2="0" y2="1">'
      + '<stop offset="0%" stop-color="' + c + '" stop-opacity="0.18"/>'
      + '<stop offset="100%" stop-color="' + c + '" stop-opacity="0"/></linearGradient>';
  });
  s += '</defs>';
  // soft dashed gridlines + y ticks
  for (var g = 0; g <= 4; g++) {
    var yy = mT + ph*g/4, val = maxV*(1 - g/4);
    s += '<line x1="' + mL + '" y1="' + yy + '" x2="' + (W-mR) + '" y2="' + yy + '" class="llm-tl-grid"/>';
    s += '<text x="' + (mL-10) + '" y="' + (yy+4) + '" text-anchor="end" class="llm-tl-tick">' + _llmShort(val, metric) + '</text>';
  }
  // x tick labels + baseline
  s += '<line x1="' + mL + '" y1="' + (mT+ph) + '" x2="' + (W-mR) + '" y2="' + (mT+ph) + '" class="llm-tl-axis"/>';
  hours.forEach(function(h, i){
    // Two lines when the day changes: the date sits above the hour so a jump of several
    // days is visible instead of reading as the next hour along.
    var parts = _llmHourTick(h, i ? hours[i-1] : null).split('|');
    if (parts.length === 2) {
      s += '<text x="' + X(i) + '" y="' + (mT+ph+20) + '" text-anchor="middle" class="llm-tl-tick llm-tl-tick-day">' + escH(parts[0]) + '</text>';
      s += '<text x="' + X(i) + '" y="' + (mT+ph+32) + '" text-anchor="middle" class="llm-tl-tick">' + escH(parts[1]) + '</text>';
      // A rule marking where one day ends and the next begins.
      if (i) s += '<line x1="' + (X(i)-(X(i)-X(i-1))/2) + '" y1="' + mT + '" x2="' + (X(i)-(X(i)-X(i-1))/2) + '" y2="' + (mT+ph) + '" class="llm-tl-daysep"/>';
    } else {
      s += '<text x="' + X(i) + '" y="' + (mT+ph+20) + '" text-anchor="middle" class="llm-tl-tick">' + escH(parts[0]) + '</text>';
    }
  });
  s += '<text x="' + (W-mR) + '" y="' + (H-6) + '" text-anchor="end" class="llm-tl-axislbl">Time (IST)</text>';
  // area + line + dots per series
  keys.forEach(function(k, ki){
    var color = LLM_TL_COLORS[ki % LLM_TL_COLORS.length];
    var segs = [], cur = [];
    hours.forEach(function(h, i){
      var d = byKey[k][h];
      if (d) cur.push([X(i), Y(d[metric])]);
      else if (cur.length){ segs.push(cur); cur = []; }
    });
    if (cur.length) segs.push(cur);
    segs.forEach(function(pts){
      if (pts.length > 1){
        // area
        var ap = 'M ' + pts[0][0] + ' ' + (mT+ph);
        pts.forEach(function(p){ ap += ' L ' + p[0] + ' ' + p[1]; });
        ap += ' L ' + pts[pts.length-1][0] + ' ' + (mT+ph) + ' Z';
        s += '<path d="' + ap + '" fill="url(#' + uid + '-' + ki + ')"/>';
        // line
        s += '<polyline points="' + pts.map(function(p){return p[0]+','+p[1];}).join(' ') + '" fill="none" stroke="' + color + '" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>';
      }
    });
    hours.forEach(function(h, i){
      var d = byKey[k][h];
      if (d) s += '<circle cx="' + X(i) + '" cy="' + Y(d[metric]) + '" r="3.6" fill="' + color + '" stroke="#fff" stroke-width="1.6"/>';
    });
  });
  // invisible crosshair layer (one vertical guide + hit rects per hour)
  s += '<line class="llm-tl-cross" x1="0" y1="' + mT + '" x2="0" y2="' + (mT+ph) + '" style="display:none"/>';
  s += '</svg>';
  host.innerHTML = s;
  host.style.position = 'relative';

  // JS hover: nearest-hour tooltip listing every series' value at that hour.
  var svg = host.querySelector('svg');
  var cross = svg.querySelector('.llm-tl-cross');
  var tip = host.querySelector('.llm-tl-tip');
  if (!tip){ tip = document.createElement('div'); tip.className = 'llm-tl-tip'; tip.style.display = 'none'; host.appendChild(tip); }
  function pt(evt){ var r = svg.getBoundingClientRect(); return (evt.clientX - r.left) / r.width * W; }
  svg.addEventListener('mousemove', function(evt){
    if (n === 0) return;
    var vx = pt(evt);
    var i = n <= 1 ? 0 : Math.round((vx - mL) / (pw/(n-1)));
    i = Math.max(0, Math.min(n-1, i));
    var h = hours[i], cx = X(i);
    cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.style.display = '';
    var rows = keys.map(function(k, ki){
      var d = byKey[k][h]; if (!d) return '';
      var c = LLM_TL_COLORS[ki % LLM_TL_COLORS.length];
      return '<div class="llm-tl-tip-row"><span class="llm-tl-tip-sw" style="background:' + c + '"></span>'
        + escH(k) + ' <b>' + fmt(d[metric]) + '</b></div>';
    }).filter(Boolean).join('');
    tip.innerHTML = '<div class="llm-tl-tip-h">' + escH(_llmHourLabel(h)) + ' IST</div>' + rows;
    tip.style.display = 'block';
    var rect = svg.getBoundingClientRect();
    var px = cx / W * rect.width;
    tip.style.left = Math.min(rect.width - tip.offsetWidth - 8, px + 12) + 'px';
    tip.style.top = '8px';
  });
  svg.addEventListener('mouseleave', function(){ cross.style.display = 'none'; tip.style.display = 'none'; });
}

function renderSolutionStats(sp) {
  var el = document.getElementById('solutionStatsGrid');
  if (!el) return;
  var d = sp || {};
  var rate = d.escalation_rate_pct != null ? d.escalation_rate_pct : 0;
  var avgRisk = d.avg_risk_score != null ? d.avg_risk_score : 0;

  var cards = [
    { val: rate + '%', lbl: 'Escalation rate',
      sub: (d.escalations || 0) + ' escalations / ' + (d.inbound_queries || 0) + ' queries',
      tone: 'red', icon: '&#8599;', clr: rate > 40 ? 'var(--red-t)' : 'var(--t1)',
      tip: 'Escalated tickets ÷ total inbound customer queries × 100. Counts every query the customer sent (not just tickets), so routine non-escalating queries pull the rate down — it is a real 0–100% rate, not a count that only climbs.' },
    { val: avgRisk, lbl: 'Avg risk score',
      sub: 'open tickets (0–100)',
      tone: 'amb', icon: '&#9888;', clr: avgRisk >= 70 ? 'var(--red-t)' : (avgRisk >= 40 ? 'var(--amb-t)' : 'var(--t1)'),
      tip: 'Average of priority_score across OPEN tickets (from the ticket priority-scoring engine). One number for how hot the current queue is; 0 = calm, 100 = severe.' },
    { val: d.critical_open || 0, lbl: 'Critical load',
      sub: 'critical open tickets',
      tone: 'red', icon: '&#128293;', clr: (d.critical_open || 0) > 0 ? 'var(--red-t)' : 'var(--grn-t)',
      tip: 'Count of OPEN tickets with priority = critical. Immediate triage signal — how many high-severity issues are live right now.' },
    { val: d.drafts_handled || 0, lbl: 'Drafts handled',
      sub: 'human-in-the-loop replies sent',
      tone: 'grn', icon: '&#9998;', clr: 'var(--grn-t)',
      tip: 'Reply drafts an agent reviewed and sent (reply_drafts with status = sent). Throughput of the human-in-the-loop review gate.' },
  ];
  el.innerHTML = renderKpiTiles(cards);
}

// Two charts for the Solution Performance section: open tickets by risk band, and why
// tickets escalate. Both driven by /analytics/solution-performance (LabelCount lists).
function renderSolutionCharts(sp) {
  var d = sp || {};
  var riskColors = { Critical: 'var(--red)', High: 'var(--amb)', Medium: 'var(--blue)', Low: 'var(--grn)' };
  var riskItems = (d.by_risk_band || []).map(function(b){ return { label: b.label, count: b.count }; });
  renderBars('riskBandPanel', riskItems, 'label', 'count', function(lbl){ return riskColors[lbl] || 'var(--t3)'; });

  var reasonItems = (d.by_escalation_reason || []).map(function(b){ return { label: b.label, count: b.count }; });
  renderBars('escReasonPanel', reasonItems, 'label', 'count', null);
}

function renderSentimentPanel(data) {
  var el = document.getElementById('sentimentPanel');
  if (!el) return;  // Customer sentiment card removed from the layout
  var total = data.total || 0;
  if (!total) { el.innerHTML = '<div class="empty-state">No sentiment data yet</div>'; return; }
  var pos = Math.round((data.positive/total)*100);
  var neg = Math.round((data.negative/total)*100);
  var neu = Math.max(0, 100-pos-neg);
  el.innerHTML = '<div class="sent-total">' + total + '<span class="sent-total-lbl"> messages</span></div>'
    + '<div class="sent-bar"><div class="sent-pos" style="flex:'+pos+'"></div><div class="sent-neu" style="flex:'+neu+'"></div><div class="sent-neg" style="flex:'+neg+'"></div></div>'
    + '<div class="sent-row"><span class="sent-lbl"><span class="sent-key sent-key-pos"></span>'+pos+'% positive</span>'
    + '<span class="sent-lbl"><span class="sent-key sent-key-neu"></span>'+neu+'% neutral</span>'
    + '<span class="sent-lbl"><span class="sent-key sent-key-neg"></span>'+neg+'% negative</span></div>';
}
function renderAgentPanel(data) {
  var el = document.getElementById('agentPanel');
  if (!data||!data.length) { el.innerHTML = '<div class="empty-state">No agent data yet</div>'; return; }
  var TEAM_CLR = ['--blue','--pur','--grn','--amb','--pnk','--red'];
  var rows = data.map(function(a, i) {
    var avg = a.avg_handle_minutes>=60 ? (a.avg_handle_minutes/60).toFixed(1)+' hr' : a.avg_handle_minutes.toFixed(0)+' min';
    var dot = 'var(' + TEAM_CLR[i % TEAM_CLR.length] + ')';
    return '<tr><td class="llm-op-cell"><span class="llm-op-dot" style="background:'+dot+'"></span>'+escH(a.agent)+'</td>'
      + '<td class="llm-num">'+a.handled+'</td><td class="llm-num">'+avg+'</td></tr>';
  }).join('');
  el.innerHTML = '<table class="mini-table llm-op-table"><thead><tr><th>Team/Agent</th><th class="llm-num">Handled</th><th class="llm-num">Avg handle time</th></tr></thead><tbody>'+rows+'</tbody></table>';
}

function feedDotColor(evType) {
  var t = (evType||'').toLowerCase();
  if (t.includes('escalat')) return '#dc2626';
  if (t.includes('ticket')) return '#2563eb';
  if (t.includes('resolve')) return '#16a34a';
  if (t.includes('message')||t.includes('inbound')||t.includes('outbound')) return '#7c3aed';
  return '#94a3b8';
}

function renderFeedList(events, prepend) {
  var list = document.getElementById('feedList');
  if (!list) return;
  if (!events || !events.length) {
    if (!prepend) list.innerHTML = '<div class="empty-state">No events yet</div>';
    return;
  }
  if (!prepend) list.innerHTML = '';
  var sorted = events.slice().sort(function(a, b) { return new Date(b.created_at) - new Date(a.created_at); });
  sorted.forEach(function(e) {
    var item = document.createElement('div');
    item.className = 'feed-item';
    var d = e.created_at ? new Date(e.created_at) : null;
    var tm = d ? d.toLocaleDateString([], {month:'short',day:'numeric'}) + ' ' + d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '';
    var meta = [];
    if (e.channel) meta.push('<span>' + escH(e.channel) + '</span>');
    if (e.intent)  meta.push('<span>' + escH(e.intent.replace(/_/g,' ')) + '</span>');
    if (e.customer_id) meta.push('<span>cust:' + escH(e.customer_id.slice(0,8)) + '…</span>');
    item.innerHTML = '<div class="feed-dot" style="background:' + feedDotColor(e.event_type) + '"></div>'
      + '<div class="feed-content"><div class="feed-type">' + escH(e.event_type || 'event') + '</div>'
      + (meta.length ? '<div class="feed-meta">' + meta.join('') + '</div>' : '') + '</div>'
      + '<div class="feed-time">' + tm + '</div>';
    if (prepend) list.insertBefore(item, list.firstChild);
    else list.appendChild(item);
  });
}

function setSseStatus(text, cssText) {
  var el = document.getElementById('sseStatus');
  if (el) { el.textContent = text; el.style.cssText = cssText; }
}

function connectSSE() {
  if (state.sseSource) { state.sseSource.close(); state.sseSource = null; }
  var es = new EventSource('/analytics/stream');
  state.sseSource = es;

  es.onopen = function() {
    setSseStatus('Live', 'background:var(--grn-bg);border:1px solid var(--grn-bd);color:var(--grn-t);font-size:10px;font-weight:500;padding:2px 8px;border-radius:20px');
  };

  es.onmessage = function(ev) {
    // 1. Analytics overview card (always update — data is cheap)
    try { var d = JSON.parse(ev.data); if (d.total_open !== undefined) renderOverview(d); } catch(e) {}

    // 2. Live event feed — use full audit trail
    fetch('/admin/audit-events', { headers: adminHeaders() })
      .then(function(r) { return r.json(); })
      .then(function(evs) { renderFeedList(evs, false); })
      .catch(function() {});

    // 3. Inbox — refresh conversation list + badge on every event
    loadConversations();

    // 4. Analytics charts — full refresh if analytics page is open
    if (activePage === 'analytics') loadAnalytics();
  };

  es.onerror = function() {
    setSseStatus('Reconnecting…', 'background:var(--amb-bg);border:1px solid var(--amb-bd);color:var(--amb-t);font-size:10px;font-weight:500;padding:2px 8px;border-radius:20px');
  };
}

// ── CONNECTORS ───────────────────────────────────────────────────────────────
window.loadConnectors = async function() {
  var grid = document.getElementById('connGrid');
  grid.innerHTML = '';
  var waStatus = 'disconnected', emStatus = 'disconnected', crmStatus = 'disconnected';
  try { var waRes = await api('/admin/whatsapp/status'); waStatus = waRes.connected ? 'connected' : (waRes.mode === 'local_test' ? 'connected' : 'disconnected'); } catch(e){}
  // /admin/email/status has no `configured` field — readiness flag is `gmail_ready`.
  try { var emRes = await api('/admin/email/status'); emStatus = emRes.gmail_ready ? 'connected' : 'disconnected'; } catch(e){}
  try { var crmRes = await api('/admin/crm/status'); crmStatus = crmRes.configured ? 'connected' : 'disconnected'; } catch(e){}
  var inboxRes = null;
  try { inboxRes = await api('/admin/email-inbox/status'); } catch(e){}

  var connectors = [
    { nm:'WhatsApp Business', desc:'Meta Cloud API · inbound webhook + outbound', status: waStatus,
      icon:'background:#22c55e', svg:'<svg viewBox="0 0 24 24" fill="#fff"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413z"/><path d="M20.52 3.449C12.831-3.984.106 1.407.101 11.893c0 2.096.549 4.14 1.595 5.945L.057 24l6.335-1.652c1.746.943 3.71 1.444 5.71 1.447h.006c9.756 0 15.466-8.65 11.466-16.001a11.816 11.816 0 0 0-3.054-4.345z"/></svg>' },
    { nm:'Call', desc:'Voice channel integration', status:'phase2',
      icon:'background:#6366f1', svg:'<svg viewBox="0 0 24 24" fill="#fff"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg>' },
    { nm:'Jira CRM', desc:'Ticket synchronisation', status: crmStatus,
      icon:'background:#0052cc', svg:'<svg viewBox="0 0 24 24" fill="#fff"><path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.218 5.218 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.004-1.005zm5.723-5.756H5.736a5.218 5.218 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.762a1.005 1.005 0 0 0-1.001-1.005z"/></svg>' },
  ];

  connectors.forEach(function(c) {
    var badgeCls = c.status === 'connected' ? 'connected' : c.status === 'error' ? 'error' : c.status === 'phase2' ? 'phase2' : 'disconnected';
    var badgeTxt = c.status === 'connected' ? 'Connected' : c.status === 'error' ? 'Error' : c.status === 'phase2' ? '✦ Phase 2' : 'Disconnected';
    var card = document.createElement('div');
    card.className = 'conn-card';
    card.innerHTML = '<div class="conn-hdr"><div class="conn-icon" style="' + c.icon + '">' + c.svg + '</div><div><div class="conn-nm">'+escH(c.nm)+'</div><div class="conn-desc">'+escH(c.desc)+'</div></div></div>'
      + '<div class="conn-status"><span class="conn-badge '+badgeCls+'">'+badgeTxt+'</span></div>';
    grid.appendChild(card);
  });

  // Email — ONE card for the channel, showing both pipes: inbound (IMAP poller)
  // and outbound (SMTP sender) are independent connections that can fail
  // separately, so each gets its own status row. Live stats + Poll Now for the
  // inbound side. Card badge = Connected only when BOTH pipes are up.
  var inboxCard = document.createElement('div');
  inboxCard.className = 'conn-card';
  inboxCard.id = 'connInboxCard';
  var inboxConfigured = inboxRes && inboxRes.configured;
  var emailBadgeCls = (inboxConfigured && emStatus === 'connected') ? 'connected' : 'disconnected';
  var emailBadgeTxt = (inboxConfigured && emStatus === 'connected') ? 'Connected'
    : (inboxConfigured || emStatus === 'connected') ? 'Partial' : 'Disconnected';
  var lastPollTxt = (inboxRes && inboxRes.last_poll_ts)
    ? new Date(inboxRes.last_poll_ts * 1000).toLocaleTimeString() : 'Never';
  var processedTxt = inboxRes ? String(inboxRes.emails_processed) : '0';
  var intervalTxt = inboxRes ? inboxRes.poll_interval_seconds + 's' : '30s';
  var mailboxTxt = (inboxRes && inboxRes.configured) ? escH(inboxRes.mailbox || 'INBOX') : '—';
  var errorHtml = (inboxRes && inboxRes.last_error)
    ? '<div style="font-size:10px;color:#dc2626;margin-top:6px;word-break:break-all">'+escH(inboxRes.last_error)+'</div>' : '';
  var pipeOk  = '<span style="color:var(--grn-t);font-weight:600">Active</span>';
  var pipeBad = '<span style="color:var(--red-t);font-weight:600">Down</span>';
  inboxCard.innerHTML =
    '<div class="conn-hdr">'
    + '<div class="conn-icon" style="background:#db4437"><svg viewBox="0 0 24 24" fill="#fff"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg></div>'
    + '<div><div class="conn-nm">Email</div><div class="conn-desc">Gmail · inbound IMAP auto-poll + outbound SMTP delivery</div></div>'
    + '</div>'
    + '<div class="conn-status"><span class="conn-badge ' + emailBadgeCls + '">' + emailBadgeTxt + '</span></div>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;font-size:11px;color:var(--t2);margin-top:10px">'
    + '<span style="color:var(--t3)">Inbound (IMAP)</span><span>' + (inboxConfigured ? pipeOk : pipeBad) + '</span>'
    + '<span style="color:var(--t3)">Outbound (SMTP)</span><span>' + (emStatus === 'connected' ? pipeOk : pipeBad) + '</span>'
    + '</div>';
  // Insert after WhatsApp so the card order is: WhatsApp · Email · Call · Jira.
  grid.insertBefore(inboxCard, grid.children[1] || null);

  // Web Chat — the customer portal's live "Chat with support" box. Served by
  // this same app (synchronous inbound + reply via the portal history poll), so
  // it is always Connected. Inserted at index 2 so order is:
  // WhatsApp · Email · Web Chat · Call · Jira.
  var webCard = document.createElement('div');
  webCard.className = 'conn-card';
  webCard.innerHTML =
    '<div class="conn-hdr">'
    + '<div class="conn-icon" style="background:#2563eb"><svg viewBox="0 0 24 24" fill="#fff"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/></svg></div>'
    + '<div><div class="conn-nm">Web Chat</div><div class="conn-desc">Customer portal · in-app chat (synchronous inbound + reply)</div></div>'
    + '</div>'
    + '<div class="conn-status"><span class="conn-badge connected">Connected</span></div>';
  grid.insertBefore(webCard, grid.children[2] || null);
};

window.triggerEmailInboxPoll = async function() {
  var btn = document.getElementById('inboxPollBtn');
  var statusEl = document.getElementById('inboxPollStatus');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Polling…';
  statusEl.style.display = 'none';
  try {
    var res = await api('/admin/email-inbox/poll', { method: 'POST' });
    var n = res.emails_processed_this_poll || 0;
    statusEl.textContent = n === 0 ? 'No new emails.' : '✓ Processed ' + n + ' new email' + (n === 1 ? '' : 's') + '.';
    statusEl.className = 'sim-status success';
    statusEl.style.display = 'block';
    var lpEl = document.getElementById('inboxLastPoll');
    if (lpEl && res.last_poll_ts) lpEl.textContent = new Date(res.last_poll_ts * 1000).toLocaleTimeString();
    var pcEl = document.getElementById('inboxProcessed');
    if (pcEl) pcEl.textContent = String(res.emails_processed || 0);
    if (n > 0) loadConversations();
  } catch(e) {
    statusEl.textContent = 'Error: ' + e.message;
    statusEl.className = 'sim-status error';
    statusEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Poll now';
  }
};

// ── SETTINGS / SIMULATOR ────────────────────────────────────────────────────
window.selectSimChannel = function(ch) {
  document.getElementById('simFormWa').style.display = ch === 'wa' ? 'block' : 'none';
  document.getElementById('simFormEm').style.display = ch === 'em' ? 'block' : 'none';
  document.getElementById('simTabWa').classList.toggle('on', ch === 'wa');
  document.getElementById('simTabEm').classList.toggle('on', ch === 'em');
};

function setSimStatus(msg, st) {
  var el = document.getElementById('simStatus');
  el.textContent = msg;
  el.className = 'sim-status ' + (st||'');
  el.style.display = msg ? 'block' : 'none';
}

window.runWhatsAppSim = async function() {
  var btn = document.getElementById('simWaBtn');
  var sig = document.getElementById('testSig').value.trim();
  sessionStorage.setItem('cx-test-signature', sig);
  btn.disabled = true; btn.textContent = 'Running…';
  setSimStatus('Processing message…', '');
  var result = document.getElementById('simResult');
  result.style.display = 'none';
  try {
    var res = await fetch('/test/whatsapp/inbound-simulate', {
      method: 'POST',
      headers: Object.assign({ 'content-type': 'application/json', 'x-test-whatsapp-signature': sig }, adminHeaders()),
      body: JSON.stringify({ from: document.getElementById('simPhone').value.trim(), text: document.getElementById('simMsg').value.trim(), outbound_provider: document.getElementById('simDelivery').value })
    });
    var data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    result.textContent = JSON.stringify(data, null, 2);
    result.style.display = 'block';
    setSimStatus('✓ WhatsApp simulation complete · Intent: ' + (data.intent||'?'), 'success');
    loadConversations();
  } catch(e) {
    setSimStatus('Error: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = 'Run simulation';
  }
};

window.runEmailSim = async function() {
  var btn = document.getElementById('simEmBtn');
  var secret = document.getElementById('emailSecret').value.trim();
  sessionStorage.setItem('cx-email-secret', secret);
  btn.disabled = true; btn.textContent = 'Running…';
  setSimStatusEm('Processing email…', '');
  var result = document.getElementById('simResultEm');
  result.style.display = 'none';
  try {
    var res = await fetch('/integrations/email/webhook', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-email-webhook-secret': secret },
      body: JSON.stringify({ from_email: document.getElementById('simEmail').value.trim(), subject: document.getElementById('simEmailSubject').value.trim(), body: document.getElementById('simEmailMsg').value.trim() })
    });
    var data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    result.textContent = JSON.stringify(data, null, 2);
    result.style.display = 'block';
    setSimStatusEm('✓ Email simulation complete · Intent: ' + (data.intent||'?'), 'success');
    loadConversations();
  } catch(e) {
    setSimStatusEm('Error: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = 'Run simulation';
  }
};

function setSimStatusEm(msg, st) {
  var el = document.getElementById('simStatusEm');
  el.textContent = msg;
  el.className = 'sim-status' + (st ? ' ' + st : '');
  el.style.display = msg ? 'block' : 'none';
}

window.loadAudit = async function() {
  var list = document.getElementById('auditList');
  if (!list) return;
  try {
    var events = await api('/admin/audit-events');
    if (!events.length) { list.innerHTML = '<div style="text-align:center;color:var(--t3);font-size:12px;padding:16px 0">No events yet</div>'; return; }
    list.innerHTML = events.slice().reverse().slice(0,50).map(function(e) {
      return '<div class="audit-item"><div class="audit-item-type">'+escH(e.event_type)+'</div>'
        + '<div class="audit-item-meta">'+(e.channel?escH(e.channel)+' · ':'')+escH(e.created_at||'')+(e.intent?' · '+escH(e.intent):'')+'</div></div>';
    }).join('');
  } catch(e) {
    list.innerHTML = '<div style="color:var(--red-t);font-size:12px;padding:8px">'+escH(e.message)+'</div>';
  }
};

// ── TICKETS (shared cache) ───────────────────────────────────────────────────
// The standalone Tickets page was removed (Fix 49) — ticket lifecycle management
// lives in the CRM (Jira sync). This cache remains: it is filled by
// loadConversations() and consumed by the inbox status logic, the spine/lineage
// views, and the right-panel Open Tickets card.
// Three buckets, because a ticket now has three states an agent can encounter.
// LOGGED is a grouping id: the system opened a thread for a question it answered on its
// own, and no human is needed. It is NOT work, so it must stay out of queues, counts and
// anything shown as "open" — but it still EXISTS, so it must not vanish from lookups
// either. The old shape was { open, closed }, and every caller did concat(open, closed) —
// which silently dropped any third status. allTickets() exists so no caller can forget one.
var _allTickets = { logged: [], open: [], closed: [] };

// Every ticket, whatever its status. Use for lookups by id and for rendering history.
function allTickets() {
  return [].concat(_allTickets.logged, _allTickets.open, _allTickets.closed);
}

// A human is on it. Use for queues, badges, counts and anything labelled "open".
function isServiceable(t) {
  return !!t && (t.status === 'open' || t.status === 'in_progress');
}

// Not finished — includes logging threads. Use for continuity/grouping questions.
function isActive(t) {
  return !!t && t.status !== 'closed';
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  var d = new Date(iso);
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
    + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Exposed on window so inline onclick= (Tickets panel rows) can reach it — the file is
// wrapped in an IIFE, so a plain function declaration is NOT in global scope.
window.goToConversation = function(conversationId, ticketId) {
  if (!conversationId) return;
  state.highlightTicketId = ticketId || null;
  // Detailed view shows one request; focus it on the jumped-to ticket so the
  // Tickets-panel jump lands on that request (not just the latest one).
  if (ticketId) {
    state.convView[conversationId] = 'detailed';
    state.detailFocus[conversationId] = ticketId;
  }
  switchPage('inbox');
  selectConv(conversationId);
};

// ── SETTINGS (admin account) ──────────────────────────────────────────────────
function userHeaders() {
  return { 'Authorization': 'Bearer ' + userToken };
}

async function userApi(path, opts) {
  opts = opts || {};
  var headers = Object.assign({}, userHeaders(), opts.headers || {});
  if (opts.body) headers['content-type'] = 'application/json';
  var response = await fetch(path, Object.assign({}, opts, { headers: headers }));
  var data = await response.json().catch(function() { return {}; });
  if (!response.ok) throw new Error(data.detail || (response.status + ' ' + response.statusText));
  return data;
}

function setUserStatus(message, type) {
  var el = document.getElementById('userSubmitStatus');
  el.textContent = message;
  el.className = 'sim-status' + (type ? ' ' + type : '');
  el.style.display = message ? 'block' : 'none';
}

function renderPortalChatTurns(turns) {
  var el = document.getElementById('portalChatMessages');
  if (!turns.length) {
    el.innerHTML = '<div class="user-empty">No messages yet — say hello!</div>';
    return;
  }
  el.innerHTML = turns.map(function(t) {
    // In the customer portal the CUSTOMER'S own message (stored as 'inbound')
    // belongs on the right (blue "you" bubble), and the AI reply (stored as
    // 'outbound') on the left. This is inverted vs. the admin inbox.
    var side = t.direction === 'inbound' ? 'outbound' : 'inbound';
    return '<div class="portal-chat-msg ' + side + '">' + escH(t.text || '') + '</div>';
  }).join('');
  el.scrollTop = el.scrollHeight;
}

window.loadPortalChat = async function() {
  try {
    var data = await userApi('/user/chat/messages');
    renderPortalChatTurns(data.turns || []);
  } catch(e) {
    document.getElementById('portalChatMessages').innerHTML =
      '<div class="user-empty" style="color:var(--red-t)">' + escH(e.message) + '</div>';
  }
};

document.getElementById('portalChatForm').addEventListener('submit', async function(e) {
  e.preventDefault();
  var input = document.getElementById('portalChatInput');
  var text = input.value.trim();
  if (!text) return;
  var btn = document.getElementById('portalChatSendBtn');
  var messagesEl = document.getElementById('portalChatMessages');
  var emptyState = messagesEl.querySelector('.user-empty');
  if (emptyState) messagesEl.innerHTML = '';
  var bubble = document.createElement('div');
  bubble.className = 'portal-chat-msg outbound';
  bubble.textContent = text;
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  input.value = '';
  input.disabled = true;
  btn.disabled = true;
  try {
    var data = await userApi('/user/chat/messages', {
      method: 'POST',
      body: JSON.stringify({ text: text })
    });
    var reply = document.createElement('div');
    reply.className = 'portal-chat-msg inbound';
    reply.textContent = data.message || '...';
    messagesEl.appendChild(reply);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    if (data.outbound_status === 'failed') {
      setUserStatus('Message processed, but delivery failed: ' + (data.outbound_error || 'provider rejected the message'), 'error');
    } else {
      setUserStatus('', '');
    }
    await loadUserTickets();
  } catch(e) {
    setUserStatus(e.message, 'error');
  } finally {
    input.disabled = false;
    btn.disabled = false;
    input.focus();
  }
});

window.loadUserTickets = async function() {
  var list = document.getElementById('userTicketList');
  var refresh = document.getElementById('userRefreshBtn');
  refresh.disabled = true;
  refresh.textContent = 'Refreshing...';
  try {
    var tickets = await userApi('/user/tickets');
    document.getElementById('userTicketCount').textContent =
      tickets.length + ' ticket' + (tickets.length === 1 ? '' : 's');
    if (!tickets.length) {
      list.innerHTML = '<div class="user-empty">No requests submitted yet.</div>';
      return;
    }
    list.innerHTML = '';
    // The CUSTOMER's own view. A logging id is internal and is never shown to them
    // (redesign decision 1), so it belongs in neither group.
    var openTickets = tickets.filter(isServiceable);
    var closedTickets = tickets.filter(function(t) { return t.status === 'closed'; });

    function renderGroup(heading, group) {
      if (!group.length) return;
      var hdr = document.createElement('div');
      hdr.className = 'user-ticket-group';
      hdr.textContent = heading + ' (' + group.length + ')';
      list.appendChild(hdr);
      group.forEach(function(ticket) {
        var item = document.createElement('div');
        item.className = 'user-ticket-item';
        var row = document.createElement('div');
        row.className = 'user-ticket-row';
        var cm = chMeta(ticket.channel);
        var chStyle = 'background:' + cm.bg + ';border-color:' + cm.bd + ';color:' + cm.clr;
        var st = (ticket.status || 'active').toLowerCase();
        var isResolvedSt = st === 'closed';
        var stCls = isResolvedSt ? 'user-status-pill user-status-pill--resolved' : 'user-status-pill';
        row.innerHTML =
          '<div class="user-ticket-main"><strong>' + escH(ticket.ticket_id || ticket.conversation_id) + '</strong>'
          + '<span>' + escH((ticket.message || '').replace('Customer portal request\\n\\n', '')) + '</span>'
          + '<span class="user-ticket-date">Created: ' + escH(fmtDateTime(ticket.created_at)) + '</span></div>'
          + '<div class="user-ticket-pills">'
          + '<span class="user-ch-pill" style="' + chStyle + '">' + escH(cm.label) + '</span>'
          + '<span class="' + stCls + '">' + escH(statusLabel(ticket.status)) + '</span>'
          + '</div>';
        item.appendChild(row);
        row.addEventListener('click', function() { openTicketModal(ticket); });
        list.appendChild(item);
      });
    }
    renderGroup('Open', openTickets);
    renderGroup('Closed', closedTickets);
  } catch(e) {
    list.innerHTML = '<div class="user-empty" style="color:var(--red-t)">' + escH(e.message) + '</div>';
  } finally {
    refresh.disabled = false;
    refresh.textContent = 'Refresh';
  }
};

// ── Knowledge graph (customer neighbourhood) ────────────────────────────────
// Radial hub-and-spoke over the /graph-view payload. Layout is DETERMINISTIC —
// positions derive from each node's index in a stable type order, never from a
// physics sim — because the inbox re-polls every ~3s and a jittering graph is
// unreadable. Health (not node type) drives colour, so "needs attention" reads
// at a glance.
// Transaction and Message were missing, so those nodes sorted after every known type
// and their ring position shifted as unrelated nodes appeared. Message sits last, right
// after Ticket, so a case's messages render beside the ticket they belong to.
var KG_TYPE_ORDER = ['Account', 'CreditCard', 'FixedDeposit', 'Loan', 'Policy', 'Claim',
                     'Transaction', 'Ticket', 'Message'];

window.closeGraphModal = function() {
  document.getElementById('graphModal').classList.add('hidden');
};

function kgEsc(s) { return escH(String(s == null ? '' : s)); }

// ── Case summary — what an agent needs before reading the thread ────────────
// Fetched separately from renderRight so a slow or unavailable LLM never delays the
// rest of the panel. The endpoint caches against the newest turn, so re-opening an
// unchanged conversation costs nothing; only Refresh forces a regeneration.
var _csumFor = null;

async function loadCaseSummary(conversationId, force) {
  if (!conversationId) return;
  if (!force && _csumFor === conversationId) return;   // already loaded for this conversation
  _csumFor = conversationId;
  var bodyEl = document.getElementById('csum-body');
  if (!bodyEl) return;
  if (force) bodyEl.innerHTML = '<span class="csum-muted">Summarising…</span>';
  try {
    var p = await api('/admin/conversations/' + encodeURIComponent(conversationId)
      + '/case-summary' + (force ? '?refresh=true' : ''));
    // The panel may have moved to another conversation while this was in flight.
    if (_csumFor !== conversationId) return;
    bodyEl = document.getElementById('csum-body');
    if (!bodyEl) return;
    if (!p.summary) {
      // Say why there is nothing rather than showing an empty card.
      bodyEl.innerHTML = '<span class="csum-muted">'
        + (p.status === 'empty' ? 'No messages yet.' : 'Summary unavailable right now.')
        + '</span>';
      return;
    }
    // The card is the situation, nothing else. An "Also outstanding" list used to sit
    // here for work that was NOT a ticket - but this system tickets anything needing
    // follow-up, so the category was empty by construction and the model filled it by
    // rewording the situation instead of returning nothing. Every value it ever
    // produced was an echo or empty, through three prompt rules written to stop it.
    // Open work is in the Open Tickets card directly below, with status and Resolve.
    bodyEl.innerHTML =
      (p.summary.situation ? '<div class="csum-sit">' + escH(p.summary.situation) + '</div>' : '');
  } catch (e) {
    if (_csumFor !== conversationId) return;
    var el = document.getElementById('csum-body');
    if (el) el.innerHTML = '<span class="csum-muted">Summary unavailable right now.</span>';
  }
}

document.addEventListener('click', function(e) {
  var btn = e.target && e.target.closest && e.target.closest('#csum-refresh');
  if (btn && state.convDetail) loadCaseSummary(state.convDetail.conversation_id, true);
});

// Open Tickets fold. A class toggle on the card — the rows stay in the DOM, so the
// Resolve buttons and their handlers survive collapsing.
document.addEventListener('click', function(e) {
  var btn = e.target && e.target.closest && e.target.closest('#tkt-toggle');
  if (!btn) return;
  var card = btn.closest('.tkt-card');
  if (!card) return;
  state.tktOpen = !card.classList.contains('on');
  card.classList.toggle('on', state.tktOpen);
});

// ── Customer Context — the record, grouped into tabs by one LLM call ─────────
// ONE call per customer. Every panel is rendered into the page up front and shown by
// a class toggle, so switching tabs never touches the API.
//
// Class names are deliberately cctx-*: the conversation view already owns .viewtab,
// and a handler selecting a shared tab class would clear both sets when either is
// clicked.
var _cctxFor = null;
// Last payload, kept client-side. renderRight rebuilds the panel on every poll, so
// without this the card would either blank out or refetch several times a minute.
var _cctxCache = null;

// Tab order is the reading order for an agent picking up a conversation: what is
// WRONG first, reference last. Empty categories are dropped rather than greyed out —
// fewer tabs means wider tabs and no wrapping in a ~260px panel.
var CCTX_TABS = [
  ['risk',     'Risk'],
  ['holdings', 'Holdings'],
  ['activity', 'Activity'],
  ['claims',   'Claims'],
  ['profile',  'Profile']
];

function cctxRenderItems(items) {
  return items.map(function(it) {
    return '<div class="cctx-item">'
      + '<div class="cctx-row">'
      + '<span class="cctx-lbl">' + escH(it.label) + '</span>'
      + '<span class="cctx-val">' + escH(it.value) + '</span>'
      + '</div>'
      + (it.sub ? '<div class="cctx-sub">' + escH(it.sub) + '</div>' : '')
      + '</div>';
  }).join('');
}

function cctxRender(payload) {
  var tabsEl = document.getElementById('cctx-tabs');
  var bodyEl = document.getElementById('cctx-body');
  if (!tabsEl || !bodyEl) return;

  if (payload.status === 'raw' && payload.raw) {
    // Parsing failed. Show what the model actually said rather than nothing — losing
    // content to a failed guess is worse than showing it unformatted.
    tabsEl.innerHTML = '';
    bodyEl.innerHTML = '<div class="cctx-muted">Could not group these records. Raw response:</div>'
      + '<pre class="cctx-raw">' + escH(payload.raw) + '</pre>';
    return;
  }

  var cats = payload.categories || {};
  var present = CCTX_TABS.filter(function(t) {
    return (cats[t[0]] || []).length > 0;
  });

  if (!present.length) {
    tabsEl.innerHTML = '';
    bodyEl.innerHTML = '<span class="cctx-muted">'
      + (payload.status === 'unavailable' ? 'Grouping unavailable right now.'
         : 'No records on file for this customer.')
      + '</span>';
    return;
  }

  tabsEl.innerHTML = present.map(function(t, i) {
    var key = t[0], count = (cats[key] || []).length;
    // Risk carries its count so the agent sees there is a problem before clicking.
    var badge = key === 'risk'
      ? '<span class="cctx-count">' + count + '</span>' : '';
    return '<button type="button" class="cctx-tab' + (i === 0 ? ' on' : '')
      + '" data-cctx="' + escH(key) + '">' + escH(t[1]) + badge + '</button>';
  }).join('');

  bodyEl.innerHTML = present.map(function(t, i) {
    return '<div class="cctx-panel' + (i === 0 ? ' on' : '') + '" data-cctx-panel="'
      + escH(t[0]) + '">' + cctxRenderItems(cats[t[0]] || []) + '</div>';
  }).join('');
}

async function loadCustomerContext(customerId, force) {
  if (!customerId) return;
  var bodyEl = document.getElementById('cctx-body');
  if (!bodyEl) return;
  // Same customer and we already have the payload: repaint the rebuilt card from
  // memory. This is the common case — the queue poll re-renders the panel regularly.
  if (!force && _cctxFor === customerId && _cctxCache) {
    cctxRender(_cctxCache);
    return;
  }
  _cctxFor = customerId;
  if (force) _cctxCache = null;
  bodyEl.innerHTML = '<span class="cctx-muted">Grouping records…</span>';
  try {
    var p = await api('/admin/customers/' + encodeURIComponent(customerId)
      + '/context' + (force ? '?refresh=true' : ''));
    // The panel may have moved to another customer while this was in flight.
    if (_cctxFor !== customerId) return;
    _cctxCache = p;
    cctxRender(p);
  } catch (e) {
    if (_cctxFor !== customerId) return;
    var el = document.getElementById('cctx-body');
    var tabs = document.getElementById('cctx-tabs');
    if (tabs) tabs.innerHTML = '';
    if (el) el.innerHTML = '<span class="cctx-muted">Context unavailable right now.</span>';
  }
}

// Tab switching is a pure class toggle — scoped to .cctx-* so it can never disturb
// the conversation view's .viewtab set.
document.addEventListener('click', function(e) {
  var tab = e.target && e.target.closest && e.target.closest('.cctx-tab');
  if (!tab) return;
  var key = tab.getAttribute('data-cctx');
  var card = tab.closest('.cctx-card');
  if (!card) return;
  card.querySelectorAll('.cctx-tab').forEach(function(t) {
    t.classList.toggle('on', t === tab);
  });
  card.querySelectorAll('.cctx-panel').forEach(function(p) {
    p.classList.toggle('on', p.getAttribute('data-cctx-panel') === key);
  });
});

document.addEventListener('click', function(e) {
  var btn = e.target && e.target.closest && e.target.closest('#cctx-refresh');
  if (btn && state.convDetail) {
    var meta = state.convs.find(function(c) {
      return c.conversation_id === state.convDetail.conversation_id;
    }) || state.convDetail;
    if (meta.customer_id) loadCustomerContext(meta.customer_id, true);
  }
});

// ── "Why this answer" — per-reply provenance ────────────────────────────────
// Every reply comes from ONE of two places: the customer's own records in the graph
// (transactional intents) or passages from the knowledge base (everything else). Which
// one is a per-message fact, so this shows the real source rather than implying every
// answer came from the graph — most don't.
window.closeWhyModal = function() {
  document.getElementById('whyModal').classList.add('hidden');
};

async function openWhyModal(turnId) {
  var modal = document.getElementById('whyModal');
  var body = document.getElementById('whyModalBody');
  document.getElementById('whyModalSub').textContent = '';
  body.innerHTML = '<div class="why-loading">Loading…</div>';
  modal.classList.remove('hidden');
  try {
    var p = await api('/admin/conversations/turns/' + encodeURIComponent(turnId) + '/provenance');
    document.getElementById('whyModalSub').textContent =
      [p.intent ? 'intent · ' + p.intent : '', p.retrieval_backend ? 'retrieval · ' + p.retrieval_backend : '']
        .filter(Boolean).join(' · ');
    // Continuity first: WHERE the data came from (graph vs KB) is a per-message fact, but
    // whether this reply CONTINUES an existing case is the thing an agent needs first —
    // and it renders above the source, not instead of it.
    var caseHtml = renderWhyCase(p.case);
    if (p.source === 'graph') {
      body.innerHTML = caseHtml + await renderWhyGraph(p);
    } else if (p.source === 'ticket') {
      body.innerHTML = caseHtml + renderWhyTicket(p);
    } else if (p.source === 'kb') {
      body.innerHTML = caseHtml + renderWhyKb(p);
    } else if (p.source === 'holding') {
      body.innerHTML = '<div class="why-none">Automatic holding message, not an answer.<br>'
        + 'The real reply is a draft awaiting agent review.</div>';
    } else {
      body.innerHTML = '<div class="why-none">No lookup ran for this message.<br>'
        + 'A holding message, an offer, or a reply that needed none.'
        + (p.account_context ? '<br>Account records were still available to the model.' : '')
        + '</div>';
    }
  } catch (e) {
    body.innerHTML = '<div class="why-none">Could not load provenance: ' + escH(e.message) + '</div>';
  }
}

// Continuity: the case this reply belongs to, and every customer message on it.
// Absent (returns '') when the reply has no ticket or the ticket has a single message —
// one message is not continuity, and showing a one-item "thread" would overstate it.
function renderWhyCase(c) {
  if (!c || !(c.messages || []).length) return '';
  var chan = (c.channels || []).length > 1
    ? ' · ' + c.channels.map(function(x) { return CH[x] ? CH[x].label : x; }).join(' + ')
    : '';
  var rows = c.messages.map(function(m, i) {
    var when = m.created_at ? new Date(m.created_at).toLocaleString([], {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
    }) : '';
    return '<li class="why-case-msg' + (m.is_this_turn ? ' is-this' : '') + '">'
      + '<span class="why-case-n">' + (i + 1) + '</span>'
      + '<span class="why-case-txt">' + escH(m.text || '') + '</span>'
      + '<span class="why-case-meta">' + escH((m.channel || '') + (when ? ' · ' + when : '')) + '</span>'
      + (m.is_this_turn ? '<span class="why-case-here">this reply</span>' : '')
      + '</li>';
  }).join('');
  return '<div class="why-banner why-banner--case">'
    + '<b>Part of an ongoing case</b>'
    + '<ul class="why-pts">'
    + '<li>Ticket <code>' + escH(c.ticket_id || '') + '</code>'
    + (c.scope ? ' · ' + escH(c.scope) : '') + ' · ' + escH(statusLabel(c.status || ''))
    + escH(chan) + '</li>'
    + '<li>' + c.messages.length + ' messages on this case — the reply below was written with them in view.</li>'
    + '</ul>'
    + '<ol class="why-case-list">' + rows + '</ol>'
    + '</div>';
}

// Graph-backed: reuse the customer's own graph, dimming everything the answer didn't read.
async function renderWhyGraph(p) {
  var head = '<div class="why-banner why-banner--graph"><b>Read from this customer\'s records</b>'
    + '<ul class="why-pts">'
    + '<li>Highlighted nodes = what a <code>' + escH(p.intent || '') + '</code> question looks up.</li>'
    + '<li>Every record of those types is read.</li>'
    + '</ul></div>';
  var custId = (state.convDetail || {}).customer_id
    || ((state.convs || []).find(function(c) { return c.conversation_id === state.selectedConvId; }) || {}).customer_id;
  if (!custId) return head;
  var gv = await api('/admin/customers/' + encodeURIComponent(custId) + '/graph-view');
  if (!gv || !gv.resolved) return head;
  // This picture answers ONE question: which of the customer's records did retrieval read
  // for this reply? Tickets take no part in that step — neo4j_answer has branches for
  // accounts, cards, loans, policies, claims and transactions, and none for tickets. Drawn
  // here they can only mislead: dimmed they imply "considered and not used", highlighted
  // they would be false. The case a reply belongs to IS shown — by the continuity banner
  // above (renderWhyCase), which is the surface that claim actually belongs to.
  gv.nodes = gv.nodes.filter(function(n) { return n.type !== 'Ticket'; });
  var kept = {};
  gv.nodes.forEach(function(n) { kept[n.id] = true; });
  gv.edges = gv.edges.filter(function(e) { return kept[e.target]; });
  var keep = {};
  (p.graph_types || []).forEach(function(t) { keep[t] = true; });
  gv.nodes.forEach(function(n) { n.dim = !(n.health === 'hub' || keep[n.type]); });
  gv.edges.forEach(function(e) {
    var t = gv.nodes.filter(function(n) { return n.id === e.target; })[0];
    e.dim = !t || t.dim;
  });
  return head + renderGraphSvg(gv);
}

// Ticket-backed: the customer's own support record, read directly from SQLite.
// Deliberately NOT the KB block: nothing was retrieved by similarity here, so that block's
// "closest matches / always returns a nearest match" caveats would describe a mechanism that
// never ran. And deliberately not the graph block either — this data is not in Neo4j, and
// drawing graph nodes for it would over-claim.
function renderWhyTicket(p) {
  var cites = p.citations || [];
  var acct = p.account_context
    ? '<li>Account records were also in the model\'s context.</li>' : '';
  var head = '<div class="why-banner"><b>Read from your support record</b>'
    + '<ul class="why-pts">'
    + '<li>The customer\'s own ticket was read directly — an exact record, not a search result.</li>'
    + acct
    + '</ul></div>';
  return head + cites.map(function(c, i) {
    return '<div class="why-chunk">'
      + '<div class="why-chunk-h"><span>' + escH(c.source || 'source ' + (i + 1)) + '</span></div>'
      + '<div class="why-chunk-t">' + escH(c.text || '') + '</div></div>';
  }).join('');
}

// KB-backed: the passages retrieved, with their retrieval confidence.
function renderWhyKb(p) {
  var cites = p.citations || [];
  // Deliberately reports ONLY what retrieval did. An earlier version said "no account
  // records were read", which was false whenever graph_context fed the model anyway.
  var acct = p.account_context
    ? '<li>Account records were also in the model\'s context.</li>' : '';
  if (!cites.length) {
    return '<div class="why-banner"><b>Nothing retrieved for this reply</b>'
      + '<ul class="why-pts"><li>Answered without a knowledge-base lookup.</li>'
      + acct + '</ul></div>';
  }
  // The caveat is real — retrieval returns its nearest neighbour even when nothing relevant
  // exists, and measured on this data wrong citations (0.62-0.63) and right ones (0.63-0.67)
  // overlap, so a high score is not proof. But nobody reads a five-line paragraph in a modal,
  // so it goes in as scannable points.
  var head = '<div class="why-banner"><b>Retrieved from the knowledge base</b>'
    + '<ul class="why-pts">'
    + '<li>Closest matches found — not proof the answer used them.</li>'
    // The mechanism, kept as its own point: it is what explains a confident-looking score
    // on an off-topic passage, so folding it into the line above loses the useful half.
    + '<li>Always returns a nearest match, even when nothing relevant exists — the model may '
    + 'have answered from general knowledge.</li>'
    + acct
    + '</ul></div>';
  return head + cites.map(function(c, i) {
    return '<div class="why-chunk">'
      + '<div class="why-chunk-h"><span>' + escH(c.source || 'source ' + (i + 1)) + '</span>'
      + '<span class="why-score">retrieval confidence ' + (c.score == null ? '—' : Number(c.score).toFixed(2)) + '</span></div>'
      + '<div class="why-chunk-t">' + escH(c.text || '') + '</div></div>';
  }).join('');
}

function openGraphModal(gv) {
  var modal = document.getElementById('graphModal');
  var hub = (gv.nodes || []).filter(function(n) { return n.health === 'hub'; })[0] || {};
  document.getElementById('graphModalTitle').textContent = (hub.label || 'Customer') + ' · knowledge graph';
  document.getElementById('graphModalSub').textContent =
    [gv.graph_customer_id, hub.sub].filter(Boolean).join(' · ');
  var counts = gv.counts || {};
  var summary = Object.keys(counts).filter(function(k) { return k !== 'Customer'; })
    .map(function(k) { return counts[k] + ' ' + k; }).join(' · ');
  document.getElementById('graphModalCounts').textContent =
    (gv.nodes || []).length + ' nodes · ' + (gv.edges || []).length + ' relationships'
    + (summary ? '  —  ' + summary : '');
  document.getElementById('graphModalBody').innerHTML = renderGraphSvg(gv);
  modal.classList.remove('hidden');
}

function renderGraphSvg(gv) {
  var nodes = gv.nodes || [], edges = gv.edges || [];
  var hub = nodes.filter(function(n) { return n.health === 'hub'; })[0];
  if (!hub) return '<div class="kg-empty">No graph data for this customer.</div>';

  // Ring members in a stable order so the same customer always lays out the same.
  var ring = nodes.filter(function(n) { return n !== hub; }).slice().sort(function(a, b) {
    var ai = KG_TYPE_ORDER.indexOf(a.type), bi = KG_TYPE_ORDER.indexOf(b.type);
    if (ai !== bi) return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
    return String(a.id).localeCompare(String(b.id));
  });

  // Box size tracks the type scale in style.css (.kg-type/.kg-name/.kg-meta). Shrinking
  // the text shrinks the boxes, which shrinks the arc budget below — so smaller type
  // also pulls the ring in and shortens the edges.
  var NW = 156, NH = 42, HW = 172, HH = 50;
  var n = ring.length;
  // Ellipse sized so NEIGHBOURING boxes clear each other. Two separate constraints:
  //  - rx from the arc budget (circumference must fit n boxes side by side);
  //  - ry from the vertical pitch of the nodes that stack down each side — those are
  //    the ones that collide, and a circumference-derived ry flattens the ellipse
  //    until they do. Sizing linearly by node count (the first attempt) inflated the
  //    ring instead; sizing ry by circumference squashed it. This bounds both.
  // Gaps of 22/24 are the tightest values that stay collision-free for n=5..24
  // (swept exhaustively); anything smaller reintroduces overlaps on some ring sizes.
  var rx = Math.max(HW / 2 + NW / 2 + 26, ((NW + 22) * n) / (2 * Math.PI));
  // Nodes per side ≈ n/2; each needs NH + gap of vertical room across the diameter.
  var perSide = Math.max(1, Math.ceil((n - 2) / 2));
  var ry = Math.max(HH / 2 + NH / 2 + 34, ((NH + 24) * perSide) / 2 + NH / 2);
  var cx = rx + NW / 2 + 12, cy = ry + NH / 2 + 12;
  var W = cx * 2, H = cy * 2;

  var pos = {};
  pos[hub.id] = { x: cx, y: cy };
  ring.forEach(function(node, i) {
    // Start at the top and go clockwise; the half-step offset stops the first and
    // last node overlapping when the count is even.
    var a = -Math.PI / 2 + (2 * Math.PI * i) / n + (n % 2 === 0 ? Math.PI / n : 0);
    pos[node.id] = { x: cx + rx * Math.cos(a), y: cy + ry * Math.sin(a) };
  });

  // Intrinsic width/height (not just a viewBox) so the CSS can bound it by height and
  // let the width follow — without them the SVG has no natural size to scale down from.
  var out = '<svg class="kg-svg" width="' + Math.round(W) + '" height="' + Math.round(H) + '" '
    + 'viewBox="0 0 ' + Math.round(W) + ' ' + Math.round(H) + '" '
    + 'preserveAspectRatio="xMidYMid meet" '
    + 'role="img" aria-label="Knowledge graph for ' + kgEsc(hub.label) + '">';

  // Edges first so node boxes paint over the lines.
  edges.forEach(function(e) {
    var s = pos[e.source], t = pos[e.target];
    if (!s || !t) return;
    out += '<line class="kg-edge' + (e.dim ? ' kg-dim' : '') + '" x1="' + s.x.toFixed(1) + '" y1="' + s.y.toFixed(1)
        + '" x2="' + t.x.toFixed(1) + '" y2="' + t.y.toFixed(1) + '"/>';
    var mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2;
    out += '<text class="kg-elabel" x="' + mx.toFixed(1) + '" y="' + (my - 3).toFixed(1)
        + '" text-anchor="middle">' + kgEsc(String(e.rel || '').toLowerCase().replace(/_/g, ' ')) + '</text>';
  });

  function box(node, w, h, isHub) {
    var p = pos[node.id];
    var x = p.x - w / 2, y = p.y - h / 2;
    var cls = 'kg-node kg-' + (node.health || 'neutral') + (node.dim ? ' kg-dim' : '');
    var title = [node.type, node.label, node.sub].filter(Boolean).join(' — ');
    // Baselines are fractions of the box height, not fixed offsets, so changing the
    // type scale + box size keeps the three lines evenly seated instead of drifting out.
    var padX = 9;
    var s = '<g class="' + cls + '"><title>' + kgEsc(title) + '</title>'
      + '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + w + '" height="' + h + '" rx="6"/>'
      + '<text class="kg-type" x="' + (x + padX) + '" y="' + (y + h * 0.30).toFixed(1) + '">'
      + kgEsc(isHub ? 'Customer' : node.type) + '</text>'
      + '<text class="kg-name" x="' + (x + padX) + '" y="' + (y + h * (node.sub ? 0.60 : 0.70)).toFixed(1) + '">'
      + kgEsc(kgTrim(node.label, isHub ? 30 : 28)) + '</text>';
    if (node.sub) {
      s += '<text class="kg-meta" x="' + (x + padX) + '" y="' + (y + h * 0.87).toFixed(1) + '">'
        + kgEsc(kgTrim(node.sub, isHub ? 33 : 31)) + '</text>';
    }
    return s + '</g>';
  }

  ring.forEach(function(node) { out += box(node, NW, NH, false); });
  out += box(hub, HW, HH, true);
  return out + '</svg>';
}

function kgTrim(s, max) {
  s = String(s == null ? '' : s);
  return s.length > max ? s.slice(0, max - 1) + '…' : s;
}

window.closeTicketModal = function() {
  document.getElementById('ticketModal').classList.add('hidden');
};
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    var gm = document.getElementById('graphModal');
    if (gm && !gm.classList.contains('hidden')) { closeGraphModal(); return; }
    var tm = document.getElementById('ticketModal');
    if (tm && !tm.classList.contains('hidden')) closeTicketModal();
  }
});

// Open a ticket's full detail (its own message + reply) in a roomy modal. Keyed on ticket_id
// (many tickets share one conversation), fetched from /user/ticket-detail/{ticket_id}.
async function openTicketModal(ticket) {
  var modal = document.getElementById('ticketModal');
  var cm = chMeta(ticket.channel);
  document.getElementById('ticketModalId').textContent = ticket.ticket_id || ticket.conversation_id || 'Ticket';
  var st = (ticket.status || 'active').toLowerCase();
  var stCls = st === 'closed' ? 'user-status-pill user-status-pill--resolved' : 'user-status-pill';
  document.getElementById('ticketModalMeta').innerHTML =
    '<span class="user-ch-pill" style="background:' + cm.bg + ';border-color:' + cm.bd + ';color:' + cm.clr + '">' + escH(cm.label) + '</span>'
    + '<span class="' + stCls + '">' + escH(statusLabel(ticket.status)) + '</span>'
    + '<span class="ticket-modal-date" style="font-size:10px;color:var(--t3)">Created: ' + escH(fmtDateTime(ticket.created_at)) + '</span>';
  var body = document.getElementById('ticketModalBody');
  body.innerHTML = '<span class="utd-loading">Loading…</span>';
  modal.classList.remove('hidden');
  try {
    var detail = await userApi('/user/ticket-detail/' + encodeURIComponent(ticket.ticket_id));
    var exchanges = detail.exchanges || [];
    if (exchanges.length) {
      // One sub-box per exchange: the customer message, the auto-sent holding
      // line (demoted), and the substantive response — in order.
      body.innerHTML = exchanges.map(function(ex, i) {
        var q = (ex.message || '').replace('Customer portal request\n\n', '');
        var holding = ex.holding
          ? '<p class="utd-holding">↳ Auto-sent: “' + escH(ex.holding.trim()) + '”</p>' : '';
        var resp = ex.response
          ? '<span class="utd-label">Response</span><p class="utd-resp">' + escH(ex.response) + '</p>'
          : (ex.holding ? '<p class="utd-resp utd-resp--pending">Awaiting response…</p>' : '');
        var when = ex.created_at ? fmtDateTime(ex.created_at) : '';
        return '<div class="utd-exchange' + (i > 0 ? ' utd-exchange--next' : '') + '">'
          + (q ? '<span class="utd-label">Your message</span><p class="utd-msg">' + escH(q) + '</p>' : '')
          + holding + resp
          + (when ? '<p class="utd-time">' + escH(when) + '</p>' : '')
          + '</div>';
      }).join('');
    } else {
      // Fallback (older payload without exchanges).
      var msg = (detail.message || '').replace('Customer portal request\n\n', '') || '—';
      var resp = detail.latest_response || 'Response pending';
      body.innerHTML =
        '<span class="utd-label">Your message</span><p class="utd-msg">' + escH(msg) + '</p>'
        + '<span class="utd-label">Latest response</span><p class="utd-resp">' + escH(resp) + '</p>';
    }
  } catch(e) {
    body.innerHTML = '<span class="utd-loading" style="color:var(--red-t)">' + escH(e.message) + '</span>';
  }
}

window.doUserLogout = function() {
  userToken = '';
  portalUser = null;
  if (portalChatTimer) { clearInterval(portalChatTimer); portalChatTimer = null; }
  sessionStorage.removeItem('cx-user-jwt');
  sessionStorage.removeItem('cx-user-account');
  document.getElementById('userIdInput').value = '';
  document.getElementById('userPasswordInput').value = '';
  switchLoginMode('user');
  showStage('apikey');
};

var portalChatTimer = null;

function bootUserPortal() {
  var userId = portalUser && portalUser.user_id ? portalUser.user_id : 'Customer';
  document.getElementById('portalUserName').textContent = userId;
  document.getElementById('portalUserAv').textContent = userId.slice(0, 2).toUpperCase();
  loadPortalChat();
  loadUserTickets();
  // Poll chat history so a support agent's manually-sent reply (held-draft flow) appears
  // for the customer without a page refresh. loadPortalChat() re-renders the whole thread
  // from the server (the source of truth), so this cannot duplicate optimistic bubbles.
  if (portalChatTimer) clearInterval(portalChatTimer);
  portalChatTimer = setInterval(function() {
    if (userToken) loadPortalChat();
    else { clearInterval(portalChatTimer); portalChatTimer = null; }
  }, 8000);
}

function loadSettings() {
  if (currentUser) {
    var nm = currentUser.username || '—';
    var av = nm.slice(0, 2).toUpperCase();
    document.getElementById('acctAv').textContent = av;
    document.getElementById('acctName').textContent = nm;
    document.getElementById('acctEmail').textContent = currentUser.email || '—';
    var since = currentUser.created_at ? new Date(currentUser.created_at).toLocaleDateString([], { year: 'numeric', month: 'long', day: 'numeric' }) : '—';
    document.getElementById('acctSince').textContent = 'Member since ' + since;
  }
  loadAdminUsers();
}

window.loadAdminUsers = async function() {
  var list = document.getElementById('adminUsersList');
  list.innerHTML = '<div style="text-align:center;color:var(--t3);font-size:12px;padding:16px 0">Loading…</div>';
  try {
    var users = await api('/admin/auth/users');
    if (!users.length) { list.innerHTML = '<div style="text-align:center;color:var(--t3);font-size:12px;padding:16px 0">No admin users yet</div>'; return; }
    list.innerHTML = users.map(function(u) {
      var av = (u.username || '?').slice(0, 2).toUpperCase();
      var isMe = currentUser && u.username === currentUser.username;
      var since = u.created_at ? new Date(u.created_at).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' }) : '';
      return '<div class="admin-user-row">'
        + '<div class="admin-user-av">' + escH(av) + '</div>'
        + '<div class="admin-user-info">'
        + '<div class="admin-user-name">' + escH(u.username) + (isMe ? ' <span class="admin-user-you">You</span>' : '') + '</div>'
        + '<div class="admin-user-meta">' + escH(u.email) + (since ? ' · ' + since : '') + '</div>'
        + '</div></div>';
    }).join('');
  } catch(e) {
    list.innerHTML = '<div style="color:var(--red-t);font-size:12px;padding:8px">' + escH(e.message) + '</div>';
  }
};

window.doChangePassword = async function() {
  var current = document.getElementById('pwdCurrent').value;
  var newPwd = document.getElementById('pwdNew').value;
  var confirm = document.getElementById('pwdConfirm').value;
  var statusEl = document.getElementById('pwdStatus');

  function setPwdStatus(msg, type) {
    statusEl.textContent = msg;
    statusEl.className = 'sim-status' + (type ? ' ' + type : '');
    statusEl.style.display = msg ? 'block' : 'none';
  }

  if (!current || !newPwd || !confirm) { setPwdStatus('All fields are required.', ''); return; }
  if (newPwd !== confirm) { setPwdStatus('New passwords do not match.', 'error'); return; }
  if (newPwd.length < 6) { setPwdStatus('New password must be at least 6 characters.', 'error'); return; }

  try {
    // Verify current password via login, then update
    await fetch('/admin/auth/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-admin-key': adminKey },
      body: JSON.stringify({ username: currentUser.username, password: current })
    }).then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error('Current password is incorrect'); return d; }); });

    await api('/admin/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ username: currentUser.username, new_password: newPwd })
    });

    document.getElementById('pwdCurrent').value = '';
    document.getElementById('pwdNew').value = '';
    document.getElementById('pwdConfirm').value = '';
    setPwdStatus('Password updated successfully.', 'success');
  } catch(e) {
    setPwdStatus(e.message, 'error');
  }
};

// ── Utils ─────────────────────────────────────────────────────────────────────
function escH(v) {
  return String(v == null ? '' : v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Real-time polling (fallback — SSE is the primary driver) ─────────────────
function startRealtime() {
  stopRealtime();
  // Inbox: fallback poll every 10s
  rtTimers.push(setInterval(function() {
    if (activePage === 'inbox') loadConversations();
  }, 10000));
  // Analytics charts: full refresh every 90s when visible
  rtTimers.push(setInterval(function() {
    if (activePage === 'analytics') loadAnalytics();
  }, 90000));
  // Connectors: poll every 20s
  rtTimers.push(setInterval(function() {
    if (activePage === 'connectors') loadConnectors();
  }, 20000));
  // Selected conversation: refresh every 12s when open
  rtTimers.push(setInterval(function() {
    if (activePage === 'inbox' && state.selectedConvId) refreshSelectedConv();
  }, 12000));
}

function stopRealtime() {
  rtTimers.forEach(function(t) { clearInterval(t); });
  rtTimers = [];
}

// ── Boot ─────────────────────────────────────────────────────────────────────
function bootApp() {
  if (currentUser) updateRibbonUser();
  loadConversations();
  startRealtime();
  connectSSE();
}

// Restore saved secrets in settings form
var savedSig = sessionStorage.getItem('cx-test-signature');
var savedEmailSecret = sessionStorage.getItem('cx-email-secret');
if (savedSig) document.getElementById('testSig').value = savedSig;
if (savedEmailSecret) document.getElementById('emailSecret').value = savedEmailSecret;

// Determine initial stage
if (userToken && portalUser && !isTokenExpired(userToken)) {
  showStage('user');
  bootUserPortal();
} else if (adminKey && adminToken && !isTokenExpired(adminToken)) {
  showStage('app');
  bootApp();
} else if (adminKey) {
  showStage('auth');
} else {
  showStage('apikey');
}

})();

// ═══════════════════════════════════════════════════════════════════════════
// System diagrams — the two things the header buttons open.
//
// Both are about the SYSTEM, not the selected customer, so neither is gated on a
// customer resolving to a graph node the way the old 360 view was. They reuse
// #graphModal (shell, CSS, close handler) but NOT renderGraphSvg: that layout is
// radial hub-and-spoke, which suits "one customer at the centre" and suits neither
// a schema with chains (Customer→CreditCard→Product) nor a left-to-right pipeline.
// ═══════════════════════════════════════════════════════════════════════════

// Which node types each transactional intent reads at answer time. Mirrors
// neo4j_answer()'s branches in services/neo4j_service/queries.py — the point of the
// schema picture is to show the ANSWER PATH, not just the data model, so a node that
// is never read at answer time honestly shows nothing here.
var KG_INTENT_READS = {
  Account:        ['account_balance_inquiry'],
  FixedDeposit:   ['account_balance_inquiry'],
  CreditCard:     ['card_management'],
  Loan:           ['loan_status', 'loan_default_notice'],
  Policy:         ['policy_status'],
  Claim:          ['claim_status', 'policy_status'],
  Transaction:    ['transaction_dispute'],
  Ticket:         ['(trusted context — get_open_cases, every message)'],
  ResolutionMemory: ['(Priority 0 — verified memories only)']
};

// Tiers give the schema its shape. Order matters: identity, then what the customer
// HOLDS, then what they are DEALING WITH, then the catalog everything hangs off.
var KG_TIERS = [
  { key: 'identity', label: 'Identity', types: ['Customer'] },
  { key: 'holdings', label: 'Holdings — what the customer has',
    types: ['Account', 'CreditCard', 'FixedDeposit', 'Loan', 'Policy', 'Claim',
            'Transaction', 'ChargePenalty', 'KYC'] },
  { key: 'case', label: 'Case layer — what they are dealing with',
    types: ['Ticket', 'Interaction', 'ResolutionMemory', 'Agent'] },
  { key: 'catalog', label: 'Catalog', types: ['Product'] }
];

// Prefetched at load and rendered synchronously on click — the same shape the customer-360
// button used (fetch first, then `onclick` only renders). A fetch inside the click handler
// was the one thing here that differed from the app's working pattern.
var _schemaData = null, _flowData = null;

// Local copy: escH lives inside the main IIFE and is not visible from here. Same scope
// boundary that hid api() — anything this block needs must be defined in this block.
function kgEscape(v) {
  return String(v == null ? '' : v).replace(/[&<>"]/g, function(c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
  });
}

function kgShowModal(title, sub, counts, body) {
  document.getElementById('graphModalTitle').textContent = title;
  document.getElementById('graphModalSub').textContent = sub;
  document.getElementById('graphModalCounts').textContent = counts;
  var bodyEl = document.getElementById('graphModalBody');
  bodyEl.innerHTML = body;
  // The colour key is built by each renderer at the foot of its own markup, which put it
  // below a wide diagram - off screen until you scrolled. The header already has a bar
  // holding the live counts, right-aligned, with the whole left side empty. Move the key
  // into it: key on the left, counts on the right, both visible before any scrolling.
  var bar = document.querySelector('.kg-legend');
  var old = bar.querySelector('.kgs-key');
  if (old) bar.removeChild(old);
  var key = bodyEl.querySelector('.kgs-key');
  if (key) bar.insertBefore(key, bar.firstChild);
  document.getElementById('graphModal').classList.remove('hidden');
}

window.openSchemaModal = function() {
  var sc = _schemaData;
  if (!sc || !sc.reachable) {
    kgShowModal('Neo4j knowledge graph', 'Node types and how they connect', '',
      '<div class="kg-empty">Schema not loaded'
      + (sc && sc.error ? ': ' + kgEscape(sc.error) : ' — is Neo4j running?') + '</div>');
    loadSystemDiagrams();
    return;
  }
  var total = (sc.nodes || []).reduce(function(a, n) { return a + (n.count || 0); }, 0);
  kgShowModal('Neo4j knowledge graph',
    'Node types and how they connect — live counts from the running database',
    (sc.nodes || []).length + ' node types · ' + (sc.edges || []).length
      + ' relationship types · ' + total + ' nodes live',
    renderSchemaSvg(sc));
};

window.openFlowModal = function() {
  var wf = _flowData;
  if (!wf || !wf.edges) {
    kgShowModal('LangGraph workflow', 'The pipeline every inbound message runs through', '',
      '<div class="kg-empty">Workflow not loaded.</div>');
    loadSystemDiagrams();
    return;
  }
  // Counted from the LAYOUT, not from wf.steps/wf.edges. The payload's step list comes
  // from the older WorkflowStep enum - it names retrieve_knowledge / decide_resolution /
  // create_or_update_ticket where the graph actually runs resolve_query / decide_ticket /
  // create_ticket / skip_ticket - and its edge list collapses each branch into one row
  // ("a | b"), so the header read 15 steps and 17 edges over a diagram showing 16 and 22.
  var drawnSteps = Object.keys(FLOW_MAP).filter(function(k) { return k.indexOf('__') !== 0; }).length;
  var branches = Object.keys(FLOW_MAP).filter(function(k) { return FLOW_MAP[k].kind === 'gate'; }).length;
  kgShowModal('LangGraph workflow',
    'The pipeline every inbound message runs through — WhatsApp, email and web chat alike',
    drawnSteps + ' steps · ' + FLOW_EDGES.length + ' edges · '
      + branches + ' decision points · ' + (wf.framework || 'LangGraph'),
    renderFlowSvg(wf));
};

// Fetch both payloads once, up front. Failures are silent: the click handler above
// reports "not loaded" and retries, so a slow start never leaves a stuck modal.
function loadSystemDiagrams() {
  // Uses fetch directly, NOT the api() helper: api() and adminKey are declared inside the
  // main IIFE, so this code (appended after it) cannot see them — that scope boundary is
  // what silently broke the first version. The key is read from sessionStorage, the same
  // place api() gets it.
  function kgFetch(path) {
    var key = '';
    try { key = sessionStorage.getItem('cx-admin-key') || ''; } catch (e) {}
    return fetch(path, { headers: { 'x-admin-key': key } }).then(function(r) {
      if (!r.ok) throw new Error(r.status + ' ' + r.statusText);
      return r.json();
    });
  }
  kgFetch('/admin/neo4j/schema')
    .then(function(d) { _schemaData = d; })
    .catch(function(e) { _schemaData = { reachable: false, error: String(e.message || e) }; });
  kgFetch('/admin/orchestration/workflow')
    .then(function(d) { _flowData = d; })
    .catch(function() { _flowData = null; });
}

// Real SVG with drawn edges. Layout is a fixed hand-authored map, NOT a physics sim: the
// schema must look identical on every open, and it only changes when the data model does.
// Live counts come from the payload; the arrangement is ours.
//
// Geometry rules learned the hard way:
//  - Every box is 200 wide. Property strings are kept under ~26 chars so 10px monospace
//    (~6px/char) fits inside 200-20 padding. Longer names are shortened, never clipped.
//  - Columns are 215 apart, rows 150 apart: enough for an edge label to sit on the gap
//    without touching either box.
//  - The Customer->Ticket edge leaves the RIGHT side and runs down a dedicated corridor
//    at x=1105, outside every column, so it never crosses another node.
var KG_COLW = 196, KG_COLGAP = 210, KG_X0 = 24;
function kgCol(i) { return KG_X0 + i * KG_COLGAP; }

// EVERY edge below is a relationship that exists in the database - verified against
// MATCH (a)-[r]->(b). An earlier version drew FixedDeposit under Account and Loan under
// CreditCard purely because they sat in the same grid column; both are children of
// Customer, so those arrows described relationships that do not exist. A diagram that
// invents an edge is worse than no diagram.
//
// Row 1 = the seven things a Customer directly owns (all :HAS_* from Customer).
// Row 2 = second-hop only: Claim (via Policy) and the case chain.
var KG_MAP = {
  Customer:        { x: kgCol(2), y:  26, w: 210, h: 84, tier: 'identity', head: 'Anchor',
                     props: ['customer_id', 'name / email / phone', 'segment / city'] },

  Account:         { x: kgCol(0), y: 210, w: KG_COLW, h: 82, tier: 'holdings', head: 'Money in',
                     props: ['account_number', 'avg_monthly_balance', 'min_balance_required'] },
  FixedDeposit:    { x: kgCol(1), y: 210, w: KG_COLW, h: 82, tier: 'holdings', head: 'Money in',
                     props: ['fd_id / principal_amount', 'maturity_date', 'maturity_amount'] },
  CreditCard:      { x: kgCol(2), y: 210, w: KG_COLW, h: 82, tier: 'holdings', head: 'Money out',
                     props: ['credit_limit', 'balance_due / dpd', 'payment_due_date'] },
  Loan:            { x: kgCol(3), y: 210, w: KG_COLW, h: 82, tier: 'holdings', head: 'Money out',
                     props: ['loan_type / amount_inr', 'emis_pending / dpd', 'next_step'] },
  Policy:          { x: kgCol(4), y: 210, w: KG_COLW, h: 82, tier: 'holdings', head: 'Insurance',
                     props: ['policy_id / coverage_inr', 'premium_inr', 'next_premium_due'] },
  Transaction:     { x: kgCol(5), y: 210, w: KG_COLW, h: 82, tier: 'holdings', head: 'Activity',
                     props: ['txn_id / amount', 'status', 'failure_reason'] },
  ChargePenalty:   { x: kgCol(6), y: 210, w: 206, h: 82, tier: 'holdings', head: 'Activity',
                     props: ['charge_type', 'amount / reason', 'reversal_status'] },

  Claim:           { x: kgCol(4), y: 370, w: KG_COLW, h: 82, tier: 'holdings', head: 'Insurance',
                     props: ['claim_id / status', 'amount_claimed_inr', 'amount_approved_inr'] },
  KYC:             { x: kgCol(5), y: 370, w: KG_COLW, h: 78, tier: 'holdings', head: 'Compliance',
                     props: ['kyc_status', 'registered_at'] },
  Product:         { x: kgCol(1), y: 370, w: 230, h: 78, tier: 'catalog', head: 'Shared catalogue',
                     props: ['product_id / name', 'Account, FD, Card, Loan'] },

  Ticket:          { x: kgCol(7), y:  26, w: KG_COLW, h: 82, tier: 'case', head: 'The case',
                     props: ['ticket_id / status', 'scope = continuity', 'intent / priority'] },
  Interaction:     { x: kgCol(7), y: 210, w: KG_COLW, h: 82, tier: 'case', head: 'One per message',
                     props: ['turn_id / channel', 'message / sentiment', 'status open->closed'] },
  Agent:           { x: kgCol(8), y: 210, w: 186, h: 82, tier: 'case', head: 'Handled by',
                     props: ['AI_AGENT  (the AI)', 'HUMAN_SR  (a person)', 'one per handler type'] },
  ResolutionMemory:{ x: kgCol(7) - 30, y: 370, w: 256, h: 82, tier: 'memory', head: 'Learning loop',
                     props: ['memory_key = problem', 'verified / times_reused', 'resolution_text'] }
};

// fs/ts = the side each line leaves and enters. Fan-out edges from Customer all leave the
// bottom; the Ticket edge leaves the right because Ticket sits beside Customer, not below.
var KG_EDGES = [
  { from: 'Customer', to: 'Account',          rel: 'HAS_ACCOUNT',     fs: 'b', ts: 't' },
  { from: 'Customer', to: 'FixedDeposit',     rel: 'HAS_FD',          fs: 'b', ts: 't' },
  { from: 'Customer', to: 'CreditCard',       rel: 'HAS_CREDIT_CARD', fs: 'b', ts: 't' },
  { from: 'Customer', to: 'Loan',             rel: 'HAS_LOAN',        fs: 'b', ts: 't' },
  { from: 'Customer', to: 'Policy',           rel: 'HAS_POLICY',      fs: 'b', ts: 't' },
  { from: 'Customer', to: 'Transaction',      rel: 'HAS_TRANSACTION', fs: 'b', ts: 't' },
  { from: 'Customer', to: 'ChargePenalty',    rel: 'HAS_CHARGE',      fs: 'b', ts: 't' },
  { from: 'Customer', to: 'Ticket',           rel: 'HAS_TICKET',      fs: 'r', ts: 'l' },

  // Second hop: a claim belongs to a policy (it also hangs off Customer directly - the
  // same node reached two ways, which is the point of a graph).
  { from: 'Policy',   to: 'Claim',            rel: 'HAS_CLAIM',       fs: 'b', ts: 't' },

  // All four holdings that carry a product point at the catalogue.
  { from: 'Account',  to: 'Product',          rel: 'PRODUCT_IS',      fs: 'b', ts: 't' },
  { from: 'FixedDeposit', to: 'Product',      rel: 'PRODUCT_IS',      fs: 'b', ts: 't' },
  { from: 'CreditCard', to: 'Product',        rel: 'PRODUCT_IS',      fs: 'b', ts: 't' },
  { from: 'Loan',     to: 'Product',          rel: 'PRODUCT_IS',      fs: 'b', ts: 't' },

  { from: 'Customer', to: 'KYC',              rel: 'KYC_VERIFIED_BY', lane: 464, gutter: 12 },
  // The SAME Claim node reached two ways - by its policy and directly by the customer.
  // That is what a graph buys you, so both edges are drawn rather than one.
  { from: 'Customer', to: 'Claim',            rel: 'HAS_CLAIM',       lane: 478, gutter: 6 },
  { from: 'Customer', to: 'Interaction',      rel: 'HAS_INTERACTION', top: 14, gutter: 1912, enter: 'b' },
  { from: 'Ticket',   to: 'Interaction',      rel: 'HAS_MESSAGE',     fs: 'b', ts: 't' },
  { from: 'Interaction', to: 'Agent',         rel: 'HANDLED_BY',      fs: 'r', ts: 'l' },
  { from: 'Interaction', to: 'ResolutionMemory', rel: 'CREATED_MEMORY', fs: 'b', ts: 't' }
];

var KG_TIER_FILL = {
  identity: ['#eff6ff', '#93c5fd', '#1d4ed8'],
  holdings: ['#f0fdf4', '#86efac', '#15803d'],
  catalog:  ['#f5f3ff', '#c4b5fd', '#6d28d9'],
  case:     ['#fffbeb', '#fcd34d', '#b45309'],
  memory:   ['#fdf2f8', '#f9a8d4', '#be185d']
};

function kgAnchor(n, side) {
  if (side === 't') return [n.x + n.w / 2, n.y];
  if (side === 'b') return [n.x + n.w / 2, n.y + n.h];
  if (side === 'l') return [n.x, n.y + n.h / 2];
  return [n.x + n.w, n.y + n.h / 2];
}

function renderSchemaSvg(sc) {
  var counts = {};
  (sc.nodes || []).forEach(function(n) { counts[n.id] = n.count; });

  var W = 1955, H = 525;
  var svg = '<svg class="kgs" style="--kgs-w:' + W + 'px;--kgs-h:' + H + 'px;--kgs-s:0.76" width="' + W + '" height="' + H
          + '" viewBox="0 0 ' + W + ' ' + H + '" xmlns="http://www.w3.org/2000/svg">';
  svg += '<defs><marker id="kgar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
       + 'markerHeight="7" orient="auto-start-reverse">'
       + '<path d="M0,0 L10,5 L0,10 z" fill="#94a3b8"/></marker></defs>';

  var kgLabels = [];
  KG_EDGES.forEach(function(e) {
    var a = KG_MAP[e.from], b = KG_MAP[e.to];
    if (!a || !b || counts[e.from] == null || counts[e.to] == null) return;
    var d, labX, labY, p1, p2;

    if (e.top) {
      // Up over the top of the drawing, right along the margin, down the outer gutter and
      // in from the right. Nothing sits above y=26 or beyond x=1890, so this is always clear.
      p1 = kgAnchor(a, 't'); p2 = kgAnchor(b, e.enter || 'r');
      d = (e.enter === 'b')
        ? 'M' + p1[0] + ',' + p1[1] + ' V' + e.top + ' H' + e.gutter + ' V' + (p2[1] + 44)
          + ' H' + p2[0] + ' V' + p2[1]
        : 'M' + p1[0] + ',' + p1[1] + ' V' + e.top + ' H' + e.gutter + ' V' + p2[1] + ' H' + p2[0];
      labX = e.gutter - 150; labY = e.top - 4;
    } else if (e.lane) {
      // Down the left edge of the source, along a horizontal lane BELOW every box, then
      // up into the target's underside. A vertical corridor could not clear the tall
      // case column, so long edges travel underneath the drawing instead.
      // LEFT out of the source, down the far-left gutter (x=10, no box there), along the
      // lane below every box, then up into the target's underside. Leaving downward
      // would immediately cross whatever sits in the column beneath the source.
      p1 = kgAnchor(a, 'l'); p2 = kgAnchor(b, e.enter || 'b');
      d = 'M' + p1[0] + ',' + p1[1] + ' H' + e.gutter + ' V' + e.lane
        + ' H' + p2[0] + ' V' + p2[1];
      labX = p2[0] - 118; labY = e.lane - 5;
    } else if (e.corridor) {
      p1 = kgAnchor(a, 'r'); p2 = kgAnchor(b, 'r');
      d = 'M' + p1[0] + ',' + p1[1] + ' H' + e.corridor + ' V' + p2[1] + ' H' + p2[0];
      labX = p1[0] + 12; labY = p1[1] - 7;
    } else if (e.fs === 'l' || e.fs === 'r') {
      p1 = kgAnchor(a, e.fs); p2 = kgAnchor(b, e.ts);
      var midX = (p1[0] + p2[0]) / 2;
      d = 'M' + p1[0] + ',' + p1[1] + ' H' + midX + ' V' + p2[1] + ' H' + p2[0];
      labX = midX - 46; labY = p1[1] - 8;
    } else {
      p1 = kgAnchor(a, e.fs); p2 = kgAnchor(b, e.ts);
      var midY = (p1[1] + p2[1]) / 2;
      d = 'M' + p1[0] + ',' + p1[1] + ' V' + midY + ' H' + p2[0] + ' V' + p2[1];
      labX = (p1[0] + p2[0]) / 2 + 7; labY = midY - 6;
    }
    svg += '<path class="kgs-e" d="' + d + '" marker-end="url(#kgar)"/>';
    kgLabels.push({ x: labX, y: labY, ax: p2[0], ay: p2[1], rel: e.rel, side: e.ts, fx: p1[0], by: b.y,
                    routed: !!(e.top || e.lane || e.corridor), text: ':' + e.rel });
    // The count is deliberately NOT on the label. For 11 of 13 edges it simply repeats
    // the number already on the target box (8 accounts, :HAS_ACCOUNT x8), and where it
    // differs it looks like a contradiction rather than a fact: :HAS_CLAIM x30 against
    // (:Claim) 15, because each claim is reached twice - from its policy and from the
    // customer. Node counts stay on the boxes, where the note above explains them.
  });

  // A label belongs to ONE arrow, so it is centred on that arrow's head rather than
  // offset from the midpoint of the run. Before this, Customer's seven fan-out labels
  // all sat at the same y and read as a single strip of text -
  // ":HAS_ACCOUNT x8 :HAS_FD x4 :HAS_CREDIT_CARD x3 ..." - which is what made the
  // diagram look busy. They never overlapped, so a collision check passed them; the
  // problem was that nothing separated them.
  //
  // Two things fix it: centre each label on its own arrow, and alternate consecutive
  // labels between two heights so neighbours cannot run together. Both rows sit just
  // above the boxes, close to the arrowheads they name.
  var KGL_CH = 11.5 * 0.6, KGL_NEAR = 14, KGL_STEP = 18;
  var seen = {};
  kgLabels.sort(function(p, q) { return p.x - q.x; });
  var band = {};
  kgLabels.forEach(function(l) {
    // PRODUCT_IS is drawn from all four holdings that carry a product, and the count is
    // the TOTAL across them - so four identical ":PRODUCT_IS x17" in a row said the same
    // thing four times and overstated each edge. Label it once, on the first arrow.
    if (seen[l.rel] && l.rel === 'PRODUCT_IS') return;
    seen[l.rel] = true;
    var w = l.text.length * KGL_CH;
    var lx, ly;
    if (l.routed) {
      // Customer -> KYC, -> Claim and -> Interaction cannot run straight: boxes sit in
      // the way, so they travel over the top or along a lane under the drawing. Their
      // arrowhead is nowhere near the run, so centring on it would put the label on the
      // wrong part of the picture - each branch already computes a point ON its own
      // path, which is where the label belongs. An earlier pass skipped these edges
      // entirely and left three unexplained lines on the diagram.
      lx = l.x; ly = l.y;
    } else if (l.side === 'l' || l.side === 'r') {
      // A SIDEWAYS arrow enters the target's left or right edge, so "just above the
      // arrowhead" is inside the box. Sit it beside the arrow when the approach has
      // room; where the boxes nearly touch (Interaction -> Agent is a 14-unit gap)
      // there is no room beside it, so lift it clear above both boxes instead.
      var gap = l.side === 'l' ? l.ax - (l.fx || 0) : (l.fx || 0) - l.ax;
      if (Math.abs(gap) > w + 16) {
        lx = l.side === 'l' ? l.ax - w - 8 : l.ax + 8;
        ly = l.ay - 6;
      } else {
        lx = l.ax - w / 2;
        ly = l.by - 8;
      }
    } else {
      var key = Math.round(l.ay);
      band[key] = (band[key] || 0) + 1;
      lx = l.ax - w / 2;
      ly = l.ay - KGL_NEAR - (band[key] % 2 ? 0 : KGL_STEP);
    }
    svg += '<text class="kgs-el" x="' + lx + '" y="' + ly + '">'
         + kgEscape(l.text) + '</text>';
  });

  Object.keys(KG_MAP).forEach(function(label) {
    var n = KG_MAP[label];
    if (counts[label] == null) return;
    var c = KG_TIER_FILL[n.tier] || KG_TIER_FILL.holdings;
    svg += '<g class="kgs-n">';
    svg += '<rect x="' + n.x + '" y="' + n.y + '" width="' + n.w + '" height="' + n.h
         + '" rx="8" fill="' + c[0] + '" stroke="' + c[1] + '" stroke-width="1.5"/>';
    svg += '<text class="kgs-h" x="' + (n.x + 11) + '" y="' + (n.y + 17) + '" fill="' + c[2] + '">'
         + kgEscape(n.head) + '</text>';
    svg += '<text class="kgs-t" x="' + (n.x + 11) + '" y="' + (n.y + 36) + '">(:'
         + kgEscape(label) + ')</text>';
    svg += '<text class="kgs-c" x="' + (n.x + n.w - 11) + '" y="' + (n.y + 36)
         + '" text-anchor="end" fill="' + c[2] + '">' + (counts[label] || 0) + '</text>';
    (n.props || []).forEach(function(pr, i) {
      svg += '<text class="kgs-p" x="' + (n.x + 11) + '" y="' + (n.y + 53 + i * 12) + '">'
           + kgEscape(pr) + '</text>';
    });
    svg += '</g>';
  });
  svg += '</svg>';

  var extra = (sc.nodes || []).filter(function(n) { return !KG_MAP[n.id]; });
  var note = extra.length
    ? '<div class="kgs-extra">Also in the database, not placed above: '
      + extra.map(function(n) { return kgEscape(n.label) + ' x' + n.count; }).join(' / ') + '</div>'
    : '';

  // Say what the big number on each box IS. Without this a viewer sees "(:Agent) 2" and
  // has no way to know whether 2 is a limit, a version, or a row count.
  return '<div class="kgs-wrap">'
    + '<div class="kgs-note">The number on each box is how many of that node type exist '
    + 'in the database right now. Every customer shares one graph — this is the whole '
    + 'system, not one person’s records.</div>'
    + svg + note
    + '<div class="kgs-key">'
    + '<span><i style="background:#eff6ff;border-color:#93c5fd"></i>Identity</span>'
    + '<span><i style="background:#f0fdf4;border-color:#86efac"></i>Holdings &amp; activity</span>'
    + '<span><i style="background:#f5f3ff;border-color:#c4b5fd"></i>Catalogue</span>'
    + '<span><i style="background:#fffbeb;border-color:#fcd34d"></i>Case layer</span>'
    + '<span><i style="background:#fdf2f8;border-color:#f9a8d4"></i>Learning loop</span>'
    + '</div></div>';
}

function flowParts(name) {
  var m = String(name).match(/^(.*?)\s*\[(.+)\]\s*$/);
  return m ? { step: m[1], agent: m[2] } : { step: String(name), agent: '' };
}

// The pipeline drawn as it actually branches. Positions are a fixed map, like the schema
// view: the topology only changes when graph.py changes, and a stable picture is worth
// more than an auto-layout that shifts every open.
//
// Two lanes below check_has_open_case: LEFT is the ticket-close branch, RIGHT is the
// answer branch. They rejoin at send_outbound_reply, which every path reaches.
var FL_W = 466;

// Landscape. Node notes carry the SAME text as the written walkthrough - an earlier
// version silently trimmed them to fit (classify_intent lost "language", resolve_query
// lost its confidence scores), so the diagram and the explanation disagreed.
//
// Row A (y=190) is the spine every message follows.
// Row B (y=40)  is the ticket-close lane, above the spine.
// Row C (y=340) is the answer lane, below the spine.
var FLOW_MAP = {
  '__start__':                   { x:   8, y: 296, w: 134, h: 58, kind: 'end',  label: 'START' },

  'receive_message':             { x: 150, y: 270, w: FL_W, h: 120, kind: 'step',
                                   note: 'log the inbound event|+ provider' },
  'resolve_identity':            { x: 640, y: 270, w: FL_W, h: 145, kind: 'step',
                                   note: 'phone OR email -> ONE Customer|(the omnichannel join)|the customer (graph)' },
  'load_conversation_context':   { x: 1130, y: 270, w: FL_W, h: 145, kind: 'step',
                                   note: 'ONE fetch, shared downstream:|turns + tickets (sql)|their records (graph)' },
  'check_has_open_case':         { x: 1620, y: 270, w: FL_W, h: 120, kind: 'gate',
                                   note: 'does this CUSTOMER have|an open case?' },

  'detect_ticket_action':        { x: 2110, y:  40, w: FL_W, h: 102, kind: 'agent', owner: 'Ticket Creation', llm: 'closure?',
                                   note: 'is this turn about closing?' },
  'select_ticket_to_close':      { x: 2600, y:  40, w: FL_W, h: 102, kind: 'gate', owner: 'Ticket Creation',
                                   note: 'WHICH ticket?' },
  'close_ticket':                { x: 3090, y:  40, w: FL_W, h: 102, kind: 'step', owner: 'Ticket Creation',
                                   note: 'mark the selected ticket closed' },

  'classify_intent':             { x: 2110, y: 470, w: FL_W, h: 136, kind: 'agent', owner: 'Intent Classification', llm: 'intent',
                                   note: 'ONE LLM call returns intent +|urgency + sentiment + language|written onto the turn (sql)' },
  'validate_customer':           { x: 2600, y: 470, w: FL_W, h: 136, kind: 'gate', owner: 'Customer Validation',
                                   note: 'registered for this intent?' },
  'reject_unregistered_customer':{ x: 2600, y: 650, w: FL_W, h: 108, kind: 'step', owner: 'Customer Validation',
                                   note: 'ask them to write from|a registered address' },
  'resolve_query':               { x: 3090, y: 470, w: FL_W, h: 164, kind: 'agent', owner: 'Query Resolution', llm: 'grade+answer',
                                   note: 'answers from the RL memory, their|tickets or records (graph),|or the KB (kb)|- then grades it L1 / L2 / L3' },
  'decide_ticket':               { x: 3580, y: 470, w: FL_W, h: 136, kind: 'gate', owner: 'Ticket Creation',
                                   note: 'does a human need to see this?|L2/L3 always -> ticket' },
  'create_ticket':               { x: 4070, y: 446, w: FL_W, h: 145, kind: 'agent', owner: 'Ticket Creation', llm: 'same matter?',
                                   note: 'same matter or new? matched on|transactions (graph)|the ticket is written (sql)' },
  'skip_ticket':                 { x: 4070, y: 600, w: FL_W, h: 92, kind: 'step', owner: 'Ticket Creation',
                                   note: 'answer directly' },

  'send_outbound_reply':         { x: 4030, y: 212, w: 500, h: 200, kind: 'gate', owner: 'Workflow Automation',
                                   note: 'REVIEW GATE|hold <=> ticket required|customer gets a holding message|an agent edits or approves,|then sends it manually' },
  'persist_audit_events':        { x: 4600, y: 240, w: FL_W, h: 145, kind: 'step',
                                   note: 'turn + citations + evidence (sql)|Interaction closed, memory (graph)' },
  '__end__':                     { x: 5090, y: 264, w: 122, h: 58, kind: 'end', label: 'END' }
};

var FLOW_EDGES = [
  { f: '__start__', t: 'receive_message', fs: 'r', ts: 'l' },
  { f: 'receive_message', t: 'resolve_identity', fs: 'r', ts: 'l' },
  { f: 'resolve_identity', t: 'load_conversation_context', fs: 'r', ts: 'l' },
  { f: 'load_conversation_context', t: 'check_has_open_case', fs: 'r', ts: 'l' },

  { f: 'check_has_open_case', t: 'detect_ticket_action', fs: 'r', ts: 'l', cond: '1  has a case' },
  { f: 'check_has_open_case', t: 'classify_intent', fs: 'r', ts: 'l', cond: '0  no case' },

  { f: 'detect_ticket_action', t: 'select_ticket_to_close', fs: 'r', ts: 'l', cond: 'CLOSE' },
  { f: 'detect_ticket_action', t: 'classify_intent', fs: 'b', ts: 't', cond: 'anything else' },
  { f: 'select_ticket_to_close', t: 'close_ticket', fs: 'r', ts: 'l', cond: 'clear' },
  { f: 'select_ticket_to_close', t: 'send_outbound_reply', fs: 'b', ts: 'l', cond: 'ambiguous - ask which' },
  { f: 'close_ticket', t: 'send_outbound_reply', fs: 'r', ts: 't' },

  { f: 'classify_intent', t: 'validate_customer', fs: 'r', ts: 'l' },
  { f: 'validate_customer', t: 'resolve_query', fs: 'r', ts: 'l', cond: 'registered' },
  { f: 'validate_customer', t: 'reject_unregistered_customer', fs: 'b', ts: 't', cond: 'not' },
  { f: 'reject_unregistered_customer', t: 'send_outbound_reply', band: 800, gx: 4590, ts: 'b' },
  { f: 'resolve_query', t: 'decide_ticket', fs: 'r', ts: 'l' },
  { f: 'decide_ticket', t: 'create_ticket', fs: 'r', ts: 'l', cond: 'required' },
  { f: 'decide_ticket', t: 'skip_ticket', fs: 'b', ts: 'l', cond: 'no' },
  { f: 'create_ticket', t: 'send_outbound_reply', fs: 't', ts: 'b' },
  { f: 'skip_ticket', t: 'send_outbound_reply', band: 800, gx: 4630, ts: 'b' },

  { f: 'send_outbound_reply', t: 'persist_audit_events', fs: 'r', ts: 'l' },
  { f: 'persist_audit_events', t: '__end__', fs: 'r', ts: 'l' }
];

var FL_FILL = {
  end:   ['#0f172a', '#0f172a', '#ffffff'],
  step:  ['#ffffff', '#cbd5e1', '#101828'],
  gate:  ['#fffbeb', '#fcd34d', '#b45309'],
  agent: ['#eff6ff', '#93c5fd', '#1d4ed8']
};

function flAnchor(n, side) {
  if (side === 't') return [n.x + n.w / 2, n.y];
  if (side === 'b') return [n.x + n.w / 2, n.y + n.h];
  if (side === 'l') return [n.x, n.y + n.h / 2];
  return [n.x + n.w, n.y + n.h / 2];
}

function renderFlowSvg(wf) {
  var W = 5300, H = 850;
  var svg = '<svg class="kgs" style="--kgs-w:' + W + 'px;--kgs-h:' + H + 'px;--kgs-s:0.44" width="' + W + '" height="' + H
          + '" viewBox="0 0 ' + W + ' ' + H + '" xmlns="http://www.w3.org/2000/svg">';
  svg += '<defs><marker id="flar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
       + 'markerHeight="7" orient="auto-start-reverse">'
       + '<path d="M0,0 L10,5 L0,10 z" fill="#94a3b8"/></marker></defs>';

  FLOW_EDGES.forEach(function(e) {
    var a = FLOW_MAP[e.f], b = FLOW_MAP[e.t];
    if (!a || !b) return;
    var p1, p2, d, lx, ly;
    if (e.band) {
      // Out the top, along a horizontal lane measured to be clear of every box, then
      // down/up into the target. Used where a direct run would clip the create/skip column.
      p1 = flAnchor(a, 'b'); p2 = flAnchor(b, e.ts);
      d = 'M' + p1[0] + ',' + p1[1] + ' V' + e.band + ' H' + e.gx
        + ' V' + p2[1] + ' H' + p2[0];
      lx = e.gx - 60; ly = e.band - 5;
      svg += '<path class="kgs-e" d="' + d + '" marker-end="url(#flar)"/>';
      if (e.cond) svg += '<text class="fl-cond" x="' + lx + '" y="' + ly + '">'
                       + kgEscape(e.cond) + '</text>';
      return;
    }
    p1 = flAnchor(a, e.fs); p2 = flAnchor(b, e.ts);
    if (e.fs === 'l' || e.fs === 'r') {
      // sideways out, then vertical, then in
      var mx = e.fs === 'l' ? Math.min(p1[0], p2[0]) - 40 : Math.max(p1[0], p2[0]) + 40;
      if (e.ts === 't' || e.ts === 'b') {
        d = 'M' + p1[0] + ',' + p1[1] + ' H' + p2[0] + ' V' + p2[1];
        lx = (p1[0] + p2[0]) / 2 - 30; ly = p1[1] - 7;
      } else {
        d = 'M' + p1[0] + ',' + p1[1] + ' H' + mx + ' V' + p2[1] + ' H' + p2[0];
        lx = e.fs === 'l' ? mx + 6 : mx - 120; ly = (p1[1] + p2[1]) / 2 - 6;
      }
    } else {
      var my = (p1[1] + p2[1]) / 2;
      d = 'M' + p1[0] + ',' + p1[1] + ' V' + my + ' H' + p2[0] + ' V' + p2[1];
      lx = p1[0] === p2[0] ? p1[0] + 8 : (p1[0] + p2[0]) / 2 + 8; ly = my - 5;
    }
    svg += '<path class="kgs-e" d="' + d + '" marker-end="url(#flar)"/>';
    if (e.cond) {
      svg += '<text class="fl-cond" x="' + lx + '" y="' + ly + '">' + kgEscape(e.cond) + '</text>';
    }
  });

  Object.keys(FLOW_MAP).forEach(function(key) {
    var n = FLOW_MAP[key];
    var c = FL_FILL[n.kind] || FL_FILL.step;
    svg += '<g class="kgs-n">';
    svg += '<rect x="' + n.x + '" y="' + n.y + '" width="' + n.w + '" height="' + n.h
         + '" rx="' + (n.kind === 'end' ? 15 : 8) + '" fill="' + c[0] + '" stroke="' + c[1]
         + '" stroke-width="1.5"/>';
    if (n.kind === 'end') {
      svg += '<text class="fl-end" x="' + (n.x + n.w / 2) + '" y="' + (n.y + 26)
           + '" text-anchor="middle" fill="' + c[2] + '">' + kgEscape(n.label) + '</text>';
    } else {
      var ty = n.y + 38;
      if (n.owner) {
        var tag = n.owner + ' agent' + (n.llm ? ' · LLM · ' + n.llm : '');
        svg += '<text class="' + (n.llm ? 'fl-llm' : 'fl-agent') + '" x="'
             + (n.x + n.w - 10) + '" y="' + (n.y + 19) + '" text-anchor="end">'
             + kgEscape(tag) + '</text>';
      }
      svg += '<text class="fl-name" x="' + (n.x + 11) + '" y="' + ty + '" fill="' + c[2] + '">'
           + kgEscape(key) + '</text>';
      (n.note || '').split('|').forEach(function(line, i) {
        if (!line) return;
        // sql / graph / kb name the STORE a fact came from. They sit inside the sentence
        // rather than on a line of their own - a separate line just restated the note in
        // different words - so they are coloured to read as sources, not as prose.
        var html = kgEscape(line).replace(/(sql|graph|kb)/g, function(w) {
          return '<tspan class="fl-store">' + w + '</tspan>';
        });
        svg += '<text class="fl-note" x="' + (n.x + 11) + '" y="' + (ty + 32 + i * 25) + '">'
             + html + '</text>';
      });
    }
    svg += '</g>';
  });
  svg += '</svg>';

  // The count is gone. It read "Decision point (6)" and counted kind==='gate' - but
  // two real decision points (detect_ticket_action, create_ticket) are now blue
  // because they call an LLM, so the number matched neither the amber boxes nor the
  // branches in the graph. A swatch does not need a tally; the branches are visible.
  return '<div class="kgs-wrap">'
    + '<div class="kgs-note kgs-note-2"><b>PII masking</b> \u2014 around every LLM call: PAN, '
    + 'Aadhaar, phone numbers, email addresses and card numbers are replaced with placeholders '
    + 'before the text leaves for the model, and restored in the reply.</div>'
    + '<div class="kgs-note kgs-note-2"><b>Deterministic safety net</b> \u2014 fraud, phishing, '
    + 'OTP sharing and regulatory complaints force critical escalation before the LLM is called.</div>'
    + '<div class="kgs-note kgs-note-2"><b>Learning loop</b> \u2014 answers are keyed by the kind '
    + 'of problem, not the customer, so one verified answer serves the next person with the same '
    + 'problem. Only procedural answers qualify; anything carrying a balance or a case\u2019s '
    + 'specifics is excluded.</div>'
    + svg
    + '<div class="kgs-key">'
    + '<span><i style="background:#ffffff;border-color:#cbd5e1"></i>Step</span>'
    + '<span><i style="background:#fffbeb;border-color:#fcd34d"></i>Decision point</span>'
    + '<span><i style="background:#eff6ff;border-color:#93c5fd"></i>Calls an LLM</span>'
    + '<span><i style="background:#0f172a;border-color:#0f172a"></i>Start / end</span>'
    + '</div></div>';
}

// Prefetch both payloads at load. Buttons are wired inline in index.html (onclick=),
// matching how every other button in this app is wired.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadSystemDiagrams);
} else {
  loadSystemDiagrams();
}
