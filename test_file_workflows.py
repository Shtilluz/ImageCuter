"""File loading and overwrite regressions; uses isolated disposable fixtures."""
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from tkinterdnd2 import TkinterDnD
from gui_cutter import SpriteManufacturerApp


class FileWorkflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = TkinterDnD.Tk()
        cls.root.withdraw()
        cls.app = SpriteManufacturerApp(cls.root)
        cls.app._add_recent = lambda _: None

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=".")
        self.folder = Path(self.directory.name).resolve()
        self.messages = patch("gui_cutter.messagebox")
        self.dialogs = self.messages.start()
        self.dialogs.askyesno.return_value = True
        self.app._tool_set("auto")
        self.app._clear_src()
        self.app._background_rgb = None
        self.app._background_mode.set("auto")
        self.app._auto_object_mode.set("objects")
        self.app._auto_group_gap.set(0)
        self.app._pixel_art.set(False)
        self.app._edge_smooth.set(True)
        self.app._edge_choke.set(0)
        self.app._export_padding.set(0)
        self.app._auto_scale_mode.set("none")
        self.app._mask_tool.set("pan")
        self.app._background_update_labels()
        self.app._auto_thresh.set(10)
        self.app._atlas_thresh.set(10)
        self.app.outdir = ""
        self.app._outdir_auto = True
        self.app.sprites.clear()
        self.app.excluded.clear()

    def tearDown(self):
        self.messages.stop()
        self.directory.cleanup()

    def image(self, name, color="red", size=(32, 32)):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", size, color).save(path)
        return path

    def atlas(self):
        source = self.image("source.png")
        self.app._load_src(str(source))
        self.app._tool_set("atlas")
        return source

    def test_tcl_paths_spaces_braces_unicode_and_uri(self):
        paths = [str(self.image("файл {версия} 1.png")), str(self.image("второй файл.png"))]
        encoded = self.root.tk.call("list", *paths)
        self.assertEqual(self.app._parse_drop_paths(encoded), paths)
        self.assertEqual(self.app._parse_drop_paths(Path(paths[0]).as_uri()), [paths[0].replace("\\", "/")])
        self.assertEqual(self.app._parse_drop_paths("{broken"), [])

    def test_native_drop_events_accept_files_and_clear_highlight(self):
        canvas = self.app._canvas
        self.assertTrue(canvas.dnd_bind("<<DropEnter>>"))
        self.assertTrue(canvas.dnd_bind("<<DropPosition>>"))
        self.assertTrue(canvas.dnd_bind("<<DropLeave>>"))
        canvas.event_generate("<<DropEnter>>")
        self.assertEqual(int(canvas.cget("highlightthickness")), 3)
        canvas.event_generate("<<DropLeave>>")
        self.assertEqual(int(canvas.cget("highlightthickness")), 0)
        # %D is the native tkdnd data slot; invoke the registered Tcl callback.
        paths = (str(self.image("native {drop}.png")), str(self.image("second file.png")))
        encoded = self.root.tk.call("list", *paths)
        self.root.tk.setvar("sprite_drop_test_data", encoded)
        binding = canvas.dnd_bind("<<Drop>>")
        self.root.tk.eval(binding.replace("%D", "$sprite_drop_test_data"))
        self.assertEqual(len(self.app.sprites), 2)

    def test_multiple_drop_keeps_every_file(self):
        paths = [str(self.image("a.png")), str(self.image("b.png", "blue"))]
        self.app._handle_drop_paths(paths)
        self.assertEqual(len(self.app.sprites), 2)

    def test_multiple_drop_atlas_survives_settings_change(self):
        self.app._tool_set("atlas")
        self.app._handle_drop_paths([str(self.image("a.png")), str(self.image("b.png", "blue"))])
        self.app._atlas_preset(32)
        self.assertEqual(len(self.app._atlas_raws), 2)
        self.assertEqual(self.app._atlas_raws[1].getpixel((0, 0)), (0, 0, 255, 255))

    def test_folder_drop_selects_batch_input(self):
        self.image("one.png")
        self.app._handle_drop_paths([str(self.folder)])
        self.assertEqual(self.app.tool, "resize")
        self.assertEqual(self.app._resize_folder_var.get(), str(self.folder))

    def test_bad_drop_preserves_source_and_reports_error(self):
        source = self.image("valid.png")
        self.app._load_src(str(source))
        bad = self.folder / "bad.png"
        bad.write_bytes(b"not an image")
        self.app._handle_drop_paths([str(bad)])
        self.assertEqual(self.app.src_path, str(source))
        self.dialogs.showwarning.assert_called()

    def test_automatic_output_tracks_source_manual_output_stays(self):
        first = self.image("first/a.png")
        second = self.image("second/b.png")
        self.app._load_src(str(first))
        self.app._load_src(str(second))
        self.assertEqual(self.app.outdir, str(second.parent))
        with patch("gui_cutter.filedialog.askdirectory", return_value=str(first.parent)):
            self.app._menu_choose_outdir()
        self.app._load_src(str(second))
        self.assertEqual(self.app.outdir, str(first.parent))

    def test_output_selected_during_export_is_preserved_on_next_load(self):
        self.app.sprites = [Image.new("RGBA", (8, 8), "red")]
        with patch("gui_cutter.filedialog.askdirectory", return_value=str(self.folder)):
            self.app._tray_save_all()
        self.app._load_src(str(self.image("other/source.png")))
        self.assertEqual(self.app.outdir, str(self.folder))

    def test_original_replacement_has_explicit_confirmation(self):
        source = self.atlas()
        original = source.read_bytes()
        self.app._atlas_name.set("source")
        self.dialogs.askyesno.return_value = False
        self.app._atlas_save()
        self.assertEqual(source.read_bytes(), original)
        title, message = self.dialogs.askyesno.call_args.args
        self.assertIn("исходное", title)
        self.assertIn(str(source), message)

    def test_clipboard_temporary_file_is_not_output_or_overwrite_target(self):
        temporary = self.image("temporary.png")
        self.app._clipboard_temporary = str(temporary)
        with patch.object(self.app, "_get_clipboard_path", return_value=str(temporary)):
            self.app._global_paste()
        self.assertEqual(self.app.src_path, "")
        self.assertEqual(self.app.outdir, "")
        self.assertFalse(temporary.exists())
        self.assertEqual(self.app._auto_overwrite_btn.cget("state"), "disabled")
        self.app._auto_overwrite()
        self.assertFalse(temporary.exists())

    def test_auto_overwrite_saves_latest_result_to_last_dropped_file_without_confirmation(self):
        previous = self.image("previous.png", "blue")
        original_previous = previous.read_bytes()
        self.app._handle_drop_paths([str(previous)])
        source = self.folder / "текущий лист.PNG"
        pixels = np.full((64, 120, 3), 255, dtype=np.uint8)
        pixels[16:48, 12:44] = (220, 30, 50)
        pixels[16:48, 76:108] = (30, 60, 220)
        Image.fromarray(pixels).save(source)
        self.app._handle_drop_paths([str(source)])
        self.assertEqual(self.app.src_path, str(source))
        self.assertEqual(len(self.app._auto_regions_cache), 2)
        original_source = self.app.src_img.copy()
        # Save must recompute brush edits even while viewing the original.
        self.app._mask_marks = np.zeros(pixels.shape[:2], dtype=np.uint8)
        self.app._mask_marks[24:32, 24:32] = 2
        self.app._mask_revision += 1
        self.app._background_preview.set(False)
        self.app.outdir = str(self.folder / "unrelated-output")
        with patch("gui_cutter.filedialog") as dialogs:
            self.app._auto_overwrite_btn.invoke()
            dialogs.askdirectory.assert_not_called()
            dialogs.asksaveasfilename.assert_not_called()
        with Image.open(source) as saved:
            self.assertEqual(saved.size, (120, 64))
            self.assertEqual(saved.getpixel((0, 0))[3], 0)
            self.assertEqual(saved.getpixel((28, 28))[3], 0)
            self.assertEqual(saved.getpixel((36, 36)), (220, 30, 50, 255))
            self.assertEqual(saved.getpixel((90, 32)), (30, 60, 220, 255))
            np.testing.assert_array_equal(np.array(saved), np.array(self.app._cv2pil(self.app._auto_rgba_cache)))
        self.assertEqual(previous.read_bytes(), original_previous)
        self.assertEqual(self.app.src_path, str(source))
        np.testing.assert_array_equal(self.app.src_img, original_source)
        self.dialogs.askyesno.assert_not_called()
        self.assertIn(str(source), self.app._status_var.get())
        saved_bytes = source.read_bytes()
        self.app._auto_overwrite_btn.invoke()
        self.assertEqual(source.read_bytes(), saved_bytes)
        self.assertEqual(list(self.folder.glob(".sprite-save-*")), [])

    def test_auto_overwrite_button_requires_file_and_nonempty_result(self):
        self.assertEqual(self.app._auto_overwrite_btn.cget("state"), "disabled")
        source = self.image("source.png")
        self.app._load_src(str(source))
        self.assertEqual(self.app._auto_overwrite_btn.cget("state"), "normal")
        self.app._clear_src()
        self.assertEqual(self.app._auto_overwrite_btn.cget("state"), "disabled")
        source = self.image("empty.png", (0, 0, 0, 0))
        original = source.read_bytes()
        self.app._load_src(str(source))
        self.assertEqual(self.app._auto_overwrite_btn.cget("state"), "disabled")
        self.app._auto_overwrite()
        self.assertEqual(source.read_bytes(), original)

    def test_auto_overwrite_preserves_webp_format_and_alpha(self):
        source = self.image("source.webp")
        self.app._load_src(str(source))
        self.app._mask_marks = np.zeros((32, 32), dtype=np.uint8)
        self.app._mask_marks[8:12, 8:12] = 2
        self.app._mask_revision += 1
        self.assertEqual(self.app._auto_overwrite_btn.cget("state"), "normal")
        self.app._auto_overwrite_btn.invoke()
        with Image.open(source) as saved:
            self.assertEqual(saved.format, "WEBP")
            self.assertEqual(saved.size, (32, 32))
            self.assertEqual(saved.getpixel((10, 10))[3], 0)
            expected = self.app._sprite_pil(self.app._auto_rgba_cache, self.app._auto_regions_cache[0], scale=True)
            np.testing.assert_array_equal(np.array(saved), np.array(expected))

    def test_auto_overwrite_converts_dropped_jpeg_and_bmp_and_archives_original(self):
        previous = None
        for extension in ("jpg", "jpeg", "JPEG", "bmp"):
            with self.subTest(extension=extension):
                source = self.folder / f"спрайт {extension}.{extension}"
                pixels = np.full((64, 64, 3), 255, dtype=np.uint8)
                pixels[16:48, 16:48] = (220, 30, 50)
                Image.fromarray(pixels).save(source)
                original = source.read_bytes()
                self.app._handle_drop_paths([str(source)])
                self.assertEqual(self.app._auto_overwrite_btn.cget("state"), "normal")
                original_pixels = self.app.src_img.copy()
                self.app.outdir = str(self.folder / "unrelated-output")
                self.app._auto_overwrite_btn.invoke()
                target = source.with_suffix(".png")
                archived = self.folder / "Оригиналы" / source.name
                self.assertFalse(source.exists())
                self.assertEqual(archived.read_bytes(), original)
                self.assertEqual(self.app.src_path, str(target))
                self.assertEqual(self.app._src_lbls["auto"].cget("text"), target.name)
                np.testing.assert_array_equal(self.app.src_img, original_pixels)
                with Image.open(target) as saved:
                    self.assertEqual(saved.format, "PNG")
                    self.assertLess(saved.width, 64)
                    self.assertLess(saved.height, 64)
                    expected = self.app._sprite_pil(self.app._auto_rgba_cache, self.app._auto_regions_cache[0], scale=True)
                    np.testing.assert_array_equal(np.array(saved), np.array(expected))
                saved_bytes = target.read_bytes()
                self.app._auto_overwrite_btn.invoke()
                self.assertEqual(target.read_bytes(), saved_bytes)
                self.assertEqual(archived.read_bytes(), original)
                self.dialogs.askyesno.assert_not_called()
                if previous:
                    self.assertEqual(previous[0].read_bytes(), previous[1])
                previous = target, saved_bytes

    def test_auto_overwrite_single_object_matches_cropped_export_with_scale_and_padding(self):
        source = self.folder / "subject.png"
        pixels = np.full((80, 100, 3), 255, dtype=np.uint8)
        pixels[20:60, 30:70] = (20, 80, 150)
        Image.fromarray(pixels).save(source)
        self.app._handle_drop_paths([str(source)])
        self.app._auto_scale_mode.set("both")
        self.app._auto_scale_w.set(32)
        self.app._auto_scale_h.set(16)
        self.app._export_padding.set(3)
        self.app._auto_overwrite_btn.invoke()
        with Image.open(source) as saved:
            self.assertEqual(saved.size, (38, 22))
            self.assertEqual(saved.getpixel((0, 0))[3], 0)
            self.assertEqual(saved.getpixel((19, 11)), (20, 80, 150, 255))
        saved_bytes = source.read_bytes()
        self.app._auto_overwrite_btn.invoke()
        self.assertEqual(source.read_bytes(), saved_bytes)

    def test_auto_overwrite_jpeg_handles_existing_png_and_original_names(self):
        source = self.folder / "source.jpg"
        Image.new("RGB", (32, 32), "red").save(source)
        original = source.read_bytes()
        target = self.image("source.png", "blue")
        previous_png = target.read_bytes()
        archived = self.folder / "Оригиналы" / source.name
        archived.parent.mkdir()
        archived.write_bytes(b"previous original")
        self.app._handle_drop_paths([str(source)])
        self.dialogs.askyesno.return_value = False
        self.app._auto_overwrite_btn.invoke()
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(target.read_bytes(), previous_png)
        self.assertEqual(self.app.src_path, str(source))
        self.assertIn(str(target), self.dialogs.askyesno.call_args.args[1])
        self.dialogs.askyesno.return_value = True
        self.app._auto_overwrite_btn.invoke()
        self.assertFalse(source.exists())
        self.assertEqual(self.app.src_path, str(target))
        self.assertEqual(archived.read_bytes(), b"previous original")
        self.assertEqual(archived.with_name("source_1.jpg").read_bytes(), original)
        with Image.open(target) as saved:
            self.assertEqual(saved.format, "PNG")
            self.assertGreater(saved.getpixel((16, 16))[0], 240)

    def test_auto_overwrite_jpeg_write_failure_does_not_move_original(self):
        source = self.folder / "source.jpeg"
        Image.new("RGB", (32, 32), "red").save(source)
        original = source.read_bytes()
        self.app._handle_drop_paths([str(source)])
        with patch("PIL.Image.Image.save", side_effect=OSError("disk full")):
            self.app._auto_overwrite_btn.invoke()
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(self.app.src_path, str(source))
        self.assertFalse(source.with_suffix(".png").exists())
        self.assertFalse((self.folder / "Оригиналы").exists())
        self.assertEqual(list(self.folder.glob(".sprite-save-*")), [])
        self.dialogs.showerror.assert_called_once()

    def test_auto_overwrite_jpeg_archive_failure_keeps_original_and_saved_png(self):
        source = self.folder / "source.jpeg"
        Image.new("RGB", (32, 32), "red").save(source)
        original = source.read_bytes()
        self.app._handle_drop_paths([str(source)])
        with patch("gui_cutter.shutil.copy2", side_effect=OSError("disk full")):
            self.app._auto_overwrite_btn.invoke()
        self.assertEqual(source.read_bytes(), original)
        target = source.with_suffix(".png")
        self.assertEqual(self.app.src_path, str(target))
        with Image.open(target) as saved:
            self.assertEqual(saved.format, "PNG")
        self.assertEqual(list((self.folder / "Оригиналы").iterdir()), [])
        self.dialogs.showwarning.assert_called_once()
        self.dialogs.showerror.assert_not_called()

    def test_auto_overwrite_write_failure_preserves_source(self):
        source = self.image("source.png")
        original = source.read_bytes()
        self.app._load_src(str(source))
        status = self.app._status_var.get()
        with patch("gui_cutter.os.replace", side_effect=PermissionError("file in use")):
            self.app._auto_overwrite_btn.invoke()
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.folder.glob(".sprite-save-*")), [])
        self.assertEqual(self.app._status_var.get(), status)
        self.dialogs.showerror.assert_called_once()

    def test_auto_overwrite_reports_missing_source_without_recreating_it(self):
        source = self.image("source.png")
        self.app._load_src(str(source))
        source.unlink()
        self.app._auto_overwrite()
        self.assertFalse(source.exists())
        self.dialogs.showerror.assert_called_once()
        self.app._workflow_update()
        self.assertEqual(self.app._auto_overwrite_btn.cget("state"), "disabled")

    def test_overwrite_without_saved_atlas_never_replaces_source(self):
        source = self.atlas()
        original = source.read_bytes()
        with patch.object(self.app, "_atlas_save") as save:
            self.app._atlas_overwrite()
            save.assert_called_once()
        self.assertEqual(source.read_bytes(), original)

    def test_overwrite_cancel_preserves_target(self):
        self.atlas()
        target = self.image("saved.png", "blue")
        original = target.read_bytes()
        self.app._atlas_last_out = str(target)
        self.dialogs.askyesno.return_value = False
        self.app._atlas_overwrite()
        self.assertEqual(target.read_bytes(), original)

    def test_successful_overwrite_and_write_failure(self):
        self.atlas()
        target = self.image("saved.png", "blue")
        self.app._atlas_last_out = str(target)
        self.app._atlas_overwrite()
        with Image.open(target) as saved:
            self.assertEqual(saved.getpixel((16, 16)), (255, 0, 0, 255))
        original = target.read_bytes()
        with patch("gui_cutter.os.replace", side_effect=PermissionError("file in use")):
            self.app._atlas_overwrite()
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(list(self.folder.glob(".sprite-save-*")), [])
        self.dialogs.showerror.assert_called()

    def test_partial_writer_failure_preserves_existing_file(self):
        target = self.image("saved.png")
        original = target.read_bytes()
        def broken_writer(path):
            Path(path).write_bytes(b"partial data")
            raise OSError("disk full")
        with self.assertRaises(OSError):
            self.app._atomic_write(str(target), broken_writer, overwrite=True)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(list(self.folder.glob(".sprite-save-*")), [])

    def test_new_export_does_not_replace_existing_file(self):
        target = self.image("saved.png")
        original = target.read_bytes()
        with self.assertRaises(FileExistsError):
            self.app._atomic_image(Image.new("RGBA", (8, 8), "blue"), str(target))
        self.assertEqual(target.read_bytes(), original)

    def test_export_numbering_handles_uppercase_extensions(self):
        self.image("SPRITE_0007.PNG")
        self.assertEqual(self.app._next_idx(str(self.folder), "sprite_"), 8)

    def test_opaque_rgba_objects_and_16_bit_input(self):
        image = np.full((64, 128, 4), 255, dtype=np.uint8)
        image[10:40, 10:40, :3] = 0
        image[10:40, 60:90, :3] = 0
        self.assertEqual(len(self.app._auto_contours(image, 245, 12)), 2)
        path = self.folder / "16bit.png"
        Image.fromarray(np.full((32, 32), 65535, dtype=np.uint16)).save(path)
        self.assertTrue(self.app._load_src(str(path)))
        self.assertEqual(self.app.src_img.dtype, np.uint8)

    def test_imported_atlas_preserves_partial_transparency(self):
        self.app._tool_set("atlas")
        self.app._handle_drop_paths([str(self.image("a.png", (255, 0, 0, 128))),
                                     str(self.image("b.png", (0, 0, 255, 128)))])
        sheet, *_ = self.app._atlas_build()
        self.assertEqual(sheet.getpixel((16, 16))[3], 128)

    def test_names_cannot_escape_output_directory(self):
        self.atlas()
        self.app._atlas_name.set("../bad/name.png")
        self.app._atlas_save()
        self.assertEqual(Path(self.app._atlas_last_out).parent, self.folder)
        self.assertEqual(self.app._safe_name("CON", "atlas"), "_CON")
        self.assertEqual(self.app._safe_name("...", "atlas"), "atlas")

    def test_project_uses_snapshot_after_original_overwrite(self):
        source = self.image("source.png")
        self.app._load_src(str(source))
        project = self.folder / "saved.smproj"
        with patch("gui_cutter.filedialog.asksaveasfilename", return_value=str(project)):
            self.app.project_save()
        Image.new("RGBA", (10, 10), "blue").save(source)
        self.app._handle_drop_paths([str(project)])
        self.assertEqual(self.app.src_img.shape[:2], (32, 32))

    def test_bad_project_keeps_current_session(self):
        source = self.image("source.png")
        self.app._load_src(str(source))
        for content in ([1, 2], {"source_data": "broken"}, {"settings": {"atlas_cols": 999999}}):
            project = self.folder / "bad.smproj"
            project.write_text(json.dumps(content), encoding="utf-8")
            self.assertFalse(self.app.project_load(str(project)))
            self.assertEqual(self.app.src_path, str(source))

    def test_imported_atlas_project_roundtrip(self):
        self.app._tool_set("atlas")
        self.app._handle_drop_paths([str(self.image("a.png")), str(self.image("b.png", "blue"))])
        self.app.excluded = {0}
        project = self.folder / "multi.smproj"
        with patch("gui_cutter.filedialog.asksaveasfilename", return_value=str(project)):
            self.app.project_save()
        self.assertTrue(self.app.project_load(str(project)))
        self.assertEqual(len(self.app._atlas_raws), 2)
        self.assertEqual(self.app.excluded, {0})

    def test_background_color_dialog_updates_both_panels(self):
        with patch("gui_cutter.colorchooser.askcolor", return_value=((40, 150, 60), "#28963c")):
            self.app._background_choose()
        self.assertEqual(self.app._background_rgb, (40, 150, 60))
        for label in self.app._background_labels:
            self.assertIn("#28963C", label.cget("text"))
        with patch("gui_cutter.colorchooser.askcolor", return_value=(None, None)):
            self.app._background_choose()
        self.assertEqual(self.app._background_rgb, (40, 150, 60))
        self.app._background_auto()
        self.assertIsNone(self.app._background_rgb)

    def test_eyedropper_samples_source_with_zoom_and_pan_and_can_cancel(self):
        self.app.src_img = np.full((80, 100, 3), (60, 150, 40), np.uint8)
        self.app.src_img[30, 20] = (210, 90, 50)
        self.app._background_start_pick()
        self.assertTrue(self.app._background_picking)
        self.app._cv_zoom = 2
        self.app._cv_img_ox, self.app._cv_img_oy = -30, 15
        # Fit = 2, zoom = 2, so each source pixel covers four canvas pixels.
        with patch.object(self.app._canvas, "winfo_width", return_value=200), \
                patch.object(self.app._canvas, "winfo_height", return_value=200):
            self.app._auto_canvas_press(SimpleNamespace(x=-31, y=15))
            self.assertTrue(self.app._background_picking)
            self.app._auto_canvas_press(SimpleNamespace(x=52, y=137))
        self.assertEqual(self.app._background_rgb, (50, 90, 210))
        self.assertFalse(self.app._background_picking)
        self.app._background_start_pick()
        self.app._cancel_action()
        self.assertFalse(self.app._background_picking)
        self.assertEqual(self.app._background_rgb, (50, 90, 210))

    def test_background_project_settings_roundtrip_and_legacy_threshold(self):
        self.app._load_src(str(self.image("source.png")))
        self.app._background_rgb = (40, 150, 60)
        self.app._background_mode.set("photo")
        self.app._auto_thresh.set(23)
        self.app._atlas_thresh.set(17)
        project = self.folder / "background.smproj"
        with patch("gui_cutter.filedialog.asksaveasfilename", return_value=str(project)):
            self.app.project_save()
        self.app._background_rgb = None
        self.app._auto_thresh.set(0)
        self.assertTrue(self.app.project_load(str(project)))
        self.assertEqual(self.app._background_rgb, (40, 150, 60))
        self.assertEqual(self.app._background_mode.get(), "photo")
        self.assertEqual(self.app._auto_thresh.get(), 23)
        self.assertEqual(self.app._atlas_thresh.get(), 17)
        project.write_text(json.dumps({"version": 3, "settings": {"atlas_thresh": 230}}))
        self.assertTrue(self.app.project_load(str(project)))
        self.assertEqual(self.app._atlas_thresh.get(), 25)
        self.assertIsNone(self.app._background_rgb)
        self.assertEqual(self.app._background_mode.get(), "auto")

    def test_bad_background_color_keeps_session(self):
        source = self.image("source.png")
        self.app._load_src(str(source))
        project = self.folder / "bad-background.smproj"
        project.write_text(json.dumps({"version": 4, "settings": {"background_rgb": [0, 0, 999]}}))
        self.assertFalse(self.app.project_load(str(project)))
        self.assertEqual(self.app.src_path, str(source))

    def test_mask_brush_drag_undo_and_escape_preserve_source(self):
        source = self.image("brush.png", "green", (80, 80))
        self.app._load_src(str(source))
        original = self.app.src_img.copy()
        self.app._mask_tool.set("remove")
        self.app._mask_radius.set(2)
        with patch.object(self.app, "_mask_point", side_effect=[(20, 20), (40, 20)]):
            self.app._auto_canvas_press(SimpleNamespace(x=0, y=0))
            self.app._auto_canvas_drag(SimpleNamespace(x=0, y=0))
            self.app._auto_canvas_release(SimpleNamespace())
        self.assertEqual(self.app._auto_rgba_cache[20, 30, 3], 0)
        np.testing.assert_array_equal(self.app.src_img, original)
        self.app._mask_undo()
        self.assertEqual(self.app._auto_rgba_cache[20, 30, 3], 255)
        self.app._cancel_action()
        self.assertEqual(self.app._mask_tool.get(), "pan")

    def test_mask_refinement_and_output_settings_survive_project_roundtrip(self):
        source = self.image("mask.png", "green", (80, 80))
        self.app._load_src(str(source))
        self.app._mask_marks = np.zeros((80, 80), np.uint8)
        self.app._mask_marks[10:15, 10:15] = 1
        self.app._mask_marks[20:25, 20:25] = 2
        self.app._mask_revision += 1
        self.app._auto_object_mode.set("single")
        self.app._auto_group_gap.set(4)
        self.app._pixel_art.set(True)
        self.app._export_padding.set(2)
        self.app._auto_run()
        refined = self.app._auto_rgba_cache.copy()
        refined[30:35, 30:35, 3] = 0
        self.app._refined_rgba = refined
        self.app._refined_key = self.app._background_signature(self.app.src_img, self.app._auto_thresh.get())
        project = self.folder / "mask.smproj"
        with patch("gui_cutter.filedialog.asksaveasfilename", return_value=str(project)):
            self.app.project_save()
        self.app._clear_src()
        self.assertTrue(self.app.project_load(str(project)))
        self.assertEqual(self.app._mask_marks[12, 12], 1)
        self.assertEqual(self.app._mask_marks[22, 22], 2)
        self.assertEqual(self.app._auto_object_mode.get(), "single")
        self.assertEqual(self.app._auto_group_gap.get(), 4)
        self.assertTrue(self.app._pixel_art.get())
        self.assertEqual(self.app._export_padding.get(), 2)
        np.testing.assert_array_equal(self.app._auto_rgba_cache, refined)

    def test_bad_mask_project_preserves_session(self):
        source = self.image("current.png")
        self.app._load_src(str(source))
        project = self.folder / "bad-mask.smproj"
        import base64
        from io import BytesIO
        mask = BytesIO()
        Image.new("L", (2, 2), 1).save(mask, format="PNG")
        project.write_text(json.dumps({"version": 5, "source_path": str(source),
                                       "mask_data": base64.b64encode(mask.getvalue()).decode()}))
        self.assertFalse(self.app.project_load(str(project)))
        self.assertEqual(self.app.src_path, str(source))

    def test_soft_edges_and_raw_refinement_survive_project_roundtrip(self):
        import cv2
        from background_extractor import extract_foreground
        image = np.full((80, 80, 3), 255, np.uint8)
        cv2.circle(image, (40, 40), 25, (100, 140, 180), -1)
        source = self.folder / "soft.png"
        cv2.imwrite(str(source), image)
        self.app._load_src(str(source))
        self.app._edge_smooth.set(True)
        self.app._edge_choke.set(2)
        self.app._refined_rgba = extract_foreground(self.app.src_img)
        self.app._refined_key = self.app._background_signature(self.app.src_img, self.app._auto_thresh.get())
        self.app._auto_run()
        expected = self.app._auto_rgba_cache.copy()
        self.assertTrue(np.any((expected[:, :, 3] > 0) & (expected[:, :, 3] < 255)))
        project = self.folder / "soft.smproj"
        with patch("gui_cutter.filedialog.asksaveasfilename", return_value=str(project)):
            self.app.project_save()
        self.app._edge_smooth.set(False)
        self.app._edge_choke.set(0)
        self.assertTrue(self.app.project_load(str(project)))
        self.assertTrue(self.app._edge_smooth.get())
        self.assertEqual(self.app._edge_choke.get(), 2)
        np.testing.assert_array_equal(self.app._auto_rgba_cache, expected)
        # Projects saved before edge processing keep their previous output.
        data = json.loads(project.read_text())
        data["version"] = 5
        del data["settings"]["edge_smooth"]
        del data["settings"]["edge_choke"]
        project.write_text(json.dumps(data))
        self.assertTrue(self.app.project_load(str(project)))
        self.assertFalse(self.app._edge_smooth.get())

    def test_atlas_never_clips_large_sprite_to_cell_preset(self):
        self.app._tool_set("atlas")
        large = Image.new("RGBA", (120, 90), (20, 100, 230, 87))
        self.app._atlas_raws = [large]
        self.app._atlas_fit_mode.set("trim")
        self.app._atlas_cell.set(32)
        self.app._atlas_raws = [large]
        sheet, _, cw, ch, _, _ = self.app._atlas_build()
        self.assertGreaterEqual(cw, 120)
        self.assertGreaterEqual(ch, 90)
        np.testing.assert_array_equal(np.array(sheet), np.array(large))

    def test_application_icon_contains_small_and_large_sizes(self):
        resources = Path(__file__).parent / "resource"
        with Image.open(resources / "Icon.ico") as icon:
            self.assertTrue({(16, 16), (32, 32), (48, 48), (256, 256)} <= icon.ico.sizes())
        self.assertEqual(len(self.app._icons), 6)

    def test_refinement_finishes_in_background_and_updates_preview(self):
        from test_background_extractor import sheet
        self.app.src_img = sheet()
        self.app._auto_run()
        self.app._refine_start()
        deadline = time.monotonic() + 10
        while self.app._refine_running and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.app._refine_running)
        self.assertIsNotNone(self.app._refined_rgba)
        self.assertEqual(self.app._auto_rgba_cache[0, 0, 3], 0)
        self.assertIn("уточнён", self.app._refine_status.cget("text"))

    def test_refinement_failure_restores_controls_and_keeps_image(self):
        from test_background_extractor import sheet
        self.app.src_img = sheet()
        original = self.app.src_img.copy()
        with patch("gui_cutter.refine_foreground", side_effect=RuntimeError("processing failed")):
            self.app._refine_start()
            deadline = time.monotonic() + 5
            while self.app._refine_running and time.monotonic() < deadline:
                self.root.update()
                time.sleep(.01)
        self.assertFalse(self.app._refine_running)
        self.assertEqual(self.app._refine_btn.cget("state"), "normal")
        self.dialogs.showinfo.assert_called()
        np.testing.assert_array_equal(self.app.src_img, original)

    def test_batch_skips_nested_output_and_directories_with_image_extension(self):
        self.image("source.png")
        self.image("output/existing.png", "blue")
        (self.folder / "directory.png").mkdir()
        self.app._resize_set_folder(str(self.folder))
        self.app._resize_recursive.set(True)
        self.app._resize_same_folder.set(False)
        self.app.outdir = str(self.folder / "output")
        self.app._resize_run()
        deadline = time.monotonic() + 5
        while self.app._resize_running and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.app._resize_running)
        self.assertTrue((self.folder / "output/source.png").exists())
        self.assertFalse((self.folder / "output/output").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
