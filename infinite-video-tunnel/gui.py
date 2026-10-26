#!/usr/bin/env python3
"""Windows GUI: tunnel render + FFmpeg-based CineForm/alpha preview."""
from __future__ import annotations

import base64
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from preview_renderer import probe, preview_png


class TunnelGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Infinite Video Tunnel — video con transparencia')
        self.root.geometry('800x850')
        self.root.minsize(600, 690)
        self.source = tk.StringVar()
        self.speed = tk.DoubleVar(value=0.5)
        self.ratio = tk.DoubleVar(value=0.5)
        self.depth = tk.IntVar(value=10)
        self.reverse = tk.BooleanVar(value=False)
        self.keep_audio = tk.BooleanVar(value=True)
        self.keep_alpha = tk.BooleanVar(value=True)
        self.height = tk.StringVar(value='1080')
        self.position = tk.DoubleVar(value=0)
        self.duration = 0
        self.meta = None
        self.running = False
        self.preview_job = None
        self.generation = 0
        self.preview_image = None
        self.messages = queue.Queue()
        self.build()
        self.root.after(80, self.poll_messages)

    def build(self):
        main = ttk.Frame(self.root, padding=18)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='INFINITE VIDEO TUNNEL', font=('Segoe UI', 18, 'bold')).pack(anchor='w', pady=(0, 5))
        ttk.Label(main, text='Vista previa para CineForm, MOV y videos con transparencia (FFmpeg).').pack(anchor='w', pady=(0, 10))
        row = ttk.Frame(main)
        row.pack(fill='x', pady=3)
        ttk.Entry(row, textvariable=self.source).pack(side='left', expand=True, fill='x')
        ttk.Button(row, text='Elegir video', command=self.choose).pack(side='left', padx=(8, 0))

        # A real preview: the old desktop version had no preview at all.
        preview_frame = ttk.LabelFrame(main, text='PREVISUALIZACIÓN (fondo a cuadros = transparencia)')
        preview_frame.pack(fill='both', expand=True, pady=(9, 6))
        self.preview_label = ttk.Label(preview_frame, text='Elegí un video para ver el túnel', anchor='center')
        self.preview_label.pack(fill='both', expand=True, padx=6, pady=6)
        seek = ttk.Frame(main)
        seek.pack(fill='x', pady=(0, 4))
        self.seek_slider = ttk.Scale(seek, from_=0, to=1000, variable=self.position, command=self.on_seek)
        self.seek_slider.pack(side='left', fill='x', expand=True)
        self.time_label = ttk.Label(seek, text='00:00 / 00:00', width=15, anchor='e')
        self.time_label.pack(side='left', padx=(10, 0))
        self.status = ttk.Label(main, text='El previsualizador decodifica con FFmpeg, no con el navegador.')
        self.status.pack(anchor='w', pady=(0, 6))
        for label, var, lo, hi in [
            ('Velocidad (ciclos/segundo)', self.speed, 0.1, 2.5),
            ('Separación de capas', self.ratio, 0.3, 0.75),
            ('Profundidad', self.depth, 4, 16)
        ]:
            field = ttk.Frame(main)
            field.pack(fill='x', pady=(5, 0))
            ttk.Label(field, text=label, width=29).pack(side='left')
            ttk.Scale(field, from_=lo, to=hi, variable=var, command=self.on_settings).pack(side='left', fill='x', expand=True)
        ttk.Checkbutton(main, text='Dirección hacia el centro', variable=self.reverse, command=self.schedule_preview).pack(anchor='w', pady=(8, 0))
        ttk.Checkbutton(main, text='Conservar audio', variable=self.keep_audio).pack(anchor='w', pady=(3, 0))
        ttk.Checkbutton(main, text='Conservar transparencia (MOV ProRes 4444)', variable=self.keep_alpha,
                        command=self.alpha_changed).pack(anchor='w', pady=(4, 0))
        settings = ttk.Frame(main)
        settings.pack(fill='x', pady=9)
        ttk.Label(settings, text='Lado corto máximo').pack(side='left')
        ttk.Combobox(settings, textvariable=self.height, state='readonly', width=10,
                     values=['540', '720', '1080', '0']).pack(side='left', padx=12)
        ttk.Label(settings, text='0 = resolución original').pack(side='left')
        self.button = ttk.Button(main, text='Exportar MOV transparente', command=self.start)
        self.button.pack(fill='x', pady=(3, 8))
        self.log = tk.Text(main, height=5, wrap='word', state='disabled')
        self.log.pack(fill='x')

    @staticmethod
    def fmt(seconds):
        return f'{int(seconds) // 60:02d}:{int(seconds) % 60:02d}'

    def alpha_changed(self):
        self.button.config(text='Exportar MOV transparente' if self.keep_alpha.get() else 'Exportar MP4 completo')

    def choose(self):
        path = filedialog.askopenfilename(filetypes=[('Videos', '*.mp4 *.mov *.webm *.mkv *.avi'), ('Todos', '*.*')])
        if not path:
            return
        self.source.set(path)
        self.meta = None
        self.generation += 1
        self.status.config(text='Leyendo archivo con FFmpeg…')
        self.preview_label.config(text='Preparando vista previa…', image='')
        threading.Thread(target=self.load_metadata, args=(path,), daemon=True).start()

    def load_metadata(self, path):
        try:
            self.messages.put(('meta', path, probe(Path(path))))
        except Exception as e:
            self.messages.put(('meta_error', path, str(e)))

    def on_seek(self, unused=None):
        if self.duration:
            self.time_label.config(text=f'{self.fmt(self.position.get() / 1000 * self.duration)} / {self.fmt(self.duration)}')
            self.schedule_preview()

    def on_settings(self, unused=None):
        self.schedule_preview()

    def schedule_preview(self):
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
        self.generation += 1
        self.preview_job = self.root.after(320, self.request_preview)

    def request_preview(self):
        self.preview_job = None
        if not self.meta or not Path(self.source.get()).is_file():
            return
        generation = self.generation
        path = Path(self.source.get())
        at = self.position.get() / 1000 * self.duration
        settings = (float(self.speed.get()), float(self.ratio.get()), int(round(self.depth.get())), self.reverse.get())
        meta = self.meta.copy()
        self.status.config(text=f'Generando vista previa · {self.fmt(at)}…')
        threading.Thread(target=self.make_preview, args=(generation, path, at, settings, meta), daemon=True).start()

    def make_preview(self, generation, path, at, settings, meta):
        try:
            png = preview_png(path, at, *settings, source_meta=meta, max_short_side=480)
            self.messages.put(('preview', generation, png))
        except Exception as e:
            self.messages.put(('preview_error', generation, str(e)))

    def poll_messages(self):
        try:
            while True:
                message = self.messages.get_nowait()
                kind = message[0]
                if kind == 'meta':
                    _, path, meta = message
                    if path == self.source.get():
                        self.meta = meta
                        self.duration = meta['duration']
                        self.position.set(0)
                        self.time_label.config(text=f'00:00 / {self.fmt(self.duration)}')
                        self.status.config(text=f"Códec: {meta['codec']} · {meta['width']}×{meta['height']} · {meta['pix_fmt']}")
                        # t=0 can be pure transparency, prefer the first second when available.
                        self.position.set(min(1000, 1000 * min(1.0, self.duration * 0.1) / self.duration))
                        self.schedule_preview()
                elif kind == 'meta_error':
                    _, path, error = message
                    if path == self.source.get():
                        self.status.config(text='Error al leer el video')
                        messagebox.showerror('Video no compatible', error)
                elif kind == 'preview':
                    _, gen, png = message
                    if gen == self.generation:
                        self.preview_image = tk.PhotoImage(data=base64.b64encode(png).decode('ascii'))
                        self.preview_label.config(image=self.preview_image, text='')
                        self.status.config(text='Vista previa generada con FFmpeg. Los cuadros indican transparencia.')
                elif kind == 'preview_error':
                    _, gen, error = message
                    if gen == self.generation:
                        self.preview_label.config(image='', text='No se pudo mostrar este fotograma')
                        self.status.config(text='Error en la vista previa')
                        self.append('Vista previa: ' + error)
        except queue.Empty:
            pass
        self.root.after(80, self.poll_messages)

    def append(self, msg):
        def update():
            self.log.config(state='normal')
            self.log.insert('end', msg + '\n')
            self.log.see('end')
            self.log.config(state='disabled')
        self.root.after(0, update)

    def start(self):
        source = Path(self.source.get())
        if not source.is_file():
            messagebox.showerror('Falta el video', 'Elegí primero un video de entrada.')
            return
        ext = '.mov' if self.keep_alpha.get() else '.mp4'
        out = filedialog.asksaveasfilename(defaultextension=ext, initialfile=source.stem + '-tunnel' + ext,
                                           filetypes=[('Video transparente ProRes 4444', '*.mov')] if self.keep_alpha.get()
                                           else [('Video MP4', '*.mp4')])
        if not out:
            return
        args = [sys.executable, str(Path(__file__).parent / 'render.py'), str(source), '-o', out,
                '--speed', str(round(self.speed.get(), 2)), '--ratio', str(round(self.ratio.get(), 2)),
                '--depth', str(round(self.depth.get())), '--height', self.height.get()]
        if self.reverse.get(): args.append('--reverse')
        if self.keep_alpha.get(): args.append('--alpha')
        if not self.keep_audio.get(): args.append('--no-audio')
        self.button.config(state='disabled')
        threading.Thread(target=self.worker, args=(args, out), daemon=True).start()

    def worker(self, args, out):
        success = False
        try:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    encoding='utf-8', errors='replace', bufsize=1)
            for line in proc.stdout:
                self.append(line.rstrip())
            success = proc.wait() == 0
        except Exception as e:
            self.append(str(e))
        finally:
            self.root.after(0, lambda: self.button.config(state='normal'))
            if success:
                self.root.after(0, lambda: messagebox.showinfo('Listo', f'Video exportado:\n{out}'))
            else:
                self.root.after(0, lambda: messagebox.showerror('Error', 'No se pudo exportar. Consultá el registro de abajo.'))


if __name__ == '__main__':
    TunnelGUI().root.mainloop()
