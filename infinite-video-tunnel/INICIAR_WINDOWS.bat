@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo No se encontro Python Launcher. Instala Python desde https://www.python.org/downloads/
  pause
  exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo No se encontro FFmpeg.
  echo Instala desde terminal PowerShell: winget install Gyan.FFmpeg
  echo Cierra y abre esta ventana despues de instalar.
  pause
  exit /b 1
)
py -3 -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
py -3 gui.py
if errorlevel 1 pause