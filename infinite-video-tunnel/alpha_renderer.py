"""Transparency-preserving tunnel renderer. FFmpeg decodes CineForm/ProRes/VP9 to RGBA.

Export MOV ProRes 4444 (recommended for editing) or WebM VP9 with alpha.
Never export H.264 MP4 when transparency is requested: it loses alpha.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from render import tunnel_frame, output_dimensions, validate_settings


def probe_video(path: Path) -> dict:
    command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
               '-show_entries', 'stream=width,height,avg_frame_rate,nb_frames,pix_fmt,codec_name:stream_tags=alpha_mode',
               '-of', 'json', str(path)]
    response = subprocess.run(command, check=True, capture_output=True, text=True)
    streams = json.loads(response.stdout).get('streams', [])
    if not streams:
        raise ValueError('No se detectó ninguna pista de video')
    return streams[0]


def exact_read(pipe, length: int) -> bytes:
    """Read exactly one frame even when the OS returns short chunks."""
    result = bytearray(length)
    view = memoryview(result)
    count = 0
    while count < length:
        n = pipe.readinto(view[count:])
        if not n:
            if count:
                raise RuntimeError('Video de entrada truncado durante la decodificación')
            return b''
        count += n
    return bytes(result)


def render_alpha_frame(frame: np.ndarray, seconds: float, speed: float = 0.5,
                       ratio: float = 0.5, depth: int = 10,
                       reverse: bool = False) -> np.ndarray:
    """Composite centered RGBA layers over transparent pixels using premultiplied alpha.

    cv2 resize operates on premultiplied RGB to avoid dark edge fringes. Each
    layer is alpha-composited OVER the previous layer, rather than overwriting
    entire rectangular regions (which would erase transparency).
    """
    if frame.ndim != 3 or frame.shape[2] != 4:
        raise ValueError('El fotograma debe tener cuatro canales RGBA')
    h, w = frame.shape[:2]
    # Numpy premultiplied RGBA in floats, including transparent pixels.
    source = frame.astype(np.float32) / 255.0
    source[:, :, :3] *= source[:, :, 3:4]
    canvas = np.zeros((h, w, 4), dtype=np.float32)
    phase = (seconds * speed) % 1.0
    if reverse:
        phase = 1.0 - phase
    for level in range(depth):
        scale = ratio ** (level - phase)
        dw, dh = round(w * scale), round(h * scale)
        if dw < 2 or dh < 2:
            break
        if scale >= 1:
            # Crop source before enlargement to avoid giant temporary images.
            crop_w = max(1, min(w, round(w / scale)))
            crop_h = max(1, min(h, round(h / scale)))
            x0 = (w - crop_w) // 2
            y0 = (h - crop_h) // 2
            src = source[y0:y0 + crop_h, x0:x0 + crop_w]
            layer = cv2.resize(src, (w, h), interpolation=cv2.INTER_LINEAR)
            dst = canvas
        else:
            x0 = (w - dw) // 2
            y0 = (h - dh) // 2
            target_w = min(dw, w - x0)
            target_h = min(dh, h - y0)
            layer = cv2.resize(source, (target_w, target_h), interpolation=cv2.INTER_AREA)
            dst = canvas[y0:y0 + target_h, x0:x0 + target_w]
        alpha = layer[:, :, 3:4]
        dst[:, :, :3] *= (1.0 - alpha)
        dst[:, :, :3] += layer[:, :, :3]
        dst[:, :, 3:4] *= (1.0 - alpha)
        dst[:, :, 3:4] += alpha

    nonzero = canvas[:, :, 3] > 1e-7
    # Convert from premultiplied RGB back to straight RGBA for FFmpeg.
    canvas[nonzero, :3] /= canvas[nonzero, 3:4]
    np.clip(canvas, 0, 1, out=canvas)
    return np.rint(canvas * 255).astype(np.uint8)


def render_alpha(input_path: Path, output_path: Path, speed: float = 0.5,
                 ratio: float = 0.5, depth: int = 10, reverse: bool = False,
                 max_short_side: int = 1080, crf: int = 19,
                 keep_audio: bool = True):
    validate_settings(speed, ratio, depth)
    if not input_path.is_file():
        raise FileNotFoundError(f'No existe el video: {input_path}')
    if input_path.resolve() == output_path.resolve():
        raise ValueError('La salida no puede sobrescribir al original')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise EnvironmentError('Instalá FFmpeg y FFprobe para procesar video transparente')
    ext = output_path.suffix.lower()
    if ext not in ('.mov', '.webm'):
        raise ValueError('La salida transparente debe terminar en .mov (ProRes 4444) o .webm (VP9). MP4 H.264 no conserva alfa.')

    info = probe_video(input_path)
    src_w, src_h = int(info['width']), int(info['height'])
    w, h = output_dimensions(src_w, src_h, max_short_side)
    numerator, denominator = map(int, info.get('avg_frame_rate', '0/1').split('/'))
    fps = numerator / denominator if denominator else 0
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('No se pudo detectar la tasa de fotogramas')
    total = int(info.get('nb_frames') or 0)
    size = w * h * 4
    fps_str = f'{numerator}/{denominator}'

    decoder = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', str(input_path),
               '-map', '0:v:0', '-an', '-sn', '-vf', f'scale={w}:{h}:flags=bicubic,format=rgba',
               '-fps_mode', 'passthrough', '-pix_fmt', 'rgba', '-f', 'rawvideo', 'pipe:1']
    encoder = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
               '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{w}x{h}', '-r', fps_str, '-i', 'pipe:0']
    if keep_audio:
        encoder += ['-i', str(input_path), '-map', '0:v:0', '-map', '1:a:0?']
    else:
        encoder += ['-map', '0:v:0', '-an']
    if ext == '.mov':
        encoder += ['-c:v', 'prores_ks', '-profile:v', '4', '-pix_fmt', 'yuva444p10le',
                    '-vendor', 'apl0', '-qscale:v', '11']
        if keep_audio:
            encoder += ['-c:a', 'pcm_s16le']
    else:
        encoder += ['-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-auto-alt-ref', '0',
                    '-deadline', 'good', '-cpu-used', '4', '-b:v', '0', '-crf', str(crf)]
        if keep_audio:
            encoder += ['-c:a', 'libopus', '-b:a', '160k']
    encoder += ['-shortest', str(output_path)]

    print(f'Entrada: {input_path.name} · {src_w}×{src_h} · {fps:.3f} fps · {info.get("codec_name", "?")}', flush=True)
    print(f'Salida RGBA: {output_path} · {w}×{h} · {"ProRes 4444" if ext == ".mov" else "VP9 alfa"}', flush=True)
    print('Aviso: H.264 MP4 no conserva transparencia. El resultado está pensado para reimportarlo a un editor.', flush=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reader = subprocess.Popen(decoder, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, bufsize=size * 2)
    writer = subprocess.Popen(encoder, stdin=subprocess.PIPE, bufsize=size * 2)
    done = 0
    started = time.monotonic()
    try:
        while True:
            raw = exact_read(reader.stdout, size)
            if not raw:
                break
            source = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)
            result = render_alpha_frame(source, done / fps, speed, ratio, depth, reverse)
            try:
                writer.stdin.write(result.tobytes())
            except BrokenPipeError as e:
                raise RuntimeError('Falló la codificación de ProRes/VP9 con alfa') from e
            done += 1
            if done % max(1, round(fps)) == 0:
                pct = f'{100 * done / total:.1f}%' if total else '—'
                print(f'Progreso: {pct} · {done / fps:.1f} segundos procesados · {time.monotonic() - started:.0f} s', flush=True)
        reader.stdout.close()
        writer.stdin.close()
        reader_code = reader.wait()
        writer_code = writer.wait()
        if reader_code or writer_code:
            raise RuntimeError(f'FFmpeg terminó con error: lectura={reader_code}; exportación={writer_code}')
        if not done:
            raise RuntimeError('No se pudieron leer fotogramas del archivo fuente')
    except BaseException:
        if reader.poll() is None:
            reader.kill()
        if writer.poll() is None:
            writer.kill()
        reader.wait()
        writer.wait()
        output_path.unlink(missing_ok=True)
        raise
    print(f'LISTO: {output_path}', flush=True)
