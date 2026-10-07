"""Regression checks for workspace interactions; run with the project's Python."""
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
import numpy as np
from PIL import Image, ImageGrab
from tkinterdnd2 import TkinterDnD
from gui_cutter import SpriteManufacturerApp, TOOLS


def main():
    root = TkinterDnD.Tk()
    root.withdraw()
    app = SpriteManufacturerApp(root)
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    root.geometry("1300x860+20+20")
    root.deiconify()
    root.update()
    assert app._canvas.winfo_width() > 600
    assert app._tray_canvas.winfo_height() == 80
    app.src_img = np.full((128, 256, 3), 255, dtype=np.uint8)
    app.src_img[20:60, 20:60, :3] = 0
    app.src_img[20:60, 90:130, :3] = 0
    app.sprites = [Image.new("RGBA", (32, 32), "red")]
    app.excluded = {0}
    for name, _, _ in TOOLS:
        app._tool_set(name)
        root.update()
        assert app._panels[name].winfo_ismapped(), name
        if "--screenshot" in sys.argv:
            ImageGrab.grab(window=root.winfo_id()).save(f"ui-{name}.png")
    app._tool_set("atlas")
    assert len(app._atlas_raws) == 2
    assert not app.excluded, "Regular sprite exclusions leaked into atlas"
    event = SimpleNamespace(x=10, y=10)
    app._tray_click(event)
    app._tray_release(event)
    assert 0 in app.excluded, "Atlas click failed to exclude"
    app._tray_click(event)
    app._tray_release(event)
    assert 0 not in app.excluded, "Atlas click failed to restore"
    app._tray_click(event)
    app._tray_release(SimpleNamespace(x=80, y=10))
    assert not app.excluded, "Dragging changed exclusion"
    app._tool_set("auto")
    root.update()
    assert app.excluded == {0}, "Sprite exclusions lost after mode switch"
    app._cv_actual_size()
    assert app._zoom_var.get() == "100%"
    app._tool_set("shape")
    root.geometry("1000x700")
    root.update()
    app._route_panel_wheel(SimpleNamespace(widget=app._sh_lb, delta=-120))
    assert app._props_scroll.yview()[0] > 0, "Panel wheel routing failed"
    app._sh_sels = [([(1, 1), (20, 1), (20, 20)], "poly")]
    app._clear_src()
    assert not app._sh_sels and not app._atlas_raws and app._atlas_sheet is None
    assert app._auto_cnt_lbl.cget("text") == "Найдено: 0"
    numeric = tk.IntVar(value=64)
    editor = app._spinbox(root, numeric, 1, 4096)
    editor.pack()
    root.update()
    editor.delete(0, tk.END)
    editor.insert(0, "0")
    editor.event_generate("<FocusOut>")
    assert numeric.get() == 1, "Invalid size was not clamped"
    editor.destroy()
    app.src_img = np.zeros((128, 128), dtype=np.uint8)
    app._tool_set("tiletest")
    root.update()
    app._clear_src()
    with tempfile.TemporaryDirectory(dir=".") as directory:
        folder = Path(directory).resolve()
        Image.new("RGB", (512, 1), "red").save(folder / "original.png")
        original_bytes = (folder / "original.png").read_bytes()
        app._resize_folder_var.set(str(folder))
        app._resize_same_folder.set(True)
        app._resize_axis.set("width")
        app._resize_run()
        deadline = time.monotonic() + 5
        while app._resize_running and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        assert not app._resize_running
        assert (folder / "original.png").read_bytes() == original_bytes
        with Image.open(folder / "original_resized.png") as result:
            assert result.size == (64, 1)
        app._resize_run()
        app._resize_cancel()
        root.update()
        time.sleep(0.02)
        root.update()
        assert not app._resize_running, "Cancel failed"
    app._tool_set("auto")
    root.geometry("1300x860")
    root.update()
    assert not errors, errors
    if "--screenshot" in sys.argv:
        app.sprites.clear()
        app.excluded.clear()
        app._tray_refresh()
        root.update()
        ImageGrab.grab(window=root.winfo_id()).save("ui-preview.png")
    root.destroy()
    print("PASS: six panels, layout, atlas clicks/drag, exclusions, zoom, scroll, source reset, numeric input, RGB/grayscale, batch copies/progress/cancel")


if __name__ == "__main__":
    main()
