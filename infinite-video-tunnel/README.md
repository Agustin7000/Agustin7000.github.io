# Infinite Video Tunnel v2.0

Generador gratuito de **zoom infinito** para videos de cualquier duración, con dos modos seleccionables. El procesamiento es local: el archivo original nunca se sube a un servidor. Sin IA ni límites artificiales de 30 segundos.

## Dos efectos

- **Zoom Relay (nuevo, predeterminado):** una copia del video nace pequeña, crece, se acerca a la pantalla y desaparece. Otra copia viene *detrás*, no por delante de tu cara. Cada copia se desvanece progresivamente. El video fuente sigue avanzando en tiempo real, sin reiniciarse al principio de cada zoom.
- **Túnel clásico:** preserva el efecto original de copias simultáneas anidadas.

**Controles de Zoom Relay:** velocidad (ciclos/segundo), escala inicial (10% por defecto), escala máxima (500% por defecto), superposición (50% predeterminado para continuidad; probá 25% si querés más separación), dirección. Para túnel clásico siguen disponibles separación y profundidad.

## Windows — recomendado para Filmora y videos transparentes

1. Descargar el código desde este repositorio (`Code → Download ZIP`), descomprimirlo.
2. Instalar [Python 3](https://python.org/downloads/) incluyendo el lanzador `py`, y FFmpeg: `winget install Gyan.FFmpeg`. Abrir una nueva terminal después de instalarlo.
3. Ejecutar **`INICIAR_WINDOWS.bat`** (instala automáticamente `opencv-python`, `numpy` y `Pillow`).
4. Elegir el video. Seleccionar **Zoom Relay** o **Túnel clásico**.
5. Usar **▶ Reproducir** para observar el efecto animado; probar velocidad, escalas y superposición. La previsualización usa FFmpeg, acepta CineForm y muestra transparencia con tablero a cuadros. La vista previa es de hasta 15 FPS y sin audio para mantenerla responsiva.
6. Activar **Conservar transparencia (MOV ProRes 4444)** para reimportar el resultado a Filmora y ponerle cualquier fondo. Exportar el video completo (con audio si está seleccionado).

Importante: una exportación MP4 H.264 normal **no conserva el canal alfa**. ProRes 4444 es un formato de edición, y algunos reproductores no lo mostrarán aunque Filmora sí.

## Herramienta web

Abrir https://agustincabrera.com.ar/infinite-video-tunnel/

Para videos decodificables por el navegador, permite previsualizar y exportar el efecto, grabando el canvas en tiempo real. Firefox suele generar WebM; Chrome puede generar MP4 según los códecs disponibles. **El navegador normalmente no puede leer MP4 CineForm con alfa de Filmora**; en ese caso utilizar la versión de Windows. La grabación con `MediaRecorder` no garantiza alfa.

## Línea de comandos

```bash
pip install -r requirements.txt
python render.py "entrada.mov" --mode relay --alpha --speed 0.5 --start-scale 0.10 --end-scale 5 --overlap 0.5 -o "resultado.mov"
```

Sin transparencia:

```bash
python render.py "entrada.mp4" --mode relay --speed 0.7 --overlap 0.45 -o "resultado.mp4"
```

Túnel clásico original:

```bash
python render.py "entrada.mp4" --mode classic --speed 0.5 --ratio 0.5 --depth 10 -o "clasico.mp4"
```

- `--alpha` para conservar transparencia y exportar MOV ProRes 4444 o WebM VP9.
- `--height 0` para resolución original (`--height 1080` limita el lado corto).
- `--no-audio` para exportar sin audio.
- `--reverse` invierte la dirección del movimiento.
- El video original se decodifica cuadro a cuadro; no hay límite artificial de duración.

## Cómo funciona Zoom Relay

Cada clon tiene una edad relativa distinta, de 0 a 1. Su escala crece exponencialmente entre la inicial y la final. Nacen cada `duración_del_ciclo × (1 - superposición)`. Los clones nuevos se pintan primero, y luego los antiguos se pintan encima: **una copia pequeña nunca tapa la grande**. Las capas aparecen y se desvanecen con transición suave y conservan los valores alfa mediante composición premultiplicada. La imagen original sigue avanzando de manera continua; solo se repite el *movimiento de zoom*, no el tiempo del video.

## Pruebas

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

Incluye comprobaciones de transparencia, orden de capas, continuidad, equivalencia entre vista previa y render, y un render de prueba CineForm → MOV ProRes 4444.

## Licencia

MIT. Ver `LICENSE`.

## v2.1 · Sincronización musical (BPM)

Existe **Control del ritmo → Sincronizar con BPM** en la web y la versión de Windows. Ingresá los BPM de la canción (40–300; ejemplo **135**) y elegí **½ tiempo / 1 tiempo / 2 tiempos / 1 compás (4/4) / 2 compases (4/4)**.

La interfaz muestra el **intervalo entre cada nueva copia** y la **duración de cada recorrido**, ambos en milisegundos. En Zoom Relay los dos valores son distintos por la superposición. La sincronización musical se aplica al **intervalo entre entradas**: `velocidad = (BPM / (60 × tiempos)) × (1 - superposición)`. Por ejemplo, a 135 BPM y 1 tiempo entra una nueva copia cada **444,44 ms**, incluso si modificás la superposición.

El primer pulso se toma del inicio del video (`t = 0`). Si el primer golpe musical aparece más tarde, alineá el inicio en tu editor. La versión Windows exporta usando toda la precisión de la velocidad, sin redondearla a dos decimales. El modo manual sigue disponible.

También puede indicarse desde la consola:

```bash
python render.py "video.mov" --mode relay --alpha --bpm 135 --beats-per-entry 1 --overlap 0.5 -o "video-a-tempo.mov"
```

Para verificar los cálculos: `python -m unittest discover -s tests -p test_tempo.py`.
