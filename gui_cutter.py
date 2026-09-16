"""
Sprite Manufacturer v3 — Unified Workspace
Автор: Shtillgor (https://midgro.uz/)
"""

import cv2
import numpy as np
import os
import base64
import io
import json
import subprocess
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw
from tkinterdnd2 import TkinterDnD, DND_FILES

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

BG      = "#1a1a1a"
BG2     = "#242424"
BTN     = "#333333"
FG      = "#e8e8e8"
FG2     = "#888888"
ACC     = "#e8a030"
GRN     = "#3dba6a"
RED     = "#e05050"
GOLD    = "#e8a030"
TOOL_BG = "#2a2a2a"

TOOLS = [
    ("auto",     "🔍", "Авто"),
    ("shape",    "✏️",  "Фигура"),
    ("grid",     "📐", "Сетка"),
    ("atlas",    "📦", "Атлас"),
    ("tiletest", "🎮", "Тайл-тест"),
]

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")


class SpriteManufacturerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sprite Manufacturer v3")
        self.root.geometry("1300x860")
        self.root.minsize(1000, 700)
        self.root.configure(bg=BG)
        self._set_icon()
        self.recent_dirs = self._load_config()

        # ── Shared state ──────────────────────────────────────────────
        self.src_img   = None   # cv2 BGRA
        self.src_path  = ""
        self.sprites   = []     # list of PIL RGBA
        self.excluded  = set()  # excluded tray indices
        self.outdir    = ""
        self.tool      = "auto"

        # Canvas zoom/pan
        self._cv_zoom    = 1.0
        self._cv_view_x  = 0
        self._cv_view_y  = 0
        self._cv_pan0    = None
        self._cv_img_ox  = 0
        self._cv_img_oy  = 0

        # Atlas state
        self._atlas_raws    = []
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
        self._sh_colors = ["#e74c3c","#3498db","#2ecc71","#f39c12","#9b59b6","#1abc9c"]

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

        self._build_ui()
        self.root.bind("<Control-v>", self._global_paste)
        self.root.bind("<Control-V>", self._global_paste)
        self.root.bind("<Escape>",    lambda _: self._sh_reset())

    # ══════════════════════════════════════════════════════════════════
    #  ICON / CONFIG
    # ══════════════════════════════════════════════════════════════════

    def _set_icon(self):
        p = os.path.join(os.path.dirname(__file__), "resource", "Icon.png")
        if os.path.exists(p):
            try:
                img = ImageTk.PhotoImage(file=p)
                self.root.iconphoto(False, img)
                self._icon = img
            except Exception as e:
                print(f"Icon: {e}")

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f).get("recent_dirs", [])
            except Exception:
                pass
        return []

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"recent_dirs": self.recent_dirs}, f, ensure_ascii=False, indent=4)
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

    def _lbl(self, parent, text, bold=False, color=FG, size=10):
        return tk.Label(parent, text=text, fg=color, bg=BG,
                        font=("Arial", size, "bold" if bold else "normal"))

    def _btn(self, parent, text, cmd, color=BTN, h=1, state=tk.NORMAL, font_size=10):
        return tk.Button(parent, text=text, command=cmd, bg=color, fg=FG,
                         font=("Arial", font_size, "bold"), height=h, state=state,
                         relief=tk.FLAT, activebackground=color, activeforeground=FG,
                         cursor="hand2")

    def _spinbox(self, parent, var, lo, hi, w=6, cmd=None):
        kw = dict(from_=lo, to=hi, textvariable=var, width=w, bg=BTN, fg=FG,
                  relief=tk.FLAT, highlightthickness=0, insertbackground=FG,
                  buttonbackground=BTN)
        if cmd:
            kw["command"] = cmd
        return tk.Spinbox(parent, **kw)

    def _sep(self, parent):
        ttk.Separator(parent, orient="horizontal").pack(fill=tk.X, pady=9)

    def _section(self, parent, title, expanded=True):
        hdr = tk.Frame(parent, bg=BTN, cursor="hand2")
        hdr.pack(fill=tk.X, pady=(5, 0))
        state = [expanded]
        arrow = tk.Label(hdr, text="▼" if expanded else "▶",
                         bg=BTN, fg=GOLD, font=("Arial", 9, "bold"), width=2)
        arrow.pack(side=tk.LEFT, padx=(4, 0))
        tk.Label(hdr, text=title, bg=BTN, fg=FG,
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT, pady=5)
        body = tk.Frame(parent, bg=BG)
        if expanded:
            body.pack(fill=tk.X, pady=(2, 4))
        def _toggle(_=None):
            state[0] = not state[0]
            arrow.config(text="▼" if state[0] else "▶")
            if state[0]:
                body.pack(fill=tk.X, pady=(2, 4))
            else:
                body.pack_forget()
        for w in (hdr, arrow) + tuple(hdr.winfo_children()):
            w.bind("<Button-1>", _toggle)
        hdr.bind("<Button-1>", _toggle)
        return body

    def _scrollable_frame(self, parent):
        """Returns (outer_frame, inner_frame) where inner is scrollable."""
        outer = tk.Frame(parent, width=320, bg=BG)
        outer.pack(side=tk.LEFT, fill=tk.Y)
        outer.pack_propagate(False)
        vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        sc = tk.Canvas(outer, bg=BG, highlightthickness=0, yscrollcommand=vsb.set)
        sc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=sc.yview)
        inner = tk.Frame(sc, bg=BG, padx=10, pady=8)
        wid = sc.create_window((0, 0), window=inner, anchor=tk.NW)
        sc.bind("<Configure>", lambda e: sc.itemconfig(wid, width=e.width))
        inner.bind("<Configure>", lambda e: sc.configure(scrollregion=sc.bbox("all")))
        def _scroll(e):
            if e.num == 4 or getattr(e, "delta", 0) > 0:
                sc.yview_scroll(-1, "units")
            else:
                sc.yview_scroll(1, "units")
        sc.bind("<MouseWheel>", _scroll)
        sc.bind("<Button-4>", _scroll)
        sc.bind("<Button-5>", _scroll)
        return outer, inner

    # ══════════════════════════════════════════════════════════════════
    #  BUILD MAIN UI
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # Menu bar
        menubar = tk.Menu(self.root, bg=BG2, fg=FG, activebackground=ACC,
                          activeforeground=FG, relief=tk.FLAT, borderwidth=0)
        self.root.config(menu=menubar)
        self._build_menu(menubar)

        # Main container (toolbar | canvas | props)
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        # Left toolbar (64px)
        self._toolbar = tk.Frame(main, width=64, bg=TOOL_BG)
        self._toolbar.pack(side=tk.LEFT, fill=tk.Y)
        self._toolbar.pack_propagate(False)
        self._tool_btns = {}
        self._build_toolbar()

        # Center canvas
        cv_frame = tk.Frame(main, bg=BG2)
        cv_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._canvas = tk.Canvas(cv_frame, bg="#1e2124", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._bind_canvas_common()

        # Right props panel (310px, scrollable)
        self._props_outer, self._props = self._scrollable_frame(main)

        # Bottom area: tray + statusbar
        bottom = tk.Frame(self.root, bg=BG2)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)

        # Sprite tray
        tray_frame = tk.Frame(bottom, bg=BG2)
        tray_frame.pack(fill=tk.X)
        tray_header = tk.Frame(tray_frame, bg=BG2)
        tray_header.pack(fill=tk.X)
        self._tray_count_lbl = tk.Label(tray_header, text="Трей: 0 спрайтов",
                                        bg=BG2, fg=FG2, font=("Arial", 8))
        self._tray_count_lbl.pack(side=tk.LEFT, padx=6, pady=2)
        tk.Button(tray_header, text="Очистить трей", command=self._tray_clear,
                  bg=RED, fg=FG, font=("Arial", 8, "bold"), relief=tk.FLAT,
                  cursor="hand2", pady=1).pack(side=tk.RIGHT, padx=4)
        tk.Button(tray_header, text="Сохранить все →", command=self._tray_save_all,
                  bg=GRN, fg=FG, font=("Arial", 8, "bold"), relief=tk.FLAT,
                  cursor="hand2", pady=1).pack(side=tk.RIGHT, padx=2)
        tray_row = tk.Frame(tray_frame, bg=BG2)
        tray_row.pack(fill=tk.X)
        self._tray_canvas = tk.Canvas(tray_row, bg=BG2, height=80, highlightthickness=0)
        self._tray_canvas.pack(side=tk.TOP, fill=tk.X)
        tray_hsb = ttk.Scrollbar(tray_row, orient=tk.HORIZONTAL, command=self._tray_canvas.xview)
        tray_hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tray_canvas.configure(xscrollcommand=tray_hsb.set)
        self._tray_canvas.bind("<Button-1>", self._tray_click)

        # Status bar
        self._status_var = tk.StringVar(value="Готов")
        status = tk.Label(bottom, textvariable=self._status_var,
                          bg="#17191c", fg=FG2, font=("Arial", 8),
                          anchor=tk.W, padx=8)
        status.pack(fill=tk.X, side=tk.BOTTOM)

        # Initial tool
        self._tool_set("auto")

    def _build_menu(self, menubar):
        # Файл
        fm = tk.Menu(menubar, tearoff=0, bg=BG2, fg=FG,
                     activebackground=ACC, activeforeground=FG)
        menubar.add_cascade(label="Файл", menu=fm)
        fm.add_command(label="Открыть изображение",   command=self._menu_open_src)
        fm.add_command(label="Вставить из буфера (Ctrl+V)", command=self._global_paste)
        fm.add_separator()
        fm.add_command(label="Открыть проект (.smproj)", command=self.project_load)
        fm.add_command(label="Сохранить проект",          command=self.project_save)
        fm.add_separator()
        fm.add_command(label="Выбрать папку вывода",    command=self._menu_choose_outdir)
        fm.add_command(label="Сохранить атлас",          command=self._atlas_save)
        fm.add_command(label="Сохранить спрайты по файлам", command=self._tray_save_all)
        fm.add_separator()
        fm.add_command(label="Выход", command=self.root.destroy)

        # Правка
        em = tk.Menu(menubar, tearoff=0, bg=BG2, fg=FG,
                     activebackground=ACC, activeforeground=FG)
        menubar.add_cascade(label="Правка", menu=em)
        em.add_command(label="Очистить трей",        command=self._tray_clear)
        em.add_command(label="Очистить исходное изображение", command=self._clear_src)

        # Вид
        vm = tk.Menu(menubar, tearoff=0, bg=BG2, fg=FG,
                     activebackground=ACC, activeforeground=FG)
        menubar.add_cascade(label="Вид", menu=vm)
        vm.add_command(label="Сбросить зум", command=self._cv_zoom_reset)

        # Справка
        hm = tk.Menu(menubar, tearoff=0, bg=BG2, fg=FG,
                     activebackground=ACC, activeforeground=FG)
        menubar.add_cascade(label="Справка", menu=hm)
        hm.add_command(label="Об авторе", command=self._show_author)

    def _build_toolbar(self):
        for name, icon, label in TOOLS:
            f = tk.Frame(self._toolbar, bg=TOOL_BG, cursor="hand2")
            f.pack(fill=tk.X, pady=2, padx=2)
            btn = tk.Button(f, text=f"{icon}\n{label}",
                            command=lambda n=name: self._tool_set(n),
                            bg=TOOL_BG, fg=FG, font=("Arial", 8), relief=tk.FLAT,
                            activebackground=ACC, activeforeground=FG,
                            cursor="hand2", width=6, height=3)
            btn.pack(fill=tk.X)
            self._tool_btns[name] = btn

    # ══════════════════════════════════════════════════════════════════
    #  TOOL SWITCHING
    # ══════════════════════════════════════════════════════════════════

    def _tool_set(self, name):
        self.tool = name
        for n, btn in self._tool_btns.items():
            btn.config(bg=ACC if n == name else TOOL_BG)
        self._rebuild_props()
        self._rebind_canvas(name)
        self._cv_draw()

    def _rebuild_props(self):
        for w in self._props.winfo_children():
            w.destroy()
        builder = {
            "auto":     self._build_props_auto,
            "shape":    self._build_props_shape,
            "grid":     self._build_props_grid,
            "atlas":    self._build_props_atlas,
            "tiletest": self._build_props_tiletest,
        }.get(self.tool)
        if builder:
            builder()

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
        else:
            cv.config(cursor="fleur")
            cv.bind("<ButtonPress-1>",   self._cv_pan_press)
            cv.bind("<B1-Motion>",       self._cv_pan_drag)
            cv.bind("<ButtonRelease-1>", self._cv_pan_release)

    def _bind_canvas_common(self):
        cv = self._canvas
        cv.bind("<Configure>",    lambda _: self._cv_draw())
        cv.bind("<MouseWheel>",   self._cv_wheel)
        cv.bind("<Button-4>",     self._cv_wheel)
        cv.bind("<Button-5>",     self._cv_wheel)
        cv.bind("<ButtonPress-2>",   self._cv_pan_press)
        cv.bind("<B2-Motion>",       self._cv_pan_drag)
        cv.bind("<ButtonRelease-2>", self._cv_pan_release)

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
            fit = min(cw/iw, ch/ih)
            old = fit * self._tc_zoom
            ix = (e.x - self._tc_ox) / old
            iy = (e.y - self._tc_oy) / old
            self._tc_zoom = max(0.05, min(30.0, self._tc_zoom * factor))
            ns = fit * self._tc_zoom
            self._tc_vx = int(e.x - ix*ns - (cw - int(iw*ns))//2)
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
        if self.tool == "atlas":
            self._cv_draw_atlas()
        elif self.tool == "tiletest":
            self._cv_draw_tiletest()
        else:
            self._cv_draw_source()

    def _cv_draw_source(self):
        cv = self._canvas
        cw = cv.winfo_width() or 800
        ch = cv.winfo_height() or 600
        cv.delete("all")
        if self.src_img is None:
            cv.create_text(cw//2, ch//2,
                text="Откройте изображение или перетащите сюда",
                fill=FG2, font=("Arial", 13), justify=tk.CENTER)
            return
        pil = self._cv2pil(self.src_img)
        if pil is None:
            return
        iw, ih = pil.size
        fit = min(cw/iw, ch/ih)
        scale = fit * self._cv_zoom
        nw = max(1, int(iw*scale))
        nh = max(1, int(ih*scale))
        self._cv_img_ox = (cw-nw)//2 + self._cv_view_x
        self._cv_img_oy = (ch-nh)//2 + self._cv_view_y
        resamp = Image.NEAREST if scale > 3 else Image.LANCZOS
        disp = pil.resize((nw, nh), resamp)
        # Draw tool overlays on the PIL image
        disp = self._cv_overlay(disp, scale)
        self._cv_photo = ImageTk.PhotoImage(disp)
        cv.create_image(self._cv_img_ox, self._cv_img_oy, anchor=tk.NW, image=self._cv_photo)
        # status
        self._status_var.set(f"Зум: {int(self._cv_zoom*100)}%  |  {iw}×{ih} px  |  {os.path.basename(self.src_path) if self.src_path else ''}")

    def _cv_overlay(self, disp, scale):
        """Draw tool-specific overlays on the display PIL image."""
        draw = ImageDraw.Draw(disp)
        if self.tool == "auto":
            if self.src_img is not None and hasattr(self, "_auto_contours_cache"):
                for c in self._auto_contours_cache:
                    x, y, w, h = cv2.boundingRect(c)
                    rx1 = int(x*scale)
                    ry1 = int(y*scale)
                    rx2 = int((x+w)*scale)
                    ry2 = int((y+h)*scale)
                    draw.rectangle([rx1, ry1, rx2, ry2], outline="#00dc50", width=2)
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
                    draw.line(sc, fill="#ffff00", width=2)
        elif self.tool == "grid":
            if self.src_img is not None and hasattr(self, "_grid_tiles_cache"):
                for (x, y, tw, th) in self._grid_tiles_cache:
                    rx1 = int(x*scale)
                    ry1 = int(y*scale)
                    rx2 = int((x+tw)*scale)
                    ry2 = int((y+th)*scale)
                    draw.rectangle([rx1, ry1, rx2, ry2], outline="#00e050", width=1)
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
                fill=FG2, font=("Arial", 13), justify=tk.CENTER)
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
        cv.create_text(cw-8, ch-8, text=info, anchor=tk.SE, fill=GOLD, font=("Arial", 9, "bold"))
        self._status_var.set(f"Атлас: {vis.width}×{vis.height}  Зум: {int(self._cv_zoom*100)}%")

    def _cv_draw_tiletest(self):
        cv = self._canvas
        cw = cv.winfo_width() or 800
        ch = cv.winfo_height() or 600
        cv.delete("all")
        if self.src_img is None:
            cv.create_text(cw//2, ch//2,
                text="Откройте изображение для тайл-теста",
                fill=FG2, font=("Arial", 13), justify=tk.CENTER)
            return
        # Split canvas: left=source, right=preview
        half = cw // 2 - 1
        self._tc_draw_source(half, ch)
        self._tc_draw_preview(half, ch, half + 2)
        cv.create_line(half+1, 0, half+1, ch, fill=BTN, width=2)

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
                draw.line([(cx2,0),(cx2,nh-1)], fill="#3a3a5e", width=1)
        for gy in range(0, ih+1, sz):
            cy2 = int(gy*scale)
            if 0 <= cy2 <= nh:
                draw.line([(0,cy2),(nw-1,cy2)], fill="#3a3a5e", width=1)
        sw = self._tc_sel_w.get() if hasattr(self, "_tc_sel_w") else sz
        sh = self._tc_sel_h.get() if hasattr(self, "_tc_sel_h") else sz
        if iw >= sw and ih >= sh:
            rx = int(self._tc_cx * scale)
            ry = int(self._tc_cy * scale)
            rw = max(2, int(sw*scale))
            rh = max(2, int(sh*scale))
            draw.rectangle([rx, ry, rx+rw-1, ry+rh-1], outline="#ffff00", width=2)
            draw.rectangle([rx+2, ry+2, rx+rw-3, ry+rh-3], outline="#ff6600", width=1)
        ph = ImageTk.PhotoImage(bg)
        self._tc_src_ph = ph
        self._canvas.create_image(self._tc_ox, self._tc_oy, anchor=tk.NW, image=ph)
        self._canvas.create_text(cw//2, ch-12, text="Исходное — тяните для смещения",
                                  fill=FG2, font=("Arial", 8, "italic"))

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
                text=f"Изображение меньше {sw}×{sh}", fill=RED, font=("Arial", 11))
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
            fill=FG2, font=("Arial", 8, "italic"))

    def _tc_checker(self, w, h, cs=8):
        img  = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)
        for r in range((h+cs-1)//cs):
            for c in range((w+cs-1)//cs):
                col = "#666666" if (r+c)%2==0 else "#999999"
                x0, y0 = c*cs, r*cs
                draw.rectangle([x0, y0, min(x0+cs,w)-1, min(y0+cs,h)-1], fill=col)
        return img

    # ══════════════════════════════════════════════════════════════════
    #  PROPS PANEL BUILDERS
    # ══════════════════════════════════════════════════════════════════

    def _build_props_auto(self):
        p = self._props
        self._lbl(p, "Авто-детекция", bold=True, size=11).pack(anchor=tk.W, pady=(0,8))
        self._btn(p, "Открыть изображение", self._menu_open_src, GRN, h=2).pack(fill=tk.X, pady=3)
        row = tk.Frame(p, bg=BG); row.pack(fill=tk.X, pady=2)
        self._btn(row, "Вставить Ctrl+V", self._global_paste, BTN, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,1))
        self._btn(row, "Очистить", self._clear_src, RED, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(1,0))
        self._src_lbl = self._lbl(p, "Файл не выбран", color=FG2)
        self._src_lbl.pack(anchor=tk.W, pady=(2,0))
        self._sep(p)
        self._lbl(p, "Порог фона (200–255):").pack(anchor=tk.W)
        self._auto_thresh = tk.Scale(p, from_=200, to=255, orient=tk.HORIZONTAL,
                                     bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self._auto_thresh.set(245)
        self._auto_thresh.pack(fill=tk.X)
        self._auto_thresh.bind("<ButtonRelease-1>", lambda _: self._auto_run())
        self._lbl(p, "Мин. размер объекта (пикс):").pack(anchor=tk.W, pady=(8,0))
        self._auto_min = tk.Scale(p, from_=5, to=150, orient=tk.HORIZONTAL,
                                  bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self._auto_min.set(12)
        self._auto_min.pack(fill=tk.X)
        self._auto_min.bind("<ButtonRelease-1>", lambda _: self._auto_run())
        self._lbl(p, "Разделение (эрозия, пикс):").pack(anchor=tk.W, pady=(8,0))
        self._auto_sep = tk.Scale(p, from_=0, to=150, orient=tk.HORIZONTAL,
                                  bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self._auto_sep.set(0)
        self._auto_sep.pack(fill=tk.X)
        self._auto_sep.bind("<ButtonRelease-1>", lambda _: self._auto_run())
        self._auto_cnt_lbl = self._lbl(p, "Найдено: 0", color=GOLD, bold=True)
        self._auto_cnt_lbl.pack(anchor=tk.W, pady=8)
        self._sep(p)
        self._btn(p, "▶  Запустить детекцию", self._auto_run, ACC, h=2).pack(fill=tk.X, pady=3)
        self._btn(p, "➕  Добавить в трей", self._auto_add_to_tray, GRN, h=2).pack(fill=tk.X, pady=3)
        self._sep(p)
        self._btn(p, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbl = self._lbl(p, "Папка не выбрана", color=FG2)
        self._outdir_lbl.pack(anchor=tk.W, pady=(3,0))
        self._btn(p, "РАЗДЕЛИТЬ И СОХРАНИТЬ", self._auto_save, ACC, h=2).pack(fill=tk.X, pady=(10,3))
        if self.src_img is not None and hasattr(self, "_src_lbl"):
            self._src_lbl.config(text=os.path.basename(self.src_path) if self.src_path else "из буфера")
        if self.outdir:
            self._outdir_lbl.config(text=self.outdir)
        self._auto_run()

    def _build_props_shape(self):
        p = self._props
        self._lbl(p, "Вырезание фигур", bold=True, size=11).pack(anchor=tk.W, pady=(0,8))
        self._btn(p, "Открыть изображение", self._menu_open_src, GRN, h=2).pack(fill=tk.X, pady=3)
        row = tk.Frame(p, bg=BG); row.pack(fill=tk.X, pady=2)
        self._btn(row, "Вставить Ctrl+V", self._global_paste, BTN, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,1))
        self._btn(row, "Очистить", self._clear_src, RED, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(1,0))
        self._src_lbl = self._lbl(p, "Файл не выбран", color=FG2)
        self._src_lbl.pack(anchor=tk.W)
        self._sep(p)
        self._lbl(p, "Инструмент рисования:", bold=True).pack(anchor=tk.W, pady=(0,5))
        if not hasattr(self, "_sh_tool_var"):
            self._sh_tool_var = tk.StringVar(value="rect")
        for txt, val in [("Прямоугольник (тяни)", "rect"),
                         ("Многоугольник (клик→ПКМ)", "poly"),
                         ("Лассо (тяни→ПКМ)", "lasso")]:
            tk.Radiobutton(p, text=txt, variable=self._sh_tool_var, value=val,
                           bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                           command=self._sh_reset).pack(anchor=tk.W)
        if not hasattr(self, "_sh_transp"):
            self._sh_transp = tk.BooleanVar(value=True)
        tk.Checkbutton(p, text="Прозрачный фон при вырезании",
                       variable=self._sh_transp, bg=BG, fg=FG,
                       selectcolor=BTN, activebackground=BG).pack(anchor=tk.W, pady=(8,0))
        self._sep(p)
        self._lbl(p, "Выделения:", bold=True).pack(anchor=tk.W, pady=(0,4))
        lf = tk.Frame(p, bg=BG2, bd=1, relief=tk.SUNKEN)
        lf.pack(fill=tk.BOTH)
        self._sh_lb = tk.Listbox(lf, bg=BG2, fg=FG, selectbackground=ACC,
                                  height=5, font=("Arial", 9), relief=tk.FLAT,
                                  highlightthickness=0)
        self._sh_lb.pack(fill=tk.BOTH)
        for i, (pts, st) in enumerate(self._sh_sels):
            self._sh_lb.insert(tk.END, f"#{i+1} {st} ({len(pts)}пт)")
        row2 = tk.Frame(p, bg=BG); row2.pack(fill=tk.X, pady=4)
        self._btn(row2, "Удалить выбранное", self._sh_del_sel).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self._btn(row2, "Очистить всё", self._sh_clear, RED).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self._sep(p)
        self._btn(p, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbl = self._lbl(p, self.outdir if self.outdir else "Папка не выбрана", color=FG2)
        self._outdir_lbl.pack(anchor=tk.W, pady=(3,0))
        self._btn(p, "✂  Вырезать → в трей", self._sh_apply, GRN, h=2).pack(fill=tk.X, pady=(8,3))
        self._btn(p, "ВЫРЕЗАТЬ И СОХРАНИТЬ", self._sh_save, ACC, h=2).pack(fill=tk.X, pady=3)
        self._lbl(p, "Esc — сброс  |  ПКМ — завершить", color=FG2, size=8).pack(anchor=tk.W)
        if self.src_img is not None and hasattr(self, "_src_lbl"):
            self._src_lbl.config(text=os.path.basename(self.src_path) if self.src_path else "из буфера")

    def _build_props_grid(self):
        p = self._props
        self._lbl(p, "Сетка тайлов", bold=True, size=11).pack(anchor=tk.W, pady=(0,8))
        self._btn(p, "Открыть изображение", self._menu_open_src, GRN, h=2).pack(fill=tk.X, pady=3)
        row = tk.Frame(p, bg=BG); row.pack(fill=tk.X, pady=2)
        self._btn(row, "Вставить Ctrl+V", self._global_paste, BTN, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,1))
        self._btn(row, "Очистить", self._clear_src, RED, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(1,0))
        self._src_lbl = self._lbl(p, "Файл не выбран", color=FG2)
        self._src_lbl.pack(anchor=tk.W)
        self._sep(p)
        self._lbl(p, "Параметры сетки:", bold=True).pack(anchor=tk.W, pady=(0,5))
        if not hasattr(self, "_grid_mode"):
            self._grid_mode = tk.StringVar(value="size")
        tk.Radiobutton(p, text="По размеру тайла", variable=self._grid_mode, value="size",
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._grid_update).pack(anchor=tk.W)
        tk.Radiobutton(p, text="По количеству ячеек", variable=self._grid_mode, value="count",
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._grid_update).pack(anchor=tk.W, pady=(0,6))
        if not hasattr(self, "_grid_tw"):
            self._grid_tw = tk.IntVar(value=32)
            self._grid_th = tk.IntVar(value=32)
            self._grid_cols = tk.IntVar(value=4)
            self._grid_rows = tk.IntVar(value=4)
            self._grid_off_x = tk.IntVar(value=0)
            self._grid_off_y = tk.IntVar(value=0)
            self._grid_skip = tk.BooleanVar(value=True)
        sf = tk.Frame(p, bg=BG); sf.pack(fill=tk.X, pady=2)
        self._lbl(sf, "Ш:").pack(side=tk.LEFT)
        self._spinbox(sf, self._grid_tw, 1, 2048, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        self._lbl(sf, "  В:").pack(side=tk.LEFT)
        self._spinbox(sf, self._grid_th, 1, 2048, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        cf = tk.Frame(p, bg=BG); cf.pack(fill=tk.X, pady=2)
        self._lbl(cf, "Стб:").pack(side=tk.LEFT)
        self._spinbox(cf, self._grid_cols, 1, 512, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        self._lbl(cf, "  Стр:").pack(side=tk.LEFT)
        self._spinbox(cf, self._grid_rows, 1, 512, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        of = tk.Frame(p, bg=BG); of.pack(fill=tk.X, pady=2)
        self._lbl(of, "Отступ X:").pack(side=tk.LEFT)
        self._spinbox(of, self._grid_off_x, 0, 512, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        self._lbl(of, "  Y:").pack(side=tk.LEFT)
        self._spinbox(of, self._grid_off_y, 0, 512, cmd=self._grid_update).pack(side=tk.LEFT, padx=2)
        tk.Checkbutton(p, text="Пропускать пустые тайлы", variable=self._grid_skip,
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._grid_update).pack(anchor=tk.W, pady=4)
        self._grid_cnt_lbl = self._lbl(p, "Тайлов: —", color=GOLD, bold=True)
        self._grid_cnt_lbl.pack(anchor=tk.W, pady=4)
        self._sep(p)
        self._btn(p, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbl = self._lbl(p, self.outdir if self.outdir else "Папка не выбрана", color=FG2)
        self._outdir_lbl.pack(anchor=tk.W, pady=(3,0))
        self._btn(p, "➕  Добавить в трей", self._grid_to_tray, GRN, h=2).pack(fill=tk.X, pady=(8,3))
        self._btn(p, "НАРЕЗАТЬ И СОХРАНИТЬ", self._grid_save, ACC, h=2).pack(fill=tk.X, pady=3)
        if self.src_img is not None and hasattr(self, "_src_lbl"):
            self._src_lbl.config(text=os.path.basename(self.src_path) if self.src_path else "из буфера")
        self._grid_update()

    def _build_props_atlas(self):
        p = self._props
        self._lbl(p, "Сборка атласа", bold=True, size=11).pack(anchor=tk.W, pady=(0,8))
        pf = tk.Frame(p, bg=BG); pf.pack(fill=tk.X, pady=(0,4))
        self._btn(pf, "📂 Открыть проект", self.project_load, BTN, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,2))
        self._btn(pf, "💾 Сохранить проект", self.project_save, BTN, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2,0))

        s1 = self._section(p, "1. Изображение")
        self._btn(s1, "Открыть изображение", self._menu_open_src, GRN, h=2).pack(fill=tk.X, pady=3)
        row = tk.Frame(s1, bg=BG); row.pack(fill=tk.X, pady=2)
        self._btn(row, "Вставить Ctrl+V", self._global_paste, BTN, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,1))
        self._btn(row, "Очистить", self._clear_src, RED, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(1,0))
        self._src_lbl = self._lbl(s1, "Файл не выбран", color=FG2)
        self._src_lbl.pack(anchor=tk.W)

        s2 = self._section(p, "2. Поиск объектов")
        self._lbl(s2, "Порог фона:").pack(anchor=tk.W)
        self._atlas_thresh = tk.Scale(s2, from_=200, to=255, orient=tk.HORIZONTAL,
                                      bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self._atlas_thresh.set(245)
        self._atlas_thresh.pack(fill=tk.X)
        self._atlas_thresh.bind("<ButtonRelease-1>", lambda _: self._atlas_update())
        self._lbl(s2, "Мин. размер (пикс):").pack(anchor=tk.W, pady=(6,0))
        self._atlas_min = tk.Scale(s2, from_=5, to=150, orient=tk.HORIZONTAL,
                                   bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self._atlas_min.set(12)
        self._atlas_min.pack(fill=tk.X)
        self._atlas_min.bind("<ButtonRelease-1>", lambda _: self._atlas_update())
        self._lbl(s2, "Разделение (эрозия):").pack(anchor=tk.W, pady=(6,0))
        self._atlas_sep = tk.Scale(s2, from_=0, to=150, orient=tk.HORIZONTAL,
                                   bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self._atlas_sep.set(0)
        self._atlas_sep.pack(fill=tk.X)
        self._atlas_sep.bind("<ButtonRelease-1>", lambda _: self._atlas_update())
        self._atlas_cnt_lbl = self._lbl(s2, "Найдено: 0", color=GOLD, bold=True)
        self._atlas_cnt_lbl.pack(anchor=tk.W, pady=(6,0))

        s3 = self._section(p, "3. Размер ячейки")
        pf3 = tk.Frame(s3, bg=BG); pf3.pack(fill=tk.X, pady=(0,4))
        for val in (16, 32, 64, 128, 256):
            self._btn(pf3, str(val), lambda v=val: self._atlas_preset(v),
                      font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        cf = tk.Frame(s3, bg=BG); cf.pack(fill=tk.X, pady=2)
        self._lbl(cf, "Ячейка (пикс):").pack(side=tk.LEFT)
        if not hasattr(self, "_atlas_cell"):
            self._atlas_cell = tk.IntVar(value=64)
        self._spinbox(cf, self._atlas_cell, 4, 2048, cmd=self._atlas_update).pack(side=tk.LEFT, padx=4)
        self._atlas_cell.trace_add("write", lambda *_: self._atlas_update())
        self._lbl(s3, "Режим подгонки:", color=FG2).pack(anchor=tk.W, pady=(4,2))
        if not hasattr(self, "_atlas_fit_mode"):
            self._atlas_fit_mode = tk.StringVar(value="trim")
        mf = tk.Frame(s3, bg=BG); mf.pack(fill=tk.X)
        tk.Radiobutton(mf, text="Обрезка", variable=self._atlas_fit_mode, value="trim",
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._atlas_mode_changed).pack(side=tk.LEFT, padx=(0,8))
        tk.Radiobutton(mf, text="Масштаб", variable=self._atlas_fit_mode, value="scale",
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._atlas_mode_changed).pack(side=tk.LEFT)
        if not hasattr(self, "_atlas_no_upscale"):
            self._atlas_no_upscale = tk.BooleanVar(value=True)
        self._atlas_noup_chk = tk.Checkbutton(s3, text="Не увеличивать мелкие",
                       variable=self._atlas_no_upscale, bg=BG, fg=FG,
                       selectcolor=BTN, activebackground=BG, command=self._atlas_update)
        self._atlas_noup_chk.pack(anchor=tk.W, pady=(2,0))
        self._lbl(s3, "Выравнивание:", color=FG2).pack(anchor=tk.W, pady=(6,2))
        alf = tk.Frame(s3, bg=BG); alf.pack(fill=tk.X)
        if not hasattr(self, "_atlas_align_w"):
            self._atlas_align_w = tk.BooleanVar(value=True)
            self._atlas_align_h = tk.BooleanVar(value=True)
        tk.Checkbutton(alf, text="По ширине", variable=self._atlas_align_w,
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._atlas_update).pack(side=tk.LEFT, padx=(0,8))
        tk.Checkbutton(alf, text="По высоте", variable=self._atlas_align_h,
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._atlas_update).pack(side=tk.LEFT)

        s4 = self._section(p, "4. Дубликаты", expanded=False)
        if not hasattr(self, "_atlas_dedup"):
            self._atlas_dedup = tk.BooleanVar(value=False)
            self._atlas_dedup_thresh = tk.IntVar(value=95)
        tk.Checkbutton(s4, text="Убрать похожие", variable=self._atlas_dedup,
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._atlas_update).pack(anchor=tk.W)
        df = tk.Frame(s4, bg=BG); df.pack(fill=tk.X, pady=(4,0))
        self._lbl(df, "Схожесть (%):").pack(side=tk.LEFT)
        self._spinbox(df, self._atlas_dedup_thresh, 50, 100, cmd=self._atlas_update).pack(side=tk.LEFT, padx=4)
        self._atlas_dedup_thresh.trace_add("write", lambda *_: self._atlas_update())
        self._atlas_dedup_lbl = self._lbl(s4, "", color=FG2)
        self._atlas_dedup_lbl.pack(anchor=tk.W)

        s5 = self._section(p, "5. Компоновка")
        gf = tk.Frame(s5, bg=BG); gf.pack(fill=tk.X, pady=2)
        self._lbl(gf, "Столбцов:").pack(side=tk.LEFT)
        if not hasattr(self, "_atlas_cols"):
            self._atlas_cols = tk.IntVar(value=8)
        self._spinbox(gf, self._atlas_cols, 1, 128, cmd=self._atlas_update).pack(side=tk.LEFT, padx=4)
        self._atlas_cols.trace_add("write", lambda *_: self._atlas_update())
        self._btn(s5, "↺ Обновить превью", self._atlas_update).pack(fill=tk.X, pady=(6,4))
        self._atlas_size_lbl = self._lbl(s5, "Размер: —", color=FG2)
        self._atlas_size_lbl.pack(anchor=tk.W)
        zf = tk.Frame(s5, bg=BG); zf.pack(fill=tk.X, pady=(4,0))
        self._lbl(zf, "Зум:").pack(side=tk.LEFT)
        self._atlas_zoom_lbl = self._lbl(zf, "100%", color=GOLD)
        self._atlas_zoom_lbl.pack(side=tk.LEFT, padx=6)
        self._btn(zf, "↺", self._cv_zoom_reset, h=1).pack(side=tk.RIGHT)

        s6 = self._section(p, "6. Сохранение")
        self._btn(s6, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbl = self._lbl(s6, self.outdir if self.outdir else "Папка не выбрана", color=FG2)
        self._outdir_lbl.pack(anchor=tk.W, pady=(3,0))
        self._lbl(s6, "Имя файла:").pack(anchor=tk.W, pady=(6,0))
        if not hasattr(self, "_atlas_name"):
            self._atlas_name = tk.StringVar(value="atlas")
            self._atlas_name_manual = False
        tk.Entry(s6, textvariable=self._atlas_name, bg=BTN, fg=FG,
                 relief=tk.FLAT, insertbackground=FG).pack(fill=tk.X, pady=(2,0))
        ttk.Separator(s6, orient="horizontal").pack(fill=tk.X, pady=(10,6))
        self._atlas_export_btn = self._btn(s6, "📁 Сохранить спрайты по файлам",
                                           self._atlas_export_files, BTN)
        self._atlas_export_btn.pack(fill=tk.X, pady=(4,0))

        # Action buttons at bottom
        self._sep(p)
        self._atlas_save_btn = self._btn(p, "СОБРАТЬ И СОХРАНИТЬ АТЛАС", self._atlas_save, ACC, h=2)
        self._atlas_save_btn.pack(fill=tk.X, pady=3)
        self._atlas_overwrite_btn = self._btn(p, "↺ Перезаписать", self._atlas_overwrite, GOLD)
        self._atlas_overwrite_btn.pack(fill=tk.X, pady=3)
        if not self._atlas_last_out:
            self._atlas_overwrite_btn.config(state=tk.DISABLED)

        if self.src_img is not None:
            if hasattr(self, "_src_lbl"):
                self._src_lbl.config(text=os.path.basename(self.src_path) if self.src_path else "из буфера")
            self._atlas_update()

    def _build_props_tiletest(self):
        p = self._props
        self._lbl(p, "Тайл-тест", bold=True, size=11).pack(anchor=tk.W, pady=(0,8))
        self._btn(p, "Открыть изображение", self._menu_open_src, GRN, h=2).pack(fill=tk.X, pady=3)
        row = tk.Frame(p, bg=BG); row.pack(fill=tk.X, pady=2)
        self._btn(row, "Вставить Ctrl+V", self._global_paste, BTN, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,1))
        self._btn(row, "Очистить", self._clear_src, RED, font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(1,0))
        self._src_lbl = self._lbl(p, "Файл не выбран", color=FG2)
        self._src_lbl.pack(anchor=tk.W)
        self._sep(p)
        self._lbl(p, "Размер тайла:", bold=True).pack(anchor=tk.W, pady=(0,5))
        if not hasattr(self, "_tc_size_var"):
            self._tc_size_var = tk.IntVar(value=64)
        szf = tk.Frame(p, bg=BG); szf.pack(fill=tk.X)
        for sz in (32, 64, 128, 256, 512):
            tk.Radiobutton(szf, text=str(sz), variable=self._tc_size_var, value=sz,
                           bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                           font=("Arial", 9, "bold"),
                           command=self._tc_size_changed).pack(side=tk.LEFT, padx=2)
        self._lbl(p, "Размер выбора:", color=FG2).pack(anchor=tk.W, pady=(8,2))
        slf = tk.Frame(p, bg=BG); slf.pack(fill=tk.X)
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
        grf = tk.Frame(p, bg=BG); grf.pack(fill=tk.X)
        for n in (3, 4, 5, 6, 7):
            tk.Radiobutton(grf, text=f"{n}×{n}", variable=self._tc_grid_var, value=n,
                           bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                           font=("Arial", 9, "bold"),
                           command=self._cv_draw).pack(side=tk.LEFT, padx=2)
        self._sep(p)
        self._lbl(p, "Позиция среза:", bold=True).pack(anchor=tk.W, pady=(0,3))
        self._tc_offset_lbl = self._lbl(p, f"X: {self._tc_cx}   Y: {self._tc_cy}", color=GOLD)
        self._tc_offset_lbl.pack(anchor=tk.W)
        if not hasattr(self, "_tc_snap"):
            self._tc_snap = tk.BooleanVar(value=False)
        tk.Checkbutton(p, text="Привязка к сетке тайлов", variable=self._tc_snap,
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG).pack(anchor=tk.W, pady=(6,0))
        self._btn(p, "Сброс позиции (0,0)", self._tc_reset).pack(fill=tk.X, pady=(6,0))
        zf = tk.Frame(p, bg=BG); zf.pack(fill=tk.X, pady=(8,0))
        self._lbl(zf, "Зум:").pack(side=tk.LEFT)
        self._tc_zoom_lbl = self._lbl(zf, "100%", color=GOLD)
        self._tc_zoom_lbl.pack(side=tk.LEFT, padx=6)
        self._btn(zf, "↺", self._cv_zoom_reset, h=1).pack(side=tk.RIGHT)
        self._sep(p)
        self._btn(p, "Выбрать папку вывода", self._menu_choose_outdir).pack(fill=tk.X)
        self._outdir_lbl = self._lbl(p, self.outdir if self.outdir else "Папка не выбрана", color=FG2)
        self._outdir_lbl.pack(anchor=tk.W, pady=(3,0))
        self._lbl(p, "Имя файла:").pack(anchor=tk.W, pady=(6,0))
        if not hasattr(self, "_tc_name_var"):
            self._tc_name_var = tk.StringVar(value="tile")
        tk.Entry(p, textvariable=self._tc_name_var, bg=BTN, fg=FG,
                 relief=tk.FLAT, insertbackground=FG).pack(fill=tk.X)
        self._btn(p, "СОХРАНИТЬ ТАЙЛ", self._tc_save, ACC, h=2).pack(fill=tk.X, pady=(8,3))
        if self.src_img is not None and hasattr(self, "_src_lbl"):
            self._src_lbl.config(text=os.path.basename(self.src_path) if self.src_path else "из буфера")
    # ══════════════════════════════════════════════════════════════════
    #  DND SETUP
    # ══════════════════════════════════════════════════════════════════

    def _setup_dnd(self, widget, on_drop, *, multi=False):
        widget.drop_target_register(DND_FILES)
        def _enter(e):
            try: widget.config(highlightthickness=3, highlightbackground=GRN)
            except tk.TclError: pass
        def _leave(e):
            try: widget.config(highlightthickness=0)
            except tk.TclError: pass
        def _drop(e):
            try: widget.config(highlightthickness=0)
            except tk.TclError: pass
            paths = self._parse_drop_paths(e.data)
            if not paths: return
            if multi:
                on_drop(paths)
            else:
                for pp in paths:
                    if pp.lower().endswith(_IMG_EXTS) or os.path.isdir(pp):
                        on_drop(pp); break
        widget.dnd_bind('<<DragEnter>>', _enter)
        widget.dnd_bind('<<DragLeave>>', _leave)
        widget.dnd_bind('<<Drop>>', _drop)

    # ══════════════════════════════════════════════════════════════════
    #  FILE OPERATIONS
    # ══════════════════════════════════════════════════════════════════

    def _menu_open_src(self):
        path = filedialog.askopenfilename(
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if path:
            self._load_src(path)

    def _load_src(self, path):
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            messagebox.showerror("Ошибка", f"Не удалось открыть:\n{path}")
            return
        self.src_img = img
        self.src_path = path
        self._cv_zoom = 1.0
        self._cv_view_x = 0
        self._cv_view_y = 0
        self._auto_contours_cache = []
        if not self.outdir:
            self.outdir = os.path.dirname(path)
            self._add_recent(self.outdir)
        if hasattr(self, "_src_lbl"):
            self._src_lbl.config(text=os.path.basename(path))
        if hasattr(self, "_outdir_lbl"):
            self._outdir_lbl.config(text=self.outdir)
        self._status_var.set(f"Открыто: {os.path.basename(path)}  ({img.shape[1]}×{img.shape[0]})")
        if self.tool == "auto":
            self._auto_run()
        elif self.tool == "grid":
            self._grid_update()
        elif self.tool == "atlas":
            self._atlas_update()
        else:
            self._cv_draw()

    def _clear_src(self):
        self.src_img = None
        self.src_path = ""
        self._cv_zoom = 1.0
        self._cv_view_x = 0
        self._cv_view_y = 0
        self._auto_contours_cache = []
        if hasattr(self, "_src_lbl"):
            self._src_lbl.config(text="Файл не выбран")
        self._cv_draw()

    def _menu_choose_outdir(self):
        d = filedialog.askdirectory()
        if d:
            self.outdir = d
            self._add_recent(d)
            if hasattr(self, "_outdir_lbl"):
                self._outdir_lbl.config(text=d)

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
                return path
        except Exception:
            pass
        return None

    def _global_paste(self, event=None):
        p = self._get_clipboard_path()
        if not p:
            messagebox.showinfo("Буфер", "В буфере нет изображения")
            return
        self._load_src(p)

    # ══════════════════════════════════════════════════════════════════
    #  CORE LOGIC UTILITIES
    # ══════════════════════════════════════════════════════════════════

    def _cv2pil(self, img):
        if img is None:
            return None
        if len(img.shape) == 2:
            return Image.fromarray(img)
        if img.shape[2] == 4:
            return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA))
        return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    def _next_idx(self, folder, prefix, ext=".png"):
        idxs = []
        for f in os.listdir(folder):
            if f.startswith(prefix) and f.endswith(ext):
                try:
                    idxs.append(int(f[len(prefix):-len(ext)]))
                except ValueError:
                    pass
        return (max(idxs) + 1) if idxs else 0

    def _parse_drop_paths(self, data):
        paths = []
        data = data.strip()
        i = 0
        while i < len(data):
            if data[i] == '{':
                try:
                    j = data.index('}', i)
                    paths.append(data[i+1:j])
                    i = j + 1
                except ValueError:
                    break
            elif data[i] == ' ':
                i += 1
            else:
                j = data.find(' ', i)
                if j == -1:
                    paths.append(data[i:])
                    break
                paths.append(data[i:j])
                i = j
        return [pp for pp in paths if pp]

    def _auto_contours(self, img, tv, ms, sep=0):
        if img is None: return []
        if len(img.shape) == 3 and img.shape[2] == 4:
            alpha = img[:, :, 3]
            _, th = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY)
        else:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            dark = int(gray[0, 0]) < 127
            if dark:
                _, th = cv2.threshold(gray, 255 - tv, 255, cv2.THRESH_BINARY)
            else:
                _, th = cv2.threshold(gray, tv, 255, cv2.THRESH_BINARY_INV)
        if sep > 0:
            k = sep * 2 + 1
            kernel = np.ones((k, k), np.uint8)
            th_work = cv2.erode(th, kernel, iterations=1)
        else:
            th_work = th
        raw, _ = cv2.findContours(th_work, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if sep == 0:
            return [c for c in raw if cv2.boundingRect(c)[2] >= ms and cv2.boundingRect(c)[3] >= ms]
        ih, iw = img.shape[:2]
        result = []
        for c in raw:
            x, y, w, h = cv2.boundingRect(c)
            if w < ms or h < ms:
                continue
            x2 = min(iw, x + w + sep)
            y2 = min(ih, y + h + sep)
            x  = max(0, x - sep)
            y  = max(0, y - sep)
            w, h = x2 - x, y2 - y
            fake = np.array([[[x, y]], [[x+w-1, y]], [[x+w-1, y+h-1]], [[x, y+h-1]]],
                            dtype=np.int32)
            result.append(fake)
        return result

    def _trim_crop(self, pil, tv, dark_bg, has_alpha):
        arr = np.array(pil)
        if has_alpha:
            mask = arr[:, :, 3] > 10
        else:
            gray = np.mean(arr[:, :, :3], axis=2).astype(np.uint8)
            if dark_bg:
                mask = gray > (255 - tv)
            else:
                mask = gray < tv
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        if not rows.any() or not cols.any():
            return pil
        rmin, rmax = int(np.where(rows)[0][0]),  int(np.where(rows)[0][-1])
        cmin, cmax = int(np.where(cols)[0][0]),  int(np.where(cols)[0][-1])
        return pil.crop((cmin, rmin, cmax + 1, rmax + 1))

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
            cell = Image.new("RGBA", (SZ, SZ), (40, 43, 48, 255))
            ox = (SZ - thumb.width)  // 2
            oy = (SZ - thumb.height) // 2
            cell.paste(thumb, (ox, oy), thumb)
            if excluded:
                overlay = Image.new("RGBA", (SZ, SZ), (160, 0, 0, 130))
                cell = Image.alpha_composite(cell, overlay)
                d = ImageDraw.Draw(cell)
                d.line([(4, 4), (SZ-4, SZ-4)], fill=(255, 60, 60), width=2)
                d.line([(SZ-4, 4), (4, SZ-4)], fill=(255, 60, 60), width=2)
            border_col = "#cc2222" if excluded else "#3ba55c"
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
            txt = f"Трей: {n_vis} из {len(self.sprites)}  (исключено: {n_exc})"
        else:
            txt = f"Трей: {len(self.sprites)} спрайтов"
        self._tray_count_lbl.config(text=txt)

    def _tray_click(self, e):
        if self.tool == "atlas":
            # In atlas mode tray shows atlas raws
            SZ, PAD = self._TRAY_SZ, self._TRAY_PAD
            cx = self._tray_canvas.canvasx(e.x)
            i = int(cx // (SZ + PAD))
            if 0 <= i < len(self._atlas_raws):
                if i in self.excluded:
                    self.excluded.discard(i)
                else:
                    self.excluded.add(i)
                self._tray_refresh_atlas_tray()
                self._atlas_assemble()
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

    def _tray_clear(self):
        self.sprites.clear()
        self.excluded.clear()
        self._tray_refresh()

    def _tray_save_all(self):
        visible = [s for i, s in enumerate(self.sprites) if i not in self.excluded]
        if not visible:
            messagebox.showinfo("Трей пуст", "Нет спрайтов в трее (или все исключены)")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._add_recent(d)
            if hasattr(self, "_outdir_lbl"):
                self._outdir_lbl.config(text=d)
        idx = self._next_idx(self.outdir, "sprite_")
        for pil in visible:
            pil.save(os.path.join(self.outdir, f"sprite_{idx:04d}.png"))
            idx += 1
        messagebox.showinfo("Готово!", f"Сохранено {len(visible)} спрайтов в:\n{self.outdir}")

    # ══════════════════════════════════════════════════════════════════
    #  AUTO TOOL
    # ══════════════════════════════════════════════════════════════════

    def _auto_run(self):
        if self.src_img is None:
            self._auto_contours_cache = []
            if hasattr(self, "_auto_cnt_lbl"):
                self._auto_cnt_lbl.config(text="Найдено: 0")
            self._cv_draw()
            return
        tv  = self._auto_thresh.get() if hasattr(self, "_auto_thresh") else 245
        ms  = self._auto_min.get()    if hasattr(self, "_auto_min")    else 12
        sep = self._auto_sep.get()    if hasattr(self, "_auto_sep")    else 0
        contours = self._auto_contours(self.src_img, tv, ms, sep=sep)
        self._auto_contours_cache = contours
        if hasattr(self, "_auto_cnt_lbl"):
            self._auto_cnt_lbl.config(text=f"Найдено: {len(contours)}")
        self._cv_draw()

    def _auto_add_to_tray(self):
        if self.src_img is None or not hasattr(self, "_auto_contours_cache"):
            messagebox.showinfo("Нет данных", "Сначала запустите детекцию")
            return
        contours = self._auto_contours_cache
        if not contours:
            messagebox.showinfo("Нет объектов", "Объекты не найдены")
            return
        img = self.src_img
        has_alpha = len(img.shape) == 3 and img.shape[2] == 4
        dark_bg   = (not has_alpha and len(img.shape) == 3 and
                     int(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[0, 0]) < 127)
        rgba = (cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                if len(img.shape) == 3 and img.shape[2] == 3 else img.copy())
        tv = self._auto_thresh.get() if hasattr(self, "_auto_thresh") else 245
        raws = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            pil = self._cv2pil(rgba[y:y+h, x:x+w]).convert("RGBA")
            pil = self._trim_crop(pil, tv, dark_bg, has_alpha)
            raws.append(pil)
        self._tray_add(raws)
        messagebox.showinfo("Трей", f"Добавлено {len(raws)} спрайтов в трей")

    def _auto_save(self):
        if self.src_img is None:
            messagebox.showwarning("Ошибка", "Откройте изображение")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._add_recent(d)
            if hasattr(self, "_outdir_lbl"):
                self._outdir_lbl.config(text=d)
        tv  = self._auto_thresh.get() if hasattr(self, "_auto_thresh") else 245
        ms  = self._auto_min.get()    if hasattr(self, "_auto_min")    else 12
        sep = self._auto_sep.get()    if hasattr(self, "_auto_sep")    else 0
        contours = self._auto_contours(self.src_img, tv, ms, sep=sep)
        if not contours:
            messagebox.showinfo("Нет объектов", "Объекты не найдены")
            return
        img = self.src_img
        rgba = (cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                if len(img.shape) == 3 and img.shape[2] == 3 else img.copy())
        idx = self._next_idx(self.outdir, "sprite_")
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            crop = rgba[y:y+h, x:x+w]
            cv2.imwrite(os.path.join(self.outdir, f"sprite_{idx:04d}.png"), crop)
            idx += 1
        messagebox.showinfo("Готово!", f"Сохранено {len(contours)} спрайтов в:\n{self.outdir}")

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

    def _sh_save(self):
        if not self._sh_sels or self.src_img is None:
            messagebox.showinfo("Нет выделений", "Нарисуйте выделения")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._add_recent(d)
            if hasattr(self, "_outdir_lbl"):
                self._outdir_lbl.config(text=d)
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
            crop.save(os.path.join(self.outdir, f"cut_{idx:04d}.png"))
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

    def _grid_save(self):
        if self.src_img is None:
            messagebox.showwarning("Ошибка", "Откройте изображение")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._add_recent(d)
            if hasattr(self, "_outdir_lbl"):
                self._outdir_lbl.config(text=d)
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
            cv2.imwrite(os.path.join(self.outdir, f"tile_{idx:04d}.png"), crop)
            idx += 1; saved += 1
        messagebox.showinfo("Готово!", f"Сохранено {saved} тайлов в:\n{self.outdir}")

    # ══════════════════════════════════════════════════════════════════
    #  ATLAS TOOL
    # ══════════════════════════════════════════════════════════════════

    def _atlas_detect_raws(self):
        img = self.src_img
        if img is None:
            self._atlas_raws = []
            return []
        tv  = self._atlas_thresh.get() if hasattr(self, "_atlas_thresh") else 245
        ms  = self._atlas_min.get()    if hasattr(self, "_atlas_min")    else 12
        sep = max(0, self._atlas_sep.get() if hasattr(self, "_atlas_sep") else 0)
        contours = self._auto_contours(img, tv, ms, sep=sep)
        if not contours:
            self._atlas_raws = []
            return []
        has_alpha = len(img.shape) == 3 and img.shape[2] == 4
        dark_bg   = (not has_alpha and len(img.shape) == 3 and
                     int(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[0, 0]) < 127)
        rgba = (cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                if len(img.shape) == 3 and img.shape[2] == 3 else img.copy())
        cell0 = max(4, self._atlas_cell.get() if hasattr(self, "_atlas_cell") else 64)
        boxes = sorted([cv2.boundingRect(c) for c in contours],
                       key=lambda b: (b[1] // max(1, cell0), b[0]))
        raws = []
        for (x, y, w, h) in boxes:
            pil = self._cv2pil(rgba[y:y+h, x:x+w]).convert("RGBA")
            pil = self._trim_crop(pil, tv, dark_bg, has_alpha)
            raws.append(pil)
        if len(raws) != len(self._atlas_raws):
            self.excluded = set()
        self._atlas_raws = raws
        return raws

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
        removed = 0
        if hasattr(self, "_atlas_dedup") and self._atlas_dedup.get():
            raws, removed = self._dedup_raws(raws, self._atlas_dedup_thresh.get())
        self._atlas_removed = removed
        if not raws:
            return None, 0, cell0, cell0, 0, 0
        cell_w = cell0 if norm_w else max(p.width for p in raws)
        cell_h = cell0 if norm_h else max(p.height for p in raws)
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
                    pil = pil.resize((nw, nh), Image.LANCZOS)
            else:
                if pil.width > cell_w or pil.height > cell_h:
                    l = max(0, (pil.width - cell_w)//2)
                    t = max(0, (pil.height - cell_h)//2)
                    pil = pil.crop((l, t, l+min(cell_w,pil.width), t+min(cell_h,pil.height)))
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
            sheet.paste(pil, (ox, oy), pil)
        return sheet, n, cell_w, cell_h, cols, rows

    def _atlas_assemble(self):
        try:
            sheet, n, cell_w, cell_h, cols, rows = self._atlas_build()
        except Exception:
            return
        self._atlas_apply(sheet, n, cell_w, cell_h, cols, rows)

    def _atlas_update(self, *_):
        if self.src_img is None:
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
            cell = Image.new("RGBA", (SZ, SZ), (40, 43, 48, 255))
            ox = (SZ - thumb.width)  // 2
            oy = (SZ - thumb.height) // 2
            cell.paste(thumb, (ox, oy), thumb)
            if excluded:
                overlay = Image.new("RGBA", (SZ, SZ), (160, 0, 0, 130))
                cell = Image.alpha_composite(cell, overlay)
                d = ImageDraw.Draw(cell)
                d.line([(4,4),(SZ-4,SZ-4)], fill=(255,60,60), width=2)
                d.line([(SZ-4,4),(4,SZ-4)], fill=(255,60,60), width=2)
            border_col = "#cc2222" if excluded else "#3ba55c"
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
        vis = Image.new("RGB", sheet.size, (30, 33, 36))
        vis.paste(sheet, (0, 0), sheet)
        draw = ImageDraw.Draw(vis)
        for r in range(rows):
            for c in range(cols):
                x, y = c*cell_w, r*cell_h
                draw.rectangle([x, y, x+cell_w-1, y+cell_h-1], outline="#00e050", width=1)
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

    def _atlas_save(self):
        if self.src_img is None:
            messagebox.showwarning("Ошибка", "Откройте изображение")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._add_recent(d)
            if hasattr(self, "_outdir_lbl"):
                self._outdir_lbl.config(text=d)
        sheet, n, *_ = self._atlas_build()
        if sheet is None:
            messagebox.showwarning("Ошибка", "Объекты не найдены")
            return
        self._atlas_sheet = sheet
        name = self._atlas_name.get().strip() if hasattr(self, "_atlas_name") else "atlas"
        if not name: name = "atlas"
        name = "".join(ch for ch in name if ch not in '\\/:*?"<>|')
        if not name.lower().endswith(".png"):
            name += ".png"
        out = os.path.join(self.outdir, name)
        if os.path.exists(out) and not messagebox.askyesno(
                "Файл существует", f"«{name}» уже существует. Перезаписать?"):
            return
        sheet.save(out)
        self._atlas_last_out = out
        if hasattr(self, "_atlas_overwrite_btn"):
            self._atlas_overwrite_btn.config(state=tk.NORMAL)
        messagebox.showinfo("Готово!",
            f"Атлас {sheet.width}×{sheet.height}px, {n} объектов\nСохранён: {out}")

    def _atlas_overwrite(self):
        if not self._atlas_last_out or self.src_img is None: return
        sheet, n, *_ = self._atlas_build()
        if sheet is None:
            messagebox.showwarning("Ошибка", "Объекты не найдены")
            return
        sheet.save(self._atlas_last_out)
        messagebox.showinfo("Готово!",
            f"Атлас {sheet.width}×{sheet.height}px, {n} объектов\nПерезаписан: {self._atlas_last_out}")

    def _atlas_export_files(self):
        if not self._atlas_raws:
            messagebox.showwarning("Ошибка", "Нет спрайтов")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._add_recent(d)
            if hasattr(self, "_outdir_lbl"):
                self._outdir_lbl.config(text=d)
        raws = [p for i, p in enumerate(self._atlas_raws) if i not in self.excluded]
        if hasattr(self, "_atlas_dedup") and self._atlas_dedup.get():
            raws, _ = self._dedup_raws(raws, self._atlas_dedup_thresh.get())
        if not raws:
            messagebox.showwarning("Ошибка", "После фильтрации нет спрайтов")
            return
        base = self._atlas_name.get() if hasattr(self, "_atlas_name") else "sprite"
        idx  = self._next_idx(self.outdir, base + "_")
        for pil in raws:
            pil.save(os.path.join(self.outdir, f"{base}_{idx:04d}.png"))
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

    def _tc_save(self):
        if self.src_img is None:
            messagebox.showwarning("Ошибка", "Откройте изображение")
            return
        if not self.outdir:
            d = filedialog.askdirectory()
            if not d: return
            self.outdir = d
            self._add_recent(d)
            if hasattr(self, "_outdir_lbl"):
                self._outdir_lbl.config(text=d)
        pil = self._cv2pil(self.src_img)
        if pil is None: return
        pil = pil.convert("RGBA")
        iw, ih = pil.size
        sw = self._tc_sel_w.get() if hasattr(self, "_tc_sel_w") else 64
        sh = self._tc_sel_h.get() if hasattr(self, "_tc_sel_h") else 64
        if iw < sw or ih < sh:
            messagebox.showwarning("Ошибка", f"Изображение меньше {sw}×{sh}")
            return
        name = self._tc_name_var.get().strip() if hasattr(self, "_tc_name_var") else "tile"
        if not name: name = "tile"
        prefix = name + "_"
        x = max(0, min(self._tc_cx, iw-sw))
        y = max(0, min(self._tc_cy, ih-sh))
        tile = pil.crop((x, y, x+sw, y+sh))
        idx = self._next_idx(self.outdir, prefix)
        out = os.path.join(self.outdir, f"{prefix}{idx:04d}.png")
        tile.save(out)
        messagebox.showinfo("Готово!", f"Кроп {sw}×{sh} сохранён:\n{out}")

    # ══════════════════════════════════════════════════════════════════
    #  PROJECT SAVE / LOAD
    # ══════════════════════════════════════════════════════════════════

    def project_save(self):
        path = filedialog.asksaveasfilename(
            title="Сохранить проект",
            defaultextension=".smproj",
            filetypes=[("Sprite Manufacturer Project", "*.smproj"), ("Все файлы", "*.*")])
        if not path: return
        data = {
            "version": 3,
            "source_path": self.src_path or "",
            "outdir": self.outdir,
            "last_out": self._atlas_last_out or "",
            "tool": self.tool,
            "settings": {
                "atlas_thresh":       self._atlas_thresh.get() if hasattr(self, "_atlas_thresh") else 245,
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
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Проект сохранён", f"Сохранено:\n{path}")

    def project_load(self):
        path = filedialog.askopenfilename(
            title="Открыть проект",
            filetypes=[("Sprite Manufacturer Project", "*.smproj"), ("Все файлы", "*.*")])
        if not path: return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл проекта:\n{e}")
            return
        img = None
        src_path = data.get("source_path", "")
        if src_path and os.path.exists(src_path):
            img = cv2.imread(src_path, cv2.IMREAD_UNCHANGED)
        if img is None and "source_data" in data:
            raw = base64.b64decode(data["source_data"])
            arr = np.frombuffer(raw, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
            if not src_path:
                src_path = "(встроено в проект)"
        self._tool_set("atlas")
        s = data.get("settings", {})
        if hasattr(self, "_atlas_thresh"): self._atlas_thresh.set(s.get("atlas_thresh", 245))
        if hasattr(self, "_atlas_min"):    self._atlas_min.set(s.get("atlas_min", 12))
        if hasattr(self, "_atlas_sep"):    self._atlas_sep.set(s.get("atlas_sep", 0))
        if hasattr(self, "_atlas_cell"):   self._atlas_cell.set(s.get("atlas_cell", 64))
        if hasattr(self, "_atlas_fit_mode"):     self._atlas_fit_mode.set(s.get("atlas_fit_mode", "trim"))
        if hasattr(self, "_atlas_no_upscale"):   self._atlas_no_upscale.set(s.get("atlas_no_upscale", True))
        if hasattr(self, "_atlas_align_w"):      self._atlas_align_w.set(s.get("atlas_align_w", True))
        if hasattr(self, "_atlas_align_h"):      self._atlas_align_h.set(s.get("atlas_align_h", True))
        if hasattr(self, "_atlas_dedup"):        self._atlas_dedup.set(s.get("atlas_dedup", False))
        if hasattr(self, "_atlas_dedup_thresh"): self._atlas_dedup_thresh.set(s.get("atlas_dedup_thresh", 95))
        if hasattr(self, "_atlas_cols"):         self._atlas_cols.set(s.get("atlas_cols", 8))
        if hasattr(self, "_atlas_name"):         self._atlas_name.set(s.get("atlas_name", "atlas"))
        self.outdir = data.get("outdir", "")
        self._atlas_last_out = data.get("last_out") or None
        if hasattr(self, "_outdir_lbl"):
            self._outdir_lbl.config(text=self.outdir if self.outdir else "Папка не выбрана")
        if self._atlas_last_out and hasattr(self, "_atlas_overwrite_btn"):
            self._atlas_overwrite_btn.config(state=tk.NORMAL)
        if img is not None:
            self.src_img  = img
            self.src_path = src_path
            if hasattr(self, "_src_lbl"):
                self._src_lbl.config(text=os.path.basename(src_path))
            self._atlas_update()

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
    root = TkinterDnD.Tk()
    app = SpriteManufacturerApp(root)
    root.update()
    root.mainloop()
