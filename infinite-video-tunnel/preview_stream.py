"""Continuous alpha-preserving FFmpeg frame stream for the Windows live preview.

Unlike the old still preview, this opens one persistent decoder for playback.
The alpha-aware tunnel is rendered for every displayed frame, without proxy files.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterator

import numpy as np

from alpha_renderer import exact_read, render_alpha_frame
from relay import render_relay_frame
from render import output_dimensions, validate_settings


def decoder_command(path: Path, start: float, width: int, height: int, fps: int = 15) -> list[str]:
    if fps < 1 or fps > 60:
        raise ValueError('FPS inválidos')
    if start < 0:
        raise ValueError('Inicio negativo')
    # Decode at a constant preview frame rate; never flatten the alpha plane.
    return ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-ss', f'{start:.4f}', '-i', str(path), '-map', '0:v:0', '-an', '-sn',
            '-vf', f'scale={width}:{height}:flags=fast_bilinear,fps={fps},format=rgba',
            '-pix_fmt', 'rgba', '-f', 'rawvideo', 'pipe:1']


def frames_from_pipe(pipe, width: int, height: int) -> Iterator[np.ndarray]:
    """Read all full RGBA frames; never silently use a truncated frame."""
    nbytes = width * height * 4
    while True:
        raw = exact_read(pipe, nbytes)
        if not raw:
            return
        yield np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)


def make_checker(width: int, height: int, tile: int = 16) -> np.ndarray:
    yy, xx = np.indices((height, width))
    checks = ((xx // tile) + (yy // tile)) % 2
    levels = np.where(checks == 0, 210, 140).astype(np.float32)
    return np.repeat(levels[..., None], 3, axis=2)


def render_preview_rgb(rgba: np.ndarray, seconds: float, speed: float, ratio: float,
                       depth: int, reverse: bool, checker: np.ndarray,
                       mode: str = "classic", start_scale: float = .10,
                       end_scale: float = 5., overlap: float = .50) -> np.ndarray:
    """Same recursive alpha algorithm as final render, over checker background."""
    validate_settings(speed, ratio, depth)
    transformed = (render_relay_frame(rgba, seconds, speed, start_scale, end_scale, overlap, reverse)
                   if mode == "relay" else render_alpha_frame(rgba, seconds, speed, ratio, depth, reverse))
    alpha = transformed[..., 3:4].astype(np.float32) / 255.0
    rgb = transformed[..., :3].astype(np.float32)
    return np.clip(rgb * alpha + checker * (1.0 - alpha), 0, 255).astype(np.uint8)


class PreviewDecoder:
    def __init__(self, path: Path, start: float, width: int, height: int, fps: int = 15):
        self.path = path
        self.start = start
        self.width = width
        self.height = height
        self.fps = fps
        self.process: subprocess.Popen | None = None

    def __enter__(self):
        self.process = subprocess.Popen(
            decoder_command(self.path, self.start, self.width, self.height, self.fps),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, bufsize=0,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return self

    def __iter__(self):
        if self.process is None or self.process.stdout is None:
            raise RuntimeError('No se inició el decodificador')
        return frames_from_pipe(self.process.stdout, self.width, self.height)

    def stop(self):
        proc = self.process
        if proc is None:
            return
        if proc.poll() is None:
            proc.kill()
        if proc.stdout:
            proc.stdout.close()
        proc.wait()
        self.process = None

    def __exit__(self, *_):
        self.stop()
