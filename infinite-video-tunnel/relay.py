"""Zoom Relay: staggered, alpha-aware copies of ONE continuously playing video.

The older (larger) copy is composited IN FRONT of each newer copy.
Each instance grows exponentially, fades in/out, and is replaced behind it.
No source-video time reset is performed. No AI or intermediate frame files.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class RelaySettings:
    start_scale: float = 0.10
    end_scale: float = 5.0
    overlap: float = 0.50


def validate_relay(start_scale: float, end_scale: float, overlap: float) -> None:
    if not 0.02 <= start_scale <= 1.0:
        raise ValueError('Escala inicial fuera de rango: 2%-100%.')
    if not 1.01 <= end_scale <= 12.0 or end_scale <= start_scale:
        raise ValueError('Escala máxima debe superar 100% (hasta 1200%).')
    if not 0 <= overlap <= 0.70:
        raise ValueError('Superposición fuera de rango: 0%-70%.')


def relay_layers(seconds: float, speed: float, start_scale: float = 0.10,
                 end_scale: float = 5.0, overlap: float = 0.50,
                 reverse: bool = False) -> list[tuple[float, float]]:
    """Return list of (scale, opacity), BACK to FRONT (newest to oldest).

    Instances are born every period*(1-overlap) seconds and live one period.
    No more than 4 concurrent copies when overlap<=70%.
    The sequence is well defined even at t=0 (earlier copies started at t<0).
    """
    validate_relay(start_scale, end_scale, overlap)
    if not 0.02 <= speed <= 10 or not math.isfinite(seconds):
        raise ValueError('Velocidad/tiempo inválido.')
    period = 1.0 / speed
    spacing = period * (1.0 - overlap)
    current = math.floor(seconds / spacing)
    alive: list[tuple[float, float]] = []
    # From newest to oldest = order for alpha compositing (old in front).
    for number in range(current, current - math.ceil(period / spacing) - 2, -1):
        age = (seconds - number * spacing) / period
        if not (0 <= age < 1):
            continue
        motion = 1.0 - age if reverse else age
        scale = start_scale * (end_scale / start_scale) ** motion
        # Fade incoming clones on their first few frames; fade the outgoing
        # front copy over its last overlap portion. No abrupt popping.
        fade_in = min(0.08, max(0.025, overlap / 3))
        fade_out = max(0.13, min(0.32, overlap))
        alpha_in = min(1.0, age / fade_in)
        alpha_out = min(1.0, (1.0 - age) / fade_out)
        # Smoothstep prevents abrupt brightness velocity at fade boundaries.
        def smooth(x: float) -> float:
            x = max(0., min(1., x))
            return x * x * (3. - 2. * x)
        alive.append((scale, smooth(alpha_in) * smooth(alpha_out)))
    return alive


def _draw_scaled(source: np.ndarray, scale: float, target: np.ndarray, opacity: float) -> None:
    """Composite PREMULTIPLIED RGBA source into PREMULTIPLIED RGBA target."""
    if opacity <= 1e-7:
        return
    height, width = target.shape[:2]
    scaled_w, scaled_h = round(width * scale), round(height * scale)
    if scaled_w < 2 or scaled_h < 2:
        return
    if scale >= 1:
        # Crop before zooming to avoid huge intermediate images.
        crop_w = max(1, min(width, round(width / scale)))
        crop_h = max(1, min(height, round(height / scale)))
        x = (width - crop_w) // 2
        y = (height - crop_h) // 2
        part = source[y:y + crop_h, x:x + crop_w]
        layer = cv2.resize(part, (width, height), interpolation=cv2.INTER_LINEAR)
        dst = target
    else:
        x = (width - scaled_w) // 2
        y = (height - scaled_h) // 2
        layer = cv2.resize(source, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
        dst = target[y:y + scaled_h, x:x + scaled_w]
    a = layer[..., 3:4] * opacity
    # premultiplied source rgb is also scaled by instance opacity
    dst[..., :3] *= (1.0 - a)
    dst[..., :3] += layer[..., :3] * opacity
    dst[..., 3:4] *= (1.0 - a)
    dst[..., 3:4] += a


def render_relay_frame(rgba: np.ndarray, seconds: float, speed: float = 0.5,
                       start_scale: float = 0.10, end_scale: float = 5.,
                       overlap: float = .50, reverse: bool = False) -> np.ndarray:
    """Return straight-alpha RGBA tunnel frame (matches preview and export)."""
    if rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.dtype != np.uint8:
        raise ValueError('Se necesita un fotograma RGBA uint8.')
    layers = relay_layers(seconds, speed, start_scale, end_scale, overlap, reverse)
    h, w = rgba.shape[:2]
    source = rgba.astype(np.float32) / 255.0
    source[..., :3] *= source[..., 3:4]
    canvas = np.zeros((h, w, 4), np.float32)
    for scale, opacity in layers:
        _draw_scaled(source, scale, canvas, opacity)
    nonzero = canvas[..., 3] > 1e-7
    canvas[nonzero, :3] /= canvas[nonzero, 3:4]
    np.clip(canvas, 0, 1, out=canvas)
    return np.rint(canvas * 255).astype(np.uint8)
