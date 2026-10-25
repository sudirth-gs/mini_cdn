/* ═══════════════════════════════════════════════════════════
   Mini CDN Dashboard — Interactive JavaScript
   ═══════════════════════════════════════════════════════════ */

const ROUTER = 'http://127.0.0.1:9000';
const REFRESH_MS = 5000;
const MAX_LOG = 30;
const EDGE_IDS = ['edge-1', 'edge-2', 'edge-3'];
const EDGE_NUM = { 'edge-1': 1, 'edge-2': 2, 'edge-3': 3 };

/** @type {{ time: string, file: string, edge: string, cache: string, latency: string }[]} */
const requestLog = [];
let animating = false;
let refreshTimer = null;

/* ═══════════════════════════════════════════════════════════
   INITIALIZATION
   ═══════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  fetchStats();
  refreshTimer = setInterval(fetchStats, REFRESH_MS);
});

/* ═══════════════════════════════════════════════════════════
   FETCH STATS FROM ROUTER
   ═══════════════════════════════════════════════════════════ */
async function fetchStats() {
  try {
    const res = await fetch(`${ROUTER}/stats`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    updateDashboard(data);
    stampUpdated();
  } catch (err) {
    console.error('[CDN] Stats fetch failed:', err);
    markAllOffline();
    stampUpdated('⚠ Connection error');
  }
}

/* ── Update all dashboard elements from stats ──────────── */
function updateDashboard(data) {
  // Router summary
  setText('total-requests', data.total_requests ?? 0);
  setText('strategy', data.strategy ?? 'round-robin');

  const edgeStats = data.edge_stats ?? {};
  let totalHits = 0, totalMisses = 0;

  EDGE_IDS.forEach(id => {
    const s = edgeStats[id];
    const n = EDGE_NUM[id];
    if (!s || s.error) {
      markEdgeOffline(n);
      return;
    }

    markEdgeOnline(n);
    setText(`region-edge-${n}`, s.region ?? '—');
    setText(`reqs-edge-${n}`, s.total_requests ?? 0);
    setText(`hits-edge-${n}`, s.cache_hits ?? 0);
    setText(`misses-edge-${n}`, s.cache_misses ?? 0);

    const lat = s.latency_ms ?? 0;
    const latBadge = document.getElementById(`latency-badge-edge-${n}`);
    if (latBadge) {
      latBadge.textContent = `${lat}ms`;
      latBadge.className = `badge ${latencyColor(lat)}`;
    }

    const hits = s.cache_hits ?? 0;
    const misses = s.cache_misses ?? 0;
    totalHits += hits;
    totalMisses += misses;
    const rate = hits + misses > 0 ? Math.round(hits / (hits + misses) * 100) : 0;
    setText(`hitrate-edge-${n}`, `${rate}%`);
    const fill = document.getElementById(`hitrate-fill-edge-${n}`);
    if (fill) fill.style.width = `${rate}%`;

    // Cached files (each entry can be a string or {filename: ...} object)
    const cachedDiv = document.getElementById(`cached-edge-${n}`);
    const rawFiles = s.cached_files ?? [];
    const files = rawFiles.map(f => typeof f === 'string' ? f : f.filename ?? f);
    if (cachedDiv) {
      cachedDiv.innerHTML = files.length > 0
        ? files.map(f => `<span class="badge badge-purple">${esc(f)}</span>`).join('')
        : '<span class="badge badge-muted">Empty</span>';
    }

    // Topology status dot
    const dot = document.getElementById(`topo-edge${n}-dot`);
    if (dot) { dot.classList.remove('dot-offline'); dot.classList.add('dot-online'); }
  });

  const overallRate = totalHits + totalMisses > 0
    ? Math.round(totalHits / (totalHits + totalMisses) * 100) : 0;
  setText('overall-hit-rate', `${overallRate}%`);
}

/* ═══════════════════════════════════════════════════════════
   SEND REQUEST — with animated topology
   ═══════════════════════════════════════════════════════════ */
async function sendRequest() {
  const file = document.getElementById('file-select').value;
  const btn = document.getElementById('send-btn');
  btn.disabled = true;

  // Reset topology visuals
  clearTopologyEffects();

  const narration = document.getElementById('narration');
  const nText = document.getElementById('narration-text');

  try {
    /* STEP 1: Client → Router */
    narrate('💻 Client sends request for ' + file + '…', '');
    highlightLine('line-client-router', 'active');
    glowNode('node-client', 'glow-blue');
    await sleep(400);

    /* STEP 2: Router picks an edge */
    glowNode('node-router', 'glow-blue');
    narrate('🔀 Router receives request, selecting next edge server (round-robin)…', '');
    await sleep(400);

    /* STEP 3: Actually send the request */
    const start = performance.now();
    const res = await fetch(`${ROUTER}/files/${file}`);
    const elapsed = Math.round(performance.now() - start);

    const cacheStatus = res.headers.get('X-Cache') || 'UNKNOWN';
    const edgeId = res.headers.get('X-Edge-ID') || '?';
    const contentType = res.headers.get('Content-Type') || '?';
    const edgeN = EDGE_NUM[edgeId] ?? 1;

    /* STEP 3b: Highlight the chosen edge */
    clearAllLines();
    highlightLine('line-client-router', 'active');
    highlightLine(`line-router-edge${edgeN}`, 'active');
    glowNode(`node-edge-${edgeN}`, 'glow-blue');

    if (cacheStatus === 'HIT') {
      narrate(`📦 Edge ${edgeN} has "${file}" in cache → `, 'hit');
      setText('narration-text',
        `📦 Edge ${edgeN} found "${file}" in cache! Serving directly — no need to contact the origin.`
      );
      narration.className = 'narration narration-hit';
      await sleep(300);
    } else {
      narrate(`📦 Edge ${edgeN} does NOT have "${file}" cached → fetching from Origin…`, 'miss');
      narration.className = 'narration narration-miss';
      highlightLine(`line-edge${edgeN}-origin`, 'active-miss');
      glowNode('node-origin', 'glow-orange');
      await sleep(500);

      /* Show origin returning the file */
      highlightLine(`line-edge${edgeN}-origin`, 'active-return');
      glowNode('node-origin', 'glow-green');
      setText('narration-text',
        `🗄️ Origin server sent "${file}" → Edge ${edgeN} cached it. Next request will be a HIT!`
      );
      narration.className = 'narration narration-miss';
      await sleep(300);
    }

    /* STEP 4: Response back to client */
    highlightLine('line-client-router', 'active-return');
    highlightLine(`line-router-edge${edgeN}`, 'active-return');
    glowNode('node-client', 'glow-green');

    const finalMsg = cacheStatus === 'HIT'
      ? `✅ Response delivered! CACHE HIT from Edge ${edgeN} (${edgeId}) in ${elapsed}ms`
      : `✅ Response delivered! CACHE MISS — fetched from origin via Edge ${edgeN} (${edgeId}) in ${elapsed}ms`;
    setText('narration-text', finalMsg);
    narration.className = cacheStatus === 'HIT' ? 'narration narration-hit' : 'narration narration-miss';

    /* Update result panel */
    showResult(res.status, cacheStatus, edgeId, elapsed, contentType);

    /* Log it */
    addLogEntry(file, edgeId, cacheStatus, elapsed);

    /* Refresh stats to reflect the new request */
    setTimeout(fetchStats, 300);

  } catch (err) {
    narrate('❌ Request failed! Is the CDN running? → ' + err.message, '');
    showResult('ERR', 'ERROR', '—', '—', '—');
  } finally {
    btn.disabled = false;
    setTimeout(clearTopologyEffects, 3000);
  }
}

/* ── Send burst of 10 requests ─────────────────────────── */
async function sendBurst() {
  const files = [
    'index.html', 'style.css', 'api.json', 'blog.html',
    'theme-dark.css', 'app.js', 'data.json', 'gallery.html',
    'analytics.csv', 'docs.md'
  ];
  for (let i = 0; i < 10; i++) {
    const file = files[i % files.length];
    document.getElementById('file-select').value = file;
    await sendRequest();
    await sleep(200);
  }
}

/* ═══════════════════════════════════════════════════════════
   TOPOLOGY ANIMATION HELPERS
   ═══════════════════════════════════════════════════════════ */
function highlightLine(id, cls) {
  const el = document.getElementById(id);
  if (el) el.classList.add(cls);
}
function clearAllLines() {
  document.querySelectorAll('.topology-line').forEach(l => {
    l.classList.remove('active', 'active-miss', 'active-return');
  });
}
function glowNode(id, cls) {
  const box = document.querySelector(`#${id} .node-box`);
  if (box) box.classList.add(cls);
}
function clearTopologyEffects() {
  clearAllLines();
  document.querySelectorAll('.node-box').forEach(b => {
    b.classList.remove('glow-blue', 'glow-green', 'glow-orange', 'glow-red');
  });
}
function narrate(text, type) {
  const el = document.getElementById('narration-text');
  const box = document.getElementById('narration');
  if (el) el.textContent = text;
  box.className = 'narration' + (type === 'hit' ? ' narration-hit' : type === 'miss' ? ' narration-miss' : '');
}

/* ═══════════════════════════════════════════════════════════
   RESULT PANEL
   ═══════════════════════════════════════════════════════════ */
function showResult(status, cache, edge, latency, ctype) {
  const panel = document.getElementById('request-result');
  panel.classList.remove('hidden');

  setText('res-status', status);
  document.getElementById('res-status').className = `badge ${status === 200 ? 'badge-green' : 'badge-red'}`;

  setText('res-cache', cache);
  document.getElementById('res-cache').className = `badge ${cache === 'HIT' ? 'badge-green' : 'badge-red'}`;

  setText('res-edge', edge);
  setText('res-latency', `${latency}ms`);
  setText('res-ctype', ctype);
}

/* ═══════════════════════════════════════════════════════════
   REQUEST LOG
   ═══════════════════════════════════════════════════════════ */
function addLogEntry(file, edge, cache, latency) {
  const entry = {
    time: new Date().toLocaleTimeString(),
    file, edge, cache,
    latency: `${latency}ms`
  };
  requestLog.unshift(entry);
  if (requestLog.length > MAX_LOG) requestLog.pop();
  renderLog();
}

function renderLog() {
  const container = document.getElementById('log-container');
  if (requestLog.length === 0) {
    container.innerHTML = '<div class="log-empty">No requests yet. Hit "Send Request" above!</div>';
    return;
  }
  container.innerHTML = requestLog.map((e, i) => `
    <div class="log-entry ${i === 0 ? 'log-entry-new' : ''}">
      <span class="log-time">${esc(e.time)}</span>
      <span class="log-file">${esc(e.file)}</span>
      <span class="log-edge">${esc(e.edge)}</span>
      <span class="badge ${e.cache === 'HIT' ? 'badge-green' : 'badge-red'}">${esc(e.cache)}</span>
      <span class="log-latency">${esc(e.latency)}</span>
    </div>
  `).join('');
}

/* ═══════════════════════════════════════════════════════════
   CACHE CONTROL
   ═══════════════════════════════════════════════════════════ */
async function invalidateFile() {
  const filename = document.getElementById('invalidate-input').value.trim();
  if (!filename) { alert('Enter a filename to invalidate.'); return; }
  try {
    const res = await fetch(`${ROUTER}/invalidate/${filename}`, { method: 'POST' });
    const data = await res.json();
    narrate(`🗑️ Invalidated "${filename}" from all edge caches.`, '');
    document.getElementById('invalidate-input').value = '';
    setTimeout(fetchStats, 500);
  } catch (err) {
    alert('Invalidation failed: ' + err.message);
  }
}

async function invalidateAll() {
  if (!confirm('Purge ALL cached files from ALL edge servers?')) return;
  try {
    await fetch(`${ROUTER}/invalidate-all`, { method: 'POST' });
    narrate('🧹 All caches purged! Every next request will be a MISS.', '');
    setTimeout(fetchStats, 500);
  } catch (err) {
    alert('Purge failed: ' + err.message);
  }
}

/* ═══════════════════════════════════════════════════════════
   EDGE STATUS HELPERS
   ═══════════════════════════════════════════════════════════ */
function markEdgeOnline(n) {
  const el = document.getElementById(`status-edge-${n}`);
  if (el) el.innerHTML = '<span class="dot dot-online"></span> Online';
}
function markEdgeOffline(n) {
  const el = document.getElementById(`status-edge-${n}`);
  if (el) el.innerHTML = '<span class="dot dot-offline"></span> Offline';
  const dot = document.getElementById(`topo-edge${n}-dot`);
  if (dot) { dot.classList.remove('dot-online'); dot.classList.add('dot-offline'); }
}
function markAllOffline() {
  [1, 2, 3].forEach(n => markEdgeOffline(n));
}

/* ═══════════════════════════════════════════════════════════
   UTILITIES
   ═══════════════════════════════════════════════════════════ */
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function stampUpdated(msg) {
  const el = document.getElementById('last-updated');
  el.textContent = msg || `Updated ${new Date().toLocaleTimeString()}`;
}

function latencyColor(ms) {
  if (ms < 20) return 'badge-green';
  if (ms < 40) return 'badge-yellow';
  return 'badge-red';
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}
