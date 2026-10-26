import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preview_stream import PreviewDecoder, frames_from_pipe, make_checker, render_preview_rgb


class StreamTests(unittest.TestCase):
    def test_checker_has_two_colors(self):
        bg = make_checker(64, 48, 8)
        self.assertEqual(bg.shape, (48, 64, 3))
        self.assertEqual(len(np.unique(bg)), 2)

    def test_transparent_frame_shows_checker(self):
        bg = make_checker(80, 80)
        frame = np.zeros((80, 80, 4), np.uint8)
        preview = render_preview_rgb(frame, .5, .5, .5, 8, False, bg)
        np.testing.assert_array_equal(preview, bg.astype(np.uint8))

    def test_shape_and_overlay(self):
        bg = make_checker(80, 80)
        frame = np.zeros((80, 80, 4), np.uint8)
        frame[25:55, 25:55, :] = [249, 33, 41, 255]
        preview = render_preview_rgb(frame, .5, .5, .5, 8, False, bg)
        self.assertEqual(preview.shape, (80, 80, 3))
        self.assertEqual(preview[0, 0, 0], 210)
        self.assertGreater(preview[40, 40, 0], 190)

    def test_cineform_continuous_decoder(self):
        fixture = Path(__file__).parent / 'input-cineform.mov'
        if not fixture.is_file():
            self.skipTest('Requiere video de prueba local, no distribuido con el repositorio')
        with PreviewDecoder(fixture, 0, 96, 96, 15) as decoder:
            frames = list(decoder)
        self.assertGreaterEqual(len(frames), 28)
        self.assertEqual(frames[0].shape, (96, 96, 4))
        self.assertTrue(np.any(frames[0][..., 3] < 255), 'Debe preservar transparencia')


if __name__ == '__main__':
    unittest.main()
