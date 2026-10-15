"""Zoom, clipping and resampling regressions without a huge preview allocation."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from canvas_preview import resize_region, viewport_region


class CanvasPreview(unittest.TestCase):
    def test_scrolled_checker_has_no_phase_jump(self):
        from gui_cutter import SpriteManufacturerApp
        app = SpriteManufacturerApp.__new__(SpriteManufacturerApp)
        app.palette = SimpleNamespace(CHECKER_A="#101010", CHECKER_B="#dddddd")
        full = app._tc_checker(100, 100, cs=12)
        tile = app._tc_checker(40, 30, cs=12, offset=(13, 17))
        np.testing.assert_array_equal(np.array(tile), np.array(full.crop((13, 17, 53, 47))))

    def test_detection_and_brush_overlays_follow_the_visible_crop(self):
        from gui_cutter import SpriteManufacturerApp
        app = SpriteManufacturerApp.__new__(SpriteManufacturerApp)
        app.tool = "auto"
        app.src_img = np.zeros((60, 60, 4), np.uint8)
        app._mask_marks = np.zeros((60, 60), np.uint8)
        app._mask_marks[32, 22] = 1
        app._mask_tool = SimpleNamespace(get=lambda: "keep")
        app._background_preview = SimpleNamespace(get=lambda: True)
        app._background_picking = False
        app.palette = SimpleNamespace(ACC="#00ff00")
        app._auto_contours_cache = [np.array([[[20, 30]], [[39, 49]]], np.int32)]
        display = app._cv_overlay(Image.new("RGBA", (10, 10)), 2, (40, 60), (120, 120))
        self.assertEqual(display.getpixel((0, 0)), (0, 255, 0, 255))
        self.assertEqual(display.getpixel((4, 4)), (70, 190, 100, 100))
        self.assertEqual(display.getpixel((7, 7)), (0, 0, 0, 0))

    def test_clipping_covers_partial_full_and_offscreen_images(self):
        self.assertEqual(viewport_region((100, 80), (20, 15), (300, 200)), (0, 0, 100, 80))
        self.assertEqual(viewport_region((1000, 800), (-220, -110), (300, 200)), (220, 110, 520, 310))
        self.assertEqual(viewport_region((100, 80), (-50, 20), (300, 200)), (50, 0, 100, 80))
        self.assertIsNone(viewport_region((100, 80), (-100, 20), (300, 200)))
        self.assertIsNone(viewport_region((100, 80), (300, 20), (300, 200)))

    def test_region_matches_full_resize_at_different_scales(self):
        pixels = np.random.default_rng(2).integers(0, 256, (73, 101, 4), dtype=np.uint8)
        image = Image.fromarray(pixels)
        for resample in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS):
            for size in ((173, 121), (52, 40), (1000, 800)):
                for box in ((0, 0, size[0]//2, size[1]//2),
                            (size[0]//5, size[1]//4, size[0]*3//4, size[1]*4//5)):
                    with self.subTest(filter=resample, size=size, box=box):
                        actual = resize_region(image, size, box, resample)
                        expected = image.resize(size, resample).crop(box)
                        if resample == Image.Resampling.NEAREST:
                            np.testing.assert_array_equal(np.array(actual), np.array(expected))
                        else:
                            # Small coefficient roundoff on low-alpha pixels
                            # must not introduce a visible seam in the viewport.
                            bg = Image.new("RGBA", actual.size, (23, 28, 36, 255))
                            a = np.array(Image.alpha_composite(bg, actual)).astype(float)
                            b = np.array(Image.alpha_composite(bg, expected)).astype(float)
                            self.assertLess(np.abs(a-b).mean(), .02)

    def test_extreme_zoom_only_resizes_visible_pixels(self):
        image = Image.new("RGBA", (960, 960), (40, 80, 120, 128))
        original_resize = Image.Image.resize
        calls = []
        def bounded_resize(part, size, *args, **kwargs):
            calls.append((part.size, size))
            self.assertLessEqual(size[0], 800)
            self.assertLessEqual(size[1], 600)
            return original_resize(part, size, *args, **kwargs)
        with patch.object(Image.Image, "resize", bounded_resize):
            tile = resize_region(image, (30000, 30000), (14500, 14700, 15300, 15300))
        self.assertEqual(tile.size, (800, 600))
        self.assertTrue(calls)
        self.assertLess(calls[0][0][0], 40)
        self.assertLess(calls[0][0][1], 40)


if __name__ == "__main__":
    unittest.main()
