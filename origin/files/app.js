// ═══════════════════════════════════════════════════════════
// app.js — Client-side application logic for Mini CDN demo
// ═══════════════════════════════════════════════════════════

/**
 * Utility: format bytes into human-readable string
 */
function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + units[i];
}

/**
 * Utility: format milliseconds into readable latency
 */
function formatLatency(ms) {
  if (ms < 1) return '<1ms';
  if (ms < 1000) return ms.toFixed(0) + 'ms';
  return (ms / 1000).toFixed(2) + 's';
}

/**
 * Utility: generate a random request ID
 */
function generateRequestId() {
  return 'req_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 6);
}

/**
 * Perform a timed fetch and return metadata
 */
async function timedFetch(url) {
  const id = generateRequestId();
  const start = performance.now();

  const response = await fetch(url);
  const elapsed = performance.now() - start;
  const body = await response.text();

  return {
    id,
    url,
    status: response.status,
    latency_ms: Math.round(elapsed),
    cache: response.headers.get('X-Cache') || 'N/A',
    edge: response.headers.get('X-Edge-ID') || 'N/A',
    content_type: response.headers.get('Content-Type') || 'unknown',
    body_size: new Blob([body]).size,
    body_preview: body.substring(0, 200),
    timestamp: new Date().toISOString(),
  };
}

/**
 * Display connection info on page load
 */
document.addEventListener('DOMContentLoaded', () => {
  console.log('╔══════════════════════════════════════╗');
  console.log('║   Mini CDN — Client App Loaded       ║');
  console.log('║   Timestamp: ' + new Date().toISOString());
  console.log('╚══════════════════════════════════════╝');
});
