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
const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true });
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
let loadWatchdog = null;

function secondsLabel(sec) {
  const n = Number.isFinite(sec) ? Math.max(0, Math.floor(sec)) : 0;
  const minutes = String(Math.floor(n / 60)).padStart(2, '0');
  return `${minutes}:${String(n % 60).padStart(2, '0')}`;
}
function timingValues() {
  const mode = $('mode').value;
  const overlap = Number($('overlap').value);
  const beatCount = Number($('beatDivision').value);
  const manual = $('timingMode').value === 'manual';
  const bpm = Number($('bpm').value);
  if (!manual && (!Number.isFinite(bpm) || bpm < 40 || bpm > 300 || !Number.isFinite(beatCount))) return null;
  // For relay, the entrance interval is (1-overlap) / speed, not 1 / speed.
  const speed = manual ? Number($('speed').value) :
    bpm / (60 * beatCount) * (mode === 'relay' ? 1 - overlap : 1);
  return {
    speed,
    cadenceMs: 1000 / speed * (mode === 'relay' ? 1 - overlap : 1),
    traversalMs: 1000 / speed
  };
}
function selectedSettings() {
  return {
    mode: $('mode').value,
    startScale: Number($('startScale').value),
    endScale: Number($('endScale').value),
    overlap: Number($('overlap').value),
    speed: timingValues()?.speed ?? Number($('speed').value),
    ratio: Number($('ratio').value),
    depth: Number($('depth').value),
    reverse: $('direction').value === 'in'
  };
}
function updateSettingLabels() {
  const bpmMode = $('timingMode').value === 'bpm';
  $('manualSpeedControls').hidden = bpmMode;
  $('bpmControls').hidden = !bpmMode;
  const timing = timingValues();
  $('speedValue').value = `${Number($('speed').value).toFixed(2).replace('.', ',')} ciclos/s`;
  if (timing) {
    const format = n => n.toLocaleString('es-AR', {maximumFractionDigits:2, minimumFractionDigits:2});
    $('cadenceValue').textContent = `${$('mode').value === 'relay' ? 'Nueva copia' : 'Ciclo completo'} cada ${format(timing.cadenceMs)} ms`;
    $('durationValue').textContent = `Duración del recorrido: ${format(timing.traversalMs)} ms · ${format(timing.speed)} ciclos/s`;
  } else {
    $('cadenceValue').textContent = 'Ingresá un BPM válido (40–300)';
    $('durationValue').textContent = 'No se puede calcular la velocidad';
  }
  $('ratioValue').value = `${Math.round(Number($('ratio').value) * 100)}%`;
  $('depthValue').value = `${$('depth').value} capas`;
  $('startScaleValue').value = `${Math.round(Number($('startScale').value) * 100)}%`;
  $('endScaleValue').value = `${Math.round(Number($('endScale').value) * 100)}%`;
  $('overlapValue').value = `${Math.round(Number($('overlap').value) * 100)}%`;
  $('relayControls').hidden = $('mode').value !== 'relay';
  $('classicControls').hidden = $('mode').value !== 'classic';
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
function smoothstep(x) {
  x = Math.max(0, Math.min(1, x));
  return x*x*(3-2*x);
}
function drawRelay(t, W, H, {speed, startScale, endScale, overlap, reverse}) {
  const period = 1 / speed;
  const spacing = period * (1 - overlap);
  const current = Math.floor(t / spacing);
  // Newer layers go on the canvas FIRST; older, larger layers draw on top.
  // Therefore a newly emerging mini-clone cannot cover the foreground face.
  for (let n = current; n > current - Math.ceil(period / spacing) - 2; --n) {
    const age = (t - n*spacing) / period;
    if (age < 0 || age >= 1) continue;
    const motion = reverse ? 1-age : age;
    const scale = startScale * Math.pow(endScale/startScale, motion);
    const fadeIn = Math.min(.08, Math.max(.025, overlap/3));
    const fadeOut = Math.max(.13, Math.min(.32, overlap));
    const opacity = smoothstep(age/fadeIn)*smoothstep((1-age)/fadeOut);
    if (opacity < .00001) continue;
    ctx.globalAlpha = opacity;
    const w = W*scale, h = H*scale;
    ctx.drawImage(video, (W-w)/2, (H-h)/2, w, h);
  }
  ctx.globalAlpha = 1;
}
function drawFrame() {
  if (!video.videoWidth || video.readyState < 2) return;
  const settings = selectedSettings();
  const {speed, ratio, depth, reverse} = settings;
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  if (settings.mode === 'relay') {
    drawRelay(video.currentTime, W, H, settings);
    return;
  }
  const cycles = video.currentTime * speed;
  let phase = cycles - Math.floor(cycles);
  if (reverse) phase = 1 - phase;
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
  msg += ' Para conservar transparencias, usá Exportar MOV transparente en la versión Windows (el grabador del navegador puede perder el alfa).';
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
  if (loadWatchdog) clearTimeout(loadWatchdog);
  $('previewNotice').hidden = true;
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
  video.onloadeddata = () => {
    if (loadWatchdog) clearTimeout(loadWatchdog);
    $('previewNotice').hidden = true;
    drawFrame();
  };
  function previewUnsupported() {
    if (loadWatchdog) clearTimeout(loadWatchdog);
    if (video.readyState >= 2 && video.videoWidth) return;
    $('previewNotice').hidden = false;
    $('previewNotice').textContent = 'Este navegador no puede decodificar el video. Si lo exportaste transparente desde Filmora en CineForm, no lo conviertas a H.264: descargá la versión v2.0 para Windows desde GitHub, donde la vista previa funciona con FFmpeg y conserva el canal alfa.';
    $('exportBtn').disabled = true;
    $('playBtn').disabled = true;
  }
  loadWatchdog = setTimeout(previewUnsupported, 6000);
  video.onerror = () => {
    previewUnsupported();
    $('exportBtn').disabled = true;
    $('playBtn').disabled = true;
    // Se muestra el aviso directamente en el visor, sin bloquear la página con una alerta.
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
  if (!timingValues()) {
    alert('Ingresá un BPM válido entre 40 y 300 para exportar.');
    return;
  }
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
for (const key of ['speed','ratio','depth','direction','mode','startScale','endScale','overlap','timingMode','bpm','beatDivision']) {
  $(key).addEventListener('input', () => {updateSettingLabels(); if (video.paused) drawFrame();});
}
$('resolution').addEventListener('change', () => {if (!exporting) resizeCanvas();});
window.addEventListener('beforeunload', e => {
  if (exporting) {e.preventDefault(); e.returnValue = '';}
});
updateSettingLabels();
showFormatNotice();
