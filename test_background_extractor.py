"""Background removal regressions, including exported sprite pixel values."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

import cv2
import numpy as np

from background_extractor import bleed_transparent_colors, extract_foreground, checkerboard_model, refine_foreground, smooth_cutout_edges, sprite_regions
from gui_cutter import SpriteManufacturerApp


BACKGROUND = (43, 151, 67)  # RGB, deliberately neither black nor white


def sheet():
    image = np.full((80, 100, 3), BACKGROUND[::-1], dtype=np.uint8)
    image[20:60, 20:60] = (190, 40, 25)
    image[20:30, 20:30] = BACKGROUND[::-1]  # exterior notch
    image[35:45, 35:45] = BACKGROUND[::-1]  # enclosed same-colour detail
    return image


class BackgroundExtraction(unittest.TestCase):
    @staticmethod
    def checker(cw=8, ch=8, ox=0, oy=0):
        yy, xx = np.indices((100, 130))
        pattern = ((xx + ox) // cw + (yy + oy) // ch) % 2
        image = np.array([(190, 195, 200), (235, 240, 245)], np.uint8)[pattern]
        image[30:70, 40:85] = (50, 20, 200)
        return image

    def test_checkerboard_fits_rectangular_cells_and_offsets(self):
        for settings in ((8, 8, 0, 0), (7, 9, 3, 5), (4, 4, 1, 2)):
            with self.subTest(settings=settings):
                image = self.checker(*settings)
                self.assertIsNotNone(checkerboard_model(image))
                result = extract_foreground(image)
                self.assertEqual(np.count_nonzero(result[:, :, 3]), 40 * 45)

    def test_checkerboard_does_not_key_matching_colors_at_wrong_positions(self):
        image = self.checker()
        # The foreground's top-left edge contains the other checker colour.
        image[30:35, 40:45] = (235, 240, 245)  # pattern expects the dark colour here
        result = extract_foreground(image, mode="checker")
        self.assertEqual(result[30, 40, 3], 255)
        self.assertEqual(result[0, 0, 3], 0)

    def test_irregular_two_color_background_is_not_a_checkerboard(self):
        image = self.checker()
        image[:10] = (190, 195, 200)
        image[-10:] = (235, 240, 245)
        self.assertIsNone(checkerboard_model(image))
        np.testing.assert_array_equal(extract_foreground(image, mode="checker")[:, :, :3], image)
        self.assertTrue(np.all(extract_foreground(image, mode="checker")[:, :, 3] == 255))

    def test_brushes_restore_same_color_detail_and_remove_enclosed_background(self):
        image = sheet()
        marks = np.zeros(image.shape[:2], np.uint8)
        marks[0, 10] = 1
        marks[40, 40] = 2
        result = extract_foreground(image, background_rgb=BACKGROUND, marks=marks)
        self.assertEqual(result[0, 10, 3], 255)
        self.assertEqual(result[0, 11, 3], 0)
        self.assertEqual(result[40, 40, 3], 0)

    def test_alpha_only_mode_leaves_background_for_manual_editing(self):
        image = sheet()
        result = extract_foreground(image, mode="alpha")
        self.assertTrue(np.all(result[:, :, 3] == 255))

    def test_refinement_honors_keep_and_remove_marks(self):
        image = sheet()
        marks = np.zeros(image.shape[:2], np.uint8)
        marks[35:45, 35:45] = 1
        marks[50:54, 50:54] = 2
        rgba = extract_foreground(image, background_rgb=BACKGROUND, marks=marks)
        result = refine_foreground(image, rgba, marks, iterations=1)
        self.assertEqual(result[40, 40, 3], 255)
        self.assertEqual(result[51, 51, 3], 0)
        self.assertEqual(result[0, 0, 3], 0)
        np.testing.assert_array_equal(result[:, :, :3], image)

    def test_refinement_requires_foreground_and_background_seeds(self):
        with self.assertRaises(ValueError):
            refine_foreground(sheet(), cv2.cvtColor(sheet(), cv2.COLOR_BGR2BGRA))

    def test_arbitrary_background_preserves_enclosed_matching_detail(self):
        result = extract_foreground(sheet(), background_rgb=BACKGROUND)
        self.assertEqual(result[0, 0, 3], 0)
        self.assertEqual(result[25, 25, 3], 0)
        self.assertEqual(result[40, 40, 3], 255)
        self.assertEqual(tuple(result[40, 40, :3]), BACKGROUND[::-1])

    def test_auto_uses_edge_vote_even_if_corner_contains_an_object(self):
        image = sheet()
        image[:5, :5] = (0, 0, 0)
        result = extract_foreground(image)
        self.assertEqual(result[0, 0, 3], 255)
        self.assertEqual(result[0, 20, 3], 0)
        self.assertEqual(result[40, 40, 3], 255)

    def test_black_and_white_backgrounds_preserve_matching_interior(self):
        for color in (0, 255):
            with self.subTest(color=color):
                image = np.full((40, 40, 3), color, dtype=np.uint8)
                image[10:30, 10:30] = 255 - color
                image[17:23, 17:23] = color
                result = extract_foreground(image)
                self.assertEqual(result[0, 0, 3], 0)
                self.assertEqual(result[20, 20, 3], 255)

    def test_no_diagonal_leak_through_pixel_art_outline(self):
        image = np.full((5, 5, 3), 255, dtype=np.uint8)
        image[1, 2] = image[2, 1] = image[2, 3] = image[3, 2] = 0
        result = extract_foreground(image, 0, (255, 255, 255))
        self.assertEqual(result[2, 2, 3], 255)
        self.assertEqual(result[0, 0, 3], 0)

    def test_every_edge_is_seeded_when_object_splits_background(self):
        image = np.full((40, 40, 3), BACKGROUND[::-1], dtype=np.uint8)
        image[:, 18:22] = (0, 0, 0)
        result = extract_foreground(image, background_rgb=BACKGROUND)
        self.assertEqual(result[20, 0, 3], 0)
        self.assertEqual(result[20, -1, 3], 0)
        self.assertEqual(result[0, 20, 3], 255)

    def test_existing_alpha_is_preserved_exactly(self):
        image = cv2.cvtColor(sheet(), cv2.COLOR_BGR2BGRA)
        image[0, 0, 3] = 0
        image[21, 31, 3] = 87
        np.testing.assert_array_equal(extract_foreground(image), image)

    def test_explicit_color_can_remove_background_with_existing_alpha(self):
        image = cv2.cvtColor(sheet(), cv2.COLOR_BGR2BGRA)
        image[21, 31, 3] = 87
        result = extract_foreground(image, background_rgb=BACKGROUND)
        self.assertEqual(result[0, 0, 3], 0)
        self.assertEqual(result[21, 31, 3], 87)

    def test_tolerance_handles_jpeg_background_noise(self):
        ok, encoded = cv2.imencode(".jpg", sheet(), [cv2.IMWRITE_JPEG_QUALITY, 90])
        self.assertTrue(ok)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        result = extract_foreground(image, 20, BACKGROUND)
        self.assertTrue(np.all(result[:10, :, 3] == 0))
        self.assertEqual(result[50, 40, 3], 255)
        self.assertEqual(result[40, 40, 3], 255)

    def test_tolerance_is_not_unbounded_color_drift(self):
        image = np.full((10, 100, 3), 0, dtype=np.uint8)
        image[:] = np.arange(100, dtype=np.uint8)[None, :, None]
        result = extract_foreground(image, 10, (0, 0, 0))
        self.assertEqual(result[5, 10, 3], 0)
        self.assertEqual(result[5, 11, 3], 255)

    def test_grayscale_and_input_is_not_modified(self):
        image = np.full((40, 40), 255, dtype=np.uint8)
        image[10:30, 10:30] = 0
        original = image.copy()
        result = extract_foreground(image)
        self.assertEqual(result.shape, (40, 40, 4))
        self.assertEqual(result[0, 0, 3], 0)
        np.testing.assert_array_equal(image, original)

    def test_uniform_sprite_is_kept_in_auto_and_removed_when_explicit(self):
        image = np.full((30, 30, 3), BACKGROUND[::-1], dtype=np.uint8)
        self.assertTrue(np.all(extract_foreground(image)[:, :, 3] == 255))
        self.assertTrue(np.all(extract_foreground(image, background_rgb=BACKGROUND)[:, :, 3] == 0))


class SmoothEdges(unittest.TestCase):
    def test_staircase_gets_partial_alpha_without_growing_into_background(self):
        image = np.full((64, 64, 3), 255, np.uint8)
        cv2.fillPoly(image, [np.array([(12, 40), (45, 12), (50, 50)])], (60, 90, 120))
        raw = extract_foreground(image)
        result = smooth_cutout_edges(image, raw)
        self.assertTrue(np.any((result[:, :, 3] > 0) & (result[:, :, 3] < 255)))
        self.assertTrue(np.all(result[raw[:, :, 3] == 0, 3] == 0))
        np.testing.assert_array_equal(result[40, 40], raw[40, 40])
        np.testing.assert_array_equal(raw[:, :, :3], image)

    def test_unmixing_reproduces_source_on_original_background(self):
        # These light edge colours can be unpremultiplied without clipping.
        # Verify the compositing equation for arbitrary, black and white B.
        for rgb, foreground in (((255, 255, 255), (220, 225, 230)),
                                ((0, 0, 0), (20, 25, 30)),
                                (BACKGROUND, (83, 160, 95))):
            with self.subTest(background=rgb):
                image = np.full((40, 40, 3), rgb[::-1], np.uint8)
                image[10:30, 10:30] = foreground
                raw = extract_foreground(image, 0, rgb)
                result = smooth_cutout_edges(image, raw, rgb)
                a = result[:, :, 3:4].astype(np.float32) / 255
                composite = result[:, :, :3] * a + np.array(rgb[::-1]) * (1-a)
                # Ignore corners, where coverage is too low to explain C
                # without clipping F to a displayable colour.
                np.testing.assert_allclose(composite[10, 15:25], image[10, 15:25], atol=1)
                # On a different background feather-only retains more B.
                naive = image[10, 15:25].astype(float) * a[10, 15:25]
                corrected = result[10, 15:25, :3] * a[10, 15:25]
                if rgb == (255, 255, 255):
                    self.assertLess(corrected.mean(), naive.mean() - 4)

    def test_checker_edges_use_the_background_at_each_cell(self):
        image = BackgroundExtraction.checker()
        # Distinct from both checker colours; unmixing stays in display range.
        image[30:70, 40:85] = (215, 218, 221)
        raw = extract_foreground(image, mode="checker")
        result = smooth_cutout_edges(image, raw, mode="checker")
        colors, pattern = checkerboard_model(image)
        a = result[:, :, 3:4].astype(np.float32) / 255
        composite = result[:, :, :3] * a + colors[pattern] * (1-a)
        np.testing.assert_allclose(composite[30, 48:52], image[30, 48:52], atol=1)

    def test_native_alpha_is_preserved_even_with_explicit_background(self):
        image = cv2.cvtColor(sheet(), cv2.COLOR_BGR2BGRA)
        image[25, 35, 3] = 87
        raw = extract_foreground(image, background_rgb=BACKGROUND)
        np.testing.assert_array_equal(smooth_cutout_edges(image, raw, BACKGROUND, choke=2), raw)

    def test_shrink_is_optional_and_brushes_protect_full_pixel_values(self):
        image = sheet()
        raw = extract_foreground(image, background_rgb=BACKGROUND)
        marks = np.zeros(image.shape[:2], np.uint8)
        marks[20, 35] = 1
        marks[21, 35] = 2
        result = smooth_cutout_edges(image, raw, BACKGROUND, marks=marks, choke=2)
        np.testing.assert_array_equal(result[20, 35], raw[20, 35])
        self.assertEqual(result[21, 35, 3], 0)
        self.assertLess(result[20, 40, 3], smooth_cutout_edges(image, raw, BACKGROUND)[20, 40, 3])
        np.testing.assert_array_equal(result[40, 40], raw[40, 40])

    def test_smoothing_keeps_thin_lines_and_cropped_boundaries(self):
        image = np.full((40, 40), 255, np.uint8)
        image[:, 10:30] = 0
        image[20, 30:38] = 0
        raw = extract_foreground(image)
        result = smooth_cutout_edges(image, raw)
        self.assertEqual(result[0, 20, 3], 255)
        self.assertTrue(np.all(result[20, 30:38, 3] > 0))


class ExtractionWorkflows(unittest.TestCase):
    def setUp(self):
        self.app = SpriteManufacturerApp.__new__(SpriteManufacturerApp)
        self.app.src_img = sheet()
        self.app._background_rgb = BACKGROUND
        self.app._cv_draw = Mock()
        self.app._auto_contours_cache = []
        self.app._atlas_raws = []
        self.app.excluded = set()

    def test_preview_tray_export_and_atlas_use_same_alpha(self):
        self.app._auto_run()
        self.assertEqual(len(self.app._auto_contours_cache), 1)
        self.assertEqual(self.app._auto_rgba_cache[40, 40, 3], 255)
        self.app._tray_add = Mock()
        with tempfile.TemporaryDirectory() as directory, patch("gui_cutter.messagebox"):
            self.app.outdir = directory
            self.app._auto_add_to_tray()
            tray = self.app._tray_add.call_args.args[0][0]
            self.app._auto_save()
            exported = cv2.imread(str(Path(directory) / "sprite_0000.png"), cv2.IMREAD_UNCHANGED)
            atlas = self.app._atlas_detect_raws()[0]
        expected = np.array(tray)
        np.testing.assert_array_equal(np.array(atlas), expected)
        np.testing.assert_array_equal(cv2.cvtColor(exported, cv2.COLOR_BGRA2RGBA), expected)
        self.assertEqual(expected[5, 5, 3], 0)
        self.assertEqual(expected[20, 20, 3], 255)

    def test_opaque_rgba_uses_background_detection(self):
        image = cv2.cvtColor(sheet(), cv2.COLOR_BGR2BGRA)
        contours = self.app._auto_contours(image, 245, 12)
        self.assertEqual([cv2.boundingRect(c) for c in contours], [(20, 20, 40, 40)])

    def test_smooth_edges_match_preview_tray_export_and_atlas(self):
        self.app._edge_smooth = SimpleNamespace(get=lambda: True)
        self.app._edge_choke = SimpleNamespace(get=lambda: 1)
        self.app._pixel_art = SimpleNamespace(get=lambda: False)
        self.test_preview_tray_export_and_atlas_use_same_alpha()
        alpha = self.app._auto_rgba_cache[:, :, 3]
        self.assertTrue(np.any((alpha > 0) & (alpha < 255)))

    def test_pixel_art_bypasses_smoothing_and_shrink(self):
        self.app._edge_smooth = SimpleNamespace(get=lambda: True)
        self.app._edge_choke = SimpleNamespace(get=lambda: 3)
        self.app._pixel_art = SimpleNamespace(get=lambda: True)
        expected = extract_foreground(self.app.src_img, background_rgb=BACKGROUND)
        np.testing.assert_array_equal(self.app._extract_rgba(self.app.src_img, 10), expected)

    def test_refined_mask_is_processed_once_without_accumulating_shrink(self):
        self.app._edge_smooth = SimpleNamespace(get=lambda: True)
        self.app._edge_choke = SimpleNamespace(get=lambda: 1)
        self.app._pixel_art = SimpleNamespace(get=lambda: False)
        raw = extract_foreground(self.app.src_img, background_rgb=BACKGROUND)
        self.app._refined_rgba = raw.copy()
        self.app._refined_key = self.app._background_signature(self.app.src_img, 10)
        a = self.app._extract_rgba(self.app.src_img, 10)
        np.testing.assert_array_equal(self.app._extract_rgba(self.app.src_img, 10), a)
        np.testing.assert_array_equal(self.app._extract_rgba(self.app.src_img, 10, process_edges=False), raw)
        np.testing.assert_array_equal(self.app._refined_rgba, raw)

    def test_nested_objects_are_isolated_despite_overlapping_bounds(self):
        alpha = np.zeros((50, 50), np.uint8)
        cv2.rectangle(alpha, (5, 5), (40, 40), 255, 2)
        alpha[20:25, 20:25] = 128
        rgba = np.full((50, 50, 4), 255, np.uint8)
        rgba[:, :, 3] = alpha
        regions = sprite_regions(alpha)
        self.assertEqual(len(regions), 2)
        first, second = [np.array(self.app._sprite_pil(rgba, region)) for region in regions]
        self.assertEqual(first[20, 20, 3], 0)
        self.assertTrue(np.all(second[:, :, 3] == 128))

    def test_separation_keeps_every_pixel_including_thin_appendages(self):
        alpha = np.zeros((60, 100), np.uint8)
        alpha[10:40, 5:35] = 255
        alpha[10:40, 45:75] = 255
        alpha[24:26, 35:45] = 255  # thin connecting bridge
        alpha[40:52, 10] = 20  # thin, faint tail
        regions = sprite_regions(alpha, min_size=3, separate=2)
        self.assertEqual(len(regions), 2)
        reconstructed = np.zeros_like(alpha)
        for x, y, w, h, mask in regions:
            reconstructed[y:y+h, x:x+w] += mask.astype(np.uint8)
        np.testing.assert_array_equal(reconstructed, alpha > 0)

    def test_grouping_retains_small_detached_parts(self):
        alpha = np.zeros((50, 70), np.uint8)
        alpha[10:30, 10:30] = 255
        alpha[15:17, 34:36] = 255
        alpha[10:30, 50:65] = 255
        regions = sprite_regions(alpha, min_size=3, group_gap=3)
        self.assertEqual(len(regions), 2)
        self.assertEqual(regions[0][:4], (10, 10, 26, 20))
        self.assertEqual(sum(int(r[4].sum()) for r in regions), np.count_nonzero(alpha))

    def test_single_object_keeps_detached_faint_particles(self):
        alpha = np.zeros((50, 70), np.uint8)
        alpha[10:30, 10:30] = 255
        alpha[40, 60] = 1
        regions = sprite_regions(alpha, min_size=12, single=True)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0][:4], (10, 10, 51, 31))

    def test_padding_does_not_multiply_partial_alpha(self):
        rgba = cv2.cvtColor(sheet(), cv2.COLOR_BGR2BGRA)
        rgba[:, :, 3] = 87
        region = sprite_regions(rgba[:, :, 3])[0]
        self.app._export_padding = SimpleNamespace(get=lambda: 2)
        sprite = np.array(self.app._sprite_pil(rgba, region))
        self.assertEqual(sprite.shape, (84, 104, 4))
        self.assertEqual(sprite[2, 2, 3], 87)
        self.assertEqual(sprite[0, 0, 3], 0)

    def test_edge_color_bleed_preserves_alpha_and_visible_colors(self):
        image = np.full((12, 12, 4), (255, 0, 255, 0), np.uint8)
        image[4:8, 4:8] = (20, 180, 60, 87)
        original = image.copy()
        result = bleed_transparent_colors(image, radius=2)
        np.testing.assert_array_equal(result[:, :, 3], original[:, :, 3])
        np.testing.assert_array_equal(result[4:8, 4:8], original[4:8, 4:8])
        self.assertEqual(tuple(result[4, 3]), (20, 180, 60, 0))
        self.assertEqual(tuple(result[0, 0]), (255, 0, 255, 0))
        np.testing.assert_array_equal(image, original)

    def test_pixel_art_scaling_introduces_no_new_colors(self):
        from PIL import Image
        self.app._pixel_art = SimpleNamespace(get=lambda: True)
        self.app._auto_scale_mode = SimpleNamespace(get=lambda: "both")
        self.app._auto_scale_w = self.app._auto_scale_h = SimpleNamespace(get=lambda: 8)
        original = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
        original.putpixel((1, 1), (0, 255, 0, 255))
        result = self.app._auto_scale_apply(original)
        self.assertEqual(set(map(tuple, np.array(result).reshape(-1, 4))),
                         set(map(tuple, np.array(original).reshape(-1, 4))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
