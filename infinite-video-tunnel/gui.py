#!/usr/bin/env python3
"""Simple local MP4 renderer GUI (Tkinter)."""
from __future__ import annotations

import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path


class TunnelGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Infinite Video Tunnel — exportar MP4')
        self.root.geometry('660x590')
        self.root.minsize(480, 460)
        self.source = tk.StringVar()
        self.speed = tk.DoubleVar(value=0.5)
        self.ratio = tk.DoubleVar(value=0.5)
        self.depth = tk.IntVar(value=10)
        self.reverse = tk.BooleanVar(value=False)
        self.keep_audio = tk.BooleanVar(value=True)
        self.keep_alpha = tk.BooleanVar(value=False)
        self.height = tk.StringVar(value='1080')
        self.running = False
        self.build()

    def build(self):
        main = ttk.Frame(self.root, padding=22)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='INFINITE VIDEO TUNNEL', font=('Segoe UI', 19, 'bold')).pack(anchor='w', pady=(0, 6))
        ttk.Label(main, text='Renderizá videos largos como MP4, sin límite de duración.').pack(anchor='w', pady=(0, 18))
        row = ttk.Frame(main)
        row.pack(fill='x', pady=4)
        ttk.Entry(row, textvariable=self.source).pack(side='left', expand=True, fill='x')
        ttk.Button(row, text='Elegir video', command=self.choose).pack(side='left', padx=(8, 0))
        for label, var, lo, hi in [('Velocidad (ciclos/segundo)', self.speed, 0.1, 2.5),
                                   ('Separación de capas', self.ratio, 0.3, 0.75),
                                   ('Profundidad', self.depth, 4, 16)]:
            ttk.Label(main, text=label).pack(anchor='w', pady=(13, 0))
            ttk.Scale(main, from_=lo, to=hi, variable=var).pack(fill='x', pady=(3, 2))
        ttk.Checkbutton(main, text='Dirección hacia el centro', variable=self.reverse).pack(anchor='w', pady=(8, 0))
        ttk.Checkbutton(main, text='Conservar audio', variable=self.keep_audio).pack(anchor='w', pady=(6, 0))
        ttk.Checkbutton(main, text='Conservar transparencia (MOV ProRes 4444)', variable=self.keep_alpha,
                        command=self.alpha_changed).pack(anchor='w', pady=(7, 0))
        ttk.Label(main, text='Para tu video recortado de Filmora: activar transparencia. MP4 H.264 no admite alfa.',
                  foreground='#888').pack(anchor='w', pady=(2, 0))
        settings = ttk.Frame(main)
        settings.pack(fill='x', pady=12)
        ttk.Label(settings, text='Lado corto máximo').pack(side='left')
        ttk.Combobox(settings, textvariable=self.height, state='readonly', width=12,
                     values=['540', '720', '1080', '0']).pack(side='left', padx=12)
        ttk.Label(settings, text='0 = resolución original').pack(side='left')
        self.button = ttk.Button(main, text='Exportar video completo', command=self.start)
        self.button.pack(fill='x', pady=8)
        self.log = tk.Text(main, height=7, wrap='word', state='disabled')
        self.log.pack(fill='both', expand=True)

    def alpha_changed(self):
        self.button.config(text='Exportar MOV transparente' if self.keep_alpha.get() else 'Exportar MP4 completo')

    def choose(self):
        path = filedialog.askopenfilename(filetypes=[('Videos', '*.mp4 *.mov *.webm *.mkv *.avi'), ('Todos', '*.*')])
        if path:
            self.source.set(path)

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
