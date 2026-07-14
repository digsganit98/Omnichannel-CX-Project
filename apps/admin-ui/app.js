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

var state = { convs: [], selectedConvId: null, convDetail: null, simTimer: null, sseSource: null, pendingDrafts: {} };
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
  if (name === 'tickets') loadTickets();
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
  if (!dn || dn === 'None' || dn === 'null') return 'Customer #' + (conv.customer_id || '').slice(-6);
  // If display_name is an email address, infer a readable name from it
  if (dn.indexOf('@') !== -1) return inferNameFromEmail(dn);
  return dn;
}

function customerInitials(conv) {
  var nm = customerLabel(conv);
  return nm.split(/\s+/).map(function(w) { return w[0]; }).join('').toUpperCase().slice(0,2);
}

function urgencyToStatus(conv) {
  if (conv.status === 'closed' || conv.status === 'resolved') return 'resolved';
  var allTkts = [].concat(_allTickets.open, _allTickets.closed);
  var convTkts = allTkts.filter(function(t) { return t.conversation_id === conv.conversation_id; });
  if (convTkts.length > 0 && convTkts.every(function(t) { return t.status === 'resolved' || t.status === 'closed'; })) return 'resolved';
  var u = (conv.last_urgency || '').toLowerCase();
  if (u === 'high' || u === 'critical') return 'urgent';
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
    _allTickets.open   = tks.filter(function(t) { return t.status === 'open' || t.status === 'in_progress'; });
    _allTickets.closed = tks.filter(function(t) { return t.status === 'resolved' || t.status === 'closed'; });
    var prevIds = state.convs.map(function(c){ return c.conversation_id; }).sort().join(',');
    var newIds = convs.map(function(c){ return c.conversation_id; }).sort().join(',');
    var hasNew = newIds !== prevIds;
    state.convs = convs;
    renderQueue();
    var urgent = convs.filter(function(c) { return urgencyToStatus(c) === 'urgent'; });
    var badge = document.getElementById('inboxBadge');
    if (urgent.length > 0) { badge.style.display='flex'; badge.textContent = urgent.length > 9 ? '9+' : urgent.length; }
    else { badge.style.display = 'none'; }
    document.getElementById('qcnt').textContent = urgent.length + ' urgent';
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
  if (state.convDetail && (state.convDetail.status === 'resolved' || state.convDetail.status === 'closed')) return;
  try {
    var detail = await api('/admin/conversations/' + encodeURIComponent(state.selectedConvId));
    var prevLen = (state.convDetail && state.convDetail.turns) ? state.convDetail.turns.length : 0;
    if (detail.turns && detail.turns.length !== prevLen) {
      state.convDetail = detail;
      renderCentre(detail);
      renderRight(detail, [].concat(_allTickets.open, _allTickets.closed));
    }
  } catch(e) {}
}

function renderQueue() {
  var search = (document.getElementById('srchInput').value || '').toLowerCase();
  var list = document.getElementById('qlist');
  list.innerHTML = '';
  var filtered = state.convs.filter(function(c) {
    if (search && !customerLabel(c).toLowerCase().includes(search) && !(c.last_message||'').toLowerCase().includes(search)) return false;
    if (activeFilter === 'urgent' && urgencyToStatus(c) !== 'urgent') return false;
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
    var stDot = sts === 'urgent' ? 'durg' : sts === 'resolved' ? 'dok' : sts === 'active' ? 'desc' : 'dopn';
    var stLabel = sts === 'urgent' ? 'Urgent' : sts === 'resolved' ? 'Resolved' : sts === 'active' ? 'Active' : 'Open';
    var div = document.createElement('div');
    div.className = 'qi' + (isOn ? ' on' : '') + (sts === 'resolved' ? ' done' : '');
    div.innerHTML = '<div class="cs ' + ch.stripe + '"></div>'
      + '<div class="qb">'
      + '<div class="qr1"><span class="qn">' + escH(customerLabel(c)) + '</span><span class="qt">' + escH(formatTime(c.updated_at)) + '</span></div>'
      + '<div class="qp">' + escH((c.last_message || c.summary || 'No messages yet').slice(0,60)) + '</div>'
      + '<div class="qf">'
      + (c.last_channel ? '<span class="cp ' + ch.pill + '">' + ch.svg + ch.label + '</span>' : '<span class="cp pdef">Unknown</span>')
      + '<span class="sl"><span class="sd ' + stDot + '"></span>' + stLabel + '</span>'
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
    var cachedTickets = _allTickets.open.length || _allTickets.closed.length
      ? Promise.resolve([].concat(_allTickets.open, _allTickets.closed))
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

  var isDone = urgencyToStatus(conv_meta) === 'resolved';
  document.getElementById('btnResolve').disabled = isDone;
  document.getElementById('btnEsc').disabled = isDone;
  document.getElementById('resbanner').style.display = isDone ? 'flex' : 'none';
  document.getElementById('compwrap').style.display = isDone ? 'none' : 'block';

  // Channel filter bar
  var seenChs = {};
  turns.forEach(function(t) { if (t.channel) seenChs[t.channel] = (seenChs[t.channel]||0)+1; });
  var bar = document.getElementById('chbar');
  bar.innerHTML = '<span class="chbar-label">View:</span>';
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
  var convIsResolved = conv.status === 'resolved' || conv.status === 'closed';
  var tktStatusMap = {};
  [].concat(_allTickets.open, _allTickets.closed).forEach(function(t) {
    tktStatusMap[t.ticket_id] = t.status;
  });

  steps.forEach(function(step, idx) {
    var isLast = idx === 0;
    var ref = step.inbound || step.outbound;
    var ch = chMeta(ref.channel);

    var urgency = ((step.inbound && step.inbound.urgency) || '').toLowerCase();
    var emotion = EMOTION_MAP[urgency] || 'Neutral';
    var emotionCls = EMOTION_CLS[urgency] || 'fe-neutral';

    var intent = ((step.inbound && step.inbound.intent) || (step.outbound && step.outbound.intent) || '').replace(/_/g, ' ');

    var d = ref.created_at ? new Date(ref.created_at) : null;
    var tm = d ? d.toLocaleDateString([], {month:'short', day:'numeric', year:'numeric'})
              + ' · ' + d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) : '';

    var stepTicketId = (step.inbound && step.inbound.ticket_id) || (step.outbound && step.outbound.ticket_id) || null;
    var tktStatus = stepTicketId ? tktStatusMap[stepTicketId] : null;
    var nodeStatus;
    if (tktStatus === 'resolved' || tktStatus === 'closed') {
      nodeStatus = 'resolved';
    } else if (tktStatus === 'open' || tktStatus === 'in_progress') {
      nodeStatus = 'active';
    } else if (!isLast) {
      nodeStatus = 'resolved';
    } else {
      nodeStatus = convIsResolved ? 'resolved' : (conv.status || 'active');
    }
    var nodeStatusCls = (nodeStatus === 'active' || nodeStatus === 'open' || nodeStatus === 'in_progress') ? 'fns-active' : 'fns-done';

    var el = document.createElement('div');
    el.className = 'flow-step';

    // LEFT — customer query
    var inboundSubject = (step.inbound && step.inbound.subject) || '';
    var inboundBody = (step.inbound && step.inbound.text) || '';
    if (inboundSubject && inboundBody.startsWith(inboundSubject)) {
      inboundBody = inboundBody.slice(inboundSubject.length).replace(/^\s+/, '');
    }
    var leftHtml = step.inbound
      ? '<div class="flow-query-card">'
        + '<div class="flow-query-hdr"><span>Customer Query</span>'
        + (urgency ? '<span class="flow-emotion ' + emotionCls + '">' + escH(emotion) + '</span>' : '')
        + '</div>'
        + (inboundSubject ? '<div class="flow-query-subject">' + escH(inboundSubject) + '</div>' : '')
        + '<div class="flow-query-text">' + escH(inboundBody) + '</div>'
        + (intent ? '<span class="flow-intent-pill">' + escH(intent) + '</span>' : '')
        + '</div>'
      : '';

    // CENTER — metadata node
    var ticketId = (step.inbound && step.inbound.ticket_id) || (step.outbound && step.outbound.ticket_id) || null;
    var centerHtml = (ticketId ? '<div class="flow-ticket-label">TICKET: ' + escH(ticketId) + '</div>' : '')
      + '<div class="flow-node" style="border-left-color:' + ch.clr + '">'
      + '<div class="flow-node-top">'
      + '<span class="flow-node-id">Turn ' + (steps.length - idx) + '</span>'
      + (isLast ? '<span class="flow-node-latest">Latest</span>' : '')
      + '</div>'
      + '<div style="margin:3px 0"><span class="cp ' + ch.pill + '" style="font-size:10px">' + ch.svg + ch.label + '</span></div>'
      + '<div class="flow-node-time">' + escH(tm) + '</div>'
      + '<span class="flow-node-status ' + nodeStatusCls + '">' + escH(nodeStatus) + '</span>'
      + '</div>'
      + (idx < steps.length - 1 ? '<div class="flow-vline"></div>' : '');

    // RIGHT — agent reply
    var rightHtml = step.outbound
      ? '<div class="flow-reply-card">'
        + '<div class="flow-reply-hdr"><span>Resolution / Reply</span>'
        + '<span class="flow-agent-pill">AI Agent</span>'
        + '</div>'
        + '<div class="flow-reply-text">' + escH(step.outbound.text || '') + '</div>'
        + '</div>'
      : '';

    el.innerHTML = '<div class="flow-left">' + leftHtml + '</div>'
      + '<div class="flow-center-col">' + centerHtml + '</div>'
      + '<div class="flow-right">' + rightHtml + '</div>';

    if (state.highlightTicketId && stepTicketId === state.highlightTicketId) {
      el.classList.add('flow-step--highlight');
    }

    box.appendChild(el);
  });

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
    var compBtns = document.getElementById('compChBtns');
    compBtns.innerHTML = '';
    var activeChans = Object.keys(seenChs);
    if (!activeChans.length) activeChans = ['whatsapp'];
    activeChans.forEach(function(ch) {
      var cm = chMeta(ch);
      var btn = document.createElement('button');
      btn.className = 'compose-ch-btn';
      btn.innerHTML = cm.svg + cm.label;
      compBtns.appendChild(btn);
    });
    document.getElementById('cinput').placeholder = 'Reply to ' + nm + '…';
  }

  renderDraftCard(conv);
}

// Render the human-in-the-loop editable draft card if this conversation has a pending
// held reply. The AI's proposed answer is shown in an editable box; the agent can correct
// it and Send (delivers to the customer + persists the outbound turn), or Discard it.
function renderDraftCard(conv) {
  var mount = document.getElementById('draftMount');
  if (!mount) return;
  var draft = state.pendingDrafts[conv.conversation_id];
  if (!draft) { mount.innerHTML = ''; return; }
  mount.innerHTML =
    '<div class="draft-card" data-draft-id="' + escH(draft.draft_id) + '">'
    + '<div class="draft-hdr"><span>✋ Held for review — edit &amp; send manually</span>'
    + '<span class="draft-reason">' + escH(draft.hold_reason || 'Escalated') + '</span></div>'
    + '<div class="draft-body">'
    + '<div class="draft-label">AI-proposed reply (editable)</div>'
    + '<textarea class="draft-textarea" id="draftText">' + escH(draft.draft_text || '') + '</textarea>'
    + '<div class="draft-actions">'
    + '<button class="draft-send-btn" onclick="sendDraft(this)">Send reply</button>'
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
    if (state.convDetail) delete state.pendingDrafts[state.convDetail.conversation_id];
    document.getElementById('draftMount').innerHTML = '';
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
    if (state.convDetail) delete state.pendingDrafts[state.convDetail.conversation_id];
    document.getElementById('draftMount').innerHTML = '';
    loadConversations();
  }).catch(function(err) {
    toast('Failed: ' + err.message);
    card.querySelectorAll('button').forEach(function(b){ b.disabled = false; });
  });
};

function renderRight(conv, tickets) {
  var conv_meta = state.convs.find(function(c) { return c.conversation_id === conv.conversation_id; }) || conv;
  var nm = customerLabel(conv_meta);
  var ini = customerInitials(conv_meta);
  document.getElementById('rpav').textContent = ini;
  document.getElementById('rpnm').textContent = nm;
  document.getElementById('rpsub').textContent = conv_meta.customer_id || '';
  document.getElementById('rpcontact').innerHTML = '';

  var turns = conv.turns || [];
  var seenChs = {};
  turns.forEach(function(t) { if (t.channel) seenChs[t.channel] = true; });
  var rpchs = document.getElementById('rpchs');
  rpchs.innerHTML = Object.keys(seenChs).map(function(ch) {
    var cm = chMeta(ch);
    return '<span class="cp ' + cm.pill + '" style="font-size:10px">' + cm.svg + cm.label + '</span>';
  }).join('');

  var NEG_KW = ['angry','bad','terrible','frustrated','late','failed','problem','damaged','not received','not credited','charged twice','cancel','fraud','stolen','unauthorized','incorrect charge','overdue','default','claim rejected','policy lapsed','blocked account','money gone','wrong transfer','human agent','human representative'];
  var POS_KW = ['thanks','thank you','great','good','helpful','resolved','approved','credited','disbursed','processed','excellent','perfect','awesome'];
  function clientSentiment(text) {
    var t = (text || '').toLowerCase();
    if (NEG_KW.some(function(w){ return t.indexOf(w) !== -1; })) return 'negative';
    if (POS_KW.some(function(w){ return t.indexOf(w) !== -1; })) return 'positive';
    return 'neutral';
  }
  var inbound = turns.filter(function(t) { return t.direction === 'inbound'; });
  var sentCounts = { positive: 0, neutral: 0, negative: 0 };
  inbound.forEach(function(t) {
    var s = (t.metadata && t.metadata.sentiment) ? t.metadata.sentiment.toLowerCase() : clientSentiment(t.text);
    if (sentCounts[s] !== undefined) sentCounts[s]++;  else sentCounts.neutral++;
  });
  var total = inbound.length || 1;
  var negPct = Math.round((sentCounts.negative / total) * 100);
  var posPct = Math.round((sentCounts.positive / total) * 100);
  var neuPct = Math.max(0, 100 - negPct - posPct);
  var msgCount = Math.min(inbound.length, 5) || 1;
  var sentLbl, sentClr, sentTrend;
  if (negPct >= 60) {
    sentLbl = 'Very frustrated'; sentClr = '#dc2626';
    sentTrend = 'Sharply declining · last ' + Math.min(msgCount, 4) + ' messages';
  } else if (negPct >= 30) {
    sentLbl = 'Frustrated'; sentClr = 'var(--red-t)';
    sentTrend = 'Trending negative · last ' + Math.min(msgCount, 3) + ' messages';
  } else if (posPct >= 55) {
    sentLbl = 'Positive'; sentClr = 'var(--grn-t)';
    sentTrend = 'Consistently positive';
  } else {
    sentLbl = 'Neutral'; sentClr = 'var(--amb-t)';
    sentTrend = 'Stable over last ' + msgCount + ' messages';
  }

  var intents = turns.filter(function(t) { return t.intent; }).map(function(t) { return t.intent; });
  var uniqueIntents = intents.filter(function(v,i,a){ return a.indexOf(v)===i; }).slice(0,3);

  var _snapTickets = (tickets || [].concat(_allTickets.open, _allTickets.closed))
    .filter(function(t) { return t.conversation_id === conv.conversation_id && (t.status === 'open' || t.status === 'in_progress'); });

  // Tenure — placeholder until graph API responds with registration_date
  var tenureLbl = '—';
  function calcTenure(dateStr) {
    if (!dateStr) return '—';
    var d = new Date(dateStr);
    if (isNaN(d)) return '—';
    var msDiff = Date.now() - d.getTime();
    var years  = Math.floor(msDiff / (1000 * 60 * 60 * 24 * 365));
    var months = Math.floor(msDiff / (1000 * 60 * 60 * 24 * 30));
    if (years  >= 1) return years  + ' yr' + (years  > 1 ? 's' : '');
    if (months >= 1) return months + ' mo';
    return '< 1 mo';
  }

  // Churn risk heuristic: negative sentiment + high-urgency turns + open tickets
  var highUrgCount = turns.filter(function(t) {
    var u = (t.urgency || '').toLowerCase();
    return u === 'high' || u === 'critical';
  }).length;
  var churnScore = negPct + Math.min(highUrgCount * 15, 45) + Math.min(_snapTickets.length * 10, 30);
  var churnLbl, churnClr;
  if (churnScore >= 50) { churnLbl = 'High'; churnClr = 'var(--red-t)'; }
  else if (churnScore >= 20) { churnLbl = 'Medium'; churnClr = 'var(--amb-t)'; }
  else { churnLbl = 'Low'; churnClr = 'var(--grn-t)'; }

  var body = document.getElementById('rpbody');
  body.innerHTML = ''
    + '<div class="rpcard"><div class="rplbl">Sentiment</div>'
    + '<div class="ssc" style="color:' + sentClr + '">' + escH(sentLbl) + '</div>'
    + '<div class="ssub">' + escH(sentTrend) + '</div>'
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
    + '<div class="rpcard"><div class="rplbl">Profile snapshot</div>'
    + '<div class="mgrid">'
    + '<div class="mc"><div class="mv" id="snap-tenure">' + escH(tenureLbl) + '</div><div class="ml">Tenure</div></div>'
    + '<div class="mc"><div class="mv" style="color:' + churnClr + '">' + escH(churnLbl) + '</div><div class="ml">Churn risk</div></div>'
    + '<div class="mc"><div class="mv" id="snap-loans">—</div><div class="ml">Loans</div></div>'
    + '<div class="mc"><div class="mv" id="snap-claims">—</div><div class="ml">Claims</div></div>'
    + '</div></div>'
    + (uniqueIntents.length ? '<div class="rpcard"><div class="rplbl">Detected intents</div>'
    + uniqueIntents.map(function(i) { return '<div style="font-size:11px;font-weight:500;padding:4px 8px;background:var(--blue-bg);border:1px solid var(--blue-bd);color:var(--blue-t);border-radius:20px;display:inline-block;margin:2px">' + escH(i.replace(/_/g,' ')) + '</div>'; }).join('')
    + '</div>' : '');

  // Async: fetch loans/claims count from Neo4j via customer graph endpoint
  var _snapCustId = conv_meta.customer_id;
  if (_snapCustId) {
    api('/admin/customers/' + encodeURIComponent(_snapCustId) + '/graph').then(function(g) {
      var loansEl = document.getElementById('snap-loans');
      var claimsEl = document.getElementById('snap-claims');
      if (loansEl) loansEl.textContent = g.loan_count;
      if (claimsEl) claimsEl.textContent = g.claim_count;
      var tenureEl = document.getElementById('snap-tenure');
      if (tenureEl && g.registration_date) tenureEl.textContent = calcTenure(g.registration_date);

      // Extract email and phone from channel identifiers
      var ids = g.identifiers || [];
      var emailId = null, phoneId = null;
      ids.forEach(function(id) {
        if (id.channel === 'email') emailId = id.identifier;
        if (id.channel === 'whatsapp') phoneId = id.identifier;
      });

      // Infer name from email: "fathima.devasahayam@..." → "Fathima Devasahayam"
      function inferName(email) {
        if (!email) return null;
        return email.split('@')[0].split(/[._-]/).map(function(w) {
          return w.charAt(0).toUpperCase() + w.slice(1);
        }).join(' ');
      }
      var inferredName = inferName(emailId);

      // Update name and avatar initials
      if (inferredName) {
        document.getElementById('rpnm').textContent = inferredName;
        var ini = inferredName.split(' ').slice(0,2).map(function(w){return w[0];}).join('').toUpperCase();
        document.getElementById('rpav').textContent = ini;
      }
      // Customer ID row (no prefix)
      document.getElementById('rpsub').textContent = _snapCustId || '';
      // Email + phone inline under customer ID
      var contactEl = document.getElementById('rpcontact');
      if (contactEl) {
        var parts = [];
        if (emailId) parts.push(escH(emailId));
        if (phoneId) parts.push(escH(phoneId));
        contactEl.innerHTML = parts.length
          ? '<div style="font-size:10px;color:var(--t3);margin-top:2px;line-height:1.6">' + parts.join('&nbsp;&nbsp;') + '</div>'
          : '';
      }
    }).catch(function() {});
  }

  var allTickets = tickets || [].concat(_allTickets.open, _allTickets.closed);
  var convTickets = allTickets.filter(function(t) { return t.conversation_id === conv.conversation_id; });
  if (convTickets.length) {
    var tktHtml = convTickets.slice(0,4).map(function(t) {
      var stBg = t.status === 'resolved' ? 'background:var(--grn-bg);border-color:var(--grn-bd);color:var(--grn-t)' :
                 t.status === 'open' || t.status === 'in_progress' ? 'background:var(--amb-bg);border-color:var(--amb-bd);color:var(--amb-t)' :
                 'background:var(--surf2);border-color:var(--bdr);color:var(--t3)';
      return '<div class="tkt-item"><div class="tkt-head">'
        + '<span class="tkt-id">' + escH(t.ticket_id.slice(0,16)) + '</span>'
        + '<span class="tkt-st" style="' + stBg + '">' + escH(t.status) + '</span>'
        + '</div><div class="tkt-desc">' + escH((t.title||t.intent||'').slice(0,60)) + '</div></div>';
    }).join('');
    body.innerHTML += '<div class="rpcard"><div class="rplbl">Tickets (' + convTickets.length + ')</div>' + tktHtml + '</div>';
  }

  body.innerHTML += '<div class="rpcard" id="rpNbaCard"><div class="rplbl">Recommended actions</div>'
    + '<div id="rpNbaBody" style="font-size:11px;color:var(--t3)">Checking…</div></div>';
  var nbaTicketId = convTickets.length ? convTickets[0].ticket_id : '';
  var nbaUrl = '/admin/agent-assist/next-best-actions?conversation_id=' + encodeURIComponent(conv.conversation_id)
    + (nbaTicketId ? '&ticket_id=' + encodeURIComponent(nbaTicketId) : '');
  api(nbaUrl).then(function(result) {
    renderNbaActions(result.actions || []);
  }).catch(function() {
    var el = document.getElementById('rpNbaBody');
    if (el) el.textContent = 'Unavailable';
  });
}

function renderNbaActions(actions) {
  var el = document.getElementById('rpNbaBody');
  if (!el) return;
  if (!actions.length) {
    el.textContent = 'No recommendations right now.';
    return;
  }
  el.innerHTML = actions.map(function(a) {
    var isCrossSell = a.action_type === 'cross_sell';
    var badge = isCrossSell
      ? '<span class="nba-badge nba-badge-crosssell">Cross-sell</span>'
      : '<span class="nba-badge">' + escH(a.action_type.replace(/_/g,' ')) + '</span>';
    return '<div class="nba-item" data-rec-id="' + escH(a.recommendation_id) + '">'
      + badge
      + '<div class="nba-reason">' + escH(a.reason) + '</div>'
      + '<div class="nba-actions">'
      + '<button class="nba-approve-btn" onclick="decideNba(this,\'approved\')">Approve</button>'
      + '<button class="nba-dismiss-btn" onclick="decideNba(this,\'dismissed\')">Dismiss</button>'
      + '</div></div>';
  }).join('');
}

window.decideNba = function(btn, status) {
  var item = btn.closest('.nba-item');
  var recId = item ? item.getAttribute('data-rec-id') : null;
  if (!recId) return;
  btn.parentElement.querySelectorAll('button').forEach(function(b) { b.disabled = true; });
  api('/admin/agent-assist/recommendations/' + encodeURIComponent(recId) + '/decision', {
    method: 'POST',
    body: JSON.stringify({ status: status }),
  }).then(function() {
    toast(status === 'approved' ? 'Recommendation approved' : 'Recommendation dismissed');
    if (item) item.style.opacity = '0.4';
  }).catch(function(err) {
    toast('Failed: ' + err.message);
    btn.parentElement.querySelectorAll('button').forEach(function(b) { b.disabled = false; });
  });
};

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

window.doResolve = function() {
  if (!state.convDetail) return;
  if (state.convDetail.status === 'closed' || state.convDetail.status === 'resolved') return;
  showConfirm({
    icon: '<svg viewBox="0 0 24 24" width="36" height="36" fill="var(--grn)"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/></svg>',
    title: 'Resolve conversation',
    msg: 'This will close the latest open ticket and mark the conversation as resolved. This action cannot be undone.',
    okLabel: 'Resolve',
    okColor: 'var(--grn)',
    onConfirm: execResolve
  });
};

async function execResolve() {
  try {
    var convId = state.convDetail.conversation_id;
    var adminUser = currentUser ? currentUser.username : 'admin';

    // Find the latest open ticket for this conversation
    var tickets = await api('/admin/tickets');
    var openTicket = tickets.filter(function(t) {
      return t.conversation_id === convId && (t.status === 'open' || t.status === 'in_progress');
    }).sort(function(a, b) { return new Date(b.created_at) - new Date(a.created_at); })[0];

    if (openTicket) {
      await api('/admin/tickets/' + openTicket.ticket_id + '/status', {
        method: 'PATCH',
        body: JSON.stringify({ status: 'resolved', actor: adminUser })
      });
      // Update cached ticket lists immediately so right panel reflects the change
      _allTickets.open = _allTickets.open.filter(function(t) { return t.ticket_id !== openTicket.ticket_id; });
      openTicket.status = 'resolved';
      _allTickets.closed = [openTicket].concat(_allTickets.closed);
    }

    // Update local state
    state.convDetail.status = 'resolved';
    state.convs.forEach(function(c) { if (c.conversation_id === convId) c.status = 'resolved'; });
    renderQueue();
    renderCentre(state.convDetail);
    renderRight(state.convDetail, [].concat(_allTickets.open, _allTickets.closed));

    // Refresh tickets panel badge/table
    api('/admin/tickets').then(function(tks) {
      var open = tks.filter(function(t) { return t.status === 'open' || t.status === 'in_progress'; });
      var badge = document.getElementById('ticketsBadge');
      if (open.length > 0) { badge.style.display = 'flex'; badge.textContent = open.length > 9 ? '9+' : open.length; }
      else { badge.style.display = 'none'; }
      if (activePage === 'tickets') { _allTickets.open = open; _allTickets.closed = tks.filter(function(t) { return t.status === 'resolved' || t.status === 'closed'; }); filterTickets(); }
    }).catch(function(){});

    toast('Conversation resolved · ticket closed ✓');
  } catch(e) {
    toast('Error: ' + e.message);
  }
}

window.doEscalate = function() {
  if (!state.convDetail) return;
  if (state.convDetail.status === 'closed' || state.convDetail.status === 'resolved') return;
  showConfirm({
    icon: '<svg viewBox="0 0 24 24" width="36" height="36" fill="var(--red)"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>',
    title: 'Escalate to senior support',
    msg: 'This will escalate the conversation to the senior support team and add an escalation note to the chat.',
    okLabel: 'Escalate',
    okColor: 'var(--red)',
    onConfirm: execEscalate
  });
};

function execEscalate() {
  var turns = state.convDetail.turns || [];
  turns.push({ direction: 'outbound', channel: null, text: '[Escalated to senior support team]', created_at: new Date().toISOString() });
  renderCentre(state.convDetail);
  toast('Escalated to senior support');
}

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
    ]);
    renderOverview(results[0]);
    renderChannelBars(results[1]);
    renderIntentBars(results[2]);
    renderAgentPanel(results[3]);
    renderFeedList(results[4], false);
    renderLlmUsagePanel(results[5]);
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
    { val: d.total_open, lbl: 'Open tickets', sub: d.total_conversations + ' total conversations', clr: d.total_open > 20 ? 'var(--amb-t)' : 'var(--t1)', subClr: '' },
    { val: d.total_resolved, lbl: 'Resolved', sub: d.total_customers + ' customers', clr: 'var(--grn-t)', subClr: '' },
    { val: negPct.toFixed(0) + '%', lbl: 'Negative sentiment today', sub: negDeltaLabel, clr: 'var(--red-t)', subClr: negDeltaClr },
    { val: frtLabel, lbl: 'Avg resolution time today', sub: frtDeltaLabel, clr: 'var(--t1)', subClr: frtDeltaClr },
  ];
  document.getElementById('overviewGrid').innerHTML = cards.map(function(c) {
    return '<div class="stat-card"><div class="stat-val" style="color:' + c.clr + '">' + c.val + '</div><div class="stat-lbl">' + c.lbl + '</div>' + (c.sub ? '<div class="stat-sub" style="color:' + (c.subClr || 'var(--t3)') + '">' + c.sub + '</div>' : '') + '</div>';
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
    return '<div class="bar-row"><span class="bar-label" title="' + escH(item[lk]) + '">' + escH(String(item[lk])) + '</span>'
      + '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%;background:' + clr + '"></div></div>'
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
    { val: calls, lbl: 'LLM calls' },
    { val: (totals.total_tokens || 0).toLocaleString(), lbl: 'Tokens' },
    { val: '$' + cost.toFixed(6), lbl: 'Estimated cost' },
    { val: avg.toFixed(0) + ' ms', lbl: 'Avg latency' },
  ];
  var opRows = (data.by_operation || []).map(function(row) {
    return '<tr><td style="font-weight:500;color:var(--t1)">' + escH((row.operation || 'unknown').replace(/_/g, ' ')) + '</td>'
      + '<td>' + (row.calls || 0) + '</td>'
      + '<td>' + Number(row.total_tokens || 0).toLocaleString() + '</td>'
      + '<td>$' + Number(row.estimated_cost_usd || 0).toFixed(6) + '</td></tr>';
  }).join('');
  el.innerHTML = '<div class="stat-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:12px">'
    + cards.map(function(c) {
      return '<div class="stat-card"><div class="stat-val">' + c.val + '</div><div class="stat-lbl">' + c.lbl + '</div></div>';
    }).join('')
    + '</div>'
    + '<table class="mini-table"><thead><tr><th>Operation</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr></thead><tbody>'
    + (opRows || '<tr><td colspan="4">No operation breakdown yet</td></tr>')
    + '</tbody></table>';
}

function renderSentimentPanel(data) {
  var el = document.getElementById('sentimentPanel');
  var total = data.total || 0;
  if (!total) { el.innerHTML = '<div class="empty-state">No sentiment data yet</div>'; return; }
  var pos = Math.round((data.positive/total)*100);
  var neg = Math.round((data.negative/total)*100);
  var neu = Math.max(0, 100-pos-neg);
  el.innerHTML = '<div style="font-size:22px;font-weight:600;margin-bottom:4px">' + total + ' messages</div>'
    + '<div class="sent-bar"><div class="sent-pos" style="flex:'+pos+'"></div><div class="sent-neu" style="flex:'+neu+'"></div><div class="sent-neg" style="flex:'+neg+'"></div></div>'
    + '<div class="sent-row"><span class="sent-lbl" style="color:var(--grn-t)">'+pos+'% positive</span><span class="sent-lbl">'+neu+'% neutral</span><span class="sent-lbl" style="color:var(--red-t)">'+neg+'% negative</span></div>';
}
function renderTrendPanel(data) {
  var el = document.getElementById('trendPanel');
  if (!data||!data.length) { el.innerHTML = '<div class="empty-state">No trend data yet</div>'; return; }
  var maxVal = Math.max.apply(null, data.map(function(d){return Math.max(d.created,d.resolved);}));
  el.innerHTML = data.map(function(d) {
    var cPct = maxVal>0 ? Math.round((d.created/maxVal)*100) : 0;
    var rPct = maxVal>0 ? Math.round((d.resolved/maxVal)*100) : 0;
    return '<div class="bar-row" style="margin-bottom:5px"><span class="bar-label" style="width:80px">' + d.date.slice(5) + '</span>'
      + '<div style="flex:1;display:flex;flex-direction:column;gap:2px">'
      + '<div class="bar-track" style="height:5px"><div class="bar-fill" style="width:'+cPct+'%;background:var(--blue)"></div></div>'
      + '<div class="bar-track" style="height:5px"><div class="bar-fill" style="width:'+rPct+'%;background:var(--grn)"></div></div>'
      + '</div><span class="bar-val" style="font-size:10px">'+d.created+'/'+d.resolved+'</span></div>';
  }).join('')
    + '<div style="display:flex;gap:12px;margin-top:6px"><span style="font-size:10px;color:var(--blue)">■ Created</span><span style="font-size:10px;color:var(--grn)">■ Resolved</span></div>';
}
function renderAgentPanel(data) {
  var el = document.getElementById('agentPanel');
  if (!data||!data.length) { el.innerHTML = '<div class="empty-state">No agent data yet</div>'; return; }
  var rows = data.map(function(a) {
    var avg = a.avg_handle_minutes>=60 ? (a.avg_handle_minutes/60).toFixed(1)+' hr' : a.avg_handle_minutes.toFixed(0)+' min';
    return '<tr><td style="font-weight:500;color:var(--t1)">'+escH(a.agent)+'</td><td>'+a.handled+'</td><td>'+avg+'</td></tr>';
  }).join('');
  el.innerHTML = '<table class="mini-table"><thead><tr><th>Team/Agent</th><th>Handled</th><th>Avg handle time</th></tr></thead><tbody>'+rows+'</tbody></table>';
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

    // 4. Tickets — refresh table if visible, badge otherwise
    if (activePage === 'tickets') {
      loadTickets();
    } else {
      api('/admin/tickets').then(function(tickets) {
        var open = tickets.filter(function(t) { return t.status === 'open' || t.status === 'in_progress'; });
        var badge = document.getElementById('ticketsBadge');
        if (open.length > 0) { badge.style.display = 'flex'; badge.textContent = open.length > 9 ? '9+' : open.length; }
        else { badge.style.display = 'none'; }
      }).catch(function() {});
    }

    // 5. Analytics charts — full refresh if analytics page is open
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
  var waStatus = 'disconnected', emStatus = 'disconnected';
  try { var waRes = await api('/admin/whatsapp/status'); waStatus = waRes.connected ? 'connected' : (waRes.mode === 'local_test' ? 'connected' : 'disconnected'); } catch(e){}
  try { var emRes = await api('/admin/email/status'); emStatus = emRes.configured ? 'connected' : 'disconnected'; } catch(e){}
  var inboxRes = null;
  try { inboxRes = await api('/admin/email-inbox/status'); } catch(e){}

  var connectors = [
    { nm:'WhatsApp Business', desc:'Meta Cloud API · inbound webhook + outbound', status: waStatus,
      icon:'background:#22c55e', svg:'<svg viewBox="0 0 24 24" fill="#fff"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413z"/><path d="M20.52 3.449C12.831-3.984.106 1.407.101 11.893c0 2.096.549 4.14 1.595 5.945L.057 24l6.335-1.652c1.746.943 3.71 1.444 5.71 1.447h.006c9.756 0 15.466-8.65 11.466-16.001a11.816 11.816 0 0 0-3.054-4.345z"/></svg>' },
    { nm:'Gmail SMTP', desc:'Outbound email delivery to customers', status: emStatus,
      icon:'background:#ea4335', svg:'<svg viewBox="0 0 24 24" fill="#fff"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>' },
    { nm:'Call', desc:'Voice channel integration', status:'phase2',
      icon:'background:#6366f1', svg:'<svg viewBox="0 0 24 24" fill="#fff"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg>' },
    { nm:'Jira CRM', desc:'Ticket synchronisation', status:'disconnected',
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

  // Email Inbox (IMAP) — extended card with live stats and Poll Now button
  var inboxCard = document.createElement('div');
  inboxCard.className = 'conn-card';
  inboxCard.id = 'connInboxCard';
  var inboxConfigured = inboxRes && inboxRes.configured;
  var inboxBadgeCls = inboxConfigured ? 'connected' : 'disconnected';
  var inboxBadgeTxt = inboxConfigured ? 'Active' : 'Not configured';
  var lastPollTxt = (inboxRes && inboxRes.last_poll_ts)
    ? new Date(inboxRes.last_poll_ts * 1000).toLocaleTimeString() : 'Never';
  var processedTxt = inboxRes ? String(inboxRes.emails_processed) : '0';
  var intervalTxt = inboxRes ? inboxRes.poll_interval_seconds + 's' : '30s';
  var mailboxTxt = (inboxRes && inboxRes.configured) ? escH(inboxRes.mailbox || 'INBOX') : '—';
  var errorHtml = (inboxRes && inboxRes.last_error)
    ? '<div style="font-size:10px;color:#dc2626;margin-top:6px;word-break:break-all">'+escH(inboxRes.last_error)+'</div>' : '';
  inboxCard.innerHTML =
    '<div class="conn-hdr">'
    + '<div class="conn-icon" style="background:#db4437"><svg viewBox="0 0 24 24" fill="#fff"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg></div>'
    + '<div><div class="conn-nm">Email Inbox (IMAP)</div><div class="conn-desc">Inbound customer emails · Gmail IMAP auto-poll</div></div>'
    + '</div>'
    + '<div class="conn-status"><span class="conn-badge ' + inboxBadgeCls + '">' + inboxBadgeTxt + '</span></div>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;font-size:11px;color:var(--t2);margin-top:10px">'
    + '<span style="color:var(--t3)">Mailbox</span><span>' + mailboxTxt + '</span>'
    + '<span style="color:var(--t3)">Poll interval</span><span>' + intervalTxt + '</span>'
    + '<span style="color:var(--t3)">Last poll</span><span id="inboxLastPoll">' + lastPollTxt + '</span>'
    + '<span style="color:var(--t3)">Emails processed</span><span id="inboxProcessed">' + processedTxt + '</span>'
    + '</div>'
    + errorHtml
    + '<button class="sim-btn" id="inboxPollBtn" onclick="triggerEmailInboxPoll()" style="margin-top:12px;font-size:11px;padding:5px 12px">'
    + (inboxConfigured ? 'Poll now' : 'Set IMAP_USERNAME + IMAP_PASSWORD in .env')
    + '</button>'
    + '<div class="sim-status" id="inboxPollStatus" style="display:none;font-size:11px;margin-top:6px"></div>';
  grid.appendChild(inboxCard);
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

// ── TICKETS ──────────────────────────────────────────────────────────────────
var _allTickets = { open: [], closed: [] };
var _convMap = {};

window.loadTickets = async function() {
  var spinner = document.getElementById('ticketsSpinner');
  if (spinner) spinner.classList.add('spinning');
  try {
    var results = await Promise.all([api('/admin/tickets'), api('/admin/conversations')]);
    var tickets = results[0], convs = results[1];

    _convMap = {};
    convs.forEach(function(c) { _convMap[c.conversation_id] = c; });

    var open   = tickets.filter(function(t) { return t.status === 'open' || t.status === 'in_progress'; });
    var closed = tickets.filter(function(t) { return t.status === 'resolved' || t.status === 'closed'; });
    open.sort(function(a, b) { return (b.priority_score || 0) - (a.priority_score || 0); });
    closed.sort(function(a, b) { return new Date(b.updated_at) - new Date(a.updated_at); });

    _allTickets.open   = open;
    _allTickets.closed = closed;

    var openBadge = document.getElementById('ticketsBadge');
    if (open.length > 0) { openBadge.style.display = 'flex'; openBadge.textContent = open.length > 9 ? '9+' : open.length; }
    else { openBadge.style.display = 'none'; }

    document.getElementById('openTktCount').textContent   = open.length   + ' ticket' + (open.length   !== 1 ? 's' : '');
    document.getElementById('closedTktCount').textContent = closed.length + ' ticket' + (closed.length !== 1 ? 's' : '');

    filterTickets();
  } catch(e) {
    document.getElementById('openTktBody').innerHTML = '<tr><td colspan="8" class="tkt-empty" style="color:var(--red-t)">' + escH(e.message) + '</td></tr>';
  } finally {
    if (spinner) spinner.classList.remove('spinning');
  }
};

window.filterTickets = function() {
  var oSearch = (document.getElementById('openTktSearch').value   || '').toLowerCase();
  var cSearch = (document.getElementById('closedTktSearch').value || '').toLowerCase();
  var oDate   = document.getElementById('openTktDate').value;
  var cDate   = document.getElementById('closedTktDate').value;
  var oFrom   = document.getElementById('openTktFrom').value;
  var oTo     = document.getElementById('openTktTo').value;
  var cFrom   = document.getElementById('closedTktFrom').value;
  var cTo     = document.getElementById('closedTktTo').value;
  renderTicketRows('openTktBody',   applyTktFilters(_allTickets.open,   oSearch, oDate, oFrom, oTo), false);
  renderTicketRows('closedTktBody', applyTktFilters(_allTickets.closed, cSearch, cDate, cFrom, cTo), true);
};

window.onTktDateChange = function(queue) {
  var sel = document.getElementById(queue + 'TktDate');
  var rangeEl = document.getElementById(queue + 'TktRange');
  if (sel.value === 'custom') {
    rangeEl.classList.remove('hidden');
  } else {
    rangeEl.classList.add('hidden');
    document.getElementById(queue + 'TktFrom').value = '';
    document.getElementById(queue + 'TktTo').value   = '';
  }
  filterTickets();
};

window.clearTktRange = function(queue) {
  document.getElementById(queue + 'TktFrom').value = '';
  document.getElementById(queue + 'TktTo').value   = '';
  document.getElementById(queue + 'TktDate').value = 'all';
  document.getElementById(queue + 'TktRange').classList.add('hidden');
  filterTickets();
};

function applyTktFilters(tickets, search, dateFilter, fromVal, toVal) {
  return tickets.filter(function(t) {
    if (search) {
      var conv = _convMap[t.conversation_id] || {};
      var custLbl = (conv.display_name && conv.display_name !== 'None' ? conv.display_name : '') || t.customer_id || '';
      var hay = [t.ticket_id, t.title, t.intent, t.assigned_team, custLbl].join(' ').toLowerCase();
      if (!hay.includes(search)) return false;
    }
    var created = new Date(t.created_at);
    if (dateFilter === 'custom') {
      if (fromVal) { var f = new Date(fromVal); f.setHours(0,0,0,0); if (created < f) return false; }
      if (toVal)   { var to = new Date(toVal);  to.setHours(23,59,59,999); if (created > to) return false; }
    } else if (dateFilter !== 'all') {
      var now = new Date(), cutoff;
      if      (dateFilter === 'today') cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      else if (dateFilter === '7d')    cutoff = new Date(now - 7  * 86400000);
      else if (dateFilter === '30d')   cutoff = new Date(now - 30 * 86400000);
      else if (dateFilter === 'month') cutoff = new Date(now.getFullYear(), now.getMonth(), 1);
      if (created < cutoff) return false;
    }
    return true;
  });
}

function tktCustomerCell(t) {
  var conv = _convMap[t.conversation_id] || {};
  var name = conv.display_name && conv.display_name !== 'None' && conv.display_name !== 'null'
    ? conv.display_name : null;
  var channel = (t.metadata && t.metadata.channel) ? t.metadata.channel.toLowerCase() : '';
  var label = name || ('cust_' + (t.customer_id || '').slice(-8));
  var icon = channel === 'whatsapp'
    ? '<svg viewBox="0 0 24 24" width="9" height="9" style="fill:#16a34a;flex-shrink:0"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51C10.25 6.01 10.052 6 9.853 6c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413z"/><path d="M20.52 3.449C12.831-3.984.106 1.407.101 11.893c0 2.096.549 4.14 1.595 5.945L.057 24l6.335-1.652c1.746.943 3.71 1.444 5.71 1.447h.006c9.756 0 15.466-8.65 11.466-16.001a11.816 11.816 0 0 0-3.054-4.345z"/></svg>'
    : channel === 'email'
    ? '<svg viewBox="0 0 24 24" width="9" height="9" style="fill:#2563eb;flex-shrink:0"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>'
    : '';
  return '<td class="tkt-customer"><div class="tkt-cust-inner">' + icon + '<span>' + escH(label) + '</span></div></td>';
}

function renderTicketRows(tbodyId, tickets, isClosed) {
  var tbody = document.getElementById(tbodyId);
  if (!tickets.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="tkt-empty">No tickets</td></tr>';
    return;
  }
  tbody.innerHTML = '';
  tickets.forEach(function(t) {
    var tr = document.createElement('tr');
    tr.className = 'tkt-row';
    tr.title = 'Click to open conversation in Inbox';

    var priCls = t.priority === 'critical' ? 'pri-crit' : t.priority === 'high' ? 'pri-high' : t.priority === 'medium' ? 'pri-med' : 'pri-low';
    var channel = (t.metadata && t.metadata.channel) ? t.metadata.channel : '—';
    var chMd = chMeta(channel);
    var dateCol = isClosed ? fmtDateTime(t.updated_at) : fmtDateTime(t.created_at);

    tr.innerHTML = '<td class="tkt-id-cell"><span class="tkt-id-pill">' + escH(t.ticket_id.slice(0, 14)) + '</span></td>'
      + '<td class="tkt-title-cell">' + escH((t.title || '—').slice(0, 48)) + '</td>'
      + '<td>' + escH(t.assigned_team || '—') + '</td>'
      + '<td><span class="tkt-pri ' + priCls + '">' + escH(t.priority || '—') + '</span></td>'
      + '<td class="tkt-intent">' + escH((t.intent || '—').replace(/_/g, ' ')) + '</td>'
      + tktCustomerCell(t)
      + '<td><span class="cp ' + chMd.pill + '" style="font-size:10px">' + chMd.svg + chMd.label + '</span></td>'
      + '<td>' + dateCol + '</td>';

    tr.addEventListener('click', function() { goToConversation(t.conversation_id, t.ticket_id); });
    tbody.appendChild(tr);
  });
}

function tktSlaCell(slaAt) {
  if (!slaAt) return '<span style="color:var(--t3)">—</span>';
  var due = new Date(slaAt);
  var now = new Date();
  var diff = due - now;
  var breached = diff < 0;
  var label = breached ? 'Breached' : fmtDuration(diff);
  var cls = breached ? 'color:var(--red-t);font-weight:600' : diff < 3600000 ? 'color:var(--amb-t);font-weight:600' : 'color:var(--t2)';
  return '<span style="' + cls + '" title="' + escH(slaAt) + '">' + label + '</span>';
}

function fmtDuration(ms) {
  var s = Math.floor(ms / 1000);
  if (s < 60) return s + 's';
  var m = Math.floor(s / 60);
  if (m < 60) return m + 'm';
  var h = Math.floor(m / 60);
  return h + 'h ' + (m % 60) + 'm';
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  var d = new Date(iso);
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
    + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function goToConversation(conversationId, ticketId) {
  if (!conversationId) return;
  state.highlightTicketId = ticketId || null;
  switchPage('inbox');
  selectConv(conversationId);
}

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
    tickets.forEach(function(ticket) {
      var item = document.createElement('div');
      item.className = 'user-ticket-item';
      var row = document.createElement('div');
      row.className = 'user-ticket-row';
      row.innerHTML =
        '<div class="user-ticket-main"><strong>' + escH(ticket.ticket_id || ticket.conversation_id) + '</strong>'
        + '<span>' + escH((ticket.message || '').replace('Customer portal request\\n\\n', '')) + '</span></div>'
        + '<div class="user-ticket-meta">' + escH(ticket.channel || '-') + '</div>'
        + '<div><span class="user-status-pill">' + escH(ticket.status || 'active') + '</span></div>'
        + '<div class="user-ticket-meta">' + escH(fmtDateTime(ticket.updated_at)) + '</div>';
      var detail = document.createElement('div');
      detail.className = 'user-ticket-detail';
      detail.style.display = 'none';
      item.appendChild(row);
      item.appendChild(detail);
      row.addEventListener('click', function() { toggleUserTicket(item, detail, ticket.conversation_id); });
      list.appendChild(item);
    });
  } catch(e) {
    list.innerHTML = '<div class="user-empty" style="color:var(--red-t)">' + escH(e.message) + '</div>';
  } finally {
    refresh.disabled = false;
    refresh.textContent = 'Refresh tickets';
  }
};

async function toggleUserTicket(item, detail, conversationId) {
  // Collapse if already open
  if (item.classList.contains('open')) {
    item.classList.remove('open');
    detail.style.display = 'none';
    return;
  }
  item.classList.add('open');
  detail.style.display = 'block';
  // Lazy-load full detail once; cache in the element so re-open is instant
  if (detail.dataset.loaded === '1') return;
  detail.innerHTML = '<span class="utd-loading">Loading…</span>';
  try {
    var ticket = await userApi('/user/tickets/' + encodeURIComponent(conversationId));
    var msg = (ticket.message || '').replace('Customer portal request\\n\\n', '') || '—';
    var resp = ticket.latest_response || 'Response pending';
    detail.innerHTML =
      '<span class="utd-label">Your message</span><p class="utd-msg">' + escH(msg) + '</p>'
      + '<span class="utd-label">Latest response</span><p class="utd-resp">' + escH(resp) + '</p>';
    detail.dataset.loaded = '1';
  } catch(e) {
    detail.innerHTML = '<span class="utd-loading" style="color:var(--red-t)">' + escH(e.message) + '</span>';
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
  // Tickets: fallback poll every 10s
  rtTimers.push(setInterval(function() {
    if (activePage === 'tickets') loadTickets();
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
