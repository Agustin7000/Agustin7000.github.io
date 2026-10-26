"""Music-synchronized entrance timing shared by Windows preview and export."""
import math

def tempo_speed(bpm: float, beats_per_entrance: float,
                mode: str = 'relay', overlap: float = 0.5) -> float:
    """Cycles/sec so new relay copies enter on the beat, independent of overlap."""
    if not math.isfinite(bpm) or not 40 <= bpm <= 300:
        raise ValueError('BPM debe estar entre 40 y 300')
    if beats_per_entrance not in (0.5, 1.0, 2.0, 4.0, 8.0):
        raise ValueError('División musical inválida')
    if mode not in ('relay', 'classic') or not 0 <= overlap <= 0.7:
        raise ValueError('Modo o superposición inválidos')
    return (bpm / (60 * beats_per_entrance)) * (1 - overlap if mode == 'relay' else 1)

def cycle_milliseconds(speed: float, mode: str = 'relay',
                       overlap: float = 0.5) -> tuple[float, float]:
    """(Milliseconds between new copies, milliseconds per complete zoom)."""
    if not math.isfinite(speed) or speed <= 0:
        raise ValueError('Velocidad inválida')
    if mode not in ('classic', 'relay') or not 0 <= overlap <= 0.7:
        raise ValueError('Modo o superposición inválidos')
    traversal = 1000 / speed
    return traversal * (1 - overlap if mode == 'relay' else 1), traversal
