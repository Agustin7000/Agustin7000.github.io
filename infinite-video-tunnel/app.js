'use strict';

/**
 * Infinite Video Tunnel
 *
 * A mathematically periodic recursive zoom. At time t, every nested copy
 * has scale ratio^(level - phase(t)). As phase goes from 0 to 1, every
 * copy takes the previous larger copy's place. At wrap, the apparent
 * infinite tunnel is unchanged (up to the smallest invisible level).
 */
const $ = (id) => document.getElementById(id);
const video = $('sourceVideo');
const canvas = $('canvas');
const ctx = canvas.getContext('2d', { alpha: false, desynchronized: true });
const fileInput = $('fileInput');
let file = null;
let fileURL = null;
let outputURL = null;
let rafId = null;
let exporting = false;
let cancelled = false;
let recorder = null;
let chunks = [];
let canvasStream = null;
let audioContext = null;
let audioSource = null;
let audioDestination = null;
let monitorGain = null;
let exportMime = '';
let targetFps = 30;

function secondsLabel(sec) {
  const n = Number.isFinite(sec) ? Math.max(0, Math.floor(sec)) : 0;
  const minutes = String(Math.floor(n / 60)).padStart(2, '0');
  return `${minutes}:${String(n % 60).padStart(2, '0')}`;
}
function selectedSettings() {
  return {
    speed: Number($('speed').value),
    ratio: Number($('ratio').value),
    depth: Number($('depth').value),
    reverse: $('direction').value === 'in'
  };
}
function updateSettingLabels() {
  $('speedValue').value = `${Number($('speed').value).toFixed(2).replace('.', ',')} ciclos/s`;
  $('ratioValue').value = `${Math.round(Number($('ratio').value) * 100)}%`;
  $('depthValue').value = `${$('depth').value} capas`;
}
function targetSize() {
  const w = video.videoWidth || 1280;
  const h = video.videoHeight || 720;
  const cap = $('resolution').value;
  const maxSide = cap === 'native' ? Math.max(w, h) : Number(cap) * (Math.max(w, h) / Math.min(w, h) > 2.1 ? 1 : 16 / 9);
  // Cap on HEIGHT for ordinary horizontal and vertical aspect ratios.
  const limit = cap === 'native' ? 1 : Math.min(1, Number(cap) / Math.min(w, h));
  const factor = limit;
  const even = n => Math.max(2, Math.round(n / 2) * 2);
  void maxSide;
  return [even(w * factor), even(h * factor)];
}
function resizeCanvas() {
  if (!video.videoWidth) return;
  const [w, h] = targetSize();
  canvas.width = w;
  canvas.height = h;
  drawFrame();
}
function drawFrame() {
  if (!video.videoWidth || video.readyState < 2) return;
  const {speed, ratio, depth, reverse} = selectedSettings();
  const W = canvas.width, H = canvas.height;
  const cycles = video.currentTime * speed;
  let phase = cycles - Math.floor(cycles);
  if (reverse) phase = 1 - phase;
  ctx.clearRect(0, 0, W, H);
  for (let level = 0; level < depth; level++) {
    const factor = Math.pow(ratio, level - phase);
    const destW = W * factor;
    const destH = H * factor;
    if (destW < 1 || destH < 1) break;
    ctx.drawImage(video, (W - destW) / 2, (H - destH) / 2, destW, destH);
  }
}
function refreshTime() {
  $('timeDisplay').textContent = `${secondsLabel(video.currentTime)} / ${secondsLabel(video.duration)}`;
  if (Number.isFinite(video.duration) && video.duration > 0) {
    $('scrubber').value = String(Math.round(1000 * video.currentTime / video.duration));
    if (exporting) {
      const percent = Math.min(100, Math.floor(100 * video.currentTime / video.duration));
      $('progress').value = percent;
      $('progressPercent').textContent = `${percent}%`;
      $('progressText').textContent = `Procesando ${secondsLabel(video.currentTime)} de ${secondsLabel(video.duration)}`;
    }
  }
}
function animationFrame() {
  drawFrame();
  refreshTime();
  if (!video.paused && !video.ended) rafId = requestAnimationFrame(animationFrame);
  else rafId = null;
}
function startDrawing() {
  if (rafId !== null) cancelAnimationFrame(rafId);
  rafId = requestAnimationFrame(animationFrame);
}
async function initAudio() {
  if (audioContext) return;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;
  audioContext = new AC();
  audioSource = audioContext.createMediaElementSource(video);
  audioDestination = audioContext.createMediaStreamDestination();
  monitorGain = audioContext.createGain();
  monitorGain.gain.value = 0;
  audioSource.connect(audioDestination);
  audioSource.connect(monitorGain);
  monitorGain.connect(audioContext.destination);
}
function chooseMime() {
  const candidates = [
    ['video/mp4;codecs="avc1.42E01E,mp4a.40.2"', 'mp4'],
    ['video/mp4', 'mp4'],
    ['video/webm;codecs=vp9,opus', 'webm'],
    ['video/webm;codecs=vp8,opus', 'webm'],
    ['video/webm', 'webm']
  ];
  if (!window.MediaRecorder || typeof MediaRecorder.isTypeSupported !== 'function') return null;
  for (const [mime, ext] of candidates) {
    if (MediaRecorder.isTypeSupported(mime)) return {mime, ext};
  }
  return null;
}
function showFormatNotice() {
  const format = chooseMime();
  let msg = 'La exportación se realiza en tiempo real: un video de 2 minutos tarda aproximadamente 2 minutos. Mantené visible la pestaña.';
  if (format && format.ext === 'webm') msg += ' Tu navegador exportará WebM; el renderizador local disponible en GitHub produce MP4 con audio.';
  if (!format) msg = 'Este navegador no admite la grabación necesaria. Probá Chrome/Edge o utilizá el renderizador local en GitHub.';
  $('formatNotice').textContent = msg;
}
function clearResult() {
  if (outputURL) URL.revokeObjectURL(outputURL);
  outputURL = null;
  $('resultBlock').hidden = true;
}
async function loadFile(nextFile) {
  if (!nextFile || exporting) return;
  if (!(nextFile.type.startsWith('video/') || /\.(mp4|mov|mkv|webm|m4v|avi)$/i.test(nextFile.name))) {
    alert('Seleccioná un archivo de video compatible con el navegador.');
    return;
  }
  video.pause();
  if (fileURL) URL.revokeObjectURL(fileURL);
  clearResult();
  file = nextFile;
  fileURL = URL.createObjectURL(nextFile);
  video.src = fileURL;
  video.load();
  $('videoMeta').textContent = nextFile.name;
  $('dropZone').hidden = true;
  $('viewer').hidden = false;
  $('playBtn').disabled = false;
  $('scrubber').disabled = false;
  $('exportBtn').disabled = false;
  $('playBtn').textContent = '▶ Previsualizar';
  video.onloadedmetadata = () => {
    if (!Number.isFinite(video.duration) || video.duration <= 0) {
      $('exportBtn').disabled = true;
      alert('Este video no tiene una duración válida. Probá convertirlo a MP4 H.264.');
      return;
    }
    $('videoMeta').textContent = `${nextFile.name} · ${secondsLabel(video.duration)}`;
    resizeCanvas();
    refreshTime();
  };
  video.onloadeddata = () => drawFrame();
  video.onerror = () => {
    $('exportBtn').disabled = true;
    $('playBtn').disabled = true;
    alert('El navegador no pudo decodificar este archivo. Convertí el video a MP4 H.264 o usá el renderizador local.');
  };
}
async function togglePreview() {
  if (!file || exporting) return;
  if (video.paused) {
    if (video.ended) video.currentTime = 0;
    try {
      await initAudio();
      await audioContext?.resume();
      await video.play();
      $('playBtn').textContent = '❚❚ Pausar';
      startDrawing();
    } catch (e) { alert(`No se pudo reproducir: ${e.message}`); }
  } else {
    video.pause();
    $('playBtn').textContent = '▶ Previsualizar';
  }
}
function cleanupStream() {
  if (canvasStream) {
    canvasStream.getTracks().forEach(track => track.stop());
    canvasStream = null;
  }
}
function endExportUi() {
  exporting = false;
  video.pause();
  $('playBtn').disabled = false;
  $('scrubber').disabled = false;
  $('exportBtn').disabled = false;
  $('cancelBtn').hidden = true;
  $('playBtn').textContent = '▶ Previsualizar';
  $('progressBlock').hidden = true;
  cleanupStream();
}
async function exportVideo() {
  if (!file || exporting) return;
  const format = chooseMime();
  if (!format || !canvas.captureStream) {
    alert('La exportación no está disponible en este navegador. Probá Chrome o Edge, o el renderizador MP4 local.');
    return;
  }
  try {
    video.pause();
    await initAudio();
    await audioContext?.resume();
    video.currentTime = 0;
    if (video.readyState < 2) await new Promise((resolve, reject) => {
      video.addEventListener('loadeddata', resolve, {once:true});
      video.addEventListener('error', reject, {once:true});
    });
    resizeCanvas();
    drawFrame();
    clearResult();
    cancelled = false;
    chunks = [];
    exporting = true;
    exportMime = format.mime;
    $('exportBtn').disabled = true;
    $('playBtn').disabled = true;
    $('scrubber').disabled = true;
    $('cancelBtn').hidden = false;
    $('progressBlock').hidden = false;
    $('progress').value = 0;
    $('progressPercent').textContent = '0%';
    canvasStream = canvas.captureStream(targetFps);
    if ($('includeAudio').checked && audioDestination) {
      audioDestination.stream.getAudioTracks().forEach(track => canvasStream.addTrack(track));
    }
    recorder = new MediaRecorder(canvasStream, {
      mimeType: exportMime,
      videoBitsPerSecond: canvas.width * canvas.height >= 1920 * 1080 ? 10_000_000 : 5_000_000
    });
    recorder.ondataavailable = event => { if (event.data && event.data.size) chunks.push(event.data); };
    recorder.onerror = event => {
      console.error('MediaRecorder error', event);
      cancelled = true;
      video.pause();
      if (recorder.state !== 'inactive') recorder.stop();
    };
    recorder.onstop = () => {
      endExportUi();
      if (cancelled) {chunks = []; return;}
      const blob = new Blob(chunks, {type: recorder.mimeType || exportMime});
      chunks = [];
      if (!blob.size) {alert('El video resultante está vacío. Probá otra resolución o navegador.'); return;}
      outputURL = URL.createObjectURL(blob);
      const ext = (recorder.mimeType || exportMime).includes('mp4') ? 'mp4' : 'webm';
      const outName = `${file.name.replace(/\.[^.]+$/, '')}-tunnel.${ext}`;
      $('downloadLink').href = outputURL;
      $('downloadLink').download = outName;
      $('resultText').textContent = `${outName} · ${(blob.size / 1048576).toFixed(1)} MB · ${secondsLabel(video.duration)}. Para MP4 de calidad constante y sin grabación en tiempo real, utilizá el renderizador local.`;
      $('resultBlock').hidden = false;
    };
    video.onended = () => {
      $('playBtn').textContent = '▶ Previsualizar';
      if (exporting && recorder && recorder.state !== 'inactive') recorder.stop();
      drawFrame();
    };
    recorder.start(1000);
    try {
      await video.play();
      startDrawing();
    } catch (e) {
      cancelled = true;
      if (recorder && recorder.state !== 'inactive') recorder.stop();
      throw e;
    }
  } catch (e) {
    console.error(e);
    cancelled = true;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    else endExportUi();
    alert(`No se pudo iniciar la exportación: ${e.message}`);
  }
}
function cancelExport() {
  if (!exporting) return;
  cancelled = true;
  video.pause();
  if (recorder && recorder.state !== 'inactive') recorder.stop();
  else endExportUi();
}

// Events
fileInput.addEventListener('change', e => loadFile(e.target.files[0]));
$('dropZone').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }});
for (const evt of ['dragenter', 'dragover']) $('dropZone').addEventListener(evt, e => {e.preventDefault(); $('dropZone').classList.add('dragging');});
for (const evt of ['dragleave','drop']) $('dropZone').addEventListener(evt, e => {e.preventDefault(); $('dropZone').classList.remove('dragging');});
$('dropZone').addEventListener('drop', e => loadFile(e.dataTransfer.files[0]));
$('playBtn').addEventListener('click', togglePreview);
$('exportBtn').addEventListener('click', exportVideo);
$('cancelBtn').addEventListener('click', cancelExport);
$('scrubber').addEventListener('input', e => {
  if (file && !exporting && Number.isFinite(video.duration)) {
    video.currentTime = Number(e.target.value) / 1000 * video.duration;
  }
});
video.addEventListener('seeked', () => {drawFrame(); refreshTime();});
video.addEventListener('pause', () => {if (!exporting) $('playBtn').textContent = '▶ Previsualizar';});
video.addEventListener('ended', () => {if (!exporting) $('playBtn').textContent = '▶ Previsualizar';});
for (const key of ['speed','ratio','depth','direction']) {
  $(key).addEventListener('input', () => {updateSettingLabels(); if (video.paused) drawFrame();});
}
$('resolution').addEventListener('change', () => {if (!exporting) resizeCanvas();});
window.addEventListener('beforeunload', e => {
  if (exporting) {e.preventDefault(); e.returnValue = '';}
});
updateSettingLabels();
showFormatNotice();