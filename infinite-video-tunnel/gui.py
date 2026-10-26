#!/usr/bin/env python3
"""Windows GUI: real-time FFmpeg CineForm/alpha tunnel playback and export.

The preview plays continuously (Play/Pause/seek) using one FFmpeg decoder.
The output rendering remains frame-accurate and full-resolution.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from PIL import Image, ImageTk

from preview_renderer import probe, preview_png
from preview_stream import PreviewDecoder, make_checker, render_preview_rgb
from render import output_dimensions

PREVIEW_FPS = 15
PREVIEW_SHORT_SIDE = 360


class TunnelGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Infinite Video Tunnel v2.0 — Zoom Relay')
        self.root.geometry('890x980')
        self.root.minsize(650, 720)
        self.source = tk.StringVar()
        self.speed = tk.DoubleVar(value=0.5)
        self.ratio = tk.DoubleVar(value=0.5)
        self.depth = tk.IntVar(value=10)
        self.reverse = tk.BooleanVar(value=False)
        self.mode = tk.StringVar(value='relay')
        self.start_scale = tk.DoubleVar(value=.10)
        self.end_scale = tk.DoubleVar(value=5.0)
        self.overlap = tk.DoubleVar(value=.50)
        self.keep_audio = tk.BooleanVar(value=True)
        self.keep_alpha = tk.BooleanVar(value=True)
        self.height = tk.StringVar(value='1080')
        self.position = tk.DoubleVar(value=0)
        self.duration = 0.0
        self.meta = None
        self.preview_job = None
        self.still_generation = 0
        self.preview_image = None
        self.messages = queue.Queue()
        self.frame_queue = queue.Queue(maxsize=2)
        self.playing = False
        self.session = 0
        self.stop_event = threading.Event()
        self.current_decoder = None
        self.decoder_lock = threading.Lock()
        self.play_settings = (.5, .5, 10, False, 'relay', .10, 5., .50)
        self._update_slider = False
        self._closing = False
        self.build()
        self.root.after(25, self.poll_messages)
        self.root.protocol('WM_DELETE_WINDOW', self.close)

    def build(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='INFINITE VIDEO TUNNEL', font=('Segoe UI', 18, 'bold')).pack(anchor='w', pady=(0, 4))
        ttk.Label(main, text='Zoom Relay: las copias llegan desde atrás, se acercan y salen. Reproducción CineForm con alfa.').pack(anchor='w', pady=(0, 8))
        row = ttk.Frame(main)
        row.pack(fill='x', pady=3)
        ttk.Entry(row, textvariable=self.source).pack(side='left', expand=True, fill='x')
        ttk.Button(row, text='Elegir video', command=self.choose).pack(side='left', padx=(8, 0))

        preview_frame = ttk.LabelFrame(main, text='REPRODUCCIÓN · tablero a cuadros = transparencia')
        preview_frame.pack(fill='both', expand=True, pady=(8, 5))
        self.preview_label = ttk.Label(preview_frame, text='Elegí un video para empezar', anchor='center')
        self.preview_label.pack(fill='both', expand=True, padx=6, pady=6)
        self.preview_label.bind('<Configure>', self.fit_preview)
        controls = ttk.Frame(main)
        controls.pack(fill='x', pady=(0, 4))
        self.play_btn = ttk.Button(controls, text='▶ Reproducir', command=self.toggle_play, state='disabled')
        self.play_btn.pack(side='left', padx=(0, 8))
        self.seek_slider = ttk.Scale(controls, from_=0, to=1000, variable=self.position, command=self.on_seek)
        self.seek_slider.pack(side='left', fill='x', expand=True)
        self.time_label = ttk.Label(controls, text='00:00 / 00:00', width=15, anchor='e')
        self.time_label.pack(side='left', padx=(10, 0))
        self.status = ttk.Label(main, text='La vista previa no necesita que el navegador lea CineForm.')
        self.status.pack(anchor='w', pady=(0, 6))
        mode_row = ttk.Frame(main)
        mode_row.pack(fill='x', pady=(4, 4))
        ttk.Label(mode_row, text='EFECTO', width=17).pack(side='left')
        ttk.Radiobutton(mode_row, text='Zoom Relay (nuevo)', variable=self.mode, value='relay',
                        command=self.mode_changed).pack(side='left', padx=(0, 16))
        ttk.Radiobutton(mode_row, text='Túnel clásico', variable=self.mode, value='classic',
                        command=self.mode_changed).pack(side='left')

        field = ttk.Frame(main)
        field.pack(fill='x', pady=(3, 4))
        ttk.Label(field, text='Velocidad (ciclos/segundo)', width=29).pack(side='left')
        ttk.Scale(field, from_=0.1, to=2.5, variable=self.speed,
                  command=self.on_settings).pack(side='left', fill='x', expand=True)

        self.classic_frame = ttk.Frame(main)
        for label, var, lo, hi in [('Separación de capas', self.ratio, 0.3, 0.75),
                                   ('Profundidad', self.depth, 4, 16)]:
            field = ttk.Frame(self.classic_frame)
            field.pack(fill='x', pady=(3, 0))
            ttk.Label(field, text=label, width=29).pack(side='left')
            ttk.Scale(field, from_=lo, to=hi, variable=var, command=self.on_settings).pack(
                side='left', fill='x', expand=True)

        self.relay_frame = ttk.Frame(main)
        for label, var, lo, hi in [('Escala inicial (2%-100%)', self.start_scale, .02, 1.0),
                                   ('Escala máxima (110%-1200%)', self.end_scale, 1.1, 12.0),
                                   ('Superposición (0%-70%)', self.overlap, 0., .70)]:
            field = ttk.Frame(self.relay_frame)
            field.pack(fill='x', pady=(3, 0))
            ttk.Label(field, text=label, width=29).pack(side='left')
            ttk.Scale(field, from_=lo, to=hi, variable=var, command=self.on_settings).pack(
                side='left', fill='x', expand=True)
        self.relay_frame.pack(fill='x')
        self.hint_label = ttk.Label(main, text='Relay: la copia grande queda delante; la nueva nace detrás y aparece al desvanecerse la anterior.',
                  foreground='#888')
        self.hint_label.pack(anchor='w', pady=(2, 4))
        ttk.Checkbutton(main, text='Invertir dirección (hacia el centro)', variable=self.reverse,
                        command=self.on_settings).pack(anchor='w', pady=(3, 0))
        ttk.Checkbutton(main, text='Conservar audio al exportar', variable=self.keep_audio).pack(anchor='w', pady=(3, 0))
        ttk.Checkbutton(main, text='Conservar transparencia (MOV ProRes 4444)', variable=self.keep_alpha,
                        command=self.alpha_changed).pack(anchor='w', pady=(4, 0))
        settings = ttk.Frame(main)
        settings.pack(fill='x', pady=9)
        ttk.Label(settings, text='Lado corto máximo al exportar').pack(side='left')
        ttk.Combobox(settings, textvariable=self.height, state='readonly', width=10,
                     values=['540', '720', '1080', '0']).pack(side='left', padx=12)
        ttk.Label(settings, text='0 = resolución original').pack(side='left')
        self.button = ttk.Button(main, text='Exportar MOV transparente', command=self.start)
        self.button.pack(fill='x', pady=(3, 8))
        self.log = tk.Text(main, height=4, wrap='word', state='disabled')
        self.log.pack(fill='x')

    @staticmethod
    def fmt(seconds):
        return f'{int(seconds) // 60:02d}:{int(seconds) % 60:02d}'

    def alpha_changed(self):
        self.button.config(text='Exportar MOV transparente' if self.keep_alpha.get() else 'Exportar MP4 completo')

    def mode_changed(self):
        if self.mode.get() == 'relay':
            self.classic_frame.pack_forget()
            self.relay_frame.pack(fill='x', before=self.hint_label)
        else:
            self.relay_frame.pack_forget()
            self.classic_frame.pack(fill='x', before=self.hint_label)
        self.on_settings()

    def choose(self):
        path = filedialog.askopenfilename(filetypes=[('Videos', '*.mp4 *.mov *.webm *.mkv *.avi'), ('Todos', '*.*')])
        if not path:
            return
        self.pause_play()
        self.source.set(path)
        self.meta = None
        self.still_generation += 1
        self.play_btn.config(state='disabled')
        self.status.config(text='Leyendo video con FFmpeg…')
        self.preview_label.config(text='Preparando vista previa…', image='')
        threading.Thread(target=self.load_metadata, args=(path,), daemon=True).start()

    def load_metadata(self, path):
        try:
            self.messages.put(('meta', path, probe(Path(path))))
        except Exception as e:
            self.messages.put(('meta_error', path, str(e)))

    def on_seek(self, unused=None):
        if not self.duration or self._update_slider:
            return
        at = self.position.get() / 1000 * self.duration
        self.time_label.config(text=f'{self.fmt(at)} / {self.fmt(self.duration)}')
        # Debounce while dragging, then resume playback at the new position.
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
        if self.playing:
            self.preview_job = self.root.after(180, self.restart_play)
        else:
            self.schedule_still()

    def on_settings(self, unused=None):
        self.play_settings = (float(self.speed.get()), float(self.ratio.get()), int(round(self.depth.get())),
                              self.reverse.get(), self.mode.get(), float(self.start_scale.get()),
                              float(self.end_scale.get()), float(self.overlap.get()))
        # The playing thread reads the latest settings for each frame.
        if not self.playing:
            self.schedule_still()

    def schedule_still(self):
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
        self.still_generation += 1
        self.preview_job = self.root.after(180, self.request_still)

    def request_still(self):
        self.preview_job = None
        if not self.meta or self.playing or not Path(self.source.get()).is_file():
            return
        gen = self.still_generation
        path = Path(self.source.get())
        at = self.position.get() / 1000 * self.duration
        settings = self.play_settings
        meta = self.meta.copy()
        threading.Thread(target=self.make_still, args=(gen, path, at, settings, meta), daemon=True).start()

    def make_still(self, gen, path, at, settings, meta):
        try:
            from io import BytesIO
            picture = Image.open(BytesIO(preview_png(path, at, *settings, source_meta=meta,
                                                     max_short_side=PREVIEW_SHORT_SIDE))).convert('RGB')
            self.messages.put(('still', gen, picture.copy()))
        except Exception as e:
            self.messages.put(('still_error', gen, str(e)))

    def toggle_play(self):
        if self.playing:
            self.pause_play()
        else:
            self.start_play()

    def start_play(self):
        if not self.meta or self.playing:
            return
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
            self.preview_job = None
        self.still_generation += 1
        if self.position.get() / 1000 * self.duration >= self.duration - 0.04:
            self._set_position(0)
        self.playing = True
        self.play_btn.config(text='❚❚ Pausar')
        self._start_decoder(self.position.get() / 1000 * self.duration)

    def restart_play(self):
        self.preview_job = None
        if self.playing:
            self._start_decoder(self.position.get() / 1000 * self.duration)

    def _stop_decoder(self):
        self.stop_event.set()
        with self.decoder_lock:
            decoder = self.current_decoder
            self.current_decoder = None
        if decoder is not None:
            decoder.stop()

    def _start_decoder(self, position_seconds):
        self.session += 1
        self._stop_decoder()
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break
        self.stop_event = threading.Event()
        generation = self.session
        source = Path(self.source.get())
        meta = self.meta.copy()
        self.status.config(text=f'Reproduciendo · vista previa {PREVIEW_FPS} fps (sin audio)')
        threading.Thread(target=self.play_worker,
                         args=(generation, source, position_seconds, meta, self.stop_event), daemon=True).start()

    def pause_play(self):
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
            self.preview_job = None
        self.playing = False
        self.session += 1
        self._stop_decoder()
        if hasattr(self, 'play_btn'):
            self.play_btn.config(text='▶ Reproducir')
        if self.meta and not self._closing:
            self.schedule_still()

    def play_worker(self, session, path, at, meta, stop):
        w, h = output_dimensions(meta['width'], meta['height'], PREVIEW_SHORT_SIDE)
        checker = make_checker(w, h)
        tick = 1 / PREVIEW_FPS
        wall_start = time.monotonic()
        index = 0
        try:
            with PreviewDecoder(path, at, w, h, PREVIEW_FPS) as decoder:
                with self.decoder_lock:
                    if stop.is_set():
                        return
                    self.current_decoder = decoder
                for frame in decoder:
                    if stop.is_set():
                        break
                    t = at + index * tick
                    target = wall_start + index * tick
                    index += 1
                    if target + tick < time.monotonic():
                        # Drop late preview frames instead of slowing video time.
                        continue
                    speed, ratio, depth, reverse, mode, start_scale, end_scale, overlap = self.play_settings
                    rgb = render_preview_rgb(frame, t, speed, ratio, depth, reverse, checker,
                                             mode, start_scale, end_scale, overlap)
                    remaining = target - time.monotonic()
                    if remaining > 0 and stop.wait(remaining):
                        break
                    if stop.is_set():
                        break
                    # Keep only fresh frames; never build up seconds of latency.
                    while self.frame_queue.full():
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            break
                    self.frame_queue.put_nowait((session, t, rgb))
            if not stop.is_set():
                self.messages.put(('play_ended', session, index > 0))
        except Exception as e:
            if not stop.is_set():
                self.messages.put(('play_error', session, str(e)))
        finally:
            with self.decoder_lock:
                if self.current_decoder is decoder if 'decoder' in locals() else False:
                    self.current_decoder = None

    def _set_position(self, seconds):
        self._update_slider = True
        self.position.set(1000 * max(0., min(seconds, self.duration)) / max(self.duration, .001))
        self._update_slider = False
        self.time_label.config(text=f'{self.fmt(seconds)} / {self.fmt(self.duration)}')

    def show_image(self, image):
        if self._closing:
            return
        # Resize to fit the current widget while preserving aspect ratio.
        width = max(100, self.preview_label.winfo_width() - 6)
        height = max(100, self.preview_label.winfo_height() - 6)
        fitted = image.copy()
        fitted.thumbnail((width, height), Image.Resampling.BILINEAR)
        self.preview_image = ImageTk.PhotoImage(fitted)
        self.preview_label.config(image=self.preview_image, text='')
        self._last_rgb = image

    def fit_preview(self, unused=None):
        if hasattr(self, '_last_rgb') and self._last_rgb is not None:
            # Avoid resize feedback: the widget's allocated size does not depend on image pixel size.
            self.show_image(self._last_rgb)

    def poll_messages(self):
        if self._closing:
            return
        try:
            while True:
                msg = self.messages.get_nowait()
                kind = msg[0]
                if kind == 'meta':
                    _, path, meta = msg
                    if path == self.source.get():
                        self.meta = meta
                        self.duration = meta['duration']
                        self._set_position(min(1., self.duration * .1))
                        self.status.config(text=f"Códec: {meta['codec']} · {meta['width']}×{meta['height']} · {meta['pix_fmt']}")
                        self.play_btn.config(state='normal')
                        self.schedule_still()
                elif kind == 'meta_error':
                    _, path, err = msg
                    if path == self.source.get():
                        self.status.config(text='Error de FFmpeg')
                        messagebox.showerror('Video no compatible', err)
                elif kind == 'still':
                    _, gen, img = msg
                    if gen == self.still_generation and not self.playing:
                        self.show_image(img)
                        self.status.config(text='Pausado · ▶ Reproducir para ver el efecto en movimiento')
                elif kind == 'still_error':
                    _, gen, err = msg
                    if gen == self.still_generation and not self.playing:
                        self.status.config(text='No se pudo mostrar el fotograma')
                        self.append('Vista previa: ' + err)
                elif kind == 'play_ended':
                    _, session, has_frames = msg
                    if session == self.session and self.playing:
                        self.pause_play()
                        if has_frames:
                            self._set_position(self.duration)
                elif kind == 'play_error':
                    _, session, err = msg
                    if session == self.session:
                        self.pause_play()
                        self.status.config(text='Error de reproducción')
                        self.append('Reproducción: ' + err)
        except queue.Empty:
            pass
        # Only the newest decoded frame should be presented if UI was busy.
        newest = None
        try:
            while True:
                newest = self.frame_queue.get_nowait()
        except queue.Empty:
            pass
        if newest is not None:
            session, t, frame = newest
            if session == self.session and self.playing:
                self.show_image(Image.fromarray(frame, mode='RGB'))
                self._set_position(t)
        self.root.after(25, self.poll_messages)

    def append(self, msg):
        def update():
            if self._closing:
                return
            self.log.config(state='normal')
            self.log.insert('end', msg + '\n')
            self.log.see('end')
            self.log.config(state='disabled')
        if not self._closing:
            self.root.after(0, update)

    def start(self):
        self.pause_play()
        source = Path(self.source.get())
        if not source.is_file():
            messagebox.showerror('Falta el video', 'Elegí primero un video de entrada.')
            return
        ext = '.mov' if self.keep_alpha.get() else '.mp4'
        out = filedialog.asksaveasfilename(defaultextension=ext,
                                           initialfile=source.stem + '-tunnel' + ext,
                                           filetypes=[('Video transparente ProRes 4444', '*.mov')]
                                           if self.keep_alpha.get() else [('Video MP4', '*.mp4')])
        if not out:
            return
        args = [sys.executable, str(Path(__file__).parent / 'render.py'), str(source), '-o', out,
                '--mode', self.mode.get(), '--start-scale', str(round(self.start_scale.get(), 3)),
                '--end-scale', str(round(self.end_scale.get(), 3)),
                '--overlap', str(round(self.overlap.get(), 3)),
                '--speed', str(round(self.speed.get(), 2)), '--ratio', str(round(self.ratio.get(), 2)),
                '--depth', str(round(self.depth.get())), '--height', self.height.get()]
        if self.reverse.get():
            args.append('--reverse')
        if self.keep_alpha.get():
            args.append('--alpha')
        if not self.keep_audio.get():
            args.append('--no-audio')
        self.button.config(state='disabled')
        threading.Thread(target=self.worker, args=(args, out), daemon=True).start()

    def worker(self, args, out):
        success = False
        try:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    encoding='utf-8', errors='replace', bufsize=1,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            for line in proc.stdout:
                self.append(line.rstrip())
            success = proc.wait() == 0
        except Exception as e:
            self.append(str(e))
        finally:
            if not self._closing:
                self.root.after(0, lambda: self.button.config(state='normal'))
                if success:
                    self.root.after(0, lambda: messagebox.showinfo('Listo', f'Video exportado:\n{out}'))
                else:
                    self.root.after(0, lambda: messagebox.showerror('Error', 'No se pudo exportar. Consultá el registro de abajo.'))

    def close(self):
        self._closing = True
        self.pause_play()
        self.root.destroy()


if __name__ == '__main__':
    TunnelGUI().root.mainloop()
