let ws = null;
let streamOn = false;
let uiMode = 'online';
let lastStatusKey = '';

function statusKey(phase, message) {
  return `${phase || ''}\0${message || ''}`;
}

function resetStatusTracking() {
  lastStatusKey = '';
}

const PHASE_LABELS = {
  idle: 'LISTO',
  waiting: 'ESPERANDO',
  waiting_file: 'ARCHIVO PENDIENTE',
  loading: 'CARGANDO',
  processing: 'PROCESANDO',
  muxing: 'EXPORTANDO',
  completed: 'COMPLETADO',
  error: 'ERROR',
  running: 'EN VIVO',
};

function isOnlineMode(m) {
  return (m || uiMode) === 'online';
}

function formatLogTime() {
  return new Date().toLocaleTimeString();
}

function appendStatusLog(message) {
  const log = document.getElementById('status-log');
  if (!log || !message) return;
  const li = document.createElement('li');
  li.innerHTML = `<span class="ts">${formatLogTime()}</span><span class="msg">${message}</span>`;
  log.prepend(li);
  while (log.children.length > 40) log.removeChild(log.lastChild);
}

function renderArtifacts(artifacts) {
  const detail = document.getElementById('status-detail');
  if (!artifacts || !artifacts.length) return;
  const wrap = document.createElement('div');
  wrap.className = 'viewer-status-artifacts';
  wrap.innerHTML = '<div style="margin:12px 0 6px;font-size:10px;letter-spacing:0.16em;color:var(--text-3)">ARTEFACTOS</div>';
  artifacts.forEach((name) => {
    const span = document.createElement('span');
    span.textContent = name;
    wrap.appendChild(span);
  });
  detail.appendChild(wrap);
}

function updateViewerPanel(mode) {
  uiMode = mode || uiMode;
  const wrap = document.getElementById('video-wrap');
  if (!wrap) return;
  wrap.classList.remove('mode-online', 'mode-offline');
  wrap.classList.add(isOnlineMode() ? 'mode-online' : 'mode-offline');
}

function setViewerStatus(phase, message, detail, extra = {}) {
  const phaseEl = document.getElementById('status-phase');
  const msgEl = document.getElementById('status-message');
  const detailEl = document.getElementById('status-detail');
  if (!phaseEl || !msgEl || !detailEl) return;

  const label = PHASE_LABELS[phase] || String(phase || 'INFO').toUpperCase();
  phaseEl.textContent = label;
  phaseEl.className = 'viewer-status-phase phase-' + (phase || 'idle');
  msgEl.textContent = message || '';
  detailEl.innerHTML = '';
  if (detail) detailEl.textContent = detail;
  if (extra.artifacts) renderArtifacts(extra.artifacts);

  const key = statusKey(phase, message);
  if (message && key !== lastStatusKey) {
    lastStatusKey = key;
    appendStatusLog(message);
  }
}

function updateProgressPanel(msg) {
  if (msg.detail) {
    const detailEl = document.getElementById('status-detail');
    if (detailEl) detailEl.textContent = msg.detail;
  }
  updateKpis(msg);
}

function updateKpis(s) {
  if (!s) return;
  if (s.total_detections != null) {
    document.getElementById('kpi-emitted').textContent = String(s.total_detections);
  }
  if (s.uptime_sec != null) {
    document.getElementById('kpi-uptime').textContent = String(s.uptime_sec);
  }
  const kpiUptimeLabel = document.querySelector('#kpi-uptime + .kpi-label');
  if (kpiUptimeLabel) {
    kpiUptimeLabel.textContent = s.uptime_frozen ? 'Duración s' : 'Uptime s';
  }
  const prog = s.progress || {};
  const hud = document.getElementById('hud-bottom');
  if (!hud) return;
  const uptimeLabel = s.uptime_frozen ? 'DURACIÓN' : 'UPTIME';
  const uptime = s.uptime_sec != null ? s.uptime_sec : '—';
  const emitted = s.total_detections != null ? s.total_detections : 0;
  hud.innerHTML =
    `<span class="dot"></span>${uptimeLabel} ${uptime}s · EMITIDAS ${emitted} · FRAMES ${prog.frames_processed ?? '—'}`;
}

function setIdleForMode(mode, hasFile) {
  if (isOnlineMode(mode)) {
    setViewerStatus('waiting', 'Esperando inicio', 'Modo online · pulse Start para conectar la cámara y ver el vídeo en vivo.');
    return;
  }
  if (!hasFile) {
    setViewerStatus(
      'waiting_file',
      'Sube un archivo',
      'Modo offline · use «Subir archivo» y después pulse Start. El vídeo anotado se guardará solo en la carpeta de salida.',
    );
    return;
  }
  setViewerStatus(
    'waiting',
    'Listo para procesar',
    'Archivo cargado · pulse Start. Una sola pasada; al terminar se guarda en la carpeta de salida.',
  );
}

function confClass(c) {
  if (c >= 0.8) return 'conf-high';
  if (c >= 0.6) return 'conf-mid';
  return 'conf-low';
}

function formatTime(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return ts.slice(11, 19) || ts;
  }
}

function prependDetection(row) {
  const body = document.getElementById('det-body');
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td class="mono">${formatTime(row.timestamp)}</td>
    <td class="plate">${row.label || '—'}</td>
    <td class="${confClass(row.confidence)}">${(row.confidence || 0).toFixed(2)}</td>
    <td>${row.camera_id || '—'}</td>
  `;
  body.prepend(tr);
  while (body.children.length > 200) body.removeChild(body.lastChild);
}

function applyStatusPayload(msg) {
  const phase = msg.phase || msg.state || 'idle';
  const message = msg.message || '';
  const detail = msg.detail || '';
  setViewerStatus(phase, message, detail, { artifacts: msg.artifacts });
  updateKpis(msg);

  if (phase === 'completed' || msg.state === 'completed') {
    setStatus('COMPLETADO', false);
    if (msg.output_dir) showOutputLink(msg.output_dir);
    stopStream();
    return;
  }
  if (phase === 'error' || msg.state === 'error') {
    setStatus('ERROR', false);
    stopStream();
    return;
  }
  if (phase === 'processing' || msg.state === 'running') {
    setStatus(isOnlineMode() ? 'LIVE' : 'PROCESANDO', isOnlineMode());
    if (isOnlineMode()) startStream();
    else stopStream();
  }
  if (phase === 'loading') {
    setStatus('CARGANDO', false);
    stopStream();
  }
}

function connectWs() {
  if (ws) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/events`);
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'detection') {
        prependDetection(msg);
        const n = document.getElementById('kpi-emitted');
        n.textContent = String(parseInt(n.textContent || '0', 10) + 1);
      }
      if (msg.type === 'status') {
        applyStatusPayload(msg);
      }
      if (msg.type === 'progress') {
        updateProgressPanel(msg);
      }
    } catch (_) {}
  };
  ws.onclose = () => { ws = null; setTimeout(connectWs, 2000); };
}

function startStream() {
  if (!isOnlineMode()) return;
  const img = document.getElementById('live-stream');
  if (!img) return;
  img.src = '/stream/mjpeg?' + Date.now();
  streamOn = true;
}

function stopStream() {
  const img = document.getElementById('live-stream');
  if (!img) return;
  img.removeAttribute('src');
  streamOn = false;
}

function setStatus(text, live) {
  document.getElementById('status-text').textContent = text;
  const dot = document.getElementById('status-dot');
  dot.classList.toggle('live', !!live);
}

function showOutputLink(dir) {
  const a = document.getElementById('output-link');
  a.style.display = 'block';
  a.textContent = 'Abrir carpeta de salida: ' + dir;
  a.href = '#';
  a.onclick = (e) => { e.preventDefault(); };
}

async function syncStatusOnce() {
  try {
    const s = await API.getStatus();
    if (s.mode) uiMode = s.mode;
    updateViewerPanel(window.TrafficControls?.getMode?.() || uiMode);
    updateKpis(s);
    if (s.running) {
      if (isOnlineMode(window.TrafficControls?.getMode?.() || s.mode)) {
        setStatus('LIVE', true);
        if (!streamOn) startStream();
      } else {
        setStatus('PROCESANDO', false);
      }
    } else if (['completed', 'error', 'processing', 'muxing', 'loading'].includes(s.phase)) {
      applyStatusPayload(s);
    } else if (window.TrafficControls) {
      window.TrafficControls.refreshIdle();
    }
    if (s.output_dir) showOutputLink(s.output_dir);
  } catch (_) {}
}

connectWs();
updateViewerPanel('online');
syncStatusOnce();

window.LiveView = {
  startStream,
  stopStream,
  setStatus,
  showOutputLink,
  prependDetection,
  updateViewerPanel,
  setViewerStatus,
  setIdleForMode,
  isOnlineMode,
  resetStatusTracking,
  updateKpis,
};
