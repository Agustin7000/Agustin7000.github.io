"""FFmpeg-based, alpha-aware still-frame preview for CineForm/ProRes/VP9 and more.

The browser cannot decode many Filmora CineForm MP4 files. This module is
used by the Windows GUI to preview without converting the source or discarding
its transparency. No external Python imaging dependency is required.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

from alpha_renderer import render_alpha_frame
from relay import render_relay_frame
from render import output_dimensions, validate_settings


def probe(path: Path) -> dict:
    """Get dimensions and duration even when the codec is browser-incompatible."""
    if not shutil.which('ffprobe') or not shutil.which('ffmpeg'):
        raise EnvironmentError('No se encontró FFmpeg/FFprobe en PATH.')
    proc = subprocess.run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,codec_name,pix_fmt,duration:format=duration',
        '-of', 'json', str(path)
    ], capture_output=True, text=True, check=True)
    details = json.loads(proc.stdout)
    streams = details.get('streams', [])
    if not streams:
        raise ValueError('El archivo no contiene una pista de video.')
    stream = streams[0]
    duration = float(details.get('format', {}).get('duration') or stream.get('duration') or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('No se pudo identificar la duración del video.')
    return {'width': int(stream['width']), 'height': int(stream['height']),
            'duration': duration, 'codec': stream.get('codec_name', '?'),
            'pix_fmt': stream.get('pix_fmt', '?')}


def decode_frame(path: Path, at_seconds: float, w: int, h: int) -> np.ndarray:
    """Seek and decode one frame as RGBA, maintaining original channel alpha."""
    args = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
        '-ss', f'{max(0., at_seconds):.4f}', '-i', str(path),
        '-map', '0:v:0', '-an', '-sn', '-frames:v', '1',
        '-vf', f'scale={w}:{h}:flags=bicubic,format=rgba',
        '-pix_fmt', 'rgba', '-f', 'rawvideo', 'pipe:1'
    ]
    p = subprocess.run(args, capture_output=True, timeout=45)
    expected = w * h * 4
    if p.returncode or len(p.stdout) != expected:
        err = p.stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError('No se pudo decodificar el fotograma con FFmpeg. ' + err[-450:])
    return np.frombuffer(p.stdout, dtype=np.uint8).copy().reshape(h, w, 4)


def checkerboard_preview(rgba: np.ndarray, tile_size: int = 16) -> np.ndarray:
    """Make the transparent tunnel visible over a checkerboard; return RGB."""
    h, w = rgba.shape[:2]
    yy, xx = np.indices((h, w))
    checker = (((xx // tile_size) + (yy // tile_size)) % 2)
    bg = np.where(checker[..., None] == 0, 208, 138).astype(np.float32)
    bg = np.broadcast_to(bg, (h, w, 3))
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    out = rgba[:, :, :3].astype(np.float32) * alpha + bg * (1.0 - alpha)
    return np.clip(out, 0, 255).astype(np.uint8)


def preview_png(path: Path, at_seconds: float, speed: float, ratio: float,
                depth: int, reverse: bool, mode: str = "classic",
                start_scale: float = .10, end_scale: float = 5., overlap: float = .50,
                *, source_meta: dict, max_short_side: int = 480) -> bytes:
    """Decode source, render effect, composite checker and return viewable PNG."""
    validate_settings(speed, ratio, depth)
    w, h = output_dimensions(source_meta['width'], source_meta['height'], max_short_side)
    t = max(0.0, min(float(at_seconds), source_meta['duration'] - 0.001))
    frame = decode_frame(path, t, w, h)
    transformed = (render_relay_frame(frame, t, speed, start_scale, end_scale, overlap, reverse)
                   if mode == "relay" else render_alpha_frame(frame, t, speed, ratio, depth, reverse))
    rgb = checkerboard_preview(transformed)
    good, encoded = cv2.imencode('.png', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not good:
        raise RuntimeError('No se pudo generar la miniatura PNG.')
    return encoded.tobytes()
