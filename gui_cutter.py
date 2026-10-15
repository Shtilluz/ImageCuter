"""
Sprite Manufacturer v3 — Unified Workspace
Автор: Shtillgor (https://midgro.uz/)
"""

import cv2
import numpy as np
import os
import sys
import base64
import io
import json
import subprocess
import tempfile
import threading
from urllib.parse import unquote, urlparse
from functools import wraps
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw
from ui_widgets import SoftButton, SoftCheck, SoftRadio, SoftSlider, ToolTip
from ui_themes import THEMES, THEME_NAMES, palette, translate_color
from tkinterdnd2 import TkinterDnD, DND_FILES
from background_extractor import bleed_transparent_colors, extract_foreground, refine_foreground, smooth_cutout_edges, sprite_regions

CONFIG_FILE = os.path.join(os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                                         else os.path.abspath(__file__)), "config.json")

TOOLS = [
    ("auto",     "🔍", "Авто"),
    ("shape",    "✏️",  "Фигура"),
    ("grid",     "📐", "Сетка"),
    ("atlas",    "📦", "Атлас"),
    ("tiletest", "🎮", "Тайл-тест"),
    ("resize",   "🔲", "Ресайз"),
]

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


def file_operation(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except (OSError, ValueError, cv2.error) as error:
            messagebox.showerror("Ошибка файла", f"Операция не завершена:\n{error}")
    return guarded


class SpriteManufacturerApp:
    def __init__(self, root):
        self.root = root
        self._config = {}
        self.recent_dirs = self._load_config()
        self._theme_name = self._config.get("theme", "light")
        if not isinstance(self._theme_name, str) or self._theme_name not in THEMES:
            self._theme_name = "light"
        self.palette = palette(self._theme_name)
        self._theme_var = tk.StringVar(value=THEME_NAMES[self._theme_name])
        self._tooltips = []
        self._section_toggles = {}
        self._last_export_dir = ""
        self._preview_bg = tk.StringVar(value="Клетка")
        self._task_preset = tk.StringVar(value="Несколько спрайтов на листе")
        self.root.title("Sprite Manufacturer v3")
        self.root.geometry("1300x860")
        self.root.minsize(1000, 700)
        self.root.configure(bg=self.palette.BG)
        self.root.option_add("*Font", "{Segoe UI} 10")
        self.root.option_add("*disabledForeground", "#83877d")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TScrollbar", background=self.palette.BTN, troughcolor=self.palette.BG2,
                        bordercolor=self.palette.BG2, arrowcolor=self.palette.FG2)
        style.configure("TSeparator", background=self.palette.BTN)
        style.map("TScrollbar", background=[("active", self.palette.BORDER), ("pressed", self.palette.BORDER)])
        style.configure("TScrollbar", arrowsize=10, borderwidth=0, relief="flat")
        style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": True, "sticky": "nswe"})]})])
        style.layout("Horizontal.TScrollbar", [("Horizontal.Scrollbar.trough", {"sticky": "ew", "children": [
            ("Horizontal.Scrollbar.thumb", {"expand": True, "sticky": "nswe"})]})])
        style.configure("Soft.TSpinbox", fieldbackground=self.palette.INPUT, foreground=self.palette.FG,
                        background=self.palette.BG, bordercolor=self.palette.BORDER, lightcolor=self.palette.INPUT, darkcolor=self.palette.INPUT,
                        arrowcolor=self.palette.FG2, padding=4, borderwidth=1, relief="flat")
        style.map("Soft.TSpinbox", bordercolor=[("focus", "#a7b7a0")],
                  fieldbackground=[("disabled", self.palette.BG2)], foreground=[("disabled", "#969d91")])
        self._set_icon()

        # ── Shared state ──────────────────────────────────────────────
        self.src_img   = None   # cv2 BGRA
        self.src_path  = ""
        self.sprites   = []     # list of PIL RGBA
        self.excluded  = set()  # excluded tray indices
        self.outdir    = ""
        self._outdir_auto = True
        self.tool      = "auto"
        self._background_rgb = None
        self._background_labels = []
        self._background_pipettes = []
        self._quick_brush_buttons = []
        self._background_picking = False
        self._background_preview = tk.BooleanVar(value=True)
        self._auto_rgba_cache = None
        self._auto_regions_cache = []
        self._background_mode = tk.StringVar(value="auto")
        self._background_mode_label = tk.StringVar(value="Авто")
        self._mask_tool = tk.StringVar(value="pan")
        self._mask_radius = tk.IntVar(value=8)
        self._mask_marks = None
        self._mask_history = []
        self._mask_revision = 0
        self._mask_last = None
        self._refined_rgba = None
        self._refined_key = None
        self._refine_running = False
        self._auto_object_mode = tk.StringVar(value="objects")
        self._auto_group_gap = tk.IntVar(value=0)
        self._pixel_art = tk.BooleanVar(value=False)
        self._export_padding = tk.IntVar(value=0)
        self._edge_bleed = tk.BooleanVar(value=True)
        self._edge_smooth = tk.BooleanVar(value=True)
        self._edge_choke = tk.IntVar(value=0)

        # Canvas zoom/pan
        self._cv_zoom    = 1.0
        self._cv_view_x  = 0
        self._cv_view_y  = 0
        self._cv_pan0    = None
        self._cv_img_ox  = 0
        self._cv_img_oy  = 0

        # Atlas state
        self._atlas_raws      = []
        self._atlas_raw_boxes = []
        self._atlas_vis     = None
        self._atlas_cell_w  = 64
        self._atlas_cell_h  = 64
        self._atlas_cols_n  = 0
        self._atlas_rows_n  = 0
        self._atlas_sheet   = None
        self._atlas_last_out = None
        self._atlas_removed  = 0
        self._tray_photos    = []

        # Shape state
        self._sh_sels  = []    # [(pts_img, type)]
        self._sh_cur   = []
        self._sh_down  = False
        self._sh_start = None
        self._sh_colors = ["#a1493d", "#4e6d43", "#91661e", "#765780", "#4c7470", "#594f45"]

        # Tiletest state
        self._tc_cx    = 0
        self._tc_cy    = 0
        self._tc_zoom  = 1.0
        self._tc_vx    = 0
        self._tc_vy    = 0
        self._tc_drag0 = None
        self._tc_pan0  = None
        self._tc_scale = 1.0
        self._tc_ox    = 0
        self._tc_oy    = 0
        self._tc_src_ph  = None
        self._tc_prev_ph = None

        # Photo refs
        self._cv_photo   = None

        # Per-panel label refs (set during pre-build)
        self._src_lbls    = {}
        self._outdir_lbls = {}
        self._panels      = {}

        self._build_ui()
        self._set_theme(self._theme_name, persist=False)
        self.root.bind("<Control-v>", self._global_paste)
        self.root.bind("<Control-V>", self._global_paste)
        self.root.bind("<Escape>",    lambda _: self._cancel_action())
        self.root.bind("<Control-o>", lambda _: self._menu_open_src())
        self.root.bind("<Control-s>", lambda _: self.project_save())
        self.root.bind("<Control-Shift-O>", lambda _: self.project_load())
        self.root.bind("<Control-0>", lambda _: self._cv_zoom_reset())
        self.root.bind("<Control-1>", lambda _: self._cv_actual_size())
        self.root.bind_all("<MouseWheel>", self._route_panel_wheel, add="+")

    # ══════════════════════════════════════════════════════════════════
    #  ICON / CONFIG
    # ══════════════════════════════════════════════════════════════════

    def _set_icon(self):
        resources = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resource")
        try:
            # A separate application identity prevents grouping under Python on Windows.
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Shtillgor.SpriteManufacturer")
            with Image.open(os.path.join(resources, "Icon.png")) as image:
                self._icons = [ImageTk.PhotoImage(image.resize((size, size), Image.Resampling.LANCZOS), master=self.root)
                               for size in (256, 128, 64, 48, 32, 16)]
            self.root.iconphoto(True, *self._icons)
            if sys.platform == "win32":
                self.root.iconbitmap(default=os.path.join(resources, "Icon.ico"))
            self.root.iconname("Sprite Manufacturer")
        except (OSError, tk.TclError, AttributeError) as error:
            print(f"Icon: {error}")

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._config = data
                    recent = data.get("recent_dirs", [])
                    if isinstance(recent, list):
                        return [path for path in recent if isinstance(path, str)][:8]
            except Exception:
                pass
        return []

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                self._config.update(recent_dirs=self.recent_dirs, theme=self._theme_name)
                json.dump(self._config, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def _add_recent(self, d):
        if d in self.recent_dirs:
            self.recent_dirs.remove(d)
        self.recent_dirs.insert(0, d)
        self.recent_dirs = self.recent_dirs[:8]
        self._save_config()

    # ══════════════════════════════════════════════════════════════════
    #  UI HELPERS
    # ══════════════════════════════════════════════════════════════════

    def _tip(self, widget, text):
        self._tooltips.append(ToolTip(widget, text, lambda: self.palette))
        return widget

    def _configure_theme_styles(self):
        p = self.palette
        style = ttk.Style(self.root)
        style.configure("TScrollbar", background=p.BTN, troughcolor=p.BG2, bordercolor=p.BG2,
                        arrowcolor=p.FG2, lightcolor=p.BTN, darkcolor=p.BTN)
        style.map("TScrollbar", background=[("active", p.BORDER), ("pressed", p.BORDER)])
        style.configure("TSeparator", background=p.BORDER)
        style.configure("Soft.TSpinbox", fieldbackground=p.INPUT, foreground=p.FG,
                        background=p.BG, bordercolor=p.BORDER, lightcolor=p.INPUT,
                        darkcolor=p.INPUT, arrowcolor=p.FG2)
        style.map("Soft.TSpinbox", bordercolor=[("focus", p.FOCUS)],
                  fieldbackground=[("disabled", p.BG2)], foreground=[("disabled", p.FG2)])
        style.configure("TCombobox", fieldbackground=p.INPUT, background=p.BTN, foreground=p.FG,
                        arrowcolor=p.FG, bordercolor=p.BORDER, lightcolor=p.INPUT, darkcolor=p.INPUT,
                        selectbackground=p.GRN, selectforeground=p.FG, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", p.INPUT)],
                  foreground=[("readonly", p.FG)], selectbackground=[("readonly", p.INPUT)],
                  selectforeground=[("readonly", p.FG)], bordercolor=[("focus", p.FOCUS)])
        self.root.option_add("*TCombobox*Listbox.background", p.INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", p.FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", p.GRN)
        self.root.option_add("*TCombobox*Listbox.selectForeground", p.FG)
        self.root.option_add("*disabledForeground", p.FG2)

    def _set_theme(self, name, persist=True):
        if name not in THEMES:
            return
        previous = self.palette
        self._theme_name, self.palette = name, palette(name)
        self._theme_var.set(THEME_NAMES[name])
        for tip in self._tooltips:
            tip.hide()
        options = ("background", "foreground", "activebackground", "activeforeground",
                   "disabledforeground", "selectbackground", "selectforeground", "insertbackground",
                   "highlightbackground", "highlightcolor", "troughcolor")
        def recolor(widget):
            if isinstance(widget, SoftButton):
                widget.configure(bg=translate_color(widget.fill, "background", previous, self.palette),
                                 fg=translate_color(widget.foreground, "foreground", previous, self.palette))
            else:
                keys = widget.keys()
                changes = {key: translate_color(widget.cget(key), key, previous, self.palette)
                           for key in options if key in keys}
                if isinstance(widget, (SoftCheck, SoftRadio)):
                    changes["fg"] = translate_color(widget.foreground, "foreground", previous, self.palette)
                if changes:
                    widget.configure(**changes)
            if hasattr(widget, "apply_theme"):
                widget.apply_theme(self.palette)
            for child in widget.winfo_children():
                recolor(child)
        recolor(self.root)
        self._configure_theme_styles()
        for key, button in self._tool_btns.items():
            button.config(bg=self.palette.GRN if key == self.tool else self.palette.TOOL_BG,
                          fg=self.palette.ACC if key == self.tool else self.palette.FG2)
        if self.tool == "atlas":
            self._tray_refresh_atlas_tray()
        else:
            self._tray_refresh()
        self._cv_draw()
        if persist:
            self._save_config()

    def _theme_selected(self, _=None):
        name = next((key for key, label in THEME_NAMES.items() if label == self._theme_var.get()), "light")
        self._set_theme(name)

    def _lbl(self, parent, text, bold=False, color=None, size=10):
        color = self.palette.FG if color is None else color
        return tk.Label(parent, text=text, fg=color, bg=self.palette.BG,
                        font=("Segoe UI", size, "bold" if bold else "normal"),
                        wraplength=290, justify=tk.LEFT)

    def _btn(self, parent, text, cmd, color=None, h=1, state=tk.NORMAL, font_size=10):
        color = self.palette.BTN if color is None else color
        foreground = self.palette.WHITE if color == self.palette.ACC else self.palette.RED_FG if color == self.palette.RED else self.palette.FG
        button = SoftButton(parent, text=text, command=cmd, bg=color, fg=foreground,
                            font=("Segoe UI", font_size), height=42 if h > 1 else 34, state=state)
        button.apply_theme(self.palette)
        return button

    def _spinbox(self, parent, var, lo, hi, w=6, cmd=None):
        editor = tk.StringVar(value=str(var.get()))
        kw = dict(from_=lo, to=hi, textvariable=editor, width=w,
                  style="Soft.TSpinbox", font=("Segoe UI", 10))
        def validate(value):
            return value == "" or (value.isdecimal() and len(value) <= 6)
        kw.update(validate="key", validatecommand=(self.root.register(validate), "%P"))
        sb = ttk.Spinbox(parent, **kw)
        def commit(_=None):
            try:
                value = int(sb.get())
            except ValueError:
                value = lo
            var.set(max(lo, min(hi, value)))
            if cmd:
                cmd()
        sb.config(command=commit)
        var.trace_add("write", lambda *_: editor.set(str(var.get())))
        sb.bind("<FocusOut>", commit)
        sb.bind("<Return>", commit)
        return sb

    def _sep(self, parent):
        tk.Frame(parent, bg=self.palette.BG, height=12).pack(fill=tk.X, pady=3)

    def _section(self, parent, title, expanded=True):
        hdr = tk.Frame(parent, bg=self.palette.BG, cursor="hand2")
        hdr.pack(fill=tk.X, pady=(12, 0))
        state = [expanded]
        arrow = tk.Label(hdr, text="▼" if expanded else "▶",
                         bg=self.palette.BG, fg=self.palette.GOLD, font=("Segoe UI", 9, "bold"), width=2)
        arrow.pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(hdr, text=title, bg=self.palette.BG, fg=self.palette.FG,
                 font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, pady=7)
        body = tk.Frame(parent, bg=self.palette.BG)
        body._section_header = hdr
        if expanded:
            body.pack(fill=tk.X, pady=(2, 4), after=hdr)
        def _toggle(_=None):
            state[0] = not state[0]
            arrow.config(text="▼" if state[0] else "▶")
            if state[0]:
                body.pack(fill=tk.X, pady=(2, 4), after=hdr)
            else:
                body.pack_forget()
        for w in (hdr, arrow) + tuple(hdr.winfo_children()):
            w.bind("<Button-1>", _toggle)
        hdr.bind("<Button-1>", _toggle)
        self._section_toggles[title] = (body, state, _toggle)
        hdr.configure(takefocus=1)
        hdr.configure(highlightthickness=1, highlightbackground=self.palette.BG)
        hdr.bind("<FocusIn>", lambda _: hdr.configure(highlightbackground=self.palette.FOCUS))
        hdr.bind("<FocusOut>", lambda _: hdr.configure(highlightbackground=self.palette.BG))
        hdr.bind("<Return>", _toggle)
        hdr.bind("<space>", _toggle)
        return body

    def _focus_brush(self, value):
        self._tool_set("auto")
        body, state, toggle = self._section_toggles["Поправить кистями"]
        if not state[0]:
            toggle()
        self._mask_tool.set(value)
        self._mask_select()
        self.root.update_idletasks()
        self._props_scroll.yview_moveto(max(0, body.winfo_y() - 45) / max(1, self._props.winfo_height()))
        self._status_var.set("Рисуйте по детали, которую нужно вернуть. Esc — закончить." if value == "keep" else
                             "Рисуйте по лишнему фону. Esc — закончить.")

    def _show_advanced(self):
        body, state, toggle = self._section_toggles["Размер и края PNG"]
        if not state[0]:
            toggle()
        self.root.update_idletasks()
        self._props_scroll.yview_moveto(max(0, body._section_header.winfo_y() - 8) / max(1, self._props.winfo_height()))

    def _apply_preset(self, _=None):
        presets = {"Несколько спрайтов на листе": ("objects", False, 12),
                   "Один персонаж или предмет": ("single", False, 1),
                   "Пиксель-арт: лист спрайтов": ("objects", True, 1)}
        values = presets.get(self._task_preset.get())
        if values is None:
            return
        mode, pixel_art, minimum = values
        self._auto_object_mode.set(mode)
        self._pixel_art.set(pixel_art)
        self._auto_min.set(minimum)
        self._auto_group_gap.set(0)
        self._auto_sep.set(0)
        self._auto_run()

    def _sync_preset(self):
        current = (self._auto_object_mode.get(), self._pixel_art.get(), self._auto_min.get())
        presets = {("objects", False, 12): "Несколько спрайтов на листе",
                   ("single", False, 1): "Один персонаж или предмет",
                   ("objects", True, 1): "Пиксель-арт: лист спрайтов"}
        self._task_preset.set(presets.get(current, "Свои настройки") if not self._auto_group_gap.get() and
                              not self._auto_sep.get() else "Свои настройки")

    def _workflow_update(self):
        if not hasattr(self, "_workflow_steps"):
            return
        image_ready = self.src_img is not None
        count = len(getattr(self, "_auto_regions_cache", []))
        if self.tool == "auto":
            ready = image_ready and count > 0
        elif self.tool == "resize":
            image_ready = bool(self._resize_folder_var.get())
            ready = image_ready and not getattr(self, "_resize_running", False)
        elif self.tool == "shape":
            ready = image_ready and bool(self._sh_sels)
        elif self.tool == "grid":
            ready = image_ready and bool(getattr(self, "_grid_tiles_cache", []))
        elif self.tool == "atlas":
            ready = self._atlas_sheet is not None
            image_ready = image_ready or ready
        else:
            ready = image_ready
        stage = 0 if not image_ready else 2 if ready else 1
        titles = ("1   Откройте картинку", "2   Уберите фон", "3   Сохраните PNG") if self.tool == "auto" else (
            "1   Выберите исходник", "2   Настройте результат", "3   Сохраните файлы")
        for index, (label, text) in enumerate(zip(self._workflow_steps, titles)):
            label.config(text=text, bg=self.palette.ACC if index == stage else self.palette.GRN if index < stage else self.palette.BG2,
                         fg=self.palette.WHITE if index == stage else self.palette.FG if index < stage else self.palette.FG2)
        labels = {"auto": "Сохранить PNG…", "shape": "Сохранить PNG…", "grid": "Сохранить тайлы…",
                  "atlas": "Сохранить атлас…", "tiletest": "Сохранить тайл…", "resize": "Обработать папку"}
        self._export_current_btn.config(text=labels[self.tool], state=tk.NORMAL if ready else tk.DISABLED)
        if hasattr(self, "_auto_save_btn"):
            available = self.src_img is not None and count > 0
            self._auto_save_btn.config(text=f"Сохранить PNG · {count}" if available else "Сохранить PNG…",
                                       state=tk.NORMAL if available else tk.DISABLED)
            self._auto_add_btn.config(state=tk.NORMAL if available else tk.DISABLED)
            self._open_export_btn.config(state=tk.NORMAL if self._last_export_dir or self.outdir else tk.DISABLED)
            self._next_step_var.set("Начните с кнопки «Открыть картинку» или перетащите файл на холст." if not image_ready else
                                    f"Найдено: {count}. Проверьте края и сохраните PNG." if available else
                                    "Спрайты не найдены. Проверьте тип фона и минимальный размер объектов.")
            folder = self._last_export_dir or self.outdir
            short = folder if len(folder) < 49 else "…" + folder[-46:]
            self._export_folder_var.set(f"Папка: {short}" if folder else "При сохранении выберите папку для PNG")
        if hasattr(self, "_refine_btn"):
            self._refine_btn.config(state=tk.NORMAL if self.src_img is not None and not self._refine_running else tk.DISABLED)
            self._mask_undo_btn.config(state=tk.NORMAL if self._mask_history else tk.DISABLED)
            self._mask_clear_btn.config(state=tk.NORMAL if self._mask_marks is not None or self._refined_rgba is not None else tk.DISABLED)
        for button in (*self._background_pipettes, *self._quick_brush_buttons):
            button.config(state=tk.NORMAL if self.src_img is not None else tk.DISABLED)

    @file_operation
    def _open_export_folder(self):
        folder = self._last_export_dir or self.outdir
        if not folder or not os.path.isdir(folder):
            return
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", folder])

    def _show_quick_start(self):
        existing = getattr(self, "_help_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return
        window = self._help_window = tk.Toplevel(self.root)
        window.title("Как получить спрайты из ИИ-картинки")
        window.configure(bg=self.palette.BG)
        window.geometry("640x680")
        window.transient(self.root)
        content = tk.Frame(window, bg=self.palette.BG, padx=24, pady=20)
        content.pack(fill=tk.BOTH, expand=True)
        tk.Label(content, text="Из картинки — в игровой спрайт", bg=self.palette.BG, fg=self.palette.FG,
                 font=("Segoe UI", 16, "bold"), anchor=tk.W).pack(anchor=tk.W, pady=(0, 14))
        entries = (
            ("1. Откройте картинку", "PNG, JPEG или WebP из вашего генератора. Можно перетащить файл в окно или вставить его через Ctrl+V."),
            ("2. Проверьте фон и края", "Обычно достаточно режима «Авто». Сравните «Оригинал» и «Результат». Клетчатая подложка означает прозрачность."),
            ("3. Сохраните PNG", "Кнопка справа сохраняет каждый найденный спрайт в отдельный файл. Чтобы собрать набор из разных картинок, добавляйте их в нижнюю ленту."),
            ("Если что-то пошло не так", "Пропала деталь → «Вернуть деталь». Остался фон → «Стереть фон». Персонаж разбился на части → выберите «Один персонаж или предмет». Искажённую клеточку поправьте кистями."),
            ("Проект или PNG?", "PNG — готовая картинка для игры. Проект .smproj — исходник и ваши правки, чтобы продолжить работу позже. Проект сохраняется через меню «Файл» или Ctrl+S."),
        )
        for title, explanation in entries:
            tk.Label(content, text=title, bg=self.palette.BG, fg=self.palette.ACC,
                     font=("Segoe UI", 11, "bold"), anchor=tk.W).pack(anchor=tk.W, pady=(7, 3))
            tk.Label(content, text=explanation, bg=self.palette.BG, fg=self.palette.FG,
                     font=("Segoe UI", 10), wraplength=580, justify=tk.LEFT).pack(anchor=tk.W)
        self._btn(content, "Понятно, начать работу", window.destroy, self.palette.ACC).pack(fill=tk.X, pady=(18, 0))
        window.bind("<Escape>", lambda _: window.destroy())

    def _scrollable_frame(self, parent):
        """Returns (outer_frame, inner_frame) where inner is scrollable."""
        outer = tk.Frame(parent, width=340, bg=self.palette.BG)
        outer.pack(side=tk.RIGHT, fill=tk.Y, before=self._cv_frame)
        outer.pack_propagate(False)
        vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        sc = tk.Canvas(outer, bg=self.palette.BG, highlightthickness=0, yscrollcommand=vsb.set)
        sc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=sc.yview)
        self._props_scroll = sc
        inner = tk.Frame(sc, bg=self.palette.BG, padx=10, pady=8)
        wid = sc.create_window((0, 0), window=inner, anchor=tk.NW)
        sc.bind("<Configure>", lambda e: sc.itemconfig(wid, width=e.width))
        inner.bind("<Configure>", lambda e: sc.configure(scrollregion=sc.bbox("all")))
        def _scroll(e):
            if e.num == 4 or getattr(e, "delta", 0) > 0:
                sc.yview_scroll(-1, "units")
            else:
                sc.yview_scroll(1, "units")
        sc.bind("<Button-4>", _scroll)
        sc.bind("<Button-5>", _scroll)
        return outer, inner

    def _route_panel_wheel(self, event):
        widget = event.widget
        while widget is not None:
            if widget == self._props_outer:
                self._props_scroll.yview_scroll(-1 if event.delta > 0 else 1, "units")
                return "break"
            widget = getattr(widget, "master", None)

    def _source_controls(self, parent, name):
        row = tk.Frame(parent, bg=self.palette.BG)
        row.pack(fill=tk.X, pady=(0, 4))
        self._src_lbls[name] = self._lbl(row, "Файл не выбран", color=self.palette.FG2, size=9)
        self._src_lbls[name].config(wraplength=230, anchor=tk.W)
        self._src_lbls[name].pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._btn(row, "×", self._clear_src, font_size=10).pack(side=tk.RIGHT)

    def _cv_actual_size(self):
        image = (None if self.tool == "resize" else
                 self._atlas_vis if self.tool == "atlas" else self._cv2pil(self.src_img))
        if image is None:
            return
        width = self._canvas.winfo_width()
        if self.tool == "tiletest":
            width = width // 2 - 1
        fit = min(width / image.width, self._canvas.winfo_height() / image.height)
        self._cv_zoom_reset()
        if self.tool == "tiletest":
            self._tc_zoom = 1 / fit
        else:
            self._cv_zoom = 1 / fit
        self._cv_draw()

    # ══════════════════════════════════════════════════════════════════
    #  BUILD MAIN UI
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # Menu bar
        menubar = tk.Menu(self.root, bg=self.palette.BG2, fg=self.palette.FG, activebackground=self.palette.ACC,
                          activeforeground=self.palette.WHITE, relief=tk.FLAT, borderwidth=0)
        self.root.config(menu=menubar)
        self._build_menu(menubar)

        top = tk.Frame(self.root, bg=self.palette.BG2, padx=12, pady=10)
        top.pack(fill=tk.X)
        if getattr(self, "_icons", None):
            tk.Label(top, image=self._icons[-2], bg=self.palette.BG2).pack(side=tk.LEFT, padx=(0, 8))
        brand = tk.Frame(top, bg=self.palette.BG2)
        brand.pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(brand, text="Sprite Manufacturer", bg=self.palette.BG2, fg=self.palette.FG,
                 font=("Segoe UI", 11, "bold"), anchor=tk.W).pack(anchor=tk.W)
        tk.Label(brand, text="Из ИИ-картинки — в игровой спрайт", bg=self.palette.BG2, fg=self.palette.FG2,
                 font=("Segoe UI", 8)).pack(anchor=tk.W)
        self._tip(self._btn(top, "Открыть картинку…", self._menu_open_src, self.palette.ACC),
                  "Откройте PNG, JPEG или WebP, созданный вашим ИИ. Ctrl+O").pack(side=tk.LEFT, padx=3)
        self._tip(self._btn(top, "Вставить", self._global_paste),
                  "Вставить картинку из буфера обмена. Ctrl+V").pack(side=tk.LEFT, padx=3)
        self._export_current_btn = self._btn(top, "Сохранить PNG…", self._save_current, self.palette.ACC)
        self._export_current_btn.configure(width=158)
        self._export_current_btn.pack(side=tk.RIGHT, padx=3)
        self._btn(top, "Как начать", self._show_quick_start).pack(side=tk.RIGHT, padx=3)
        theme = ttk.Combobox(top, textvariable=self._theme_var, values=list(THEME_NAMES.values()),
                             state="readonly", width=12, font=("Segoe UI", 9))
        theme.pack(side=tk.RIGHT, padx=6)
        theme.bind("<<ComboboxSelected>>", self._theme_selected)
        self._tip(theme, "Тема интерфейса: светлая, тёмная или с повышенным контрастом. Выбор сохраняется.")

        steps = tk.Frame(self.root, bg=self.palette.BG, padx=12, pady=5)
        steps.pack(fill=tk.X)
        self._workflow_steps = []
        for title in ("1   Откройте картинку", "2   Уберите фон", "3   Сохраните PNG"):
            label = tk.Label(steps, text=title, bg=self.palette.BG2, fg=self.palette.FG2,
                             font=("Segoe UI", 9, "bold"), pady=7)
            label.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
            self._workflow_steps.append(label)

        # Reserve the result strip before the expanding workspace.
        bottom = tk.Frame(self.root, bg=self.palette.BG2)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)

        # Main container (toolbar | canvas | props)
        main = tk.Frame(self.root, bg=self.palette.BG)
        main.pack(fill=tk.BOTH, expand=True)

        # Left toolbar (64px)
        self._toolbar = tk.Frame(main, width=164, bg=self.palette.TOOL_BG)
        self._toolbar.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 4), pady=8)
        self._toolbar.pack_propagate(False)
        self._tool_btns = {}
        self._build_toolbar()

        # Center canvas
        cv_frame = self._cv_frame = tk.Frame(main, bg=self.palette.BG2)
        cv_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=8)
        viewbar = tk.Frame(cv_frame, bg=self.palette.BG2, padx=10, pady=5)
        viewbar.pack(fill=tk.X)
        self._view_title = tk.Label(viewbar, text="Исходное изображение", bg=self.palette.BG2,
                                    fg=self.palette.FG, font=("Segoe UI", 10, "bold"))
        self._view_title.pack(side=tk.LEFT)
        self._zoom_var = tk.StringVar(value="—")
        tk.Label(viewbar, textvariable=self._zoom_var, bg=self.palette.BG2, fg=self.palette.FG2,
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=8)
        self._btn(viewbar, "1:1", self._cv_actual_size, font_size=9).pack(side=tk.RIGHT, padx=3)
        self._btn(viewbar, "Вписать", self._cv_zoom_reset, font_size=9).pack(side=tk.RIGHT, padx=3)
        self._canvas = tk.Canvas(cv_frame, bg=self.palette.CANVAS, highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._welcome_panel = tk.Frame(self._canvas, bg=self.palette.CANVAS, padx=12, pady=16)
        tk.Label(self._welcome_panel, text="Спрайты из ИИ-картинки", bg=self.palette.CANVAS, fg=self.palette.FG,
                 font=("Segoe UI", 18, "bold")).pack(pady=(0, 12))
        self._welcome_copy = tk.Label(self._welcome_panel,
            text="Перетащите сюда картинку из генератора.\nПрограмма поможет убрать фон, отделить объекты\nи сохранить прозрачные PNG для игры.",
            bg=self.palette.CANVAS, fg=self.palette.FG2, font=("Segoe UI", 10), wraplength=400, justify=tk.CENTER)
        self._welcome_copy.pack(pady=(0, 16))
        welcome_actions = tk.Frame(self._welcome_panel, bg=self.palette.CANVAS)
        welcome_actions.pack()
        self._btn(welcome_actions, "Открыть картинку…", self._menu_open_src, self.palette.ACC, h=2).pack(side=tk.LEFT, padx=4)
        self._btn(welcome_actions, "Вставить · Ctrl+V", self._global_paste, h=2).pack(side=tk.LEFT, padx=4)
        self._preview_bar = tk.Frame(cv_frame, bg=self.palette.BG2, padx=8, pady=3)
        self._preview_bar.pack(fill=tk.X, before=self._canvas)
        for text, value in (("Результат", True), ("Оригинал", False)):
            radio = SoftRadio(self._preview_bar, text=text, variable=self._background_preview, value=value,
                              bg=self.palette.BG2, fg=self.palette.FG, font=("Segoe UI", 9), command=self._cv_draw)
            radio.pack(side=tk.LEFT, padx=(0, 8))
        self._tip(radio, "Сравните исходную картинку с результатом удаления фона. Исходник сохраняется.")
        preview_background = ttk.Combobox(self._preview_bar, textvariable=self._preview_bg, state="readonly",
                                         values=("Клетка", "Светлый", "Тёмный"), width=9, font=("Segoe UI", 9))
        preview_background.pack(side=tk.RIGHT)
        preview_background.bind("<<ComboboxSelected>>", lambda _: self._cv_draw())
        tk.Label(self._preview_bar, text="Подложка:", bg=self.palette.BG2, fg=self.palette.FG2,
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=5)
        self._tip(preview_background, "Меняет только фон просмотра: удобно проверять светлые и тёмные края спрайта.")
        self._bind_canvas_common()
        self._setup_dnd(self._canvas, self._handle_drop_paths, multi=True)
        self._setup_dnd(self.root, self._handle_drop_paths, multi=True)
        self._canvas.bind("<Double-Button-1>", lambda _: self._menu_open_src()
                          if self.src_img is None else None)
        self._tool_hint = tk.StringVar()
        self._tool_hint_label = tk.Label(cv_frame, textvariable=self._tool_hint, bg=self.palette.BG2, fg=self.palette.FG2,
                 font=("Segoe UI", 9), anchor=tk.W, padx=12, pady=7,
                 wraplength=620, justify=tk.LEFT)
        self._tool_hint_label.pack(fill=tk.X)
        cv_frame.bind("<Configure>", lambda event: self._tool_hint_label.configure(wraplength=max(200, event.width - 24)))

        # Right props panel (310px, scrollable)
        self._props_outer, self._props = self._scrollable_frame(main)

        # Bottom area: tray + statusbar

        # Sprite tray
        tray_frame = tk.Frame(bottom, bg=self.palette.BG2)
        tray_frame.pack(fill=tk.X)
        tray_header = tk.Frame(tray_frame, bg=self.palette.BG2)
        tray_header.pack(fill=tk.X)
        self._tray_count_lbl = tk.Label(tray_header, text="Готовые спрайты: 0",
                                        bg=self.palette.BG2, fg=self.palette.FG, font=("Segoe UI", 10, "bold"))
        self._tray_count_lbl.pack(side=tk.LEFT, padx=12, pady=8)
        self._tray_clear_btn = self._btn(tray_header, "Очистить ленту", self._tray_clear, font_size=9)
        self._tray_clear_btn.pack(side=tk.RIGHT, padx=6)
        self._tray_save_btn = self._btn(tray_header, "Сохранить выбранные PNG…", self._tray_save_all, self.palette.ACC, font_size=9)
        self._tray_save_btn.pack(side=tk.RIGHT, padx=2)
        self._tip(self._tray_save_btn, "Сохранить включённые спрайты из нижней ленты. Зачёркнутые миниатюры будут пропущены.")
        self._tray_atlas_btn = self._btn(tray_header, "Собрать атлас", self._tray_to_atlas, font_size=9, state=tk.DISABLED)
        self._tray_atlas_btn.pack(side=tk.RIGHT, padx=4)
        self._tip(self._tray_atlas_btn, "Собрать включённые спрайты из этой ленты на один PNG-лист. Размеры и порядок настраиваются в разделе «Собрать атлас».")
        tray_row = tk.Frame(tray_frame, bg=self.palette.BG2)
        tray_row.pack(fill=tk.X)
        self._tray_canvas = tk.Canvas(tray_row, bg=self.palette.BG2, height=80, highlightthickness=0)
        self._tray_canvas.pack(side=tk.TOP, fill=tk.X)
        tray_hsb = ttk.Scrollbar(tray_row, orient=tk.HORIZONTAL, command=self._tray_canvas.xview)
        tray_hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tray_canvas.configure(xscrollcommand=tray_hsb.set)
        self._tray_canvas.bind("<Button-1>", self._tray_click)
        self._tray_canvas.bind("<B1-Motion>", self._tray_drag)
        self._tray_canvas.bind("<ButtonRelease-1>", self._tray_release)

        # Status bar
        self._status_var = tk.StringVar(value="Готов к работе • Ctrl+O — открыть • Ctrl+V — вставить")
        status = tk.Label(bottom, textvariable=self._status_var,
                          bg=self.palette.BG2, fg=self.palette.FG2, font=("Segoe UI", 8),
                          anchor=tk.W, padx=8)
        status.pack(fill=tk.X, side=tk.BOTTOM)

        # Pre-build all tool panels once; _rebuild_props just shows/hides them
        for _tn in ("auto", "shape", "grid", "atlas", "tiletest", "resize"):
            _fr = tk.Frame(self._props, bg=self.palette.BG)
            getattr(self, f"_build_props_{_tn}")(_fr)
            self._panels[_tn] = _fr

        # Initial tool
        self._tool_set("auto")
        self._tray_refresh()

    def _build_menu(self, menubar):
        # Файл
        fm = tk.Menu(menubar, tearoff=0, bg=self.palette.BG2, fg=self.palette.FG,
                     activebackground=self.palette.ACC, activeforeground=self.palette.WHITE)
        menubar.add_cascade(label="Файл", menu=fm)
        fm.add_command(label="Открыть изображение",   command=self._menu_open_src)
        fm.add_command(label="Вставить из буфера (Ctrl+V)", command=self._global_paste)
        fm.add_separator()
        fm.add_command(label="Открыть проект (.smproj)", command=self.project_load)
        fm.add_command(label="Сохранить проект — продолжить позже (Ctrl+S)", command=self.project_save)
        fm.add_separator()
        fm.add_command(label="Выбрать папку вывода",    command=self._menu_choose_outdir)
        fm.add_command(label="Сохранить атлас",          command=self._atlas_save)
        fm.add_command(label="Сохранить спрайты по файлам", command=self._tray_save_all)
        fm.add_separator()
        fm.add_command(label="Выход", command=self.root.destroy)

        # Правка
        em = tk.Menu(menubar, tearoff=0, bg=self.palette.BG2, fg=self.palette.FG,
                     activebackground=self.palette.ACC, activeforeground=self.palette.WHITE)
        menubar.add_cascade(label="Правка", menu=em)
        em.add_command(label="Очистить трей",        command=self._tray_clear)
        em.add_command(label="Очистить исходное изображение", command=self._clear_src)

        # Вид
        vm = tk.Menu(menubar, tearoff=0, bg=self.palette.BG2, fg=self.palette.FG,
                     activebackground=self.palette.ACC, activeforeground=self.palette.WHITE)
        menubar.add_cascade(label="Вид", menu=vm)
        vm.add_command(label="Сбросить зум", command=self._cv_zoom_reset)
        themes_menu = tk.Menu(vm, tearoff=0, bg=self.palette.BG2, fg=self.palette.FG,
                              activebackground=self.palette.ACC, activeforeground=self.palette.WHITE)
        vm.add_cascade(label="Тема интерфейса", menu=themes_menu)
        for key, label in THEME_NAMES.items():
            themes_menu.add_radiobutton(label=label, variable=self._theme_var, value=label,
                                        command=lambda name=key: self._set_theme(name))

        # Справка
        hm = tk.Menu(menubar, tearoff=0, bg=self.palette.BG2, fg=self.palette.FG,
                     activebackground=self.palette.ACC, activeforeground=self.palette.WHITE)
        menubar.add_cascade(label="Справка", menu=hm)
        hm.add_command(label="Как получить спрайты — быстрый старт", command=self._show_quick_start)
        hm.add_command(label="Об авторе", command=self._show_author)
        hm.add_command(label="Горячие клавиши", command=lambda: messagebox.showinfo(
            "Горячие клавиши", "Ctrl+O — открыть изображение\nCtrl+V — вставить изображение\n"
            "Ctrl+S — сохранить проект\nCtrl+Shift+O — открыть проект\n"
            "Ctrl+0 — вписать в окно\nCtrl+1 — реальный размер\n"
            "Колесо — масштаб; средняя кнопка — перемещение\n"
            "Esc — отменить контур; ПКМ — завершить контур"))

    def _build_toolbar(self):
        self._toolbar_captions = {}
        labels = {"auto": ("Извлечь спрайты", "Убрать фон → PNG"),
                  "atlas": ("Собрать атлас", "Спрайты на одном листе"),
                  "shape": ("Вырезать вручную", "Рамка, многоугольник, лассо"),
                  "grid": ("Нарезать по сетке", "Ровные кадры и тайлы"),
                  "tiletest": ("Проверить тайл", "Есть ли видимые стыки?"),
                  "resize": ("Изменить размер", "Сразу для папки файлов")}
        for name in ("auto", "atlas", "shape", "grid", "tiletest", "resize"):
            if name in ("auto", "shape"):
                tk.Label(self._toolbar, text="ДЛЯ ИИ-СПРАЙТОВ" if name == "auto" else "ДРУГИЕ ИНСТРУМЕНТЫ",
                         bg=self.palette.TOOL_BG, fg=self.palette.FG2,
                         font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, padx=10, pady=(16, 6))
            f = tk.Frame(self._toolbar, bg=self.palette.TOOL_BG, cursor="hand2")
            f.pack(fill=tk.X, pady=2, padx=2)
            btn = SoftButton(f, text=labels[name][0],
                            command=lambda n=name: self._tool_set(n),
                            bg=self.palette.TOOL_BG, fg=self.palette.FG, font=("Segoe UI", 10), height=38)
            btn.pack(fill=tk.X)
            self._tip(btn, labels[name][1])
            caption = tk.Label(f, text=labels[name][1], bg=self.palette.TOOL_BG, fg=self.palette.FG2,
                               font=("Segoe UI", 8), wraplength=150, justify=tk.LEFT)
            caption.pack(anchor=tk.W, padx=10, pady=(0, 5))
            caption.bind("<Button-1>", lambda _, n=name: self._tool_set(n))
            self._toolbar_captions[name] = caption
            self._tool_btns[name] = btn
        self._toolbar.bind("<Configure>", self._layout_toolbar)

    def _layout_toolbar(self, event):
        compact = event.height < 500
        for name, caption in self._toolbar_captions.items():
            if compact and name not in ("auto", "atlas"):
                caption.pack_forget()
            elif not caption.winfo_manager():
                caption.pack(anchor=tk.W, padx=10, pady=(0, 5), after=self._tool_btns[name])

    # ══════════════════════════════════════════════════════════════════
    #  TOOL SWITCHING
    # ══════════════════════════════════════════════════════════════════

    def _tool_set(self, name):
        self._background_picking = False
        if self.tool == "atlas":
            self._atlas_excluded = self.excluded
        else:
            self._sprite_excluded = self.excluded
        self.excluded = getattr(self, "_atlas_excluded" if name == "atlas" else "_sprite_excluded", set())
        self.tool = name
        for n, btn in self._tool_btns.items():
            btn.config(bg=self.palette.GRN if n == name else self.palette.TOOL_BG, fg=self.palette.ACC if n == name else self.palette.FG2)
        self._rebuild_props()
        self._rebind_canvas(name)
        self._props_scroll.yview_moveto(0)
        hints = {
            "auto": "Сравните оригинал и результат. Светлый или тёмный фон просмотра помогает проверить края.",
            "shape": "Тяните для выделения • ПКМ — завершить контур • Esc — отменить текущий контур",
            "grid": "Задайте размер тайла или число ячеек, затем добавьте результат в спрайты",
            "atlas": "Клик — исключить ячейку • Перетаскивание — изменить порядок",
            "tiletest": "Тяните выделение слева; справа — проверка стыков тайла",
            "resize": "Выберите папку, размер и место сохранения в панели справа",
        }
        self._tool_hint.set(hints[name] + "\nКолесо — масштаб • Средняя кнопка — перемещение")
        self._view_title.config(text="Атлас текстур" if name == "atlas" else
                                "Проверка бесшовности" if name == "tiletest" else
                                "Пакетное изменение размеров" if name == "resize" else "Исходное изображение")
        if name == "auto":
            self._preview_bar.pack(fill=tk.X, before=self._canvas)
            self._auto_footer.pack(side=tk.BOTTOM, fill=tk.X, before=self._props_scroll)
        else:
            self._preview_bar.pack_forget()
            self._auto_footer.pack_forget()
        if name != "atlas":
            self._tray_refresh()
        self._cv_draw()

    def _save_current(self):
        actions = {"auto": self._auto_save, "shape": self._sh_save,
                   "grid": self._grid_save, "atlas": self._atlas_save,
                   "tiletest": self._tc_save, "resize": self._resize_run}
        actions[self.tool]()

    def _rebuild_props(self):
        for f in self._panels.values():
            f.pack_forget()
        self._panels[self.tool].pack(fill=tk.BOTH, expand=True)
        fname = (os.path.basename(self.src_path) if self.src_path
                 else ("из буфера" if self.src_img is not None else "Файл не выбран"))
        if self.tool == "atlas" and getattr(self, "_atlas_imported", False):
            fname = f"Готовых спрайтов: {len(self._atlas_raws)}"
        if self.tool in self._src_lbls:
            self._src_lbls[self.tool].config(text=fname)
        if self.tool in self._outdir_lbls:
            self._outdir_lbls[self.tool].config(text=self.outdir or "Папка не выбрана")
        if self.tool == "auto":
            self._auto_run()
        elif self.tool == "grid":
            self._grid_update()
        elif self.tool == "atlas" and (self.src_img is not None or getattr(self, "_atlas_imported", False)):
            self._atlas_update()

    def _rebind_canvas(self, name):
        cv = self._canvas
        # unbind all tool-specific
        for seq in ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>",
                    "<ButtonPress-3>", "<Motion>"):
            try:
                cv.unbind(seq)
            except Exception:
                pass
        self._bind_canvas_common()
        if name == "shape":
            cv.config(cursor="crosshair")
            cv.bind("<ButtonPress-1>",   self._sh_press)
            cv.bind("<B1-Motion>",       self._sh_drag)
            cv.bind("<ButtonRelease-1>", self._sh_release)
            cv.bind("<ButtonPress-3>",   self._sh_finish)
            cv.bind("<Motion>",          self._sh_move)
        elif name == "tiletest":
            cv.config(cursor="fleur")
            cv.bind("<ButtonPress-1>",   self._tc_press)
            cv.bind("<B1-Motion>",       self._tc_drag)
            cv.bind("<ButtonRelease-1>", self._tc_release)
        elif name == "atlas":
            cv.config(cursor="fleur")
            cv.bind("<ButtonPress-1>",   self._atl_press)
            cv.bind("<B1-Motion>",       self._atl_drag)
            cv.bind("<ButtonRelease-1>", self._atl_release)
        else:
            cv.config(cursor="crosshair" if name == "auto" and self._mask_tool.get() != "pan" else "fleur")
            cv.bind("<ButtonPress-1>",   self._auto_canvas_press if name == "auto" else self._cv_pan_press)
            cv.bind("<B1-Motion>",       self._auto_canvas_drag if name == "auto" else self._cv_pan_drag)
            cv.bind("<ButtonRelease-1>", self._auto_canvas_release if name == "auto" else self._cv_pan_release)
            if name == "auto":
                cv.bind("<Motion>", self._auto_canvas_hover)

    def _bind_canvas_common(self):
        cv = self._canvas
        cv.bind("<Configure>",    lambda _: self._cv_draw())
        cv.bind("<MouseWheel>",   self._cv_wheel)
        cv.bind("<Button-4>",     self._cv_wheel)
        cv.bind("<Button-5>",     self._cv_wheel)
        cv.bind("<ButtonPress-2>",   self._cv_pan_press)
        cv.bind("<B2-Motion>",       self._cv_pan_drag)
        cv.bind("<ButtonRelease-2>", self._cv_pan_release)
        cv.bind("<Leave>", lambda _: cv.delete("mask_cursor"))

    # ══════════════════════════════════════════════════════════════════
    #  CANVAS ZOOM/PAN
    # ══════════════════════════════════════════════════════════════════

    def _cv_wheel(self, e):
        factor = 1.15 if (getattr(e, "delta", 0) > 0 or e.num == 4) else 1/1.15
        cw = self._canvas.winfo_width() or 800
        ch = self._canvas.winfo_height() or 600
        if self.tool == "atlas" and self._atlas_vis:
            vis = self._atlas_vis
            fit = min(cw/vis.width, ch/vis.height)
            old = fit * self._cv_zoom
            ix = (e.x - self._cv_img_ox) / old
            iy = (e.y - self._cv_img_oy) / old
            self._cv_zoom = max(0.05, min(30.0, self._cv_zoom * factor))
            ns = fit * self._cv_zoom
            self._cv_view_x = int(e.x - ix*ns - (cw - int(vis.width*ns))//2)
            self._cv_view_y = int(e.y - iy*ns - (ch - int(vis.height*ns))//2)
        elif self.tool == "tiletest" and self.src_img is not None:
            pil = self._cv2pil(self.src_img)
            if pil is None:
                return
            iw, ih = pil.size
            half = cw // 2 - 1
            fit = min(half/iw, ch/ih)
            old = fit * self._tc_zoom
            ix = (e.x - self._tc_ox) / old
            iy = (e.y - self._tc_oy) / old
            self._tc_zoom = max(0.05, min(30.0, self._tc_zoom * factor))
            ns = fit * self._tc_zoom
            self._tc_vx = int(e.x - ix*ns - (half - int(iw*ns))//2)
            self._tc_vy = int(e.y - iy*ns - (ch - int(ih*ns))//2)
            if hasattr(self, "_tc_zoom_lbl"):
                self._tc_zoom_lbl.config(text=f"{int(self._tc_zoom*100)}%")
        elif self.src_img is not None:
            pil = self._cv2pil(self.src_img)
            if pil is None:
                return
            iw, ih = pil.size
            fit = min(cw/iw, ch/ih)
            old = fit * self._cv_zoom
            ix = (e.x - self._cv_img_ox) / old
            iy = (e.y - self._cv_img_oy) / old
            self._cv_zoom = max(0.05, min(30.0, self._cv_zoom * factor))
            ns = fit * self._cv_zoom
            self._cv_view_x = int(e.x - ix*ns - (cw - int(iw*ns))//2)
            self._cv_view_y = int(e.y - iy*ns - (ch - int(ih*ns))//2)
        self._cv_draw()

    def _cv_pan_press(self, e):
        self._canvas.focus_set()
        if self.tool == "tiletest":
            self._tc_pan0 = (e.x, e.y, self._tc_vx, self._tc_vy)
        else:
            self._cv_pan0 = (e.x, e.y, self._cv_view_x, self._cv_view_y)

    def _cv_pan_drag(self, e):
        if self.tool == "tiletest" and self._tc_pan0:
            sx, sy, vx0, vy0 = self._tc_pan0
            self._tc_vx = vx0 + (e.x - sx)
            self._tc_vy = vy0 + (e.y - sy)
        elif self._cv_pan0:
            sx, sy, vx0, vy0 = self._cv_pan0
            self._cv_view_x = vx0 + (e.x - sx)
            self._cv_view_y = vy0 + (e.y - sy)
        self._cv_draw()

    def _cv_pan_release(self, _=None):
        self._cv_pan0 = None
        self._tc_pan0 = None

    def _cv_zoom_reset(self):
        self._cv_zoom = 1.0
        self._cv_view_x = 0
        self._cv_view_y = 0
        self._tc_zoom = 1.0
        self._tc_vx = 0
        self._tc_vy = 0
        self._cv_draw()

    def _cv_to_img(self, cx, cy):
        return (cx - self._cv_img_ox), (cy - self._cv_img_oy)

    # ══════════════════════════════════════════════════════════════════
    #  CANVAS DRAWING
    # ══════════════════════════════════════════════════════════════════

    def _cv_draw(self):
        self._welcome_panel.place_forget()
        if self.tool == "atlas":
            self._cv_draw_atlas()
        elif self.tool == "tiletest":
            self._cv_draw_tiletest()
        elif self.tool == "resize":
            self._cv_draw_resize()
        else:
            self._cv_draw_source()
        self._workflow_update()
        if self.tool == "auto":
            self._view_title.config(text="Результат извлечения" if self.src_img is not None and self._background_preview.get()
                                    and not self._background_picking else "Исходная картинка")
        image = (None if self.tool == "resize" else
                 self._atlas_vis if self.tool == "atlas" else self._cv2pil(self.src_img))
        if image is None:
            self._zoom_var.set("—")
        else:
            width = self._canvas.winfo_width()
            if self.tool == "tiletest":
                width = width // 2 - 1
            fit = min(width / image.width, self._canvas.winfo_height() / image.height)
            zoom = self._tc_zoom if self.tool == "tiletest" else self._cv_zoom
            self._zoom_var.set(f"{fit * zoom * 100:.0f}%")

    def _cv_draw_resize(self):
        cv = self._canvas
        cv.delete("all")
        width, height = cv.winfo_width(), cv.winfo_height()
        files = getattr(self, "_resize_preview_files", [])
        self._status_var.set("Пакетная обработка • Результаты сохраняются в отдельные файлы")
        if not files:
            cv.create_text(width//2, height//2-24, text="Изменение размеров файлов",
                           fill=self.palette.FG, font=("Segoe UI", 20), width=max(200, width-40))
            cv.create_text(width//2, height//2+26,
                           text="Выберите папку с изображениями в панели справа.\nЗадайте размер и место сохранения копий.",
                           fill=self.palette.FG2, font=("Segoe UI", 11), justify=tk.CENTER, width=max(200, width-40))
            return
        cv.create_text(24, 28, anchor=tk.W, text=f"Изображения в папке: {len(files)}",
                       fill=self.palette.FG, font=("Segoe UI", 16))
        cv.create_text(24, 64, anchor=tk.W, text=self._resize_folder_var.get(),
                       fill=self.palette.FG2, font=("Segoe UI", 10), width=max(200, width-48))
        for index, path in enumerate(files[:max(1, (height-130)//32)]):
            cv.create_text(24, 112+index*32, anchor=tk.W,
                           text=f"{index+1:02d}    {os.path.basename(path)}", fill=self.palette.FG,
                           font=("Segoe UI", 11), width=max(200, width-48))

    def _cv_draw_source(self):
        cv = self._canvas
        cw = cv.winfo_width() or 800
        ch = cv.winfo_height() or 600
        cv.delete("all")
        if self.src_img is None:
            if self.tool == "auto":
                width = min(480, max(300, cw - 24))
                self._welcome_copy.config(wraplength=width - 30)
                self._welcome_panel.place(relx=.5, rely=.5, anchor=tk.CENTER, width=width)
                self._status_var.set("Начните с ИИ-картинки · PNG, JPEG, WebP · Можно перетащить файл или нажать Ctrl+V")
                return
            cv.create_text(cw//2, ch//2-26,
                text="Начните с изображения", fill=self.palette.FG, font=("Segoe UI", 20), justify=tk.CENTER)
            cv.create_text(cw//2, ch//2+24,
                text="Перетащите файл сюда или нажмите Ctrl+O\nCtrl+V — вставить из буфера • Двойной клик — открыть",
                fill=self.palette.FG2, font=("Segoe UI", 11), justify=tk.CENTER, width=max(200, cw-40))
            self._status_var.set("Готов к работе")
            return
        preview = (self._auto_rgba_cache if self.tool == "auto" and
                   self._background_preview.get() and not self._background_picking
                   and self._auto_rgba_cache is not None else self.src_img)
        pil = self._cv2pil(preview)
        if pil is None:
            return
        iw, ih = pil.size
        fit = min(cw/iw, ch/ih)
        scale = fit * self._cv_zoom
        nw = max(1, int(iw*scale))
        nh = max(1, int(ih*scale))
        self._cv_img_ox = (cw-nw)//2 + self._cv_view_x
        self._cv_img_oy = (ch-nh)//2 + self._cv_view_y
        resamp = self._resampling()
        disp = pil.resize((nw, nh), resamp)
        # Draw tool overlays on the PIL image
        disp = self._cv_overlay(disp, scale)
        if disp.mode == "RGBA":
            if self.tool == "auto" and self._preview_bg.get() != "Клетка":
                checker = Image.new("RGBA", (nw, nh), "#f8f8f8" if self._preview_bg.get() == "Светлый" else "#171c24")
            else:
                checker = self._tc_checker(nw, nh, cs=12).convert("RGBA")
            disp = Image.alpha_composite(checker, disp)
        self._cv_photo = ImageTk.PhotoImage(disp)
        cv.create_image(self._cv_img_ox, self._cv_img_oy, anchor=tk.NW, image=self._cv_photo)
        # status
        self._status_var.set(f"{iw}×{ih} px  |  {os.path.basename(self.src_path) if self.src_path else 'Из буфера'}")

    def _cv_overlay(self, disp, scale):
        """Draw tool-specific overlays on the display PIL image."""
        if self.tool == "auto" and self._mask_marks is not None and self._mask_tool.get() != "pan":
            overlay = np.zeros((*self._mask_marks.shape, 4), np.uint8)
            overlay[self._mask_marks == 1] = (70, 190, 100, 100)
            overlay[self._mask_marks == 2] = (220, 70, 55, 100)
            layer = Image.fromarray(overlay).resize(disp.size, Image.Resampling.NEAREST)
            disp = Image.alpha_composite(disp.convert("RGBA"), layer)
        draw = ImageDraw.Draw(disp)
        if self.tool == "auto" and self._background_preview.get() and not self._background_picking:
            if self.src_img is not None and hasattr(self, "_auto_contours_cache"):
                for c in self._auto_contours_cache:
                    x, y, w, h = cv2.boundingRect(c)
                    rx1 = int(x*scale)
                    ry1 = int(y*scale)
                    rx2 = int((x+w)*scale)
                    ry2 = int((y+h)*scale)
                    draw.rectangle([rx1, ry1, rx2, ry2], outline=self.palette.ACC, width=2)
        elif self.tool == "shape":
            for i, (pts, _) in enumerate(self._sh_sels):
                col = self._sh_colors[i % len(self._sh_colors)]
                sc = [(int(px*scale), int(py*scale)) for px, py in pts]
                if len(sc) >= 2:
                    draw.polygon(sc, outline=col)
                for p in sc:
                    draw.ellipse([p[0]-3, p[1]-3, p[0]+3, p[1]+3], fill=col)
            if self._sh_down and self._sh_cur:
                sc = [(int(px*scale), int(py*scale)) for px, py in self._sh_cur]
                if len(sc) >= 2:
                    draw.line(sc, fill="#a36b20", width=2)
        elif self.tool == "grid":
            if self.src_img is not None and hasattr(self, "_grid_tiles_cache"):
                for (x, y, tw, th) in self._grid_tiles_cache:
                    rx1 = int(x*scale)
                    ry1 = int(y*scale)
                    rx2 = int((x+tw)*scale)
                    ry2 = int((y+th)*scale)
                    draw.rectangle([rx1, ry1, rx2, ry2], outline=self.palette.ACC, width=1)
        return disp

    def _cv_draw_atlas(self):
        cv = self._canvas
        cw = cv.winfo_width() or 800
        ch = cv.winfo_height() or 600
        cv.delete("all")
        vis = self._atlas_vis
        if vis is None:
            cv.create_text(cw//2, ch//2,
                text="Откройте изображение (Файл → Открыть)\nатлас будет собран автоматически",
                fill=self.palette.FG2, font=("Segoe UI", 13), justify=tk.CENTER)
            return
        fit = min(cw/vis.width, ch/vis.height)
        scale = fit * self._cv_zoom
        nw = max(1, int(vis.width*scale))
        nh = max(1, int(vis.height*scale))
        self._cv_img_ox = (cw-nw)//2 + self._cv_view_x
        self._cv_img_oy = (ch-nh)//2 + self._cv_view_y
        resamp = Image.NEAREST if scale > 3 else Image.LANCZOS
        disp = vis.resize((nw, nh), resamp)
        self._cv_photo = ImageTk.PhotoImage(disp)
        cv.create_image(self._cv_img_ox, self._cv_img_oy, anchor=tk.NW, image=self._cv_photo)
        # info overlay
        info = f"{vis.width}×{vis.height}px  {self._atlas_cols_n}×{self._atlas_rows_n}  {self._atlas_cell_w}px/яч"
        cv.create_text(cw-8, ch-8, text=info, anchor=tk.SE, fill=self.palette.GOLD, font=("Segoe UI", 9, "bold"))
        self._status_var.set(f"Атлас: {vis.width}×{vis.height}  Зум: {int(self._cv_zoom*100)}%")

    def _cv_draw_tiletest(self):
        cv = self._canvas
        cw = cv.winfo_width() or 800
        ch = cv.winfo_height() or 600
        cv.delete("all")
        if self.src_img is None:
            cv.create_text(cw//2, ch//2,
                text="Откройте изображение для тайл-теста",
                fill=self.palette.FG2, font=("Segoe UI", 13), justify=tk.CENTER)
            return
        # Split canvas: left=source, right=preview
        half = cw // 2 - 1
        self._tc_draw_source(half, ch)
        self._tc_draw_preview(half, ch, half + 2)
        cv.create_line(half+1, 0, half+1, ch, fill=self.palette.BTN, width=2)

    def _tc_draw_source(self, cw, ch):
        pil = self._cv2pil(self.src_img)
        if pil is None:
            return
        iw, ih = pil.size
        fit = min(cw/iw, ch/ih)
        scale = fit * self._tc_zoom
        nw = max(1, int(iw*scale))
        nh = max(1, int(ih*scale))
        self._tc_scale = scale
        self._tc_ox = (cw-nw)//2 + self._tc_vx
        self._tc_oy = (ch-nh)//2 + self._tc_vy
        bg = self._tc_checker(nw, nh)
        scaled = pil.resize((nw, nh), Image.LANCZOS)
        bg.paste(scaled.convert("RGB"), mask=scaled.split()[3])
        draw = ImageDraw.Draw(bg)
        sz = self._tc_size_var.get() if hasattr(self, "_tc_size_var") else 64
        for gx in range(0, iw+1, sz):
            cx2 = int(gx*scale)
            if 0 <= cx2 <= nw:
                draw.line([(cx2,0),(cx2,nh-1)], fill=self.palette.BORDER, width=1)
        for gy in range(0, ih+1, sz):
            cy2 = int(gy*scale)
            if 0 <= cy2 <= nh:
                draw.line([(0,cy2),(nw-1,cy2)], fill=self.palette.BORDER, width=1)
        sw = self._tc_sel_w.get() if hasattr(self, "_tc_sel_w") else sz
        sh = self._tc_sel_h.get() if hasattr(self, "_tc_sel_h") else sz
        if iw >= sw and ih >= sh:
            rx = int(self._tc_cx * scale)
            ry = int(self._tc_cy * scale)
            rw = max(2, int(sw*scale))
            rh = max(2, int(sh*scale))
            draw.rectangle([rx, ry, rx+rw-1, ry+rh-1], outline="#a36b20", width=2)
            draw.rectangle([rx+2, ry+2, rx+rw-3, ry+rh-3], outline="#ffffff", width=1)
        ph = ImageTk.PhotoImage(bg)
        self._tc_src_ph = ph
        self._canvas.create_image(self._tc_ox, self._tc_oy, anchor=tk.NW, image=ph)
        self._canvas.create_text(cw//2, ch-12, text="Исходное — тяните для смещения",
                                  fill=self.palette.FG2, font=("Segoe UI", 8, "italic"))

    def _tc_draw_preview(self, cw, ch, ox):
        pil = self._cv2pil(self.src_img)
        if pil is None:
            return
        iw, ih = pil.size
        sw = self._tc_sel_w.get() if hasattr(self, "_tc_sel_w") else 64
        sh = self._tc_sel_h.get() if hasattr(self, "_tc_sel_h") else 64
        sz = self._tc_size_var.get() if hasattr(self, "_tc_size_var") else 64
        n  = self._tc_grid_var.get() if hasattr(self, "_tc_grid_var") else 3
        if iw < sw or ih < sh:
            self._canvas.create_text(ox + cw//2, ch//2,
                text=f"Изображение меньше {sw}×{sh}", fill=self.palette.RED, font=("Segoe UI", 11))
            return
        x = max(0, min(self._tc_cx, iw-sw))
        y = max(0, min(self._tc_cy, ih-sh))
        crop = pil.crop((x, y, x+sw, y+sh))
        tile = crop.resize((sz, sz), Image.LANCZOS) if (sw != sz or sh != sz) else crop
        gp = sz*n
        checker = self._tc_checker(gp, gp, cs=max(4, sz//8))
        grid = checker.convert("RGBA")
        for row in range(n):
            for col in range(n):
                grid.paste(tile, (col*sz, row*sz), tile)
        s  = min(cw/gp, ch/gp)
        nw2 = max(1, int(gp*s))
        nh2 = max(1, int(gp*s))
        resamp = Image.NEAREST if sz <= 64 else Image.LANCZOS
        disp = grid.resize((nw2, nh2), resamp)
        ph2 = ImageTk.PhotoImage(disp)
        self._tc_prev_ph = ph2
        px = ox + (cw-nw2)//2
        py = (ch-nh2)//2
        self._canvas.create_image(px, py, anchor=tk.NW, image=ph2)
        self._canvas.create_text(ox + cw//2, ch-12,
            text=f"Тайл {n}×{n} — видны стыки",
            fill=self.palette.FG2, font=("Segoe UI", 8, "italic"))

    def _tc_checker(self, w, h, cs=8):
        img  = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)
        for r in range((h+cs-1)//cs):
            for c in range((w+cs-1)//cs):
                col = self.palette.CHECKER_A if (r+c)%2==0 else self.palette.CHECKER_B
                x0, y0 = c*cs, r*cs
                draw.rectangle([x0, y0, min(x0+cs,w)-1, min(y0+cs,h)-1], fill=col)
        return img

    # ══════════════════════════════════════════════════════════════════
    #  PROPS PANEL BUILDERS
    # ══════════════════════════════════════════════════════════════════

    def _background_controls(self, parent, title="Фон"):
        self._lbl(parent, title, bold=True).pack(anchor=tk.W)
        names = {"auto": "Авто", "solid": "Однотонный", "checker": "Нарисованная клеточка",
                 "alpha": "Без удаления фона"}
        mode = ttk.Combobox(parent, state="readonly", textvariable=self._background_mode_label,
                            values=list(names.values()), width=25)
        mode.pack(fill=tk.X, pady=(3, 2))
        def select(_):
            self._background_mode.set(next(key for key, label in names.items() if label == mode.get()))
            if self._background_mode.get() != "solid":
                self._background_rgb = None
            self._background_changed()
        mode.bind("<<ComboboxSelected>>", select)
        self._tip(mode, "Начните с «Авто». Если фон остался, выберите его тип или укажите цвет пипеткой. «Без удаления фона» оставляет только ручную правку.")
        label = self._lbl(parent, "", color=self.palette.FG2)
        label.pack(anchor=tk.W, pady=(2, 4))
        self._background_labels.append(label)
        self._background_update_labels()
        row = tk.Frame(parent, bg=self.palette.BG)
        row.pack(fill=tk.X)
        self._btn(row, "Цвет…", self._background_choose).pack(side=tk.LEFT, expand=True, fill=tk.X)
        pipette = self._btn(row, "Пипетка", self._background_start_pick, state=tk.DISABLED)
        pipette.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
        self._background_pipettes.append(pipette)
        self._btn(row, "Авто", self._background_auto).pack(side=tk.LEFT, expand=True, fill=tk.X)

    def _sprite_options(self, parent, callback, show_group=True):
        row = tk.Frame(parent, bg=self.palette.BG)
        row.pack(fill=tk.X, pady=(3, 0))
        for text, value in (("Лист спрайтов", "objects"), ("Один объект", "single")):
            SoftRadio(row, text=text, variable=self._auto_object_mode, value=value,
                      bg=self.palette.BG, fg=self.palette.FG, command=callback).pack(side=tk.LEFT, expand=True)
        if show_group:
            self._sprite_group_controls(parent, callback)

    def _sprite_group_controls(self, parent, callback):
        row = tk.Frame(parent, bg=self.palette.BG)
        row.pack(fill=tk.X, pady=3)
        self._lbl(row, "Объединить близкие части:", size=9).pack(side=tk.LEFT)
        editor = self._spinbox(row, self._auto_group_gap, 0, 64, cmd=callback)
        editor.pack(side=tk.LEFT, padx=3)
        self._tip(editor, "Расстояние в пикселях. Помогает вернуть отдельное оружие, волосы и эффекты к персонажу. Объединение имеет приоритет над разделением.")
        self._lbl(parent, "0 — отдельно. Больше — близкие фрагменты станут одним спрайтом.",
                  color=self.palette.FG2, size=9).pack(anchor=tk.W)

    def _edge_controls(self, parent, callback):
        smooth = SoftCheck(parent, text="Сгладить края и убрать цвет фона", variable=self._edge_smooth,
                           bg=self.palette.BG, fg=self.palette.FG, font=("Segoe UI", 9), command=callback)
        smooth.pack(anchor=tk.W, pady=(6, 3))
        self._tip(smooth, "Смягчает контур и очищает пограничные пиксели от примеси выбранного фона. Работает при сохранении, в лотке и атласе. Исходная прозрачность и режим «Пиксель-арт» сохраняют свои края.")
        row = tk.Frame(parent, bg=self.palette.BG)
        row.pack(fill=tk.X)
        self._lbl(row, "Сжать край, пикс:", size=9).pack(side=tk.LEFT)
        editor = self._spinbox(row, self._edge_choke, 0, 6, cmd=callback)
        editor.pack(side=tk.LEFT, padx=4)
        self._tip(editor, "Осталась кайма? Включите сглаживание и попробуйте 1–2 пикселя. Большие значения обрезают тонкие детали. 0 — без сжатия. Кисть «Оставить» защищает отмеченные пиксели.")

    def _sprite_output_controls(self, parent, callback):
        SoftCheck(parent, text="Пиксель-арт: чёткие пиксели", variable=self._pixel_art,
                  bg=self.palette.BG, fg=self.palette.FG, command=callback).pack(anchor=tk.W, pady=3)
        self._edge_controls(parent, callback)
        SoftCheck(parent, text="Цвет краёв в прозрачных полях", variable=self._edge_bleed,
                  bg=self.palette.BG, fg=self.palette.FG, command=callback).pack(anchor=tk.W, pady=3)
        row = tk.Frame(parent, bg=self.palette.BG)
        row.pack(fill=tk.X, pady=3)
        self._lbl(row, "Поля вокруг спрайта, пикс:", size=9).pack(side=tk.LEFT)
        self._spinbox(row, self._export_padding, 0, 64, cmd=callback).pack(side=tk.LEFT, padx=3)

    def _resampling(self):
        return Image.Resampling.NEAREST if self._pixel_art.get() else Image.Resampling.LANCZOS

    def _background_update_labels(self):
        color = self._background_rgb
        self._background_mode_label.set({"auto": "Авто", "solid": "Однотонный",
                                         "checker": "Нарисованная клеточка",
                                         "alpha": "Без удаления фона"}[self._background_mode.get()])
        text = ({"auto": "Авто: прозрачность, клетка или цвет",
                 "solid": "Цвет фона оценивается по краям",
                 "checker": "Для регулярной клетки. Искажённый рисунок исправьте кистями.",
                 "alpha": "Исходное изображение. Фон можно убрать кистями."}[self._background_mode.get()]
                if color is None else "Выбран: #{:02X}{:02X}{:02X}".format(*color))
        for label in self._background_labels:
            label.config(text=text)

    def _background_changed(self):
        self._background_picking = False
        self._background_update_labels()
        self._rebind_canvas(self.tool)
        self._auto_run()
        if self.tool == "atlas":
            self._atlas_update()

    def _background_auto(self):
        self._background_rgb = None
        self._background_mode.set("auto")
        self._background_changed()

    def _background_choose(self):
        initial = "#{:02x}{:02x}{:02x}".format(*(self._background_rgb or (255, 255, 255)))
        rgb, _ = colorchooser.askcolor(color=initial, parent=self.root, title="Цвет фона")
        if rgb is not None:
            self._background_rgb = tuple(round(channel) for channel in rgb)
            self._background_mode.set("solid")
            self._background_changed()

    def _background_start_pick(self):
        if self.src_img is None:
            messagebox.showinfo("Нет изображения", "Сначала откройте изображение")
            return
        self._tool_set("auto")
        self._mask_tool.set("pan")
        self._background_picking = True
        self._cv_pan0 = None
        self._canvas.config(cursor="crosshair")
        self._cv_draw()
        self._status_var.set("Нажмите на фон исходного изображения • Esc — отмена")

    def _cancel_action(self):
        if self._mask_last is not None:
            self._mask_revision += 1
        self._background_picking = False
        self._mask_tool.set("pan")
        self._mask_last = None
        self._rebind_canvas(self.tool)
        if self.tool == "auto":
            self._auto_run()
        self._sh_reset()

    def _auto_canvas_press(self, event):
        if not self._background_picking:
            if self._mask_tool.get() != "pan" and self.src_img is not None:
                self._mask_begin(event)
                return
            return self._cv_pan_press(event)
        if self.src_img is None:
            return
        ih, iw = self.src_img.shape[:2]
        scale = min(self._canvas.winfo_width() / iw,
                    self._canvas.winfo_height() / ih) * self._cv_zoom
        fx = (event.x - self._cv_img_ox) / scale
        fy = (event.y - self._cv_img_oy) / scale
        if not (0 <= fx < iw and 0 <= fy < ih):
            return
        pixel = self.src_img[int(fy), int(fx)]
        if np.ndim(pixel) and len(pixel) == 4 and pixel[3] == 0:
            self._status_var.set("Здесь уже прозрачно. Выберите непрозрачный участок фона.")
            return
        self._background_rgb = (tuple(int(c) for c in pixel[:3][::-1]) if np.ndim(pixel)
                                else (int(pixel),) * 3)
        self._background_mode.set("solid")
        self._background_changed()

    def _mask_select(self):
        self._background_picking = False
        self._mask_last = None
        self._rebind_canvas(self.tool)
        self._cv_draw()

    def _mask_point(self, event):
        if self.src_img is None:
            return None
        h, w = self.src_img.shape[:2]
        scale = min(self._canvas.winfo_width() / w, self._canvas.winfo_height() / h) * self._cv_zoom
        x = (event.x - self._cv_img_ox) / scale
        y = (event.y - self._cv_img_oy) / scale
        return (int(x), int(y)) if 0 <= x < w and 0 <= y < h else None

    def _mask_snapshot(self):
        if self._mask_marks is None:
            self._mask_marks = np.zeros(self.src_img.shape[:2], np.uint8)
        self._mask_history.append(cv2.imencode(".png", self._mask_marks)[1].tobytes())
        self._mask_history = self._mask_history[-20:]

    def _mask_begin(self, event):
        point = self._mask_point(event)
        if point is None:
            return
        self._mask_snapshot()
        self._mask_last = point
        self._mask_paint(point)

    def _mask_paint(self, point):
        value = 1 if self._mask_tool.get() == "keep" else 2
        radius = self._mask_radius.get()
        if self._mask_last is not None:
            cv2.line(self._mask_marks, self._mask_last, point, value, radius * 2 + 1)
        cv2.circle(self._mask_marks, point, radius, value, -1)
        self._mask_last = point
        self._cv_draw()

    def _auto_canvas_drag(self, event):
        if self._mask_last is not None:
            point = self._mask_point(event)
            if point is not None:
                self._mask_paint(point)
                self._auto_canvas_hover(event, point)
        elif not self._background_picking and self._mask_tool.get() == "pan":
            self._cv_pan_drag(event)

    def _auto_canvas_hover(self, event, point=None):
        self._canvas.delete("mask_cursor")
        if self._background_picking or self._mask_tool.get() == "pan":
            return
        if point is None and self._mask_point(event) is None:
            return
        h, w = self.src_img.shape[:2]
        scale = min(self._canvas.winfo_width() / w, self._canvas.winfo_height() / h) * self._cv_zoom
        radius = self._mask_radius.get() * scale
        self._canvas.create_oval(event.x - radius, event.y - radius, event.x + radius, event.y + radius,
                                 outline=self.palette.ACC if self._mask_tool.get() == "keep" else self.palette.RED_FG,
                                 width=2, tags="mask_cursor")

    def _auto_canvas_release(self, event):
        if self._mask_last is not None:
            self._mask_last = None
            self._mask_revision += 1
            self._auto_run()
        self._cv_pan_release(event)

    def _mask_undo(self):
        if self._mask_history:
            self._mask_marks = cv2.imdecode(np.frombuffer(self._mask_history.pop(), np.uint8), cv2.IMREAD_GRAYSCALE)
            self._mask_revision += 1
            self._auto_run()

    def _mask_clear(self):
        if self.src_img is not None:
            self._mask_snapshot()
            self._mask_marks.fill(0)
            self._refined_rgba = None
            self._refined_key = None
            self._mask_revision += 1
            self._auto_run()

    def _refine_start(self):
        if self.src_img is None or self._refine_running:
            return
        self._auto_run()
        image = self.src_img.copy()
        rgba = self._extract_rgba(self.src_img, self._auto_thresh.get(), process_edges=False)
        marks = self._mask_marks.copy() if self._mask_marks is not None else None
        key = self._background_signature(self.src_img, self._auto_thresh.get())
        self._refine_running = True
        self._refine_btn.config(state=tk.DISABLED)
        self._refine_status.config(text="Уточняю контур…")
        result = []
        def worker():
            try:
                result.append((refine_foreground(image, rgba, marks), None))
            except Exception as error:
                # Always complete the job, including native-library/allocation
                # failures, so the UI cannot remain disabled indefinitely.
                result.append((None, str(error) or type(error).__name__))
        threading.Thread(target=worker, daemon=True).start()
        def poll():
            if not result:
                self.root.after(80, poll)
                return
            self._refine_running = False
            self._refine_btn.config(state=tk.NORMAL)
            refined, error = result[0]
            if self.src_img is None or key != self._background_signature(self.src_img, self._auto_thresh.get()):
                self._refine_status.config(text="Настройки изменились. Повторите уточнение.")
            elif error:
                self._refine_status.config(text="Не удалось уточнить. Добавьте отметки кистями.")
                messagebox.showinfo("Уточнение контура", error)
            else:
                self._refined_rgba, self._refined_key = refined, key
                self._refine_status.config(text="Контур уточнён. Проверьте мелкие детали.")
                self._auto_run()
        self.root.after(80, poll)

    def _build_props_auto(self, parent=None):
        p = parent if parent is not None else self._props
        self._lbl(p, "Спрайты из ИИ-картинки", bold=True, size=12).pack(anchor=tk.W, pady=(0,8))
        self._source_controls(p, "auto")
        self._next_step_var = tk.StringVar(value="Откройте картинку, чтобы начать.")
        tk.Label(p, textvariable=self._next_step_var, bg=self.palette.GRN, fg=self.palette.FG,
                 font=("Segoe UI", 9), wraplength=286, justify=tk.LEFT, padx=8, pady=8).pack(fill=tk.X, pady=(4, 10))
        self._lbl(p, "1. Что на картинке?", bold=True).pack(anchor=tk.W)
        preset = ttk.Combobox(p, state="readonly", textvariable=self._task_preset,
                              values=("Несколько спрайтов на листе", "Один персонаж или предмет", "Пиксель-арт: лист спрайтов"))
        preset.pack(fill=tk.X, pady=(4, 12))
        preset.bind("<<ComboboxSelected>>", self._apply_preset)
        self._tip(preset, "«Один персонаж» сохранит отдельные части и частицы вместе. «Пиксель-арт» включает масштабирование без сглаживания. Ручные правки сохраняются.")
        self._background_controls(p, "2. Уберите фон")
        self._lbl(p, "Чувствительность к фону:").pack(anchor=tk.W, pady=(6, 0))
        self._auto_thresh = SoftSlider(p, from_=0, to=100, orient=tk.HORIZONTAL,
                                     bg=self.palette.BG, fg=self.palette.FG, troughcolor=self.palette.BTN, highlightthickness=0)
        self._auto_thresh.set(10)
        self._auto_thresh.pack(fill=tk.X)
        self._auto_thresh.bind("<ButtonRelease-1>", lambda _: self._auto_run())
        self._tip(self._auto_thresh, "Больше — удаляется больше похожих оттенков фона. Если пропадают детали, уменьшите значение. Изменения видны после отпускания ползунка.")
        quick_fix = tk.Frame(p, bg=self.palette.BG)
        quick_fix.pack(fill=tk.X, pady=3)
        keep = self._btn(quick_fix, "Вернуть деталь", lambda: self._focus_brush("keep"), font_size=9, state=tk.DISABLED)
        keep.pack(side=tk.LEFT, expand=True, fill=tk.X)
        remove = self._btn(quick_fix, "Стереть фон", lambda: self._focus_brush("remove"), font_size=9, state=tk.DISABLED)
        remove.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0))
        self._quick_brush_buttons.extend((keep, remove))
        self._auto_cnt_lbl = self._lbl(p, "Найдено: 0", color=self.palette.GOLD, bold=True)
        self._auto_cnt_lbl.pack(anchor=tk.W, pady=6)
        details = self._section(p, "Разделение и мелкие части", expanded=False)
        self._lbl(details, "Не брать объекты меньше, пикс:").pack(anchor=tk.W, pady=(8,0))
        self._auto_min = SoftSlider(details, from_=1, to=150, orient=tk.HORIZONTAL,
                                  bg=self.palette.BG, fg=self.palette.FG, troughcolor=self.palette.BTN, highlightthickness=0)
        self._auto_min.set(12)
        self._auto_min.pack(fill=tk.X)
        self._auto_min.bind("<ButtonRelease-1>", lambda _: self._auto_run())
        self._sprite_group_controls(details, self._auto_run)
        self._lbl(details, "Разделить слипшиеся спрайты, пикс:").pack(anchor=tk.W, pady=(8,0))
        self._auto_sep = SoftSlider(details, from_=0, to=150, orient=tk.HORIZONTAL,
                                  bg=self.palette.BG, fg=self.palette.FG, troughcolor=self.palette.BTN, highlightthickness=0)
        self._auto_sep.set(0)
        self._auto_sep.pack(fill=tk.X)
        self._auto_sep.bind("<ButtonRelease-1>", lambda _: self._auto_run())
        masks = self._section(p, "Поправить кистями", expanded=False)
        row = tk.Frame(masks, bg=self.palette.BG)
        row.pack(fill=tk.X)
        for text, value in (("Обзор", "pan"), ("Оставить", "keep"), ("Удалить", "remove")):
            SoftRadio(row, text=text, variable=self._mask_tool, value=value,
                      bg=self.palette.BG, fg=self.palette.FG, command=self._mask_select).pack(side=tk.LEFT, expand=True)
        row = tk.Frame(masks, bg=self.palette.BG)
        row.pack(fill=tk.X)
        self._lbl(row, "Радиус кисти, пикс:").pack(side=tk.LEFT)
        self._spinbox(row, self._mask_radius, 1, 100).pack(side=tk.LEFT, padx=4)
        self._lbl(masks, "Рисуйте по объекту или фону. «Оставить» защищает детали при уточнении. Esc — обзор.",
                  color=self.palette.FG2, size=9).pack(anchor=tk.W, pady=4)
        row = tk.Frame(masks, bg=self.palette.BG)
        row.pack(fill=tk.X)
        self._mask_undo_btn = self._btn(row, "Отменить мазок", self._mask_undo, state=tk.DISABLED)
        self._mask_undo_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self._mask_clear_btn = self._btn(row, "Сброс маски", self._mask_clear, state=tk.DISABLED)
        self._mask_clear_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
        self._refine_btn = self._btn(masks, "Уточнить края автоматически", self._refine_start)
        self._refine_btn.pack(fill=tk.X, pady=4)
        self._refine_status = self._lbl(masks, "Уточнение отделяет похожий фон по цвету и границам.", color=self.palette.FG2, size=9)
        self._refine_status.pack(anchor=tk.W)
        self._sep(p)
        p = self._section(p, "Размер и края PNG", expanded=False)
        self._sprite_output_controls(p, self._auto_run)
        self._lbl(p, "Масштаб при сохранении:", bold=True).pack(anchor=tk.W, pady=(0,4))
        if not hasattr(self, "_auto_scale_mode"):
            self._auto_scale_mode = tk.StringVar(value="none")
            self._auto_scale_w = tk.IntVar(value=64)
            self._auto_scale_h = tk.IntVar(value=64)
        for txt, val in [("Не масштабировать", "none"),
                         ("По ширине", "w"),
                         ("По высоте", "h"),
                         ("По ширине и высоте", "both")]:
            SoftRadio(p, text=txt, variable=self._auto_scale_mode, value=val,
                           bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                           command=self._auto_scale_update).pack(anchor=tk.W)
        wf = tk.Frame(p, bg=self.palette.BG); wf.pack(fill=tk.X, pady=(4,0))
        self._lbl(wf, "Ширина:").pack(side=tk.LEFT)
        self._auto_scale_w_sb = self._spinbox(wf, self._auto_scale_w, 1, 4096, w=6)
        self._auto_scale_w_sb.pack(side=tk.LEFT, padx=4)
        self._lbl(wf, "пикс").pack(side=tk.LEFT)
        hf = tk.Frame(p, bg=self.palette.BG); hf.pack(fill=tk.X, pady=(2,0))
        self._lbl(hf, "Высота:").pack(side=tk.LEFT)
        self._auto_scale_h_sb = self._spinbox(hf, self._auto_scale_h, 1, 4096, w=6)
        self._auto_scale_h_sb.pack(side=tk.LEFT, padx=4)
        self._lbl(hf, "пикс").pack(side=tk.LEFT)
        self._auto_scale_update()
        self._sep(p)
        self._btn(p, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbls["auto"] = self._lbl(p, "Папка не выбрана", color=self.palette.FG2)
        self._outdir_lbls["auto"].pack(anchor=tk.W, pady=(3,0))

        self._auto_footer = tk.Frame(self._props_outer, bg=self.palette.BG2, padx=10, pady=8,
                                     highlightthickness=1, highlightbackground=self.palette.BORDER)
        self._auto_save_btn = self._btn(self._auto_footer, "Сохранить PNG…", self._auto_save, self.palette.ACC, h=2, state=tk.DISABLED)
        self._auto_save_btn.pack(fill=tk.X, pady=(0, 4))
        self._tip(self._auto_save_btn, "Каждый найденный спрайт сохранится отдельным PNG с прозрачностью. Исходную картинку можно продолжать редактировать.")
        secondary = tk.Frame(self._auto_footer, bg=self.palette.BG2)
        secondary.pack(fill=tk.X, pady=(0, 4))
        self._auto_add_btn = self._btn(secondary, "Добавить в нижнюю ленту", self._auto_add_to_tray, state=tk.DISABLED, font_size=9)
        self._auto_add_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self._tip(self._auto_add_btn, "Собирайте набор из нескольких картинок. В ленте можно исключить лишние спрайты, а затем сохранить выбранные.")
        more = self._btn(secondary, "Настройки…", self._show_advanced, font_size=9)
        more.pack(side=tk.LEFT, padx=(4, 0))
        self._tip(more, "Открыть размер и края PNG: сглаживание, кайма, пиксель-арт и прозрачные поля. Остальные настройки находятся в разделах этой панели.")
        row = tk.Frame(self._auto_footer, bg=self.palette.BG2)
        row.pack(fill=tk.X)
        self._btn(row, "Выбрать папку…", self._menu_choose_outdir, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X)
        self._open_export_btn = self._btn(row, "Открыть папку", self._open_export_folder, font_size=9, state=tk.DISABLED)
        self._open_export_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(4, 0))
        self._export_folder_var = tk.StringVar(value="При сохранении выберите папку для PNG")
        tk.Label(self._auto_footer, textvariable=self._export_folder_var, bg=self.palette.BG2, fg=self.palette.FG2,
                 font=("Segoe UI", 8), wraplength=290, justify=tk.LEFT).pack(anchor=tk.W, pady=(5, 0))

    def _build_props_shape(self, parent=None):
        p = parent if parent is not None else self._props
        self._lbl(p, "Вырезание фигур", bold=True, size=11).pack(anchor=tk.W, pady=(0,8))
        self._source_controls(p, "shape")
        self._sep(p)
        self._lbl(p, "Инструмент рисования:", bold=True).pack(anchor=tk.W, pady=(0,5))
        if not hasattr(self, "_sh_tool_var"):
            self._sh_tool_var = tk.StringVar(value="rect")
        for txt, val in [("Прямоугольник (тяни)", "rect"),
                         ("Многоугольник (клик→ПКМ)", "poly"),
                         ("Лассо (тяни→ПКМ)", "lasso")]:
            SoftRadio(p, text=txt, variable=self._sh_tool_var, value=val,
                           bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                           command=self._sh_reset).pack(anchor=tk.W)
        if not hasattr(self, "_sh_transp"):
            self._sh_transp = tk.BooleanVar(value=True)
        SoftCheck(p, text="Прозрачный фон при вырезании",
                       variable=self._sh_transp, bg=self.palette.BG, fg=self.palette.FG,
                       selectcolor=self.palette.BTN, activebackground=self.palette.BG).pack(anchor=tk.W, pady=(8,0))
        self._sep(p)
        self._lbl(p, "Выделения:", bold=True).pack(anchor=tk.W, pady=(0,4))
        lf = tk.Frame(p, bg=self.palette.INPUT, bd=0, highlightthickness=1, highlightbackground=self.palette.BORDER)
        lf.pack(fill=tk.BOTH)
        self._sh_lb = tk.Listbox(lf, bg=self.palette.INPUT, fg=self.palette.FG, selectbackground=self.palette.GRN,
                                  selectforeground=self.palette.FG, activestyle="none", selectborderwidth=0,
                                  height=5, font=("Segoe UI", 9), relief=tk.FLAT,
                                  highlightthickness=0)
        self._sh_lb.pack(fill=tk.BOTH)
        for i, (pts, st) in enumerate(self._sh_sels):
            self._sh_lb.insert(tk.END, f"#{i+1} {st} ({len(pts)}пт)")
        row2 = tk.Frame(p, bg=self.palette.BG); row2.pack(fill=tk.X, pady=4)
        self._btn(row2, "Удалить выбранное", self._sh_del_sel).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self._btn(row2, "Очистить всё", self._sh_clear, self.palette.RED).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self._sep(p)
        self._btn(p, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbls["shape"] = self._lbl(p, "Папка не выбрана", color=self.palette.FG2)
        self._outdir_lbls["shape"].pack(anchor=tk.W, pady=(3,0))
        self._btn(p, "Вырезать в спрайты", self._sh_apply, self.palette.GRN, h=2).pack(fill=tk.X, pady=(8,3))
        self._btn(p, "Вырезать и сохранить…", self._sh_save, self.palette.ACC, h=2).pack(fill=tk.X, pady=3)
        self._lbl(p, "Esc — сброс  |  ПКМ — завершить", color=self.palette.FG2, size=8).pack(anchor=tk.W)

    def _build_props_grid(self, parent=None):
        p = parent if parent is not None else self._props
        self._lbl(p, "Сетка тайлов", bold=True, size=11).pack(anchor=tk.W, pady=(0,8))
        self._source_controls(p, "grid")
        self._sep(p)
        self._lbl(p, "Параметры сетки:", bold=True).pack(anchor=tk.W, pady=(0,5))
        if not hasattr(self, "_grid_mode"):
            self._grid_mode = tk.StringVar(value="size")
        SoftRadio(p, text="По размеру тайла", variable=self._grid_mode, value="size",
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       command=self._grid_update).pack(anchor=tk.W)
        SoftRadio(p, text="По количеству ячеек", variable=self._grid_mode, value="count",
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       command=self._grid_update).pack(anchor=tk.W, pady=(0,6))
        if not hasattr(self, "_grid_tw"):
            self._grid_tw = tk.IntVar(value=32)
            self._grid_th = tk.IntVar(value=32)
            self._grid_cols = tk.IntVar(value=4)
            self._grid_rows = tk.IntVar(value=4)
            self._grid_off_x = tk.IntVar(value=0)
            self._grid_off_y = tk.IntVar(value=0)
            self._grid_skip = tk.BooleanVar(value=True)
        sf = tk.Frame(p, bg=self.palette.BG); sf.pack(fill=tk.X, pady=2)
        self._lbl(sf, "Ш:").pack(side=tk.LEFT)
        self._spinbox(sf, self._grid_tw, 1, 2048, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        self._lbl(sf, "  В:").pack(side=tk.LEFT)
        self._spinbox(sf, self._grid_th, 1, 2048, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        cf = tk.Frame(p, bg=self.palette.BG); cf.pack(fill=tk.X, pady=2)
        self._lbl(cf, "Стб:").pack(side=tk.LEFT)
        self._spinbox(cf, self._grid_cols, 1, 512, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        self._lbl(cf, "  Стр:").pack(side=tk.LEFT)
        self._spinbox(cf, self._grid_rows, 1, 512, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        of = tk.Frame(p, bg=self.palette.BG); of.pack(fill=tk.X, pady=2)
        self._lbl(of, "Отступ X:").pack(side=tk.LEFT)
        self._spinbox(of, self._grid_off_x, 0, 512, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        self._lbl(of, "  Y:").pack(side=tk.LEFT)
        self._spinbox(of, self._grid_off_y, 0, 512, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        SoftCheck(p, text="Пропускать пустые тайлы", variable=self._grid_skip,
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       command=self._grid_update).pack(anchor=tk.W, pady=4)
        self._grid_cnt_lbl = self._lbl(p, "Тайлов: —", color=self.palette.GOLD, bold=True)
        self._grid_cnt_lbl.pack(anchor=tk.W, pady=4)
        self._sep(p)
        self._btn(p, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbls["grid"] = self._lbl(p, "Папка не выбрана", color=self.palette.FG2)
        self._outdir_lbls["grid"].pack(anchor=tk.W, pady=(3,0))
        self._btn(p, "Добавить в спрайты", self._grid_to_tray, self.palette.GRN, h=2).pack(fill=tk.X, pady=(8,3))
        self._btn(p, "Нарезать и сохранить…", self._grid_save, self.palette.ACC, h=2).pack(fill=tk.X, pady=3)

    def _build_props_atlas(self, parent=None):
        p = parent if parent is not None else self._props
        self._lbl(p, "Сборка атласа", bold=True, size=11).pack(anchor=tk.W, pady=(0,8))
        self._source_controls(p, "atlas")

        s2 = self._section(p, "Поиск объектов", expanded=False)
        self._background_controls(s2)
        self._sprite_options(s2, self._atlas_update)
        self._sprite_output_controls(s2, self._atlas_update)
        self._lbl(s2, "Допуск цвета фона (0–100):").pack(anchor=tk.W)
        self._atlas_thresh = SoftSlider(s2, from_=0, to=100, orient=tk.HORIZONTAL,
                                      bg=self.palette.BG, fg=self.palette.FG, troughcolor=self.palette.BTN, highlightthickness=0)
        self._atlas_thresh.set(10)
        self._atlas_thresh.pack(fill=tk.X)
        self._atlas_thresh.bind("<ButtonRelease-1>", lambda _: self._atlas_update())
        self._lbl(s2, "Мин. размер (пикс):").pack(anchor=tk.W, pady=(6,0))
        self._atlas_min = SoftSlider(s2, from_=1, to=150, orient=tk.HORIZONTAL,
                                   bg=self.palette.BG, fg=self.palette.FG, troughcolor=self.palette.BTN, highlightthickness=0)
        self._atlas_min.set(3)
        self._atlas_min.pack(fill=tk.X)
        self._atlas_min.bind("<ButtonRelease-1>", lambda _: self._atlas_update())
        self._lbl(s2, "Разделение (эрозия):").pack(anchor=tk.W, pady=(6,0))
        self._atlas_sep = SoftSlider(s2, from_=0, to=150, orient=tk.HORIZONTAL,
                                   bg=self.palette.BG, fg=self.palette.FG, troughcolor=self.palette.BTN, highlightthickness=0)
        self._atlas_sep.set(0)
        self._atlas_sep.pack(fill=tk.X)
        self._atlas_sep.bind("<ButtonRelease-1>", lambda _: self._atlas_update())
        self._atlas_cnt_lbl = self._lbl(s2, "Найдено: 0", color=self.palette.GOLD, bold=True)
        self._atlas_cnt_lbl.pack(anchor=tk.W, pady=(6,0))

        s3 = self._section(p, "Размер ячейки")
        pf3 = tk.Frame(s3, bg=self.palette.BG); pf3.pack(fill=tk.X, pady=(0,4))
        for val in (16, 32, 64, 128, 256):
            self._btn(pf3, str(val), lambda v=val: self._atlas_preset(v),
                      font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        cf = tk.Frame(s3, bg=self.palette.BG); cf.pack(fill=tk.X, pady=2)
        self._lbl(cf, "Ячейка (пикс):").pack(side=tk.LEFT)
        if not hasattr(self, "_atlas_cell"):
            self._atlas_cell = tk.IntVar(value=64)
        self._spinbox(cf, self._atlas_cell, 4, 2048, cmd=self._atlas_update).pack(side=tk.LEFT, padx=4)
        self._atlas_cell.trace_add("write", lambda *_: self._atlas_update())
        self._lbl(s3, "Режим подгонки:", color=self.palette.FG2).pack(anchor=tk.W, pady=(4,2))
        if not hasattr(self, "_atlas_fit_mode"):
            self._atlas_fit_mode = tk.StringVar(value="trim")
        mf = tk.Frame(s3, bg=self.palette.BG); mf.pack(fill=tk.X)
        SoftRadio(mf, text="Без масштаба", variable=self._atlas_fit_mode, value="trim",
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       command=self._atlas_mode_changed).pack(side=tk.LEFT, padx=(0,8))
        SoftRadio(mf, text="Масштаб", variable=self._atlas_fit_mode, value="scale",
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       command=self._atlas_mode_changed).pack(side=tk.LEFT)
        if not hasattr(self, "_atlas_no_upscale"):
            self._atlas_no_upscale = tk.BooleanVar(value=True)
        self._atlas_noup_chk = SoftCheck(s3, text="Не увеличивать мелкие",
                       variable=self._atlas_no_upscale, bg=self.palette.BG, fg=self.palette.FG,
                       selectcolor=self.palette.BTN, activebackground=self.palette.BG, command=self._atlas_update)
        self._atlas_noup_chk.pack(anchor=tk.W, pady=(2,0))
        self._lbl(s3, "Выравнивание:", color=self.palette.FG2).pack(anchor=tk.W, pady=(6,2))
        alf = tk.Frame(s3, bg=self.palette.BG); alf.pack(fill=tk.X)
        if not hasattr(self, "_atlas_align_w"):
            self._atlas_align_w = tk.BooleanVar(value=True)
            self._atlas_align_h = tk.BooleanVar(value=True)
        SoftCheck(alf, text="По ширине", variable=self._atlas_align_w,
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       command=self._atlas_update).pack(side=tk.LEFT, padx=(0,8))
        SoftCheck(alf, text="По высоте", variable=self._atlas_align_h,
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       command=self._atlas_update).pack(side=tk.LEFT)

        s4 = self._section(p, "Дубликаты", expanded=False)
        if not hasattr(self, "_atlas_dedup"):
            self._atlas_dedup = tk.BooleanVar(value=False)
            self._atlas_dedup_thresh = tk.IntVar(value=95)
        SoftCheck(s4, text="Убрать похожие", variable=self._atlas_dedup,
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       command=self._atlas_update).pack(anchor=tk.W)
        df = tk.Frame(s4, bg=self.palette.BG); df.pack(fill=tk.X, pady=(4,0))
        self._lbl(df, "Схожесть (%):").pack(side=tk.LEFT)
        self._spinbox(df, self._atlas_dedup_thresh, 50, 100, cmd=self._atlas_update).pack(side=tk.LEFT, padx=4)
        self._atlas_dedup_thresh.trace_add("write", lambda *_: self._atlas_update())
        self._atlas_dedup_lbl = self._lbl(s4, "", color=self.palette.FG2)
        self._atlas_dedup_lbl.pack(anchor=tk.W)

        s5 = self._section(p, "Компоновка", expanded=False)
        gf = tk.Frame(s5, bg=self.palette.BG); gf.pack(fill=tk.X, pady=2)
        self._lbl(gf, "Столбцов:").pack(side=tk.LEFT)
        if not hasattr(self, "_atlas_cols"):
            self._atlas_cols = tk.IntVar(value=8)
        self._spinbox(gf, self._atlas_cols, 1, 128, cmd=self._atlas_update).pack(side=tk.LEFT, padx=4)
        self._atlas_cols.trace_add("write", lambda *_: self._atlas_update())
        if not hasattr(self, "_atlas_keep_order"):
            self._atlas_keep_order = tk.BooleanVar(value=True)
        SoftCheck(s5, text="Сохранять порядок", variable=self._atlas_keep_order,
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       command=self._atlas_update).pack(anchor=tk.W, pady=(4,0))
        self._lbl(s5, "Перетащите ячейку: в центр другой — обмен, к краю (между ячейками) — вставка со сдвигом",
                  color=self.palette.FG2).pack(anchor=tk.W)
        self._btn(s5, "⇄ Сбросить порядок", self._atlas_reset_order).pack(fill=tk.X, pady=(4,0))
        self._btn(s5, "↺ Обновить превью", self._atlas_update).pack(fill=tk.X, pady=(6,4))
        self._atlas_size_lbl = self._lbl(s5, "Размер: —", color=self.palette.FG2)
        self._atlas_size_lbl.pack(anchor=tk.W)
        zf = tk.Frame(s5, bg=self.palette.BG); zf.pack(fill=tk.X, pady=(4,0))
        self._lbl(zf, "Зум:").pack(side=tk.LEFT)
        self._atlas_zoom_lbl = self._lbl(zf, "100%", color=self.palette.GOLD)
        self._atlas_zoom_lbl.pack(side=tk.LEFT, padx=6)
        self._btn(zf, "↺", self._cv_zoom_reset, h=1).pack(side=tk.RIGHT)

        s6 = self._section(p, "Сохранение")
        self._btn(s6, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbls["atlas"] = self._lbl(s6, "Папка не выбрана", color=self.palette.FG2)
        self._outdir_lbls["atlas"].pack(anchor=tk.W, pady=(3,0))
        self._lbl(s6, "Имя файла:").pack(anchor=tk.W, pady=(6,0))
        if not hasattr(self, "_atlas_name"):
            self._atlas_name = tk.StringVar(value="atlas")
            self._atlas_name_manual = False
        tk.Entry(s6, textvariable=self._atlas_name, bg=self.palette.INPUT, fg=self.palette.FG,
                 relief=tk.FLAT, insertbackground=self.palette.FG, highlightthickness=1,
                 highlightbackground=self.palette.BORDER, highlightcolor="#a7b7a0").pack(fill=tk.X, pady=(2,0), ipady=5)
        ttk.Separator(s6, orient="horizontal").pack(fill=tk.X, pady=(10,6))
        self._atlas_export_btn = self._btn(s6, "📁 Сохранить спрайты по файлам",
                                           self._atlas_export_files, self.palette.BTN)
        self._atlas_export_btn.pack(fill=tk.X, pady=(4,0))

        # Action buttons at bottom
        self._sep(p)
        self._atlas_save_btn = self._btn(p, "Сохранить атлас…", self._atlas_save, self.palette.ACC, h=2)
        self._atlas_save_btn.pack(fill=tk.X, pady=3)
        self._atlas_overwrite_btn = self._btn(p, "Перезаписать файл…", self._atlas_overwrite, self.palette.BTN, state=tk.DISABLED)
        self._atlas_overwrite_btn.pack(fill=tk.X, pady=3)
        self._atlas_target_lbl = self._lbl(p, "Сначала сохраните атлас, чтобы выбрать файл для перезаписи.", color=self.palette.FG2, size=9)
        self._atlas_target_lbl.pack(anchor=tk.W, pady=(2, 6))

    def _build_props_tiletest(self, parent=None):
        p = parent if parent is not None else self._props
        self._lbl(p, "Тайл-тест", bold=True, size=11).pack(anchor=tk.W, pady=(0,8))
        self._source_controls(p, "tiletest")
        self._sep(p)
        self._lbl(p, "Размер тайла:", bold=True).pack(anchor=tk.W, pady=(0,5))
        if not hasattr(self, "_tc_size_var"):
            self._tc_size_var = tk.IntVar(value=64)
        szf = tk.Frame(p, bg=self.palette.BG); szf.pack(fill=tk.X)
        for sz in (32, 64, 128, 256, 512):
            SoftRadio(szf, text=str(sz), variable=self._tc_size_var, value=sz,
                           bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                           font=("Segoe UI", 9, "bold"),
                           command=self._tc_size_changed).pack(side=tk.LEFT, padx=2)
        self._lbl(p, "Размер выбора:", color=self.palette.FG2).pack(anchor=tk.W, pady=(8,2))
        slf = tk.Frame(p, bg=self.palette.BG); slf.pack(fill=tk.X)
        if not hasattr(self, "_tc_sel_w"):
            self._tc_sel_w = tk.IntVar(value=64)
            self._tc_sel_h = tk.IntVar(value=64)
        self._lbl(slf, "Ш:").pack(side=tk.LEFT)
        self._spinbox(slf, self._tc_sel_w, 1, 4096, w=5, cmd=self._cv_draw).pack(side=tk.LEFT, padx=(2,8))
        self._lbl(slf, "В:").pack(side=tk.LEFT)
        self._spinbox(slf, self._tc_sel_h, 1, 4096, w=5, cmd=self._cv_draw).pack(side=tk.LEFT, padx=2)
        self._sep(p)
        self._lbl(p, "Размер сетки превью:", bold=True).pack(anchor=tk.W, pady=(0,5))
        if not hasattr(self, "_tc_grid_var"):
            self._tc_grid_var = tk.IntVar(value=3)
        grf = tk.Frame(p, bg=self.palette.BG); grf.pack(fill=tk.X)
        for n in (3, 4, 5, 6, 7):
            SoftRadio(grf, text=f"{n}×{n}", variable=self._tc_grid_var, value=n,
                           bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                           font=("Segoe UI", 9, "bold"),
                           command=self._cv_draw).pack(side=tk.LEFT, padx=2)
        self._sep(p)
        self._lbl(p, "Позиция среза:", bold=True).pack(anchor=tk.W, pady=(0,3))
        self._tc_offset_lbl = self._lbl(p, f"X: {self._tc_cx}   Y: {self._tc_cy}", color=self.palette.GOLD)
        self._tc_offset_lbl.pack(anchor=tk.W)
        if not hasattr(self, "_tc_snap"):
            self._tc_snap = tk.BooleanVar(value=False)
        SoftCheck(p, text="Привязка к сетке тайлов", variable=self._tc_snap,
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG).pack(anchor=tk.W, pady=(6,0))
        self._btn(p, "Сброс позиции (0,0)", self._tc_reset).pack(fill=tk.X, pady=(6,0))
        zf = tk.Frame(p, bg=self.palette.BG); zf.pack(fill=tk.X, pady=(8,0))
        self._lbl(zf, "Зум:").pack(side=tk.LEFT)
        self._tc_zoom_lbl = self._lbl(zf, "100%", color=self.palette.GOLD)
        self._tc_zoom_lbl.pack(side=tk.LEFT, padx=6)
        self._btn(zf, "↺", self._cv_zoom_reset, h=1).pack(side=tk.RIGHT)
        self._sep(p)
        self._btn(p, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbls["tiletest"] = self._lbl(p, "Папка не выбрана", color=self.palette.FG2)
        self._outdir_lbls["tiletest"].pack(anchor=tk.W, pady=(3,0))
        self._lbl(p, "Имя файла:").pack(anchor=tk.W, pady=(6,0))
        if not hasattr(self, "_tc_name_var"):
            self._tc_name_var = tk.StringVar(value="tile")
        tk.Entry(p, textvariable=self._tc_name_var, bg=self.palette.INPUT, fg=self.palette.FG,
                 relief=tk.FLAT, insertbackground=self.palette.FG, highlightthickness=1,
                 highlightbackground=self.palette.BORDER, highlightcolor="#a7b7a0").pack(fill=tk.X, ipady=5)
        self._btn(p, "Сохранить тайл…", self._tc_save, self.palette.ACC, h=2).pack(fill=tk.X, pady=(8,3))
    # ══════════════════════════════════════════════════════════════════
    #  DND SETUP
    # ══════════════════════════════════════════════════════════════════

    def _setup_dnd(self, widget, on_drop, *, multi=False):
        widget.drop_target_register(DND_FILES)
        def _enter(e):
            try: widget.config(highlightthickness=3, highlightbackground=self.palette.GRN)
            except tk.TclError: pass
            return "copy"
        def _leave(e):
            try: widget.config(highlightthickness=0)
            except tk.TclError: pass
        def _drop(e):
            try: widget.config(highlightthickness=0)
            except tk.TclError: pass
            paths = self._parse_drop_paths(e.data)
            if not paths:
                messagebox.showwarning("Не удалось загрузить", "Не удалось разобрать список файлов.")
                return "refuse_drop"
            if multi:
                on_drop(paths)
            else:
                for pp in paths:
                    if pp.lower().endswith(_IMG_EXTS) or os.path.isdir(pp):
                        on_drop(pp); break
            return "copy"
        widget.dnd_bind('<<DropEnter>>', _enter)
        widget.dnd_bind('<<DropPosition>>', lambda _: "copy")
        widget.dnd_bind('<<DropLeave>>', _leave)
        widget.dnd_bind('<<Drop>>', _drop)

    def _handle_drop_paths(self, paths):
        paths = list(dict.fromkeys(os.path.abspath(path) for path in paths))
        if len(paths) == 1 and os.path.isdir(paths[0]):
            self._tool_set("resize")
            self._resize_set_folder(paths[0])
            return
        if len(paths) == 1 and paths[0].lower().endswith(".smproj"):
            self.project_load(paths[0])
            return
        images, failures = [], []
        for path in paths:
            if not os.path.isfile(path) or not path.lower().endswith(_IMG_EXTS):
                failures.append(path)
                continue
            try:
                with Image.open(path) as image:
                    images.append((path, image.convert("RGBA")))
            except (OSError, ValueError):
                failures.append(path)
        if len(paths) == 1 and images:
            self._load_src(images[0][0])
        elif images:
            if self.tool == "atlas":
                self._load_src(images[0][0])
                self._atlas_imported = True
                self._atlas_raws = [image for _, image in images]
                self._atlas_raw_boxes = [(index, 0, image.width, image.height)
                                         for index, (_, image) in enumerate(images)]
                self._atlas_order = list(self._atlas_raw_boxes)
                self._atlas_update()
            else:
                if self.tool == "resize":
                    self._tool_set("auto")
                self._tray_add([image for _, image in images])
                if self._outdir_auto:
                    self.outdir = os.path.dirname(images[0][0])
                    self._update_outdir_lbl(self.outdir)
            self._status_var.set(f"Загружено файлов: {len(images)}")
        if failures:
            messagebox.showwarning("Пропущенные файлы",
                "Не удалось загрузить:\n" + "\n".join(failures[:10]))

    # ══════════════════════════════════════════════════════════════════
    #  FILE OPERATIONS
    # ══════════════════════════════════════════════════════════════════

    def _menu_open_src(self):
        path = filedialog.askopenfilename(
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if path:
            self._load_src(path)

    def _load_src(self, path, from_clipboard=False):
        try:
            arr = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
        except (OSError, cv2.error):
            img = None
        if img is None:
            messagebox.showerror("Ошибка", f"Не удалось открыть:\n{path}")
            return False
        if img.dtype == np.uint16:
            img = (img / 257).astype(np.uint8)
        self.src_img = img
        self.src_path = "" if from_clipboard else os.path.abspath(path)
        self._reset_source_state()
        self._cv_zoom = 1.0
        self._cv_view_x = 0
        self._cv_view_y = 0
        self._auto_contours_cache = []
        if not from_clipboard and (not self.outdir or self._outdir_auto):
            self.outdir = os.path.dirname(path)
            self._add_recent(self.outdir)
        self._update_src_lbl("Из буфера" if from_clipboard else os.path.basename(path))
        self._update_outdir_lbl(self.outdir)
        self._status_var.set(f"Открыто: {os.path.basename(path)}  ({img.shape[1]}×{img.shape[0]})")
        if self.tool == "auto":
            self._auto_run()
        elif self.tool == "grid":
            self._grid_update()
        elif self.tool == "atlas":
            self._atlas_update()
        else:
            self._cv_draw()

        return True

    def _clear_src(self):
        self.src_img = None
        self.src_path = ""
        self._reset_source_state()
        self._cv_zoom = 1.0
        self._cv_view_x = 0
        self._cv_view_y = 0
        self._auto_contours_cache = []
        self._update_src_lbl("Файл не выбран")
        self._cv_draw()

    def _menu_choose_outdir(self):
        d = filedialog.askdirectory()
        if d:
            self.outdir = d
            self._last_export_dir = ""
            self._outdir_auto = False
            self._add_recent(d)
            self._update_outdir_lbl(d)

    def _reset_source_state(self):
        self._last_export_dir = ""
        self._mask_tool.set("pan")
        self._background_preview.set(True)
        self._auto_rgba_cache = None
        self._auto_regions_cache = []
        self._mask_marks = None
        self._mask_history = []
        self._mask_revision += 1
        self._mask_last = None
        self._refined_rgba = None
        self._refined_key = None
        self._background_picking = False
        self._rebind_canvas(self.tool)
        self._sh_clear()
        self._tc_reset()
        self._grid_tiles_cache = []
        self._atlas_raws = []
        self._atlas_raw_boxes = []
        self._atlas_order = []
        self._atlas_sheet = self._atlas_vis = None
        self._atlas_last_out = None
        self._atlas_imported = False
        self._auto_cnt_lbl.config(text="Найдено: 0")
        self._grid_cnt_lbl.config(text="Тайлов: —")
        self._atlas_cnt_lbl.config(text="Найдено: 0")
        self._atlas_size_lbl.config(text="Размер: —")
        self._tc_zoom = 1.0
        self._tc_vx = self._tc_vy = 0
        self._sh_down = False
        self._atlas_excluded = set()
        if self.tool == "atlas":
            self.excluded = self._atlas_excluded
            self._tray_refresh_atlas_tray()
        self._atlas_overwrite_btn.config(state=tk.DISABLED)
        self._atlas_target_lbl.config(text="Сначала сохраните атлас, чтобы выбрать файл для перезаписи.")

    def _update_src_lbl(self, text):
        for lbl in self._src_lbls.values():
            lbl.config(text=text)

    def _update_outdir_lbl(self, text):
        for lbl in self._outdir_lbls.values():
            lbl.config(text=text)
        if hasattr(self, "_auto_save_btn"):
            self._workflow_update()

    # ══════════════════════════════════════════════════════════════════
    #  CLIPBOARD
    # ══════════════════════════════════════════════════════════════════

    def _get_clipboard_path(self):
        try:
            from PIL import ImageGrab
            data = ImageGrab.grabclipboard()
            if isinstance(data, Image.Image):
                fd, path = tempfile.mkstemp(suffix='.png', prefix='imgcuter_')
                os.close(fd)
                data.save(path)
                self._clipboard_temporary = path
                return path
            if isinstance(data, list):
                for pp in data:
                    if isinstance(pp, str) and os.path.isfile(pp) and pp.lower().endswith(_IMG_EXTS):
                        return pp
        except Exception:
            pass
        try:
            for mime in ('image/png', 'image/jpeg', 'image/bmp'):
                res = subprocess.run(
                    ['xclip', '-selection', 'clipboard', '-t', mime, '-o'],
                    capture_output=True, timeout=3)
                if res.returncode == 0 and res.stdout:
                    ext = '.jpg' if 'jpeg' in mime else f'.{mime.split("/")[1]}'
                    img = Image.open(io.BytesIO(res.stdout))
                    fd, path = tempfile.mkstemp(suffix=ext, prefix='imgcuter_')
                    os.close(fd)
                    img.save(path)
                    self._clipboard_temporary = path
                    return path
        except Exception:
            pass
        try:
            res = subprocess.run(['wl-paste', '--type', 'image/png'],
                                 capture_output=True, timeout=3)
            if res.returncode == 0 and res.stdout:
                img = Image.open(io.BytesIO(res.stdout))
                fd, path = tempfile.mkstemp(suffix='.png', prefix='imgcuter_')
                os.close(fd)
                img.save(path)
                self._clipboard_temporary = path
                return path
        except Exception:
            pass
        return None

    def _global_paste(self, event=None):
        if event is not None and isinstance(self.root.focus_get(), (tk.Entry, tk.Spinbox, tk.Text, ttk.Entry)):
            return
        p = self._get_clipboard_path()
        if not p:
            messagebox.showinfo("Буфер", "В буфере нет изображения")
            return
        temporary = p == getattr(self, "_clipboard_temporary", None)
        try:
            self._load_src(p, from_clipboard=temporary)
        finally:
            if temporary:
                try:
                    os.unlink(p)
                except OSError:
                    pass
                self._clipboard_temporary = None
        return "break"

    # ══════════════════════════════════════════════════════════════════
    #  CORE LOGIC UTILITIES
    # ══════════════════════════════════════════════════════════════════

    def _imwrite(self, path, img):
        self._atomic_image(self._cv2pil(img), path)

    @staticmethod
    def _atomic_write(path, writer, overwrite=False):
        path = os.path.abspath(path)
        fd, temporary = tempfile.mkstemp(prefix=".sprite-save-", suffix=".tmp", dir=os.path.dirname(path))
        os.close(fd)
        try:
            writer(temporary)
            if overwrite:
                os.replace(temporary, path)
            elif os.name == "nt":
                os.rename(temporary, path)
            else:
                os.link(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _atomic_image(self, image, path, overwrite=False):
        self._atomic_write(path, lambda temporary: image.save(temporary, format="PNG"), overwrite)

    @staticmethod
    def _safe_name(value, fallback):
        name = "".join(character for character in value.strip()
                       if character not in '\\/:*?"<>|' and ord(character) >= 32).strip(" .")
        if name.lower().endswith(".png"):
            name = name[:-4].rstrip(" .")
        if not name:
            name = fallback
        if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
            name = "_" + name
        return name[:160]

    def _confirm_replace(self, path):
        original = bool(self.src_path) and os.path.normcase(os.path.realpath(path)) == os.path.normcase(os.path.realpath(self.src_path))
        return messagebox.askyesno(
            "Заменить исходное изображение?" if original else "Перезаписать файл?",
            ("Исходное изображение будет заменено атласом.\n" if original else "Перезаписать этот файл?\n")
            + os.path.abspath(path), default="no")

    def _cv2pil(self, img):
        if img is None:
            return None
        if len(img.shape) == 2:
            return Image.fromarray(img).convert("RGBA")
        if img.shape[2] == 4:
            return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA))
        return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert("RGBA")

    def _next_idx(self, folder, prefix, ext=".png"):
        idxs = []
        for f in os.listdir(folder):
            if f.casefold().startswith(prefix.casefold()) and f.casefold().endswith(ext.casefold()):
                try:
                    idxs.append(int(f[len(prefix):-len(ext)]))
                except ValueError:
                    pass
        return (max(idxs) + 1) if idxs else 0

    def _parse_drop_paths(self, data):
        try:
            paths = self.root.tk.splitlist(data)
        except tk.TclError:
            return []
        result = []
        for path in paths:
            if path.startswith("file:"):
                parsed = urlparse(path)
                path = unquote(parsed.path)
                if parsed.netloc:
                    path = "//" + parsed.netloc + path
                elif os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == ":":
                    path = path[1:]
            if path:
                result.append(path)
        return result

    def _background_signature(self, img, tolerance):
        mode = self._background_mode.get() if hasattr(self, "_background_mode") else "auto"
        return (id(img), tolerance, getattr(self, "_background_rgb", None), mode,
                getattr(self, "_mask_revision", 0))

    def _extract_rgba(self, img, tolerance, process_edges=True):
        # Accept legacy threshold arguments from older integrations.
        if tolerance > 100:
            tolerance = 255 - tolerance
        key = self._background_signature(img, tolerance)
        mode = self._background_mode.get() if hasattr(self, "_background_mode") else "auto"
        marks = getattr(self, "_mask_marks", None) if img is self.src_img else None
        if key == getattr(self, "_refined_key", None) and self._refined_rgba is not None:
            rgba = self._refined_rgba.copy()
        else:
            rgba = extract_foreground(img, tolerance, getattr(self, "_background_rgb", None), mode, marks)
        if (process_edges and hasattr(self, "_edge_smooth") and self._edge_smooth.get() and
                not self._pixel_art.get()):
            rgba = smooth_cutout_edges(img, rgba, getattr(self, "_background_rgb", None), mode,
                                       marks, self._edge_choke.get(), tolerance)
        return rgba

    def _detection_regions(self, alpha, ms, sep=0):
        single = hasattr(self, "_auto_object_mode") and self._auto_object_mode.get() == "single"
        gap = self._auto_group_gap.get() if hasattr(self, "_auto_group_gap") else 0
        return sprite_regions(alpha, ms, sep, gap, single)

    @staticmethod
    def _region_contour(region):
        x, y, w, h = region[:4]
        return np.array([[[x, y]], [[x+w-1, y]], [[x+w-1, y+h-1]], [[x, y+h-1]]], np.int32)

    def _sprite_pil(self, rgba, region, scale=False):
        x, y, w, h, mask = region
        crop = rgba[y:y+h, x:x+w].copy()
        crop[~mask.astype(bool), 3] = 0
        image = self._cv2pil(crop).convert("RGBA")
        if scale:
            image = self._auto_scale_apply(image)
        padding = self._export_padding.get() if hasattr(self, "_export_padding") else 0
        if padding:
            padded = Image.new("RGBA", (image.width + padding * 2, image.height + padding * 2))
            padded.alpha_composite(image, (padding, padding))
            image = padded
        if hasattr(self, "_edge_bleed") and self._edge_bleed.get():
            image = Image.fromarray(bleed_transparent_colors(np.array(image)))
        return image

    def _auto_contours(self, img, tv, ms, sep=0, mask=None):
        if img is None: return []
        alpha = self._extract_rgba(img, tv)[:, :, 3] if mask is None else mask
        return [self._region_contour(r) for r in self._detection_regions(alpha, ms, sep)]

    def _dedup_raws(self, raws, thresh):
        SIZE = 32
        def _sig(pil):
            a = np.array(pil.resize((SIZE, SIZE), Image.LANCZOS).convert("RGBA"),
                         dtype=np.float32) / 255.0
            return a.flatten()
        sigs = [_sig(pp) for pp in raws]
        limit = 1.0 - thresh / 100.0
        kept = []
        kept_sigs = []
        for pil, sig in zip(raws, sigs):
            dup = any(float(np.mean((sig - ks) ** 2)) <= limit for ks in kept_sigs)
            if not dup:
                kept.append(pil)
                kept_sigs.append(sig)
        return kept, len(raws) - len(kept)

    def _tile_is_empty(self, crop):
        if crop is None or crop.size == 0: return True
        if len(crop.shape) == 3 and crop.shape[2] == 4:
            return int(crop[:, :, 3].mean()) < 5
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        return float(gray.std()) < 3.0

    # ══════════════════════════════════════════════════════════════════
    #  SPRITE TRAY
    # ══════════════════════════════════════════════════════════════════

    _TRAY_SZ  = 64
    _TRAY_PAD = 4

    def _tray_add(self, pil_list):
        self.sprites.extend(pil_list)
        self._tray_refresh()

    def _tray_refresh(self):
        SZ, PAD = self._TRAY_SZ, self._TRAY_PAD
        tc = self._tray_canvas
        tc.delete("all")
        self._tray_photos = []
        for i, pil in enumerate(self.sprites):
            excluded = i in self.excluded
            thumb = pil.copy()
            thumb.thumbnail((SZ-4, SZ-4), Image.LANCZOS)
            cell = self._tc_checker(SZ, SZ).convert("RGBA")
            ox = (SZ - thumb.width)  // 2
            oy = (SZ - thumb.height) // 2
            cell.alpha_composite(thumb.convert("RGBA"), (ox, oy))
            if excluded:
                overlay = Image.new("RGBA", (SZ, SZ), (160, 0, 0, 130))
                cell = Image.alpha_composite(cell, overlay)
                d = ImageDraw.Draw(cell)
                d.line([(4, 4), (SZ-4, SZ-4)], fill=(255, 60, 60), width=2)
                d.line([(SZ-4, 4), (4, SZ-4)], fill=(255, 60, 60), width=2)
            border_col = self.palette.RED if excluded else self.palette.BORDER
            d2 = ImageDraw.Draw(cell)
            d2.rectangle([0, 0, SZ-1, SZ-1], outline=border_col, width=2)
            photo = ImageTk.PhotoImage(cell)
            self._tray_photos.append(photo)
            x = PAD + i * (SZ + PAD)
            tc.create_image(x, PAD, anchor=tk.NW, image=photo)
        total_w = PAD + len(self.sprites) * (SZ + PAD)
        tc.configure(scrollregion=(0, 0, max(total_w, 1), SZ + PAD*2))
        n_exc = len(self.excluded)
        n_vis = len(self.sprites) - n_exc
        if n_exc:
            txt = f"Готовые спрайты: {n_vis} из {len(self.sprites)}"
        else:
            txt = f"Готовые спрайты: {len(self.sprites)}"
        self._tray_count_lbl.config(text=txt)
        self._tray_actions(n_vis, len(self.sprites))
        if not self.sprites:
            tc.create_text(12, 32, anchor=tk.W, text="Здесь можно собрать набор из разных картинок. Добавьте найденные спрайты кнопкой справа.",
                           fill=self.palette.FG2, font=("Segoe UI", 10))

    def _tray_actions(self, active, total):
        self._tray_save_btn.config(state=tk.NORMAL if active else tk.DISABLED)
        self._tray_clear_btn.config(text="Исключить все" if self.tool == "atlas" else "Очистить ленту",
                                    state=tk.NORMAL if total else tk.DISABLED)
        self._tray_atlas_btn.config(state=tk.NORMAL if active and self.tool != "atlas" else tk.DISABLED)

    def _tray_to_atlas(self):
        if self.tool == "atlas":
            return
        visible = [sprite.copy() for index, sprite in enumerate(self.sprites) if index not in self.excluded]
        if not visible:
            return
        self._atlas_imported = True
        self._atlas_raws = visible
        self._atlas_raw_boxes = [(index, 0, image.width, image.height) for index, image in enumerate(visible)]
        self._atlas_order = list(self._atlas_raw_boxes)
        self._atlas_excluded = set()
        self._atlas_last_out = None
        self._atlas_overwrite_btn.config(state=tk.DISABLED)
        self._atlas_target_lbl.config(text="Сначала сохраните атлас, чтобы выбрать файл для перезаписи.")
        self._tool_set("atlas")

    def _tray_click(self, e):
        if self.tool == "atlas":
            # In atlas mode tray shows atlas raws
            SZ, PAD = self._TRAY_SZ, self._TRAY_PAD
            cx = self._tray_canvas.canvasx(e.x)
            i = int(cx // (SZ + PAD))
            if 0 <= i < len(self._atlas_raws):
                self._tray_drag_src = i
            return
        SZ, PAD = self._TRAY_SZ, self._TRAY_PAD
        cx = self._tray_canvas.canvasx(e.x)
        i = int(cx // (SZ + PAD))
        if 0 <= i < len(self.sprites):
            if i in self.excluded:
                self.excluded.discard(i)
            else:
                self.excluded.add(i)
            self._tray_refresh()

    def _tray_slot(self, e):
        SZ, PAD = self._TRAY_SZ, self._TRAY_PAD
        return int(self._tray_canvas.canvasx(e.x) // (SZ + PAD))

    def _tray_drag(self, e):
        src = getattr(self, "_tray_drag_src", None)
        tc = self._tray_canvas
        tc.delete("drag_hl")
        if self.tool != "atlas" or src is None:
            return
        SZ, PAD = self._TRAY_SZ, self._TRAY_PAD
        j = self._tray_slot(e)
        if 0 <= j < len(self._atlas_raws) and j != src:
            x = PAD + j * (SZ + PAD)
            tc.create_rectangle(x, PAD, x + SZ, PAD + SZ, outline="#a36b20",
                                width=3, tags="drag_hl")

    def _tray_release(self, e):
        src = getattr(self, "_tray_drag_src", None)
        self._tray_drag_src = None
        self._tray_canvas.delete("drag_hl")
        if self.tool != "atlas" or src is None:
            return
        j = self._tray_slot(e)
        if j != src and 0 <= j < len(self._atlas_raws):
            self._atlas_swap(src, j)
        elif j == src:
            if src in self.excluded:
                self.excluded.discard(src)
            else:
                self.excluded.add(src)
            self._tray_refresh_atlas_tray()
            self._atlas_assemble()

    def _tray_clear(self):
        if self.tool == "atlas":
            self.excluded = set(range(len(self._atlas_raws)))
            self._tray_refresh_atlas_tray()
            self._atlas_assemble()
            return
        self.sprites.clear()
        self.excluded.clear()
        self._tray_refresh()

    @file_operation
    def _tray_save_all(self):
        if self.tool == "atlas":
            self._atlas_export_files()
            return
        visible = [s for i, s in enumerate(self.sprites) if i not in self.excluded]
        if not visible:
            messagebox.showinfo("Трей пуст", "Нет спрайтов в трее (или все исключены)")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._outdir_auto = False
            self._add_recent(d)
            self._update_outdir_lbl(d)
        idx = self._next_idx(self.outdir, "sprite_")
        for pil in visible:
            self._atomic_image(pil, os.path.join(self.outdir, f"sprite_{idx:04d}.png"))
            idx += 1
        messagebox.showinfo("Готово!", f"Сохранено {len(visible)} спрайтов в:\n{self.outdir}")

    # ══════════════════════════════════════════════════════════════════
    #  AUTO TOOL
    # ══════════════════════════════════════════════════════════════════

    def _auto_scale_update(self):
        if not hasattr(self, "_auto_scale_mode"):
            return
        mode = self._auto_scale_mode.get()
        w_state = tk.NORMAL if mode in ("w", "both") else tk.DISABLED
        h_state = tk.NORMAL if mode in ("h", "both") else tk.DISABLED
        if hasattr(self, "_auto_scale_w_sb"):
            self._auto_scale_w_sb.config(state=w_state)
        if hasattr(self, "_auto_scale_h_sb"):
            self._auto_scale_h_sb.config(state=h_state)

    def _auto_scale_apply(self, pil_img):
        if not hasattr(self, "_auto_scale_mode"):
            return pil_img
        mode = self._auto_scale_mode.get()
        if mode == "none":
            return pil_img
        ow, oh = pil_img.size
        if ow == 0 or oh == 0:
            return pil_img
        sw = self._auto_scale_w.get()
        sh = self._auto_scale_h.get()
        if mode == "w":
            nw = sw
            nh = max(1, round(oh * sw / ow))
        elif mode == "h":
            nh = sh
            nw = max(1, round(ow * sh / oh))
        else:
            nw, nh = sw, sh
        return pil_img.resize((nw, nh), self._resampling())

    def _auto_run(self):
        if hasattr(self, "_task_preset"):
            self._sync_preset()
        if self.src_img is None:
            self._auto_contours_cache = []
            self._auto_rgba_cache = None
            self._auto_regions_cache = []
            if hasattr(self, "_auto_cnt_lbl"):
                self._auto_cnt_lbl.config(text="Найдено: 0")
            self._cv_draw()
            return
        tv  = self._auto_thresh.get() if hasattr(self, "_auto_thresh") else 10
        ms  = self._auto_min.get()    if hasattr(self, "_auto_min")    else 12
        sep = self._auto_sep.get()    if hasattr(self, "_auto_sep")    else 0
        self._auto_rgba_cache = self._extract_rgba(self.src_img, tv)
        self._auto_regions_cache = self._detection_regions(self._auto_rgba_cache[:, :, 3], ms, sep)
        contours = [self._region_contour(region) for region in self._auto_regions_cache]
        self._auto_contours_cache = contours
        if hasattr(self, "_auto_cnt_lbl"):
            self._auto_cnt_lbl.config(text=f"Найдено: {len(contours)}")
        self._cv_draw()

    def _auto_add_to_tray(self):
        if self.src_img is None or not hasattr(self, "_auto_contours_cache"):
            messagebox.showinfo("Нет данных", "Сначала запустите детекцию")
            return
        self._auto_run()
        contours = self._auto_contours_cache
        if not contours:
            messagebox.showinfo("Нет объектов", "Объекты не найдены")
            return
        rgba = self._auto_rgba_cache
        raws = [self._sprite_pil(rgba, region, scale=True) for region in self._auto_regions_cache]
        self._tray_add(raws)
        if hasattr(self, "_status_var"):
            self._status_var.set(f"Добавлено в нижнюю ленту: {len(raws)}. Можно открыть следующую картинку или сохранить выбранные PNG.")

    @file_operation
    def _auto_save(self):
        if self.src_img is None:
            messagebox.showwarning("Ошибка", "Откройте изображение")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._outdir_auto = False
            self._add_recent(d)
            self._update_outdir_lbl(d)
        self._auto_run()
        contours = self._auto_contours_cache
        if not contours:
            messagebox.showinfo("Нет объектов", "Объекты не найдены")
            return
        rgba = self._auto_rgba_cache
        idx = self._next_idx(self.outdir, "sprite_")
        for region in self._auto_regions_cache:
            pil_crop = self._sprite_pil(rgba, region, scale=True)
            crop = cv2.cvtColor(np.array(pil_crop), cv2.COLOR_RGBA2BGRA)
            self._imwrite(os.path.join(self.outdir, f"sprite_{idx:04d}.png"), crop)
            idx += 1
        self._last_export_dir = self.outdir
        if hasattr(self, "_auto_save_btn"):
            self._workflow_update()
        messagebox.showinfo("Спрайты готовы", f"Сохранено PNG: {len(contours)}\n\nПапка:\n{self.outdir}")

    # ══════════════════════════════════════════════════════════════════
    #  SHAPE TOOL
    # ══════════════════════════════════════════════════════════════════

    def _sh_reset(self):
        self._sh_cur  = []
        self._sh_down = False
        self._sh_start = None
        self._cv_draw()

    def _sh_press(self, e):
        if self.src_img is None: return
        self._canvas.focus_set()
        pil = self._cv2pil(self.src_img)
        if pil is None: return
        iw, ih = pil.size
        cw = self._canvas.winfo_width() or 800
        ch = self._canvas.winfo_height() or 600
        fit = min(cw/iw, ch/ih)
        scale = fit * self._cv_zoom
        ix = (e.x - self._cv_img_ox) / scale
        iy = (e.y - self._cv_img_oy) / scale
        tool = self._sh_tool_var.get() if hasattr(self, "_sh_tool_var") else "rect"
        if tool == "rect":
            self._sh_down  = True
            self._sh_start = (ix, iy)
        else:
            self._sh_cur.append((ix, iy))
            self._sh_down = True

    def _sh_drag(self, e):
        if not self._sh_down: return
        tool = self._sh_tool_var.get() if hasattr(self, "_sh_tool_var") else "rect"
        if tool == "lasso":
            pil = self._cv2pil(self.src_img)
            if pil is None: return
            iw, ih = pil.size
            cw = self._canvas.winfo_width() or 800
            ch = self._canvas.winfo_height() or 600
            fit = min(cw/iw, ch/ih)
            scale = fit * self._cv_zoom
            ix = (e.x - self._cv_img_ox) / scale
            iy = (e.y - self._cv_img_oy) / scale
            self._sh_cur.append((ix, iy))
        self._cv_draw()

    def _sh_release(self, e):
        tool = self._sh_tool_var.get() if hasattr(self, "_sh_tool_var") else "rect"
        if tool == "rect" and self._sh_down and self._sh_start:
            pil = self._cv2pil(self.src_img)
            if pil is None: return
            iw, ih = pil.size
            cw = self._canvas.winfo_width() or 800
            ch = self._canvas.winfo_height() or 600
            fit = min(cw/iw, ch/ih)
            scale = fit * self._cv_zoom
            ix = (e.x - self._cv_img_ox) / scale
            iy = (e.y - self._cv_img_oy) / scale
            sx, sy = self._sh_start
            pts = [(sx, sy), (ix, sy), (ix, iy), (sx, iy)]
            self._sh_add(pts, "rect")
            self._sh_down  = False
            self._sh_start = None

    def _sh_finish(self, _=None):
        tool = self._sh_tool_var.get() if hasattr(self, "_sh_tool_var") else "rect"
        if tool in ("poly", "lasso") and len(self._sh_cur) >= 3:
            self._sh_add(list(self._sh_cur), tool)
        self._sh_cur  = []
        self._sh_down = False

    def _sh_move(self, e):
        if self._sh_down:
            self._cv_draw()

    def _sh_add(self, pts, stype):
        self._sh_sels.append((pts, stype))
        if hasattr(self, "_sh_lb"):
            n = len(self._sh_sels)
            self._sh_lb.insert(tk.END, f"#{n} {stype} ({len(pts)}пт)")
        self._cv_draw()

    def _sh_del_sel(self):
        if not hasattr(self, "_sh_lb"): return
        sel = self._sh_lb.curselection()
        if not sel: return
        i = sel[0]
        self._sh_sels.pop(i)
        self._sh_lb.delete(0, tk.END)
        for j, (pts, st) in enumerate(self._sh_sels):
            self._sh_lb.insert(tk.END, f"#{j+1} {st} ({len(pts)}пт)")
        self._cv_draw()

    def _sh_clear(self):
        self._sh_sels.clear()
        self._sh_cur = []
        if hasattr(self, "_sh_lb"):
            self._sh_lb.delete(0, tk.END)
        self._cv_draw()

    def _sh_apply(self):
        if not self._sh_sels or self.src_img is None:
            messagebox.showinfo("Нет выделений", "Нарисуйте выделения на холсте")
            return
        pil = self._cv2pil(self.src_img)
        if pil is None: return
        base = pil.convert("RGBA")
        iw, ih = base.size
        transp = self._sh_transp.get() if hasattr(self, "_sh_transp") else True
        raws = []
        for pts, _ in self._sh_sels:
            xs = [int(x) for x, _ in pts]
            ys = [int(y) for _, y in pts]
            x0 = max(0, min(xs)); y0 = max(0, min(ys))
            x1 = min(iw, max(xs)); y1 = min(ih, max(ys))
            if x1 <= x0 or y1 <= y0: continue
            if transp:
                mask = Image.new("L", (iw, ih), 0)
                md   = ImageDraw.Draw(mask)
                md.polygon([(int(x), int(y)) for x, y in pts], fill=255)
                out  = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
                out.paste(base, mask=mask)
                crop = out.crop((x0, y0, x1, y1))
            else:
                crop = base.crop((x0, y0, x1, y1)).convert("RGBA")
            raws.append(crop)
        if raws:
            self._tray_add(raws)
            messagebox.showinfo("Трей", f"Добавлено {len(raws)} фигур в трей")

    @file_operation
    def _sh_save(self):
        if not self._sh_sels or self.src_img is None:
            messagebox.showinfo("Нет выделений", "Нарисуйте выделения")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._outdir_auto = False
            self._add_recent(d)
            self._update_outdir_lbl(d)
        pil = self._cv2pil(self.src_img)
        if pil is None: return
        base = pil.convert("RGBA")
        iw, ih = base.size
        transp = self._sh_transp.get() if hasattr(self, "_sh_transp") else True
        idx = self._next_idx(self.outdir, "cut_")
        saved = 0
        for pts, _ in self._sh_sels:
            xs = [int(x) for x, _ in pts]
            ys = [int(y) for _, y in pts]
            x0 = max(0, min(xs)); y0 = max(0, min(ys))
            x1 = min(iw, max(xs)); y1 = min(ih, max(ys))
            if x1 <= x0 or y1 <= y0: continue
            if transp:
                mask = Image.new("L", (iw, ih), 0)
                md   = ImageDraw.Draw(mask)
                md.polygon([(int(x), int(y)) for x, y in pts], fill=255)
                out  = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
                out.paste(base, mask=mask)
                crop = out.crop((x0, y0, x1, y1))
            else:
                crop = base.crop((x0, y0, x1, y1)).convert("RGBA")
            self._atomic_image(crop, os.path.join(self.outdir, f"cut_{idx:04d}.png"))
            idx += 1; saved += 1
        messagebox.showinfo("Готово!", f"Вырезано {saved} фигур в:\n{self.outdir}")

    # ══════════════════════════════════════════════════════════════════
    #  GRID TOOL
    # ══════════════════════════════════════════════════════════════════

    def _grid_tiles(self):
        if self.src_img is None: return []
        ih, iw = self.src_img.shape[:2]
        off_x = max(0, self._grid_off_x.get()) if hasattr(self, "_grid_off_x") else 0
        off_y = max(0, self._grid_off_y.get()) if hasattr(self, "_grid_off_y") else 0
        mode = self._grid_mode.get() if hasattr(self, "_grid_mode") else "size"
        if mode == "size":
            tw = max(1, self._grid_tw.get())
            th = max(1, self._grid_th.get())
            cols = max(1, (iw - 2*off_x) // tw)
            rows = max(1, (ih - 2*off_y) // th)
        else:
            cols = max(1, self._grid_cols.get())
            rows = max(1, self._grid_rows.get())
            avw = max(1, iw - 2*off_x)
            avh = max(1, ih - 2*off_y)
            tw = max(1, avw // cols)
            th = max(1, avh // rows)
        tiles = []
        for r in range(rows):
            for c in range(cols):
                x = off_x + c * tw
                y = off_y + r * th
                if x + tw > iw or y + th > ih:
                    continue
                tiles.append((x, y, tw, th))
        return tiles

    def _grid_update(self, *_):
        if self.src_img is None:
            if hasattr(self, "_grid_cnt_lbl"):
                self._grid_cnt_lbl.config(text="Тайлов: —")
            self._cv_draw()
            return
        tiles = self._grid_tiles()
        skip  = self._grid_skip.get() if hasattr(self, "_grid_skip") else True
        img   = self.src_img
        count = 0
        for (x, y, tw, th) in tiles:
            crop = img[y:y+th, x:x+tw]
            if not (skip and self._tile_is_empty(crop)):
                count += 1
        self._grid_tiles_cache = tiles
        if hasattr(self, "_grid_cnt_lbl"):
            self._grid_cnt_lbl.config(text=f"Тайлов: {count}")
        self._cv_draw()

    def _grid_to_tray(self):
        if self.src_img is None:
            messagebox.showinfo("Нет изображения", "Откройте изображение")
            return
        tiles = self._grid_tiles()
        if not tiles:
            messagebox.showinfo("Нет тайлов", "Сетка не содержит тайлов")
            return
        skip = self._grid_skip.get() if hasattr(self, "_grid_skip") else True
        img  = self.src_img
        rgba = (cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                if len(img.shape) == 3 and img.shape[2] == 3 else img.copy())
        raws = []
        for (x, y, tw, th) in tiles:
            crop = rgba[y:y+th, x:x+tw]
            if skip and self._tile_is_empty(crop): continue
            pil = self._cv2pil(crop).convert("RGBA")
            raws.append(pil)
        if raws:
            self._tray_add(raws)
            messagebox.showinfo("Трей", f"Добавлено {len(raws)} тайлов в трей")

    @file_operation
    def _grid_save(self):
        if self.src_img is None:
            messagebox.showwarning("Ошибка", "Откройте изображение")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._outdir_auto = False
            self._add_recent(d)
            self._update_outdir_lbl(d)
        tiles = self._grid_tiles()
        if not tiles:
            messagebox.showinfo("Нет тайлов", "Сетка не содержит тайлов")
            return
        skip = self._grid_skip.get() if hasattr(self, "_grid_skip") else True
        img  = self.src_img
        rgba = (cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                if len(img.shape) == 3 and img.shape[2] == 3 else img.copy())
        idx = self._next_idx(self.outdir, "tile_")
        saved = 0
        for (x, y, tw, th) in tiles:
            crop = rgba[y:y+th, x:x+tw]
            if skip and self._tile_is_empty(crop): continue
            self._imwrite(os.path.join(self.outdir, f"tile_{idx:04d}.png"), crop)
            idx += 1; saved += 1
        messagebox.showinfo("Готово!", f"Сохранено {saved} тайлов в:\n{self.outdir}")

    # ══════════════════════════════════════════════════════════════════
    #  ATLAS TOOL
    # ══════════════════════════════════════════════════════════════════

    def _atlas_detect_raws(self):
        if getattr(self, "_atlas_imported", False):
            return self._atlas_raws
        img = self.src_img
        if img is None:
            self._atlas_raws = []
            return []
        tv  = self._atlas_thresh.get() if hasattr(self, "_atlas_thresh") else 10
        ms  = self._atlas_min.get()    if hasattr(self, "_atlas_min")    else 12
        sep = max(0, self._atlas_sep.get() if hasattr(self, "_atlas_sep") else 0)
        rgba = self._extract_rgba(img, tv)
        regions = self._detection_regions(rgba[:, :, 3], ms, sep)
        if not regions:
            self._atlas_raws = []
            return []
        cell0 = max(4, self._atlas_cell.get() if hasattr(self, "_atlas_cell") else 64)
        region_map = {tuple(region[:4]): region for region in regions}
        boxes = sorted(region_map,
                       key=lambda b: (b[1] // max(1, cell0), b[0]))

        # Keep previous (incl. manually swapped) order; new boxes go to the end
        # in default order. Order is matched by box identity.
        keep = self._atlas_keep_order.get() if hasattr(self, "_atlas_keep_order") else True
        prev = getattr(self, "_atlas_order", [])
        if keep and prev:
            present = set(boxes)
            kept = [b for b in prev if b in present]
            kept_set = set(kept)
            boxes = kept + [b for b in boxes if b not in kept_set]

        # Remap excluded by box identity so resorting on cell-size change
        # doesn't shift crosses to wrong sprites.
        old_boxes = getattr(self, "_atlas_raw_boxes", [])
        excluded_boxes = {old_boxes[i] for i in self.excluded if i < len(old_boxes)}

        raws = []
        for box in boxes:
            raws.append(self._sprite_pil(rgba, region_map[box]))

        if excluded_boxes:
            self.excluded = {i for i, b in enumerate(boxes) if b in excluded_boxes}
        elif len(raws) != len(self._atlas_raws):
            self.excluded = set()

        self._atlas_raw_boxes = boxes
        self._atlas_order = list(boxes)
        self._atlas_raws = raws
        return raws

    def _atlas_swap(self, i, j):
        n = len(self._atlas_raws)
        if i == j or not (0 <= i < n and 0 <= j < n):
            return
        for lst in (self._atlas_raws, self._atlas_raw_boxes):
            lst[i], lst[j] = lst[j], lst[i]
        self._atlas_order = list(self._atlas_raw_boxes)
        ei, ej = i in self.excluded, j in self.excluded
        self.excluded.discard(i); self.excluded.discard(j)
        if ei: self.excluded.add(j)
        if ej: self.excluded.add(i)
        self._tray_refresh_atlas_tray()
        self._atlas_assemble()

    def _atlas_move(self, src, dst, after):
        """Take src out and insert it before/after dst; the rest shift."""
        n = len(self._atlas_raws)
        if not (0 <= src < n and 0 <= dst < n):
            return
        order = [i for i in range(n) if i != src]
        order.insert(order.index(dst) + (1 if after else 0), src)
        if order == list(range(n)):
            return
        self._atlas_raws = [self._atlas_raws[i] for i in order]
        self._atlas_raw_boxes = [self._atlas_raw_boxes[i] for i in order]
        self._atlas_order = list(self._atlas_raw_boxes)
        self.excluded = {new for new, old in enumerate(order) if old in self.excluded}
        self._tray_refresh_atlas_tray()
        self._atlas_assemble()

    def _atl_cell_at(self, x, y, zone=False):
        """Raw index of the atlas cell under canvas point, or None.
        With zone=True returns (index, 'left'|'center'|'right')."""
        vis = self._atlas_vis
        cmap = getattr(self, "_atlas_cell_map", [])
        if vis is None or not cmap:
            return (None, None) if zone else None
        cw = self._canvas.winfo_width() or 800
        ch = self._canvas.winfo_height() or 600
        scale = min(cw/vis.width, ch/vis.height) * self._cv_zoom
        ix = (x - self._cv_img_ox) / scale
        iy = (y - self._cv_img_oy) / scale
        if ix < 0 or iy < 0:
            return (None, None) if zone else None
        c = int(ix // self._atlas_cell_w)
        r = int(iy // self._atlas_cell_h)
        if c >= self._atlas_cols_n or r >= self._atlas_rows_n:
            return (None, None) if zone else None
        k = r * self._atlas_cols_n + c
        if k >= len(cmap):
            return (None, None) if zone else None
        if not zone:
            return cmap[k]
        fx = (ix / self._atlas_cell_w) - c
        return cmap[k], ("left" if fx < 0.25 else "right" if fx > 0.75 else "center")

    def _atl_press(self, e):
        self._canvas.focus_set()
        self._atl_src = self._atl_cell_at(e.x, e.y)
        self._atl_moved = False
        if self._atl_src is None:
            self._cv_pan_press(e)

    def _atl_drag(self, e):
        if self._atl_src is None:
            self._cv_pan_drag(e)
            return
        self._atl_moved = True
        cv = self._canvas
        cv.delete("atl_hl")
        vis = self._atlas_vis
        cw = cv.winfo_width() or 800
        ch = cv.winfo_height() or 600
        scale = min(cw/vis.width, ch/vis.height) * self._cv_zoom
        cmap = self._atlas_cell_map
        k = cmap.index(self._atl_src) if self._atl_src in cmap else None
        cw_, ch_ = self._atlas_cell_w * scale, self._atlas_cell_h * scale

        def cell_xy(idx):
            r, c = divmod(cmap.index(idx), self._atlas_cols_n)
            return self._cv_img_ox + c*cw_, self._cv_img_oy + r*ch_
        if k is not None:
            x0, y0 = cell_xy(self._atl_src)
            cv.create_rectangle(x0, y0, x0+cw_, y0+ch_, outline="#a36b20", width=3, tags="atl_hl")
        dst, zn = self._atl_cell_at(e.x, e.y, zone=True)
        if dst is not None and dst != self._atl_src:
            x0, y0 = cell_xy(dst)
            if zn == "center":
                cv.create_rectangle(x0, y0, x0+cw_, y0+ch_, outline="#a36b20", width=3, tags="atl_hl")
            else:
                lx = x0 if zn == "left" else x0 + cw_
                cv.create_line(lx, y0, lx, y0+ch_, fill=self.palette.ACC, width=5, tags="atl_hl")

    def _atl_release(self, e):
        src = getattr(self, "_atl_src", None)
        self._atl_src = None
        self._canvas.delete("atl_hl")
        if src is None:
            self._cv_pan_release()
            return
        dst, zn = self._atl_cell_at(e.x, e.y, zone=True)
        if dst is None or dst == src:
            return
        if zn == "center":
            self._atlas_swap(src, dst)
        else:
            self._atlas_move(src, dst, after=(zn == "right"))

    def _atlas_reset_order(self):
        self._atlas_order = []
        self._atlas_update()

    def _atlas_build(self):
        cell0 = max(4, self._atlas_cell.get() if hasattr(self, "_atlas_cell") else 64)
        raws_all = self._atlas_raws
        if not raws_all:
            return None, 0, cell0, cell0, 0, 0
        cols   = max(1, self._atlas_cols.get() if hasattr(self, "_atlas_cols") else 8)
        mode   = self._atlas_fit_mode.get() if hasattr(self, "_atlas_fit_mode") else "trim"
        no_up  = self._atlas_no_upscale.get() if hasattr(self, "_atlas_no_upscale") else True
        norm_w = self._atlas_align_w.get() if hasattr(self, "_atlas_align_w") else True
        norm_h = self._atlas_align_h.get() if hasattr(self, "_atlas_align_h") else True
        raws = [p for i, p in enumerate(raws_all) if i not in self.excluded]
        if not raws:
            return None, 0, cell0, cell0, 0, 0
        cell_map = [i for i in range(len(raws_all)) if i not in self.excluded]
        removed = 0
        if hasattr(self, "_atlas_dedup") and self._atlas_dedup.get():
            before = {id(p): i for i, p in zip(cell_map, raws)}
            raws, removed = self._dedup_raws(raws, self._atlas_dedup_thresh.get())
            cell_map = [before[id(p)] for p in raws]
        self._atlas_removed = removed
        self._atlas_cell_map = cell_map
        if not raws:
            return None, 0, cell0, cell0, 0, 0
        cell_w = cell0 if norm_w else max(p.width for p in raws)
        cell_h = cell0 if norm_h else max(p.height for p in raws)
        if mode == "trim":
            # Tight extraction must never crop a large character to a preset cell.
            cell_w = max(cell_w, max(p.width for p in raws))
            cell_h = max(cell_h, max(p.height for p in raws))
        tiles = []
        for pil in raws:
            if mode == "scale":
                if norm_w and norm_h:
                    scale = min(cell_w/pil.width, cell_h/pil.height)
                elif norm_w:
                    scale = cell_w/pil.width
                elif norm_h:
                    scale = cell_h/pil.height
                else:
                    scale = 1.0
                if no_up:
                    scale = min(scale, 1.0)
                if scale != 1.0:
                    nw = max(1, round(pil.width*scale))
                    nh = max(1, round(pil.height*scale))
                    pil = pil.resize((nw, nh), self._resampling())
            tiles.append(pil)
        if not norm_w:
            cell_w = max(t.width for t in tiles)
        if not norm_h:
            cell_h = max(t.height for t in tiles)
        n    = len(tiles)
        cols = min(cols, n)
        rows = (n + cols - 1) // cols
        sheet = Image.new("RGBA", (cols*cell_w, rows*cell_h), (0,0,0,0))
        for i, pil in enumerate(tiles):
            r, c = divmod(i, cols)
            ox = c*cell_w + (cell_w-pil.width)//2
            oy = r*cell_h + (cell_h-pil.height)//2
            sheet.paste(pil, (ox, oy))
        return sheet, n, cell_w, cell_h, cols, rows

    def _atlas_assemble(self):
        try:
            sheet, n, cell_w, cell_h, cols, rows = self._atlas_build()
        except Exception:
            return
        self._atlas_apply(sheet, n, cell_w, cell_h, cols, rows)

    def _atlas_update(self, *_):
        if self.src_img is None and not getattr(self, "_atlas_imported", False):
            self._atlas_vis = None
            self._cv_draw()
            return
        try:
            self._atlas_detect_raws()
            self._tray_refresh_atlas_tray()
            sheet, n, cell_w, cell_h, cols, rows = self._atlas_build()
        except Exception:
            return
        self._atlas_apply(sheet, n, cell_w, cell_h, cols, rows)

    def _tray_refresh_atlas_tray(self):
        SZ, PAD = self._TRAY_SZ, self._TRAY_PAD
        tc = self._tray_canvas
        tc.delete("all")
        self._tray_photos = []
        raws = self._atlas_raws
        for i, pil in enumerate(raws):
            excluded = i in self.excluded
            thumb = pil.copy()
            thumb.thumbnail((SZ-4, SZ-4), Image.LANCZOS)
            cell = self._tc_checker(SZ, SZ).convert("RGBA")
            ox = (SZ - thumb.width)  // 2
            oy = (SZ - thumb.height) // 2
            cell.alpha_composite(thumb.convert("RGBA"), (ox, oy))
            if excluded:
                overlay = Image.new("RGBA", (SZ, SZ), (160, 0, 0, 130))
                cell = Image.alpha_composite(cell, overlay)
                d = ImageDraw.Draw(cell)
                d.line([(4,4),(SZ-4,SZ-4)], fill=(255,60,60), width=2)
                d.line([(SZ-4,4),(4,SZ-4)], fill=(255,60,60), width=2)
            border_col = self.palette.RED if excluded else self.palette.BORDER
            d2 = ImageDraw.Draw(cell)
            d2.rectangle([0,0,SZ-1,SZ-1], outline=border_col, width=2)
            photo = ImageTk.PhotoImage(cell)
            self._tray_photos.append(photo)
            x = PAD + i * (SZ + PAD)
            tc.create_image(x, PAD, anchor=tk.NW, image=photo)
        total_w = PAD + len(raws) * (SZ + PAD)
        tc.configure(scrollregion=(0, 0, max(total_w, 1), SZ + PAD*2))
        n_exc = len(self.excluded)
        n_vis = len(raws) - n_exc
        txt = (f"Атлас-трей: {n_vis} из {len(raws)}  (исключено: {n_exc})" if n_exc
               else f"Атлас-трей: {len(raws)} объектов")
        self._tray_count_lbl.config(text=txt)
        self._tray_actions(n_vis, len(raws))

    def _atlas_apply(self, sheet, n, cell_w, cell_h, cols, rows):
        total   = len(self._atlas_raws)
        n_exc   = len(self.excluded)
        removed = getattr(self, "_atlas_removed", 0)
        cnt_txt = f"Найдено: {total}"
        if n_exc: cnt_txt += f"  (исключено: {n_exc})"
        if removed: cnt_txt += f"  (дубл.: {removed})"
        if hasattr(self, "_atlas_cnt_lbl"):
            self._atlas_cnt_lbl.config(text=cnt_txt)
        if hasattr(self, "_atlas_dedup_lbl"):
            self._atlas_dedup_lbl.config(text=f"Удалено дубл.: {removed}" if removed else "")
        self._atlas_sheet = sheet
        if sheet is None:
            self._atlas_vis = None
            self._cv_draw()
            if hasattr(self, "_atlas_size_lbl"):
                self._atlas_size_lbl.config(text="Размер: —")
            return
        self._atlas_cell_w = cell_w
        self._atlas_cell_h = cell_h
        self._atlas_cols_n = cols
        self._atlas_rows_n = rows
        vis = self._tc_checker(sheet.width, sheet.height, cs=12).convert("RGBA")
        vis.alpha_composite(sheet.convert("RGBA"), (0, 0))
        draw = ImageDraw.Draw(vis)
        for r in range(rows):
            for c in range(cols):
                x, y = c*cell_w, r*cell_h
                draw.rectangle([x, y, x+cell_w-1, y+cell_h-1], outline=self.palette.ACC, width=1)
        self._atlas_vis = vis
        cell_txt = f"{cell_w}×{cell_h}" if cell_w != cell_h else f"{cell_w}"
        if hasattr(self, "_atlas_size_lbl"):
            self._atlas_size_lbl.config(
                text=f"{sheet.width}×{sheet.height}px  {cols}×{rows}яч  {cell_txt}px/яч")
        if hasattr(self, "_atlas_zoom_lbl"):
            self._atlas_zoom_lbl.config(text=f"{int(self._cv_zoom*100)}%")
        self._cv_draw()

    def _atlas_preset(self, v):
        if hasattr(self, "_atlas_cell"):
            self._atlas_cell.set(v)
        self._atlas_update()

    def _atlas_mode_changed(self):
        mode = self._atlas_fit_mode.get() if hasattr(self, "_atlas_fit_mode") else "trim"
        state = tk.NORMAL if mode == "scale" else tk.DISABLED
        if hasattr(self, "_atlas_noup_chk"):
            self._atlas_noup_chk.config(state=state)
        self._atlas_update()

    @file_operation
    def _atlas_save(self):
        if self.src_img is None and not getattr(self, "_atlas_imported", False):
            messagebox.showwarning("Ошибка", "Откройте изображение")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._outdir_auto = False
            self._add_recent(d)
            self._update_outdir_lbl(d)
        sheet, n, *_ = self._atlas_build()
        if sheet is None:
            messagebox.showwarning("Ошибка", "Объекты не найдены")
            return
        self._atlas_sheet = sheet
        name = self._safe_name(self._atlas_name.get(), "atlas") + ".png"
        out = os.path.join(self.outdir, name)
        existed = os.path.exists(out)
        if existed and not self._confirm_replace(out):
            return
        self._atomic_image(sheet, out, overwrite=existed)
        self._atlas_last_out = out
        self._atlas_target_lbl.config(text=f"Файл для перезаписи:\n{os.path.abspath(out)}")
        if hasattr(self, "_atlas_overwrite_btn"):
            self._atlas_overwrite_btn.config(state=tk.NORMAL)
        messagebox.showinfo("Готово!",
            f"Атлас {sheet.width}×{sheet.height}px, {n} объектов\nСохранён: {out}")

    @file_operation
    def _atlas_overwrite(self):
        if self.src_img is None and not getattr(self, "_atlas_imported", False):
            messagebox.showwarning("Ошибка", "Откройте изображение")
            return
        target = self._atlas_last_out
        if not target:
            self._atlas_save()
            return
        sheet, n, *_ = self._atlas_build()
        if sheet is None:
            messagebox.showwarning("Ошибка", "Объекты не найдены")
            return
        if not self._confirm_replace(target):
            return
        if not target.lower().endswith(".png"):
            messagebox.showerror("Ошибка", "Атлас сохраняется в PNG. Используйте «Сохранить атлас».")
            return
        self._atomic_image(sheet, target, overwrite=True)
        self._atlas_last_out = target
        messagebox.showinfo("Готово!",
            f"Атлас {sheet.width}×{sheet.height}px, {n} объектов\nПерезаписан: {target}")

    @file_operation
    def _atlas_export_files(self):
        if not self._atlas_raws:
            messagebox.showwarning("Ошибка", "Нет спрайтов")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._outdir_auto = False
            self._add_recent(d)
            self._update_outdir_lbl(d)
        raws = [p for i, p in enumerate(self._atlas_raws) if i not in self.excluded]
        if hasattr(self, "_atlas_dedup") and self._atlas_dedup.get():
            raws, _ = self._dedup_raws(raws, self._atlas_dedup_thresh.get())
        if not raws:
            messagebox.showwarning("Ошибка", "После фильтрации нет спрайтов")
            return
        base = self._safe_name(self._atlas_name.get(), "sprite")
        idx  = self._next_idx(self.outdir, base + "_")
        for pil in raws:
            self._atomic_image(pil, os.path.join(self.outdir, f"{base}_{idx:04d}.png"))
            idx += 1
        messagebox.showinfo("Готово!", f"Сохранено {len(raws)} спрайтов в:\n{self.outdir}")

    # ══════════════════════════════════════════════════════════════════
    #  TILETEST TOOL
    # ══════════════════════════════════════════════════════════════════

    def _tc_size_changed(self):
        sz = self._tc_size_var.get() if hasattr(self, "_tc_size_var") else 64
        if hasattr(self, "_tc_sel_w"):
            self._tc_sel_w.set(sz)
        if hasattr(self, "_tc_sel_h"):
            self._tc_sel_h.set(sz)
        if self.src_img is not None:
            pil = self._cv2pil(self.src_img)
            if pil:
                iw, ih = pil.size
                self._tc_cx = int(max(0, min(self._tc_cx, iw-sz)))
                self._tc_cy = int(max(0, min(self._tc_cy, ih-sz)))
        if hasattr(self, "_tc_offset_lbl"):
            self._tc_offset_lbl.config(text=f"X: {self._tc_cx}   Y: {self._tc_cy}")
        self._cv_draw()

    def _tc_reset(self):
        self._tc_cx = 0
        self._tc_cy = 0
        if hasattr(self, "_tc_offset_lbl"):
            self._tc_offset_lbl.config(text="X: 0   Y: 0")
        self._cv_draw()

    def _tc_press(self, e):
        if self.src_img is None: return
        self._canvas.focus_set()
        pil = self._cv2pil(self.src_img)
        if pil is None: return
        cw = self._canvas.winfo_width() or 800
        ch = self._canvas.winfo_height() or 600
        half = cw // 2 - 1
        if e.x > half: return
        iw, ih = pil.size
        fit = min(half/iw, ch/ih)
        scale = fit * self._tc_zoom
        sw = self._tc_sel_w.get() if hasattr(self, "_tc_sel_w") else 64
        sh = self._tc_sel_h.get() if hasattr(self, "_tc_sel_h") else 64
        if iw < sw or ih < sh: return
        ix = (e.x - self._tc_ox) / scale
        iy = (e.y - self._tc_oy) / scale
        self._tc_cx = int(max(0, min(ix - sw/2, iw-sw)))
        self._tc_cy = int(max(0, min(iy - sh/2, ih-sh)))
        if hasattr(self, "_tc_snap") and self._tc_snap.get():
            sz = self._tc_size_var.get() if hasattr(self, "_tc_size_var") else 64
            self._tc_cx = (self._tc_cx // sz) * sz
            self._tc_cy = (self._tc_cy // sz) * sz
        self._tc_drag0 = (e.x, e.y, self._tc_cx, self._tc_cy)
        if hasattr(self, "_tc_offset_lbl"):
            self._tc_offset_lbl.config(text=f"X: {self._tc_cx}   Y: {self._tc_cy}")
        self._cv_draw()

    def _tc_drag(self, e):
        if self._tc_drag0 is None or self.src_img is None: return
        pil = self._cv2pil(self.src_img)
        if pil is None: return
        cw = self._canvas.winfo_width() or 800
        ch = self._canvas.winfo_height() or 600
        half = cw // 2 - 1
        iw, ih = pil.size
        fit = min(half/iw, ch/ih)
        scale = fit * self._tc_zoom
        sw = self._tc_sel_w.get() if hasattr(self, "_tc_sel_w") else 64
        sh = self._tc_sel_h.get() if hasattr(self, "_tc_sel_h") else 64
        sx, sy, cx0, cy0 = self._tc_drag0
        dx = (e.x - sx) / scale
        dy = (e.y - sy) / scale
        nx = cx0 + dx
        ny = cy0 + dy
        if hasattr(self, "_tc_snap") and self._tc_snap.get():
            sn = self._tc_size_var.get() if hasattr(self, "_tc_size_var") else 64
            nx = round(nx / sn) * sn
            ny = round(ny / sn) * sn
        self._tc_cx = int(max(0, min(nx, iw-sw)))
        self._tc_cy = int(max(0, min(ny, ih-sh)))
        if hasattr(self, "_tc_offset_lbl"):
            self._tc_offset_lbl.config(text=f"X: {self._tc_cx}   Y: {self._tc_cy}")
        self._cv_draw()

    def _tc_release(self, _=None):
        self._tc_drag0 = None

    @file_operation
    def _tc_save(self):
        if self.src_img is None:
            messagebox.showwarning("Ошибка", "Откройте изображение")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._outdir_auto = False
            self._add_recent(d)
            self._update_outdir_lbl(d)
        pil = self._cv2pil(self.src_img)
        if pil is None: return
        pil = pil.convert("RGBA")
        iw, ih = pil.size
        sw = self._tc_sel_w.get() if hasattr(self, "_tc_sel_w") else 64
        sh = self._tc_sel_h.get() if hasattr(self, "_tc_sel_h") else 64
        if iw < sw or ih < sh:
            messagebox.showwarning("Ошибка", f"Изображение меньше {sw}×{sh}")
            return
        name = self._safe_name(self._tc_name_var.get(), "tile")
        prefix = name + "_"
        x = max(0, min(self._tc_cx, iw-sw))
        y = max(0, min(self._tc_cy, ih-sh))
        tile = pil.crop((x, y, x+sw, y+sh))
        idx = self._next_idx(self.outdir, prefix)
        out = os.path.join(self.outdir, f"{prefix}{idx:04d}.png")
        self._atomic_image(tile, out)
        messagebox.showinfo("Готово!", f"Кроп {sw}×{sh} сохранён:\n{out}")

    # ══════════════════════════════════════════════════════════════════
    #  PROJECT SAVE / LOAD
    # ══════════════════════════════════════════════════════════════════

    @file_operation
    def project_save(self):
        path = filedialog.asksaveasfilename(
            title="Сохранить проект",
            defaultextension=".smproj",
            filetypes=[("Sprite Manufacturer Project", "*.smproj"), ("Все файлы", "*.*")])
        if not path: return
        data = {
            "version": 6,
            "source_path": self.src_path or "",
            "outdir": self.outdir,
            "last_out": self._atlas_last_out or "",
            "tool": self.tool,
            "settings": {
                "background_rgb": self._background_rgb,
                "background_mode": self._background_mode.get(),
                "background_preview": self._background_preview.get(),
                "object_mode": self._auto_object_mode.get(),
                "auto_group_gap": self._auto_group_gap.get(),
                "pixel_art": self._pixel_art.get(),
                "edge_bleed": self._edge_bleed.get(),
                "edge_smooth": self._edge_smooth.get(),
                "edge_choke": self._edge_choke.get(),
                "export_padding": self._export_padding.get(),
                "mask_radius": self._mask_radius.get(),
                "auto_scale_mode": self._auto_scale_mode.get(),
                "auto_scale_w": self._auto_scale_w.get(),
                "auto_scale_h": self._auto_scale_h.get(),
                "auto_thresh": self._auto_thresh.get(),
                "auto_min": self._auto_min.get(),
                "auto_sep": self._auto_sep.get(),
                "atlas_thresh":       self._atlas_thresh.get() if hasattr(self, "_atlas_thresh") else 10,
                "atlas_min":          self._atlas_min.get() if hasattr(self, "_atlas_min") else 12,
                "atlas_sep":          self._atlas_sep.get() if hasattr(self, "_atlas_sep") else 0,
                "atlas_cell":         self._atlas_cell.get() if hasattr(self, "_atlas_cell") else 64,
                "atlas_fit_mode":     self._atlas_fit_mode.get() if hasattr(self, "_atlas_fit_mode") else "trim",
                "atlas_no_upscale":   self._atlas_no_upscale.get() if hasattr(self, "_atlas_no_upscale") else True,
                "atlas_align_w":      self._atlas_align_w.get() if hasattr(self, "_atlas_align_w") else True,
                "atlas_align_h":      self._atlas_align_h.get() if hasattr(self, "_atlas_align_h") else True,
                "atlas_dedup":        self._atlas_dedup.get() if hasattr(self, "_atlas_dedup") else False,
                "atlas_dedup_thresh": self._atlas_dedup_thresh.get() if hasattr(self, "_atlas_dedup_thresh") else 95,
                "atlas_cols":         self._atlas_cols.get() if hasattr(self, "_atlas_cols") else 8,
                "atlas_name":         self._atlas_name.get() if hasattr(self, "_atlas_name") else "atlas",
            },
        }
        if self.src_img is not None:
            buf = io.BytesIO()
            self._cv2pil(self.src_img).save(buf, format="PNG")
            data["source_data"] = base64.b64encode(buf.getvalue()).decode()
            if self._mask_marks is not None and self._mask_marks.any():
                data["mask_data"] = base64.b64encode(cv2.imencode(".png", self._mask_marks)[1]).decode()
            if self._refined_key == self._background_signature(self.src_img, self._auto_thresh.get()):
                data["refined_alpha"] = base64.b64encode(cv2.imencode(".png", self._refined_rgba[:, :, 3])[1]).decode()
        if getattr(self, "_atlas_imported", False):
            data["imported_sprites"] = []
            for image in self._atlas_raws:
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                data["imported_sprites"].append(base64.b64encode(buf.getvalue()).decode())
            data["excluded"] = sorted(self.excluded if self.tool == "atlas" else getattr(self, "_atlas_excluded", set()))
        def write_project(temporary):
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        self._atomic_write(path, write_project, overwrite=True)
        messagebox.showinfo("Проект сохранён", f"Сохранено:\n{path}")

    def project_load(self, path=None):
        path = path or filedialog.askopenfilename(
            title="Открыть проект",
            filetypes=[("Sprite Manufacturer Project", "*.smproj"), ("Все файлы", "*.*")])
        if not path:
            return
        numeric = {
            "auto_thresh": ("_auto_thresh", 10, 0, 100),
            "auto_min": ("_auto_min", 3, 1, 150),
            "auto_sep": ("_auto_sep", 0, 0, 150),
            "auto_group_gap": ("_auto_group_gap", 0, 0, 64),
            "export_padding": ("_export_padding", 0, 0, 64),
            "edge_choke": ("_edge_choke", 0, 0, 6),
            "mask_radius": ("_mask_radius", 8, 1, 100),
            "auto_scale_w": ("_auto_scale_w", 64, 1, 4096),
            "auto_scale_h": ("_auto_scale_h", 64, 1, 4096),
            "atlas_thresh": ("_atlas_thresh", 10, 0, 100),
            "atlas_min": ("_atlas_min", 3, 1, 150),
            "atlas_sep": ("_atlas_sep", 0, 0, 150),
            "atlas_cell": ("_atlas_cell", 64, 4, 2048),
            "atlas_dedup_thresh": ("_atlas_dedup_thresh", 95, 50, 100),
            "atlas_cols": ("_atlas_cols", 8, 1, 128),
        }
        boolean = {"background_preview": True, "pixel_art": False, "edge_bleed": True,
                   "edge_smooth": False,
                   "atlas_no_upscale": True, "atlas_align_w": True,
                   "atlas_align_h": True, "atlas_dedup": False}
        try:
            with open(path, encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, dict) or not isinstance(data.get("settings", {}), dict):
                raise ValueError("Некорректная структура проекта")
            settings = dict(data.get("settings", {}))
            if data.get("version", 3) < 4:
                old_threshold = settings.get("atlas_thresh", 245)
                if type(old_threshold) is not int or not 200 <= old_threshold <= 255:
                    raise ValueError("Некорректная настройка: atlas_thresh")
                settings["atlas_thresh"] = 255 - old_threshold
            background_rgb = settings.get("background_rgb")
            if background_rgb is not None and (
                    not isinstance(background_rgb, list) or len(background_rgb) != 3 or
                    any(type(c) is not int or not 0 <= c <= 255 for c in background_rgb)):
                raise ValueError("Некорректный цвет фона")
            choices = {"background_mode": ("auto", "solid", "checker", "alpha"),
                       "object_mode": ("objects", "single"),
                       "auto_scale_mode": ("none", "w", "h", "both")}
            for key, values in choices.items():
                if settings.get(key, values[0]) not in values:
                    raise ValueError(f"Некорректная настройка: {key}")
            for key, (_, default, low, high) in numeric.items():
                value = settings.get(key, default)
                if type(value) is not int or not low <= value <= high:
                    raise ValueError(f"Некорректная настройка: {key}")
            for key, default in boolean.items():
                if type(settings.get(key, default)) is not bool:
                    raise ValueError(f"Некорректная настройка: {key}")
            mode = settings.get("atlas_fit_mode", "trim")
            if mode not in ("trim", "scale"):
                raise ValueError("Некорректный режим подгонки")
            for key in ("source_path", "outdir", "last_out"):
                if not isinstance(data.get(key, ""), str):
                    raise ValueError(f"Некорректный путь: {key}")
            name = settings.get("atlas_name", "atlas")
            if not isinstance(name, str):
                raise ValueError("Некорректное имя атласа")
            src_path = data.get("source_path", "")
            image = None
            # Restore the saved snapshot even if the original was overwritten.
            if data.get("source_data"):
                raw = base64.b64decode(data["source_data"], validate=True)
                image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
                if image is None:
                    raise ValueError("Повреждено встроенное изображение")
            elif src_path and os.path.isfile(src_path):
                image = cv2.imdecode(np.fromfile(src_path, np.uint8), cv2.IMREAD_UNCHANGED)
                if image is None:
                    raise ValueError("Не удалось прочитать исходное изображение")
            elif src_path:
                raise ValueError(f"Исходный файл не найден: {src_path}")
            masks = {}
            for key in ("mask_data", "refined_alpha"):
                if data.get(key):
                    mask = cv2.imdecode(np.frombuffer(base64.b64decode(data[key], validate=True), np.uint8),
                                        cv2.IMREAD_UNCHANGED)
                    if image is None or mask is None or mask.ndim != 2 or mask.shape != image.shape[:2] or mask.dtype != np.uint8:
                        raise ValueError("Маска не соответствует исходному изображению")
                    if key == "mask_data" and np.any(mask > 2):
                        raise ValueError("Некорректные отметки маски")
                    masks[key] = mask
            imported = []
            payloads = data.get("imported_sprites", [])
            if not isinstance(payloads, list):
                raise ValueError("Некорректный список спрайтов")
            for payload in payloads:
                with Image.open(io.BytesIO(base64.b64decode(payload, validate=True))) as sprite:
                    imported.append(sprite.convert("RGBA"))
            excluded = data.get("excluded", [])
            if not isinstance(excluded, list) or any(type(i) is not int or not 0 <= i < len(imported) for i in excluded):
                raise ValueError("Некорректные исключения спрайтов")
        except (OSError, ValueError, TypeError, cv2.error) as error:
            messagebox.showerror("Ошибка проекта", f"Не удалось открыть проект:\n{error}")
            return False

        self.src_img = None
        self.src_path = ""
        self._reset_source_state()
        self._cv_zoom_reset()
        self._tool_set("atlas")
        self._background_rgb = tuple(background_rgb) if background_rgb is not None else None
        self._background_mode.set(settings.get("background_mode", "auto"))
        self._auto_object_mode.set(settings.get("object_mode", "objects"))
        self._auto_scale_mode.set(settings.get("auto_scale_mode", "none"))
        self._background_update_labels()
        for key, (attribute, default, _, _) in numeric.items():
            getattr(self, attribute).set(settings.get(key, default))
        for key, default in boolean.items():
            getattr(self, "_" + key).set(settings.get(key, default))
        self._atlas_fit_mode.set(mode)
        self._atlas_name.set(name)
        self.outdir = data.get("outdir", "")
        self._outdir_auto = not bool(self.outdir)
        self._update_outdir_lbl(self.outdir or "Папка не выбрана")
        self.src_img = image
        if image is not None and image.dtype == np.uint16:
            self.src_img = (image / 257).astype(np.uint8)
        self.src_path = src_path
        self._mask_marks = masks.get("mask_data")
        if "refined_alpha" in masks:
            self._refined_rgba = (cv2.cvtColor(self.src_img, cv2.COLOR_GRAY2BGRA) if self.src_img.ndim == 2 else
                                  cv2.cvtColor(self.src_img, cv2.COLOR_BGR2BGRA) if self.src_img.shape[2] == 3 else self.src_img.copy())
            self._refined_rgba[:, :, 3] = masks["refined_alpha"]
            self._refined_key = self._background_signature(self.src_img, self._auto_thresh.get())
        self._auto_scale_update()
        self._auto_contours_cache = []
        self._update_src_lbl(os.path.basename(src_path) if src_path else
                             "Из проекта" if image is not None else "Файл не выбран")
        if imported:
            self._atlas_imported = True
            self._atlas_raws = imported
            self._atlas_raw_boxes = [(i, 0, sprite.width, sprite.height) for i, sprite in enumerate(imported)]
            self.excluded = set(excluded)
        if image is not None or imported:
            self._atlas_update()
        saved_tool = data.get("tool", "atlas")
        self._tool_set(saved_tool if isinstance(saved_tool, str) and saved_tool in self._panels else "atlas")
        self._atlas_last_out = data.get("last_out") or None
        self._atlas_overwrite_btn.config(state=tk.NORMAL if self._atlas_last_out else tk.DISABLED)
        self._atlas_target_lbl.config(text=f"Файл для перезаписи:\n{os.path.abspath(self._atlas_last_out)}"
                                      if self._atlas_last_out else "Сначала сохраните атлас, чтобы выбрать файл для перезаписи.")
        self._status_var.set(f"Проект открыт: {os.path.basename(path)}")
        return True

    # ══════════════════════════════════════════════════════════════════
    #  RESIZE PANEL
    # ══════════════════════════════════════════════════════════════════

    def _build_props_resize(self, parent=None):
        p = parent if parent is not None else self._props
        self._lbl(p, "Пакетный ресайз", bold=True, size=11).pack(anchor=tk.W, pady=(0, 8))

        self._btn(p, "📂 Выбрать папку", self._resize_pick_folder, self.palette.GRN, h=2).pack(fill=tk.X, pady=3)

        if not hasattr(self, "_resize_folder_var"):
            self._resize_folder_var = tk.StringVar(value="")
        self._resize_folder_lbl = self._lbl(p, "Папка не выбрана", color=self.palette.FG2)
        self._resize_folder_lbl.pack(anchor=tk.W, pady=(0, 4))

        if not hasattr(self, "_resize_recursive"):
            self._resize_recursive = tk.BooleanVar(value=False)
        SoftCheck(p, text="Сканировать подпапки", variable=self._resize_recursive,
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(0, 6))

        self._sep(p)
        self._lbl(p, "Целевой размер (px):", bold=True).pack(anchor=tk.W, pady=(0, 5))

        if not hasattr(self, "_resize_size_var"):
            self._resize_size_var = tk.IntVar(value=64)
        szf = tk.Frame(p, bg=self.palette.BG); szf.pack(fill=tk.X)
        for sz in (32, 64, 128, 256, 512):
            SoftRadio(szf, text=str(sz), variable=self._resize_size_var, value=sz,
                           bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                           font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=2)

        self._lbl(p, "Выравнивать по:", color=self.palette.FG2).pack(anchor=tk.W, pady=(8, 2))
        if not hasattr(self, "_resize_axis"):
            self._resize_axis = tk.StringVar(value="both")
        axf = tk.Frame(p, bg=self.palette.BG); axf.pack(fill=tk.X)
        for val, txt in (("both", "Оба (квадрат)"), ("width", "Ширина"), ("height", "Высота")):
            SoftRadio(axf, text=txt, variable=self._resize_axis, value=val,
                           bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                           font=("Segoe UI", 9)).pack(anchor=tk.W)

        self._sep(p)
        self._lbl(p, "Папка вывода:", bold=True).pack(anchor=tk.W, pady=(0, 3))
        self._btn(p, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbls["resize"] = self._lbl(p, "Папка не выбрана", color=self.palette.FG2)
        self._outdir_lbls["resize"].pack(anchor=tk.W, pady=(3, 0))

        if not hasattr(self, "_resize_same_folder"):
            self._resize_same_folder = tk.BooleanVar(value=False)
        SoftCheck(p, text="Сохранять рядом с оригиналом", variable=self._resize_same_folder,
                       bg=self.palette.BG, fg=self.palette.FG, selectcolor=self.palette.BTN, activebackground=self.palette.BG,
                       font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(4, 0))

        self._sep(p)
        self._resize_status_lbl = self._lbl(p, "", color=self.palette.GOLD, bold=True)
        self._resize_status_lbl.pack(anchor=tk.W, pady=(0, 4))

        self._resize_run_btn = self._btn(p, "Изменить размеры", self._resize_run, self.palette.ACC, h=2)
        self._resize_run_btn.pack(fill=tk.X, pady=(4, 3))
        self._resize_cancel_btn = self._btn(p, "Остановить", self._resize_cancel, state=tk.DISABLED)
        self._resize_cancel_btn.pack(fill=tk.X, pady=3)
        self._lbl(p, "Оригиналы сохраняются. Копии рядом получают суффикс _resized.",
                  color=self.palette.FG2, size=9).pack(anchor=tk.W, pady=5)

    def _resize_cancel(self):
        self._resize_cancelled = True

    def _resize_pick_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку с изображениями")
        if not folder:
            return
        self._resize_set_folder(folder)

    @file_operation
    def _resize_set_folder(self, folder):
        self._resize_folder_var.set(folder)
        self._resize_preview_files = sorted(os.path.join(folder, name) for name in os.listdir(folder)
                                            if os.path.splitext(name)[1].lower() in _IMG_EXTS
                                            and os.path.isfile(os.path.join(folder, name)))
        self._cv_draw()
        short = folder if len(folder) <= 40 else "…" + folder[-37:]
        self._resize_folder_lbl.config(text=short)
        self._add_recent(folder)

    @file_operation
    def _resize_run(self):
        if getattr(self, "_resize_running", False):
            return
        folder = self._resize_folder_var.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Ошибка", "Папка не выбрана или не существует.")
            return

        size = self._resize_size_var.get()
        axis = self._resize_axis.get()
        recursive = self._resize_recursive.get()
        same = self._resize_same_folder.get()
        outdir = self.outdir if not same else None

        if not same and not outdir:
            messagebox.showerror("Ошибка", "Выберите папку вывода или включите «Сохранять рядом с оригиналом».")
            return

        # Collect images
        files = []
        if recursive:
            for root_dir, dirs, fnames in os.walk(folder):
                if outdir and os.path.normcase(os.path.realpath(outdir)) != os.path.normcase(os.path.realpath(folder)):
                    dirs[:] = [name for name in dirs if os.path.normcase(os.path.realpath(os.path.join(root_dir, name))) != os.path.normcase(os.path.realpath(outdir))]
                for fn in fnames:
                    if os.path.splitext(fn)[1].lower() in _IMG_EXTS:
                        files.append(os.path.join(root_dir, fn))
        else:
            for fn in os.listdir(folder):
                if os.path.splitext(fn)[1].lower() in _IMG_EXTS and os.path.isfile(os.path.join(folder, fn)):
                    files.append(os.path.join(folder, fn))

        if not files:
            messagebox.showinfo("Пусто", "В выбранной папке нет изображений.")
            return

        self._resize_preview_files = files
        if self.tool == "resize":
            self._cv_draw()

        self._resize_running = True
        self._resize_cancelled = False
        self._resize_run_btn.config(state=tk.DISABLED)
        self._resize_cancel_btn.config(state=tk.NORMAL)
        if self.tool == "resize":
            self._export_current_btn.config(state=tk.DISABLED)
        pending = iter(files)
        counts = {"ok": 0, "err": 0, "processed": 0}

        def finish():
            self._resize_running = False
            self._resize_run_btn.config(state=tk.NORMAL)
            self._resize_cancel_btn.config(state=tk.DISABLED)
            msg = f"{'Остановлено' if self._resize_cancelled else 'Готово'}: {counts['ok']} файлов"
            if counts["err"]:
                msg += f", ошибок: {counts['err']}"
            self._resize_status_lbl.config(text=msg)
            self._status_var.set(msg)
            if self.tool == "resize":
                self._export_current_btn.config(state=tk.NORMAL)

        def step():
            if self._resize_cancelled:
                finish()
                return
            fpath = next(pending, None)
            if fpath is None:
                finish()
                return
            try:
                with Image.open(fpath) as original:
                    img = original.convert("RGBA")
                w, h = img.size
                if axis == "both":
                    new_w, new_h = size, size
                elif axis == "width":
                    new_w = size
                    new_h = max(1, round(h * size / w)) if w else size
                else:  # height
                    new_h = size
                    new_w = max(1, round(w * size / h)) if h else size
                img = img.resize((new_w, new_h), self._resampling())

                if same:
                    dst = fpath
                else:
                    rel = os.path.relpath(fpath, folder)
                    dst = os.path.join(outdir, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)

                # Force PNG to preserve transparency
                base, ext = os.path.splitext(dst)
                dst = base + ".png"
                if same or os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(fpath)):
                    dst = base + "_resized.png"
                candidate = dst
                index = 1
                while os.path.exists(candidate):
                    candidate = os.path.splitext(dst)[0] + f"_{index}.png"
                    index += 1
                dst = candidate
                self._atomic_image(img, dst)
                counts["ok"] += 1
            except Exception as e:
                print(f"resize error {fpath}: {e}")
                counts["err"] += 1
            counts["processed"] += 1
            self._resize_status_lbl.config(text=f"Обработано: {counts['processed']} / {len(files)}")
            self.root.after(10, step)

        self.root.after(10, step)

    # ══════════════════════════════════════════════════════════════════
    #  MISC
    # ══════════════════════════════════════════════════════════════════

    def _show_author(self):
        messagebox.showinfo("Об авторе", (
            "Автор: Shtillgor\n"
            "Сайт: https://midgro.uz/\n\n"
            "Вы можете свободно использовать это ПО,\n"
            "но обязаны указывать автора и ссылку на сайт\n"
            "в заметном месте вашего проекта."
        ))


if __name__ == "__main__":
    root = TkinterDnD.Tk(className="SpriteManufacturer")
    app = SpriteManufacturerApp(root)
    root.update()
    if "--smoke-test" in sys.argv:
        root.withdraw()
        for name, _, _ in TOOLS:
            app._tool_set(name)
            root.update_idletasks()
        root.after(100, root.destroy)
    root.mainloop()
