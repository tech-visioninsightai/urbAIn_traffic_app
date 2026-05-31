const API = {
  async getStatus() {
    const r = await fetch('/api/session/status');
    return r.json();
  },
  async getPipelines() {
    const r = await fetch('/api/session/pipelines');
    return r.json();
  },
  async start(body) {
    const r = await fetch('/api/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((d) => d.msg || d).join('; ')
        : (data.detail || r.statusText || 'Start failed');
      throw new Error(detail);
    }
    return data;
  },
  async stop() {
    const r = await fetch('/api/session/stop', { method: 'POST' });
    return r.json();
  },
  async uploadFile(file) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/upload/file', { method: 'POST', body: fd });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      throw new Error(data.detail || r.statusText || 'Upload failed');
    }
    if (!data.path) {
      throw new Error('El servidor no devolvió la ruta del archivo');
    }
    return data;
  },
};
