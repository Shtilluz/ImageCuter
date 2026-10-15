"""Beginner workflow, live themes, and state-preserving UI regressions."""

import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageTk
from tkinter import ttk
from tkinterdnd2 import TkinterDnD

from gui_cutter import SpriteManufacturerApp
from test_background_extractor import sheet
from ui_themes import THEMES


def contrast(first, second):
    def luminance(color):
        channels = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
    a, b = sorted((luminance(first), luminance(second)))
    return (b + .05) / (a + .05)


class PaletteReadability(unittest.TestCase):
    def test_body_secondary_and_primary_button_text_have_readable_contrast(self):
        for name, colors in THEMES.items():
            for foreground, background in (("FG", "BG"), ("FG2", "BG"), ("WHITE", "ACC"), ("FG", "INPUT"), ("ACC", "GRN")):
                with self.subTest(theme=name, foreground=foreground, background=background):
                    self.assertGreaterEqual(contrast(colors[foreground], colors[background]), 4.5)


class WorkspaceExperience(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config_path = Path(self.directory.name) / "config.json"
        self.config_patch = patch("gui_cutter.CONFIG_FILE", str(self.config_path))
        self.config_patch.start()
        self.root = TkinterDnD.Tk()
        self.root.withdraw()
        self.app = SpriteManufacturerApp(self.root)
        self.message_patch = patch("gui_cutter.messagebox")
        self.messages = self.message_patch.start()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        self.message_patch.stop()
        self.config_patch.stop()
        self.directory.cleanup()

    def source(self):
        self.app.src_img = sheet()
        self.app._auto_run()

    def test_start_screen_explains_next_action_and_disables_export(self):
        self.assertEqual(self.app._auto_save_btn.cget("state"), "disabled")
        self.assertEqual(self.app._export_current_btn.cget("state"), "disabled")
        self.assertIn("Открыть картинку", self.app._next_step_var.get())
        self.assertTrue(all(button.cget("state") == "disabled" for button in self.app._background_pipettes))
        self.source()
        self.assertEqual(self.app._auto_save_btn.cget("state"), "normal")
        self.assertEqual(self.app._export_current_btn.cget("state"), "normal")
        self.assertTrue(all(button.cget("state") == "normal" for button in self.app._background_pipettes))

    def test_soft_sprite_previews_composite_alpha_once(self):
        sprite = Image.new("RGBA", (12, 12), (70, 150, 210, 128))
        self.app.sprites = [sprite]
        self.app._tray_refresh()
        thumbnail = ImageTk.getimage(self.app._tray_photos[0])
        self.assertEqual(thumbnail.getpixel((32, 32))[3], 255)
        background = Image.new("RGBA", (1, 1), self.app.palette.CHECKER_A)
        expected = Image.alpha_composite(background, Image.new("RGBA", (1, 1), sprite.getpixel((0, 0))))
        self.assertEqual(thumbnail.getpixel((32, 32)), expected.getpixel((0, 0)))
        self.app._tray_to_atlas()
        sheet = np.array(self.app._atlas_sheet)
        y, x = np.argwhere(sheet[:, :, 3] == 128)[0]
        checker = self.app._tc_checker(self.app._atlas_sheet.width, self.app._atlas_sheet.height, cs=12)
        expected = Image.alpha_composite(checker.convert("RGBA"), self.app._atlas_sheet)
        self.assertEqual(self.app._atlas_vis.getpixel((int(x), int(y))), expected.getpixel((int(x), int(y))))
        self.assertEqual(ImageTk.getimage(self.app._tray_photos[0]).getpixel((32, 32))[3], 255)

    def test_new_source_returns_to_viewing_instead_of_leaving_brush_active(self):
        source = Path(self.directory.name) / "new.png"
        Image.new("RGBA", (40, 40), "red").save(source)
        self.source()
        self.app._mask_tool.set("remove")
        self.app._background_preview.set(False)
        self.app._load_src(str(source))
        self.assertEqual(self.app._mask_tool.get(), "pan")
        self.assertTrue(self.app._background_preview.get())

    def test_all_themes_preserve_source_manual_mask_and_sprite_selection(self):
        self.source()
        self.app._mask_marks = np.zeros(self.app.src_img.shape[:2], np.uint8)
        self.app._mask_marks[40, 40] = 1
        self.app._mask_revision += 1
        self.app._auto_run()
        self.app.sprites = [Image.new("RGBA", (12, 12), "red"), Image.new("RGBA", (12, 12), "blue")]
        self.app.excluded = {1}
        self.app._cv_zoom = 1.5
        self.app._cv_view_x, self.app._cv_view_y = 7, 12
        source, marks, output = self.app.src_img.copy(), self.app._mask_marks.copy(), self.app._auto_rgba_cache.copy()
        for theme in ("dark", "contrast", "light", "dark"):
            self.app._set_theme(theme, persist=False)
            self.root.update_idletasks()
            self.assertEqual(self.root.cget("bg"), THEMES[theme]["BG"])
            self.assertEqual(self.app._auto_save_btn.foreground, THEMES[theme]["WHITE"])
            self.assertEqual(self.app._auto_thresh.palette.INPUT, THEMES[theme]["INPUT"])
            self.assertEqual(ttk.Style(self.root).lookup("TCombobox", "fieldbackground", ("readonly",)), THEMES[theme]["INPUT"])
            np.testing.assert_array_equal(self.app.src_img, source)
            np.testing.assert_array_equal(self.app._mask_marks, marks)
            np.testing.assert_array_equal(self.app._auto_rgba_cache, output)
            self.assertEqual(self.app.excluded, {1})
            self.assertEqual((self.app._cv_zoom, self.app._cv_view_x, self.app._cv_view_y), (1.5, 7, 12))

    def test_theme_persists_without_losing_other_configuration(self):
        self.config_path.write_text(json.dumps({"recent_dirs": ["/tmp/sprites"], "custom": {"keep": True}}))
        self.app.recent_dirs = self.app._load_config()
        self.app._set_theme("dark")
        saved = json.loads(self.config_path.read_text())
        self.assertEqual(saved["theme"], "dark")
        self.assertEqual(saved["recent_dirs"], ["/tmp/sprites"])
        self.assertEqual(saved["custom"], {"keep": True})
        self.root.destroy()
        self.root = TkinterDnD.Tk()
        self.root.withdraw()
        self.app = SpriteManufacturerApp(self.root)
        self.assertEqual(self.app._theme_name, "dark")

    def test_presets_do_not_erase_brush_edits(self):
        self.source()
        self.app._mask_marks = np.zeros(self.app.src_img.shape[:2], np.uint8)
        self.app._mask_marks[40, 40] = 2
        marks = self.app._mask_marks.copy()
        self.app._task_preset.set("Один персонаж или предмет")
        self.app._apply_preset()
        self.assertEqual(self.app._auto_object_mode.get(), "single")
        np.testing.assert_array_equal(self.app._mask_marks, marks)
        self.app._task_preset.set("Пиксель-арт: лист спрайтов")
        self.app._apply_preset()
        self.assertTrue(self.app._pixel_art.get())
        self.assertEqual(self.app._auto_min.get(), 1)
        self.app._auto_group_gap.set(4)
        self.app._auto_run()
        self.assertEqual(self.app._task_preset.get(), "Свои настройки")

    def test_ai_sheet_preset_filters_small_noise_and_pixel_art_can_keep_it(self):
        self.app.src_img = sheet()
        self.app.src_img[3:6, 3:6] = 0
        self.app._auto_run()
        self.assertEqual(len(self.app._auto_regions_cache), 1)
        self.app._task_preset.set("Пиксель-арт: лист спрайтов")
        self.app._apply_preset()
        self.assertEqual(len(self.app._auto_regions_cache), 2)

    def test_save_stays_visible_at_minimum_window_size_and_after_scrolling(self):
        self.source()
        self.root.geometry("1000x700")
        self.root.deiconify()
        self.root.update()
        self.assertGreaterEqual(self.app._props_outer.winfo_width(), 330)
        self.assertGreaterEqual(self.app._auto_save_btn.winfo_width(), 280)
        last_tool = self.app._tool_btns["resize"]
        self.assertLessEqual(last_tool.winfo_rooty() + last_tool.winfo_height(),
                             self.app._toolbar.winfo_rooty() + self.app._toolbar.winfo_height())
        self.app._show_advanced()
        self.root.update()
        self.assertGreater(self.app._props_scroll.yview()[0], 0)
        body, state, _ = self.app._section_toggles["Размер и края PNG"]
        self.assertTrue(state[0])
        self.assertGreaterEqual(body.winfo_rooty(), self.app._props_scroll.winfo_rooty())
        self.assertLess(body.winfo_rooty(), self.app._auto_save_btn.winfo_rooty())
        self.app._focus_brush("remove")
        self.app._props_scroll.yview_moveto(1)
        self.root.update()
        self.assertTrue(self.app._auto_save_btn.winfo_ismapped())
        y = self.app._auto_save_btn.winfo_rooty()
        self.assertGreaterEqual(y, self.root.winfo_rooty())
        self.assertLess(y + self.app._auto_save_btn.winfo_height(), self.root.winfo_rooty() + self.root.winfo_height())
        self.assertEqual(self.app._mask_tool.get(), "remove")

    def test_comparison_and_preview_background_do_not_change_extracted_pixels(self):
        self.source()
        expected = self.app._auto_rgba_cache.copy()
        for preview in (False, True):
            self.app._background_preview.set(preview)
            for backdrop in ("Клетка", "Светлый", "Тёмный"):
                self.app._preview_bg.set(backdrop)
                self.app._cv_draw()
                np.testing.assert_array_equal(self.app._auto_rgba_cache, expected)

    def test_maximum_zoom_keeps_all_preview_buffers_inside_canvas(self):
        self.source()
        self.root.geometry("1000x700")
        self.root.deiconify()
        self.root.update()
        resize = Image.Image.resize
        sizes = []
        def bounded_resize(image, size, *args, **kwargs):
            self.assertLessEqual(size[0], self.app._canvas.winfo_width())
            self.assertLessEqual(size[1], self.app._canvas.winfo_height())
            sizes.append(size)
            return resize(image, size, *args, **kwargs)
        for tool in ("auto", "shape", "grid", "atlas", "tiletest"):
            self.app._tool_set(tool)
            self.root.update()
            self.app._cv_zoom = self.app._tc_zoom = 30
            with self.subTest(tool=tool), patch.object(Image.Image, "resize", bounded_resize):
                self.app._cv_draw()
        self.assertTrue(sizes)

    def test_close_button_cancels_jobs_and_returns_from_mainloop(self):
        self.source()
        calls = []
        self.root.after(100, lambda: calls.append("stale batch step"))
        self.app._refine_running = self.app._resize_running = True
        close_command = self.root.protocol("WM_DELETE_WINDOW")
        self.root.after(0, lambda: self.root.tk.call(close_command))
        self.root.mainloop()
        self.assertTrue(self.app._closing)
        self.assertFalse(self.app._refine_running or self.app._resize_running)
        self.assertFalse(self.root.tk.call("after", "info"))
        self.assertEqual(calls, [])
        self.app._close()  # Repeated shutdown must be harmless.

    def test_brush_shortcuts_open_correct_tool_and_help_is_reusable(self):
        self.source()
        self.app._focus_brush("keep")
        self.assertEqual(self.app._mask_tool.get(), "keep")
        self.assertTrue(self.app._section_toggles["Поправить кистями"][1][0])
        self.app._show_quick_start()
        window = self.app._help_window
        self.app._show_quick_start()
        self.assertIs(self.app._help_window, window)
        self.app._set_theme("dark", persist=False)
        self.assertEqual(window.cget("bg"), THEMES["dark"]["BG"])

    def test_tray_can_build_export_and_restore_atlas_without_source_image(self):
        self.app.sprites = [Image.new("RGBA", (12, 12), "red"), Image.new("RGBA", (12, 12), "blue")]
        self.app.excluded = {1}
        self.app._tray_refresh()
        self.app._tray_to_atlas()
        self.assertEqual(self.app.tool, "atlas")
        self.assertEqual(len(self.app._atlas_raws), 1)
        self.assertIsNotNone(self.app._atlas_sheet)
        self.assertIsNone(self.app.src_img)
        self.app.outdir = self.directory.name
        self.app._atlas_save()
        self.assertTrue(Path(self.app._atlas_last_out).is_file())
        project = Path(self.directory.name) / "atlas.smproj"
        with patch("gui_cutter.filedialog.asksaveasfilename", return_value=str(project)):
            self.app.project_save()
        self.assertTrue(self.app.project_load(str(project)))
        self.assertIsNotNone(self.app._atlas_sheet)
        self.app._tool_set("auto")
        self.assertEqual(self.app.excluded, {1})


if __name__ == "__main__":
    unittest.main(verbosity=2)
