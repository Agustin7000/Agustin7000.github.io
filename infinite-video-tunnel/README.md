# INFINITE VIDEO TUNNEL

Generador gratuito de **zoom infinito / efecto túnel recursivo** para videos completos. Creado para trabajar con MP4 de varios minutos, sin límites de duración de la página ni servicios externos de IA.

## Usarlo desde el navegador

**Sitio web:** https://agustincabrera.com.ar/infinite-video-tunnel/

1. Cargá un video desde tu computadora. El video **no se sube a ningún servidor**.
2. Ajustá la velocidad del túnel y, opcionalmente, la separación, profundidad y dirección.
3. Mirá la vista previa y presioná **Exportar video completo**.
4. Dejá la pestaña abierta y visible; el navegador graba la animación en tiempo real. Un video de 2 minutos requiere aproximadamente 2 minutos de reproducción para exportarse.
5. Descargá el resultado cuando termine.

**Compatibilidad:** Firefox exporta normalmente WebM; otros navegadores pueden exportar MP4 si su implementación de `MediaRecorder` lo permite. La disponibilidad de audio también depende del navegador. Para **MP4 H.264 con audio de forma confiable**, usá el renderizador local siguiente.

No hay un límite artificial de 30 segundos. Los límites efectivos son RAM, rendimiento y codecs del navegador.

## MP4 en Windows, sin límite de duración

1. Descargá el ZIP del proyecto desde GitHub (**Code → Download ZIP**) y extraelo.
2. Instalá [Python 3](https://www.python.org/downloads/) (marcando **Add python.exe to PATH**).
3. Instalá FFmpeg desde PowerShell: `winget install Gyan.FFmpeg`, y abrí una nueva terminal.
4. Hacé doble clic en `INICIAR_WINDOWS.bat`.
5. Elegí un video, ajustá los controles y exportá MP4. El audio original se incluye si tiene pista de audio.

El exportador procesa fotograma por fotograma; no está limitado por una grabación en tiempo real. La duración de proceso depende de resolución y CPU.

### Modo consola

```bash
pip install -r requirements.txt
python render.py "entrada.mp4" --speed 0.5 --ratio 0.5 --depth 10 -o "salida-tunnel.mp4"
```

Parámetros: `--speed` (ciclos/s), `--ratio` (relación de escala), `--depth` (número de capas), `--reverse` (hacia el centro), `--height 720` (límite del lado corto), `--no-audio`.

## Cómo funciona

No usa IA, ni genera fotogramas sintéticos. Para cada fotograma del video fuente, crea capas recursivas centradas con escala:

`escala(capa, tiempo) = separacion ^ (capa - fracción(tiempo × velocidad))`

Al cumplirse cada ciclo, las escalas de todas las capas se desplazan exactamente una posición: la capa que era pequeña se vuelve la grande. La ilusión se repite continuamente y no requiere cortar el video ni reiniciar el movimiento. Los bordes de las copias pueden ser visibles: es parte del efecto recursivo (Droste).

## Nota sobre privacidad

El sitio es HTML/CSS/JS estático; procesa los archivos en el navegador mediante Canvas y MediaRecorder, sin endpoints de subida. El renderizador local trabaja íntegramente en tu computadora.

## Licencia

MIT. Ver `LICENSE`.