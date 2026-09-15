(function () {
  const video = document.getElementById('video');
  const fps = document.getElementById('fps');
  const start = document.getElementById('start');
  const status = document.getElementById('status');
  const results = document.getElementById('results');
  const grid = document.getElementById('candidate-grid');
  const failures = document.getElementById('failures');
  let timer = null;

  function showStatus(data) {
    const progress = data.progress || {};
    const counts = data.phase === 'analysis' ? ` ${progress.processed || 0} processed, ${progress.successful || 0} successful, ${progress.failed || 0} failed.` : '';
    status.innerHTML = `<div class="status-row"><strong>${data.phase || 'waiting'}</strong><span class="muted">${data.sampling_fps || fps.value} FPS${counts}</span></div>${data.error ? `<p>${escapeHtml(data.error)}</p>` : ''}`;
  }

  function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }

  async function poll(runId) {
    const response = await fetch(`/api/runs/${runId}/status`);
    if (!response.ok) throw new Error('Could not poll the visualizer run.');
    const data = await response.json();
    showStatus(data);
    if (data.terminal) {
      clearInterval(timer);
      start.disabled = false;
      await showResults(runId);
    }
  }

  async function showResults(runId) {
    const response = await fetch(`/api/runs/${runId}/results`);
    if (!response.ok) return;
    const data = await response.json();
    grid.innerHTML = (data.candidates || []).map(candidate => {
      const provenance = candidate.provenance || {};
      const timestamp = provenance.timestamp_seconds == null ? 'Timestamp unavailable' : `${Number(provenance.timestamp_seconds).toFixed(2)}s`;
      return `<article class="candidate"><img src="${candidate.image_url}" alt="Rank ${candidate.rank}, frame ${candidate.frame_index}"><div class="candidate-body"><span class="candidate-rank">#${candidate.rank} / frame ${candidate.frame_index}</span><span class="candidate-score">${Number(candidate.score).toFixed(1)}</span><p class="candidate-meta">${timestamp}${candidate.reasoning ? ` · ${escapeHtml(candidate.reasoning)}` : ''}</p></div></article>`;
    }).join('');
    const messages = [];
    (data.failed || []).forEach(item => messages.push(`Failed frame ${item.frame_index}: ${escapeHtml(item.error || 'unknown error')}`));
    (data.skipped || []).forEach(item => messages.push(`Skipped frame ${item.frame_index}: ${escapeHtml(item.reason || 'no reason provided')}`));
    failures.innerHTML = messages.length ? `<strong>Diagnostics</strong><ul>${messages.map(message => `<li>${message}</li>`).join('')}</ul>` : '';
    results.hidden = !(data.candidates || []).length && !messages.length;
  }

  start.addEventListener('click', async function () {
    if (!video.files.length) { status.innerHTML = '<p>Please choose a video file first.</p>'; return; }
    start.disabled = true;
    results.hidden = true;
    const file = video.files[0];
    try {
      const response = await fetch('/api/runs', { method: 'POST', headers: {'Content-Length': String(file.size), 'X-Video-Filename': file.name, 'X-Sample-Fps': fps.value, 'Content-Type': 'application/octet-stream'}, body: file });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'The upload was rejected.');
      showStatus({phase: 'queued', sampling_fps: fps.value});
      timer = setInterval(() => poll(data.run_id).catch(error => { clearInterval(timer); start.disabled = false; status.innerHTML = `<p>${escapeHtml(error.message)}</p>`; }), 700);
      await poll(data.run_id);
    } catch (error) {
      start.disabled = false;
      status.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
    }
  });
}());
