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

## Video transparente desde Filmora (v1.2)

**Usá el renderizador Windows; la exportación web no garantiza canal alfa.**

1. Exportá desde Filmora un video que realmente conserve transparencia (por ejemplo CineForm o ProRes 4444). No lo conviertas a H.264 para reproducirlo: el MP4 H.264 tradicional elimina el alfa.
2. Abrí `INICIAR_WINDOWS.bat`, seleccioná el video original y activá **Conservar transparencia (MOV ProRes 4444)**.
3. Ajustá velocidad / separación / profundidad y exportá. El resultado conserva las zonas transparentes y se puede volver a colocar sobre otro fondo en Filmora.
4. Tené en cuenta que ProRes 4444 es un códec de edición que puede generar archivos bastante grandes y no abrirse en reproductores comunes. Comprobá el resultado **dentro de Filmora con una imagen debajo**.

Para transparencia desde la línea de comandos:

```bash
python render.py "entrada-cineform.mov" --alpha --speed 0.5 --ratio 0.5 --depth 10 -o "tunnel-transparente.mov"
```

También admite salida WebM VP9 con alfa si indicás un nombre terminado en `.webm`, por ejemplo:

```bash
python render.py "entrada-cineform.mov" --alpha -o "tunnel-transparente.webm"
```

La entrada puede ser `.mp4`, `.mov`, `.webm` u otro contenedor que FFmpeg pueda decodificar. Si un archivo MP4 no se abre en el navegador, **no lo conviertas a H.264** si querés conservar la transparencia; abrí el original en el exportador local.

La transparencia se conserva mediante composición de capas con alfa pre-multiplicado (evita contornos oscuros). La versión de navegador muestra un tablero de transparencia si el navegador es capaz de decodificar el archivo, pero la exportación web con `MediaRecorder` no tiene garantía de canal alfa; para un resultado fiable usá ProRes 4444 local.

### Pruebas realizadas

Render de una secuencia de prueba transparente con **CineForm → ProRes 4444** y **CineForm → VP9 WebM alfa**, verificando formato de píxeles (`yuva444p12le`, `alpha_mode=1`), fotogramas y valores de alfa tras decodificar el resultado. Las pruebas no sustituyen probar tu archivo específico exportado de Filmora.

## Previsualizador de video transparente (v1.2)

El previsualizador del navegador **no puede decodificar MP4 CineForm de Filmora en muchos navegadores**: puede verse vacío aunque el archivo sea válido. La versión 1.2 ahora muestra un aviso tras unos segundos si no puede decodificarlo, en lugar de dejar una pantalla vacía sin explicación.

**Solución sin convertir el original:** abrir `INICIAR_WINDOWS.bat` y usar el nuevo previsualizador. Se decodifica directamente con FFmpeg y muestra el zoom sobre un tablero a cuadros para revelar las áreas transparentes. Incluye un deslizador para ver diferentes instantes del video y permite ajustar velocidad, separación y profundidad antes de exportar a MOV ProRes 4444. La previsualización es por fotogramas, no reproducción en tiempo real.

El material original no se altera. La transparencia sólo se pierde si se escoge exportar a MP4 H.264 normal; para usarlo sobre fondos en Filmora, seleccionar **Conservar transparencia**.

## Reproducción continua de CineForm transparente (v1.3)

**Esta es la opción recomendada para videos transparentes de Filmora.** La vista web depende de los códecs admitidos por Chrome/Firefox, que habitualmente no decodifican CineForm MP4. El programa de Windows no usa el reproductor del navegador.

1. Abrí `INICIAR_WINDOWS.bat` (Python 3, FFmpeg instalado y accesible desde PATH).
2. Elegí el MP4 CineForm transparente de Filmora.
3. Apretá **▶ Reproducir** para ver el **túnel animado de principio a fin** sobre el tablero que representa transparencia.
4. Ajustá velocidad, separación o profundidad mientras se reproduce, usá **❚❚ Pausar** o mové la línea de tiempo.
5. Marcá **Conservar transparencia (MOV ProRes 4444)** y exportá el resultado para volver a colocarlo encima de otro fondo en Filmora.

La reproducción de Windows decodifica cuadros continuamente con FFmpeg y muestra hasta **15 fps a resolución reducida (lado corto máximo 360 píxeles)** para que se puedan ajustar los controles sin renderizar el video completo. Según el rendimiento del equipo, puede descartar cuadros atrasados; la exportación final mantiene la resolución y los fotogramas originales. **Esta vista previa es sin audio**; el audio puede conservarse en la exportación. No genera archivos proxy permanentes.

Se requiere además `Pillow` (se instala automáticamente desde `requirements.txt`).
