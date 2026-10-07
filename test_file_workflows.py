"""File loading and overwrite regressions; uses isolated disposable fixtures."""
import json
from pathlib import Path
import tempfile
import time
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
