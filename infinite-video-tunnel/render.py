#!/usr/bin/env python3
"""Offline, frame-accurate, full-length infinite recursive video tunnel.

Requirements: Python 3.9+, opencv-python, numpy, FFmpeg on PATH.
The renderer outputs H.264 MP4 and copies/syncs audio through FFmpeg.

Usage:
  python render.py input.mp4 --speed 0.5 --ratio 0.5 --depth 10 -o tunnel.mp4
"""
from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from relay import render_relay_frame, validate_relay


def validate_settings(speed: float, ratio: float, depth: int):
    if not 0.02 <= speed <= 10:
        raise ValueError("Velocidad fuera de rango (0.02 a 10 ciclos/s)")
    if not 0.1 <= ratio <= 0.9:
        raise ValueError("Separación fuera de rango (0.1 a 0.9)")
    if not 2 <= depth <= 32:
        raise ValueError("Profundidad fuera de rango (2 a 32 capas)")


def tunnel_frame(frame: np.ndarray, seconds: float, speed: float = 0.5,
                 ratio: float = 0.5, depth: int = 10, reverse: bool = False) -> np.ndarray:
    """Render a centered, periodic tunnel using the SAME source video frame.

    At the wrap of phase 0..1, all nested image scales shift by one
    level, preserving the visible composition except subpixel center.
    """
    height, width = frame.shape[:2]
    phase = (seconds * speed) % 1.0
    if reverse:
        phase = 1.0 - phase

    canvas = np.zeros_like(frame)
    # Draw outermost to innermost; later nested layers replace the center.
    for level in range(depth):
        scale = ratio ** (level - phase)
        dw, dh = max(1, round(width * scale)), max(1, round(height * scale))
        if dw < 2 or dh < 2:
            break
        if scale >= 1.0:
            # Zoom without allocating enormous intermediate scaled images.
            crop_w = max(1, min(width, round(width / scale)))
            crop_h = max(1, min(height, round(height / scale)))
            x = (width - crop_w) // 2
            y = (height - crop_h) // 2
            crop = frame[y:y + crop_h, x:x + crop_w]
            canvas[:] = cv2.resize(crop, (width, height), interpolation=cv2.INTER_LINEAR)
        else:
            x = (width - dw) // 2
            y = (height - dh) // 2
            # Avoid odd-pixel size overflow and preserve the center.
            dest_w = min(dw, width - x)
            dest_h = min(dh, height - y)
            resized = cv2.resize(frame, (dest_w, dest_h), interpolation=cv2.INTER_AREA)
            canvas[y:y + dest_h, x:x + dest_w] = resized
    return canvas


def positive_even(value: float) -> int:
    return max(2, int(round(value / 2) * 2))


def output_dimensions(width: int, height: int, cap: int) -> tuple[int, int]:
    if cap <= 0:
        return positive_even(width), positive_even(height)
    scale = min(1.0, cap / min(width, height))
    return positive_even(width * scale), positive_even(height * scale)


def render(input_path: Path, output_path: Path, speed: float = 0.5,
           ratio: float = 0.5, depth: int = 10, reverse: bool = False,
           max_short_side: int = 1080, crf: int = 19, preset: str = 'veryfast',
           keep_audio: bool = True, mode: str = "classic",
           start_scale: float = .10, end_scale: float = 5., overlap: float = .50) -> None:
    validate_settings(speed, ratio, depth)
    if mode not in ("classic", "relay"):
        raise ValueError("Modo desconocido")
    if mode == "relay":
        validate_relay(start_scale, end_scale, overlap)
    if not input_path.is_file():
        raise FileNotFoundError(f"No existe el video: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError('La salida no puede sobrescribir al video original')
    if not shutil.which('ffmpeg'):
        raise EnvironmentError('No se encontró FFmpeg. Instalalo y agregalo a PATH.')
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError('No se pudo abrir el video. Probá convertirlo a MP4 H.264.')
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not src_w or not src_h or not math.isfinite(fps) or fps <= 0:
        cap.release()
        raise ValueError('No se pudo identificar la resolución/FPS del archivo')
    w, h = output_dimensions(src_w, src_h, max_short_side)
    fps_str = f'{fps:.8f}'
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
           '-f', 'rawvideo', '-vcodec', 'rawvideo', '-pix_fmt', 'bgr24',
           '-s', f'{w}x{h}', '-r', fps_str, '-i', 'pipe:0']
    if keep_audio:
        cmd += ['-i', str(input_path), '-map', '0:v:0', '-map', '1:a:0?',
                '-c:a', 'aac', '-b:a', '192k']
    else:
        cmd += ['-map', '0:v:0', '-an']
    cmd += ['-c:v', 'libx264', '-preset', preset, '-crf', str(crf),
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-shortest', str(output_path)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f'Entrada: {input_path.name} · {src_w}x{src_h} · {fps:.3f} fps', flush=True)
    print(f'Salida: {output_path} · {w}x{h} · {"audio sí" if keep_audio else "sin audio"}', flush=True)
    print(f'Túnel: velocidad={speed}, separación={ratio}, capas={depth}, dirección={"adentro" if reverse else "afuera"}', flush=True)
    encoder = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    started = time.monotonic()
    processed = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame.shape[1] != w or frame.shape[0] != h:
                frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
            if mode == "relay":
                rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                result = render_relay_frame(rgba, processed / fps, speed, start_scale, end_scale, overlap, reverse)
                # H.264 cannot store alpha. Composite onto black for an honest RGB export.
                alpha = result[..., 3:4].astype(np.float32) / 255.0
                transformed = cv2.cvtColor(np.rint(result[..., :3] * alpha).astype(np.uint8),
                                           cv2.COLOR_RGB2BGR)
            else:
                transformed = tunnel_frame(frame, processed / fps, speed, ratio, depth, reverse)
            try:
                encoder.stdin.write(transformed.tobytes())
            except BrokenPipeError as e:
                raise RuntimeError('FFmpeg dejó de aceptar fotogramas; revisá el códec y espacio disponible') from e
            processed += 1
            if processed % max(1, int(fps)) == 0:
                elapsed = time.monotonic() - started
                pct = 100 * processed / total if total else 0
                print(f'Progreso: {pct:5.1f}% · {processed / fps:.1f} s renderizados · {elapsed:.0f} s transcurridos', flush=True)
    except (Exception, KeyboardInterrupt):
        if encoder.stdin and not encoder.stdin.closed:
            encoder.stdin.close()
        encoder.terminate()
        encoder.wait()
        output_path.unlink(missing_ok=True)
        raise
    finally:
        cap.release()
    if encoder.stdin and not encoder.stdin.closed:
        encoder.stdin.close()
    code = encoder.wait()
    if code:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f'FFmpeg terminó con código {code}')
    print(f'LISTO: {output_path}', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Aplica túnel de zoom infinito al video entero (MP4 + audio).')
    parser.add_argument('input', type=Path, help='Ruta al video de entrada')
    parser.add_argument('-o', '--output', type=Path, help='Archivo de salida (por defecto <nombre>-tunnel.mp4)')
    parser.add_argument('--speed', type=float, default=0.5, help='Ciclos por segundo (modo manual)')
    parser.add_argument('--bpm', type=float, help='Sincronizar entradas con BPM; reemplaza --speed')
    parser.add_argument('--beats-per-entry', type=float, choices=[0.5, 1, 2, 4, 8], default=1,
                        help='Tiempos por nueva copia (4 = un compás de 4/4)')
    parser.add_argument('--ratio', type=float, default=0.5, help='Relación entre niveles, por defecto 0.5')
    parser.add_argument('--depth', type=int, default=10, help='Cantidad de capas recursivas')
    parser.add_argument('--reverse', action='store_true', help='Invertir la dirección, hacia el centro')
    parser.add_argument('--height', type=int, default=1080, help='Límite del lado corto en píxeles; 0 = original')
    parser.add_argument('--crf', type=int, default=19, help='Calidad MP4, menor = mejor (0-51)')
    parser.add_argument('--no-audio', action='store_true', help='Exportar sin audio')
    parser.add_argument('--alpha', action='store_true', help='Conservar transparencia: MOV ProRes 4444 o WebM VP9')
    parser.add_argument('--mode', choices=['classic', 'relay'], default='classic', help='Efecto: túnel clásico o Zoom Relay')
    parser.add_argument('--start-scale', type=float, default=0.10, help='Escala inicial de Relay (0.10 = 10%%)')
    parser.add_argument('--end-scale', type=float, default=5.0, help='Escala final de Relay (5 = 500%%)')
    parser.add_argument('--overlap', type=float, default=.50, help='Fracción de superposición de Relay (0-0.7)')
    args = parser.parse_args()
    ext = '.mov' if args.alpha else '.mp4'
    output = args.output or args.input.with_name(args.input.stem + '-tunnel' + ext)
    try:
        if args.bpm is not None:
            from tempo import tempo_speed
            args.speed = tempo_speed(args.bpm, args.beats_per_entry, args.mode, args.overlap)
        if args.alpha:
            from alpha_renderer import render_alpha
            render_alpha(args.input, output, args.speed, args.ratio, args.depth, args.reverse,
                         args.height, args.crf, keep_audio=not args.no_audio,
                         mode=args.mode, start_scale=args.start_scale,
                         end_scale=args.end_scale, overlap=args.overlap)
        else:
            render(args.input, output, args.speed, args.ratio, args.depth, args.reverse,
                   args.height, args.crf, keep_audio=not args.no_audio,
                   mode=args.mode, start_scale=args.start_scale,
                   end_scale=args.end_scale, overlap=args.overlap)
    except (Exception, KeyboardInterrupt) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
