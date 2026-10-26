"""Regression tests for Zoom Relay's order, timing, alpha and UI preview parity."""
import unittest

import numpy as np

from relay import relay_layers, render_relay_frame
from preview_stream import render_preview_rgb, make_checker


class ZoomRelayTests(unittest.TestCase):
    def setUp(self):
        self.src = np.zeros((96, 128, 4), np.uint8)
        yy, xx = np.ogrid[:96, :128]
        mask = ((xx - 64) / 18) ** 2 + ((yy - 48) / 33) ** 2 < 1
        self.src[mask] = [230, 40, 90, 255]

    def test_empty_source_remains_transparent(self):
        empty = np.zeros_like(self.src)
        for t in (0, 0.1, 1, 20):
            np.testing.assert_array_equal(render_relay_frame(empty, t), empty)

    def test_alpha_present_and_frame_shape(self):
        for t in (0, 0.2, 0.8, 1.4):
            out = render_relay_frame(self.src, t)
            self.assertEqual(out.shape, self.src.shape)
            self.assertTrue(np.any(out[..., 3] > 0))
            self.assertTrue(np.any(out[..., 3] == 0))

    def test_continuity_at_new_clone_birth(self):
        # The new clone begins at zero opacity; adding it cannot cause a pop.
        for t in (0, 1., 2., 7.):
            left = render_relay_frame(self.src, t - 0.000001)
            right = render_relay_frame(self.src, t + 0.000001)
            self.assertLess(np.abs(left.astype(int) - right.astype(int)).mean(), 1.3)

    def test_older_large_instance_draws_over_newborn(self):
        # Newborn is behind the older copy: newest is first (backmost).
        layers = relay_layers(1.01, speed=.5, overlap=.5)
        self.assertEqual(len(layers), 2)
        self.assertLess(layers[0][0], layers[1][0])
        out = render_relay_frame(self.src, 1.01, speed=.5, overlap=.5)
        self.assertGreater(out[48, 64, 3], 0)

    def test_preview_matches_export_compositing(self):
        checker = make_checker(128, 96)
        t = .88
        out = render_relay_frame(self.src, t, .5, .1, 5., .5)
        alpha = out[..., 3:4].astype(np.float32) / 255
        expected = np.clip(out[..., :3] * alpha + checker * (1 - alpha), 0, 255).astype(np.uint8)
        actual = render_preview_rgb(self.src, t, .5, .5, 10, False, checker,
                                    'relay', .1, 5., .5)
        np.testing.assert_array_equal(actual, expected)

    def test_invalid_controls(self):
        with self.assertRaises(ValueError):
            render_relay_frame(self.src, 1, overlap=.9)
        with self.assertRaises(ValueError):
            render_relay_frame(self.src, 1, start_scale=0)


if __name__ == '__main__':
    unittest.main()
