"""Verify music-synchronized clone entrances, independent of overlap."""
import unittest
from tempo import tempo_speed, cycle_milliseconds

class TempoTests(unittest.TestCase):
    def test_135_bpm_quarter_note(self):
        for overlap in (0, 0.25, 0.5, 0.7):
            speed = tempo_speed(135, 1, 'relay', overlap)
            spacing, duration = cycle_milliseconds(speed, 'relay', overlap)
            self.assertAlmostEqual(spacing, 60000 / 135, places=8)
            self.assertAlmostEqual(duration, 1000 / speed, places=8)

    def test_divisions(self):
        for beats in (0.5, 1, 2, 4, 8):
            rate = tempo_speed(135, beats, 'relay', 0.5)
            spacing, _ = cycle_milliseconds(rate, 'relay', 0.5)
            self.assertAlmostEqual(spacing, 60000 * beats / 135, places=8)

    def test_classic(self):
        rate = tempo_speed(135, 1, 'classic', 0.5)
        self.assertAlmostEqual(rate, 2.25)
        self.assertAlmostEqual(cycle_milliseconds(rate, 'classic', .5)[0], 60000 / 135)

    def test_manual(self):
        cadence, lifespan = cycle_milliseconds(.5, 'relay', .5)
        self.assertEqual((cadence, lifespan), (1000, 2000))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            tempo_speed(0, 1)
        with self.assertRaises(ValueError):
            tempo_speed(135, 1, 'relay', .9)

if __name__ == '__main__':
    unittest.main()
