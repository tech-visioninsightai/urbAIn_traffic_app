let mode = 'online';
let uploadedPath = null;

function setMode(m) {
  mode = m;
  document.querySelectorAll('[data-mode]').forEach((el) => {
    el.classList.toggle('active', el.dataset.mode === m);
  });
  const label = m === 'online' ? 'ONLINE' : m === 'offline_image' ? 'OFFLINE FOTO' : 'OFFLINE VÍDEO';
  document.getElementById('chip-mode').textContent = label;

  LiveView.updateViewerPanel(m);
  LiveView.stopStream();

  if (m === 'online') {
    LiveView.setIdleForMode(m, false);
  } else {
    LiveView.setIdleForMode(m, !!uploadedPath);
  }
}

document.querySelectorAll('[data-mode]').forEach((el) => {
  el.addEventListener('click', () => setMode(el.dataset.mode));
});

document.getElementById('file-input').addEventListener('change', async (ev) => {
  const file = ev.target.files?.[0];
  if (!file) return;
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  const isImage = ['jpg', 'jpeg', 'png', 'webp', 'bmp'].includes(ext);
  setMode(isImage ? 'offline_image' : 'offline_video');

  LiveView.setViewerStatus('loading', 'Subiendo archivo…', file.name);

  try {
    const res = await API.uploadFile(file);
    uploadedPath = res.path;
    document.getElementById('chip-upload').textContent = '✓ ' + (res.filename || file.name);
    LiveView.setStatus('ARCHIVO OK', false);
    LiveView.setIdleForMode(mode, true);
  } catch (e) {
    uploadedPath = null;
    document.getElementById('chip-upload').textContent = 'Subir archivo';
    LiveView.setStatus('UPLOAD ERROR', false);
    LiveView.setViewerStatus('error', 'Error al subir el archivo', String(e));
  }
});

document.getElementById('btn-start').addEventListener('click', async () => {
  document.getElementById('det-body').innerHTML = '';
  document.getElementById('kpi-emitted').textContent = '0';
  document.getElementById('status-log').innerHTML = '';
  LiveView.resetStatusTracking();

  LiveView.updateViewerPanel(mode);

  const body = { pipeline_id: 'c15', mode };
  if (mode === 'online') {
    body.camera_uri = null;
    LiveView.setViewerStatus(
      'loading',
      'Conectando cámara…',
      'Ping a 192.168.1.64 y apertura del stream RTSP en vivo',
    );
  } else if (!uploadedPath) {
    LiveView.setViewerStatus('waiting_file', 'Falta el archivo', 'Sube un vídeo o imagen antes de Start');
    LiveView.setStatus('SUBE ARCHIVO', false);
    return;
  } else {
    body.file_path = uploadedPath;
    LiveView.setViewerStatus('loading', 'Iniciando procesamiento offline…', uploadedPath);
  }

  LiveView.setStatus('STARTING…', false);

  try {
    await API.start(body);
    if (mode === 'online') {
      LiveView.setStatus('LIVE', true);
      LiveView.startStream();
    } else {
      LiveView.setStatus('PROCESANDO', false);
      LiveView.stopStream();
    }
  } catch (e) {
    LiveView.setStatus('ERROR', false);
    LiveView.setViewerStatus('error', 'No se pudo iniciar la sesión', String(e));
  }
});

document.getElementById('btn-stop').addEventListener('click', async () => {
  LiveView.setViewerStatus('muxing', 'Deteniendo…', 'Cerrando pipeline y guardando artefactos');
  try {
    const res = await API.stop();
    LiveView.stopStream();
    LiveView.setStatus('IDLE', false);
    if (res.output_dir) {
      LiveView.showOutputLink(res.output_dir);
      if (!LiveView.isOnlineMode()) {
        LiveView.setViewerStatus(
          'completed',
          'Detenido por el usuario',
          'Revisa la carpeta de salida para el vídeo anotado, logs y crops.',
        );
      }
    } else {
      LiveView.setIdleForMode(mode, !!uploadedPath);
    }
  } catch (_) {
    LiveView.setStatus('IDLE', false);
    LiveView.setIdleForMode(mode, !!uploadedPath);
  }
});

setMode('online');

window.TrafficControls = {
  getMode: () => mode,
  hasUpload: () => !!uploadedPath,
  getUploadPath: () => uploadedPath,
  refreshIdle: () => LiveView.setIdleForMode(mode, !!uploadedPath),
};
