"""
ИИ Разделитель Спрайтов
Автор: Shtillgor (https://midgro.uz/)

ЛИЦЕНЗИЯ:
Данное ПО можно использовать свободно при условии обязательного указания автора
и ссылки на сайт (https://midgro.uz/) в заметном месте вашего проекта или документации.
"""

import cv2
import numpy as np
import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Цвета
BG   = "#2e3136"
BG2  = "#36393f"
BTN  = "#4f545c"
ACC  = "#7289da"
GRN  = "#43b581"
GOLD = "#faa61a"
RED  = "#e74c3c"
FG   = "white"
FG2  = "#b9bbbe"


class SpriteCutterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ИИ Разделитель Спрайтов v2")
        self.root.geometry("1200x850")
        self.root.minsize(960, 680)
        self.root.configure(bg=BG)

        self._set_icon()
        self.recent_dirs = self._load_config()

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",        background=BG,  borderwidth=0)
        style.configure("TNotebook.Tab",    background=BTN, foreground=FG, padding=[14, 6],
                        font=("Arial", 10, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", ACC)],
                  foreground=[("selected", FG)])
        style.configure("TSeparator",       background=BTN)
        style.configure("TCombobox",        fieldbackground=BTN, background=BTN, foreground=FG)
        style.configure("TScrollbar",       background=BTN, troughcolor=BG2)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        for attr, title in [("t_auto", "  Авто-нарезчик  "),
                             ("t_tile", "  Тайловая сетка  "),
                             ("t_shape","  Вырезание фигур  "),
                             ("t_mgr",  "  Менеджер спрайтов  "),
                             ("t_atlas","  Сборка атласа  "),
                             ("t_tilecheck", "  Тайл-тест  ")]:
            f = tk.Frame(self.nb, bg=BG)
            setattr(self, attr, f)
            self.nb.add(f, text=title)

        self._build_auto()
        self._build_tile()
        self._build_shape()
        self._build_mgr()
        self._build_atlas()
        self._build_tilecheck()

    # ═══════════════════════════════════════════════════════════════
    #  ОБЩИЕ УТИЛИТЫ
    # ═══════════════════════════════════════════════════════════════

    def _set_icon(self):
        p = os.path.join(os.path.dirname(__file__), "resource", "Icon.png")
        if os.path.exists(p):
            try:
                img = ImageTk.PhotoImage(file=p)
                self.root.iconphoto(False, img)
                self._icon = img
            except Exception as e:
                print(f"Иконка: {e}")

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f).get("recent_dirs", [])
            except:
                pass
        return []

    def _save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"recent_dirs": self.recent_dirs}, f, ensure_ascii=False, indent=4)

    def _add_recent(self, d):
        if d in self.recent_dirs:
            self.recent_dirs.remove(d)
        self.recent_dirs.insert(0, d)
        self.recent_dirs = self.recent_dirs[:8]
        self._save_config()

    def _sidebar(self, parent):
        sb = tk.Frame(parent, width=305, bg=BG, padx=10, pady=10)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        sb.pack_propagate(False)
        return sb

    def _area(self, parent):
        a = tk.Frame(parent, bg=BG2)
        a.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3, pady=3)
        return a

    def _lbl(self, parent, text, bold=False, color=FG, size=10):
        return tk.Label(parent, text=text, fg=color, bg=BG,
                        font=("Arial", size, "bold" if bold else "normal"))

    def _btn(self, parent, text, cmd, color=BTN, h=1, state=tk.NORMAL, font_size=10):
        return tk.Button(parent, text=text, command=cmd, bg=color, fg=FG,
                         font=("Arial", font_size, "bold"), height=h, state=state,
                         relief=tk.FLAT, activebackground=color, activeforeground=FG,
                         cursor="hand2")

    def _sep(self, parent):
        ttk.Separator(parent, orient="horizontal").pack(fill=tk.X, pady=9)

    def _help_btn(self, parent, tab_id):
        titles = {
            "auto":  "Авто-нарезчик",
            "tile":  "Тайловая сетка",
            "shape": "Вырезание фигур",
            "mgr":   "Менеджер спрайтов",
            "atlas": "Сборка атласа",
            "tc":    "Тайл-тест",
        }
        f = tk.Frame(parent, bg=BG)
        f.pack(fill=tk.X, pady=(0, 10))
        tk.Label(f, text=titles.get(tab_id, ""), fg=FG, bg=BG,
                 font=("Arial", 11, "bold")).pack(side=tk.LEFT)
        tk.Button(f, text=" ? ", command=lambda: self._show_tab_help(tab_id),
                  bg=ACC, fg=FG, font=("Arial", 9, "bold"), relief=tk.FLAT,
                  cursor="hand2", padx=5, pady=1,
                  activebackground="#5b6de8", activeforeground=FG).pack(side=tk.RIGHT)

    def _spinbox(self, parent, var, lo, hi, w=6, cmd=None):
        kw = dict(from_=lo, to=hi, textvariable=var, width=w, bg=BTN, fg=FG,
                  relief=tk.FLAT, highlightthickness=0, insertbackground=FG,
                  buttonbackground=BTN)
        if cmd:
            kw["command"] = cmd
        return tk.Spinbox(parent, **kw)

    def _cv2pil(self, img):
        if img is None:
            return None
        if len(img.shape) == 2:
            return Image.fromarray(img)
        if img.shape[2] == 4:
            return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA))
        return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    def _fit(self, pil_img, w, h):
        if w < 10: w = 700
        if h < 10: h = 600
        pil_img.thumbnail((w, h), Image.LANCZOS)
        return pil_img

    def _next_idx(self, folder, prefix, ext=".png"):
        idxs = []
        for f in os.listdir(folder):
            if f.startswith(prefix) and f.endswith(ext):
                try:
                    idxs.append(int(f[len(prefix):-len(ext)]))
                except ValueError:
                    pass
        return (max(idxs) + 1) if idxs else 0

    # ═══════════════════════════════════════════════════════════════
    #  ВКЛАДКА 1 — АВТО-НАРЕЗЧИК
    # ═══════════════════════════════════════════════════════════════

    def _build_auto(self):
        sb = self._sidebar(self.t_auto)
        area = self._area(self.t_auto)

        self._help_btn(sb, "auto")
        self._lbl(sb, "1. Настройка путей", bold=True).pack(anchor=tk.W, pady=(0, 8))
        self._btn(sb, "Выбрать картинки (PNG/JPG)", self.auto_open, GRN, h=2).pack(fill=tk.X, pady=3)
        self.auto_lbl_in = self._lbl(sb, "Файлы не выбраны", color=FG2)
        self.auto_lbl_in.pack(anchor=tk.W)

        self._btn(sb, "Папка сохранения", self.auto_out_dir).pack(fill=tk.X, pady=(10, 3))
        self._lbl(sb, "Недавние папки:").pack(anchor=tk.W)
        self.auto_recent = tk.StringVar()
        self.auto_cb = ttk.Combobox(sb, textvariable=self.auto_recent, state="readonly")
        self.auto_cb.pack(fill=tk.X, pady=(0, 4))
        self.auto_cb["values"] = self.recent_dirs
        if self.recent_dirs: self.auto_cb.current(0)
        self.auto_cb.bind("<<ComboboxSelected>>", self._auto_recent_sel)
        self.auto_lbl_out = self._lbl(sb, "Папка не выбрана", color=FG2)
        self.auto_lbl_out.pack(anchor=tk.W)

        self._sep(sb)
        self._lbl(sb, "2. Параметры нарезки", bold=True).pack(anchor=tk.W, pady=(0, 5))

        self._lbl(sb, "Порог фона (200–255):").pack(anchor=tk.W)
        self.auto_thresh = tk.Scale(sb, from_=200, to=255, orient=tk.HORIZONTAL,
                                    bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self.auto_thresh.set(245)
        self.auto_thresh.pack(fill=tk.X)
        self.auto_thresh.bind("<ButtonRelease-1>", lambda _: self._auto_process())

        self._lbl(sb, "Мин. размер объекта (пикс):").pack(anchor=tk.W, pady=(8, 0))
        self.auto_min = tk.Scale(sb, from_=5, to=150, orient=tk.HORIZONTAL,
                                 bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self.auto_min.set(12)
        self.auto_min.pack(fill=tk.X)
        self.auto_min.bind("<ButtonRelease-1>", lambda _: self._auto_process())

        self._lbl(sb, "Отступ вокруг (пикс):").pack(anchor=tk.W, pady=(8, 0))
        self.auto_pad = tk.Scale(sb, from_=0, to=40, orient=tk.HORIZONTAL,
                                 bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self.auto_pad.set(2)
        self.auto_pad.pack(fill=tk.X)
        self.auto_pad.bind("<ButtonRelease-1>", lambda _: self._auto_process())

        self.auto_lbl_cnt = self._lbl(sb, "Найдено объектов: 0", color=GOLD, bold=True)
        self.auto_lbl_cnt.pack(anchor=tk.W, pady=8)

        self._sep(sb)
        nav = tk.Frame(sb, bg=BG)
        nav.pack(fill=tk.X)
        self.auto_btn_prev = self._btn(nav, "◀", self.auto_prev, state=tk.DISABLED)
        self.auto_btn_prev.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.auto_nav = self._lbl(nav, "0 / 0")
        self.auto_nav.pack(side=tk.LEFT, padx=6)
        self.auto_btn_next = self._btn(nav, "▶", self.auto_next, state=tk.DISABLED)
        self.auto_btn_next.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        btm = tk.Frame(sb, bg=BG)
        btm.pack(side=tk.BOTTOM, fill=tk.X)
        self._btn(btm, "РАЗДЕЛИТЬ И СОХРАНИТЬ ВСЕ", self.auto_save, ACC, h=2).pack(fill=tk.X, pady=(0, 6))
        row = tk.Frame(btm, bg=BG)
        row.pack(fill=tk.X)
        self._btn(row, "Инструкция", self._show_help).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self._btn(row, "Автор",      self._show_author).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.auto_preview = tk.Label(area, text="Выберите изображение", bg="#1e2124", fg=FG2,
                                     font=("Arial", 14))
        self.auto_preview.pack(fill=tk.BOTH, expand=True)

        self.auto_paths  = []
        self.auto_idx    = 0
        self.auto_orig   = None
        self.auto_outdir = ""
        self.auto_photo  = None

    def auto_open(self):
        ps = filedialog.askopenfilenames(
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if not ps: return
        self.auto_paths = list(ps)
        self.auto_idx = 0
        if not self.auto_outdir:
            self.auto_outdir = os.path.dirname(ps[0])
            self.auto_lbl_out.config(text=self.auto_outdir)
            self._add_recent(self.auto_outdir)
        self._auto_display()

    def auto_out_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.auto_outdir = d
            self.auto_lbl_out.config(text=d)
            self._add_recent(d)

    def _auto_recent_sel(self, _=None):
        d = self.auto_recent.get()
        if os.path.isdir(d):
            self.auto_outdir = d
            self.auto_lbl_out.config(text=d)
        else:
            messagebox.showwarning("Внимание", "Папка не найдена")

    def auto_prev(self):
        if self.auto_idx > 0:
            self.auto_idx -= 1
            self._auto_display()

    def auto_next(self):
        if self.auto_idx < len(self.auto_paths) - 1:
            self.auto_idx += 1
            self._auto_display()

    def _auto_display(self):
        if not self.auto_paths: return
        path = self.auto_paths[self.auto_idx]
        n = len(self.auto_paths)
        self.auto_lbl_in.config(text=f"Файлов: {n}\nТекущий: {os.path.basename(path)}")
        self.auto_nav.config(text=f"{self.auto_idx+1} / {n}")
        self.auto_btn_prev.config(state=tk.NORMAL if self.auto_idx > 0 else tk.DISABLED)
        self.auto_btn_next.config(state=tk.NORMAL if self.auto_idx < n-1 else tk.DISABLED)
        self.auto_orig = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        self._auto_process()

    def _auto_contours(self, img, tv, ms):
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
        raw, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return [c for c in raw if cv2.boundingRect(c)[2] >= ms and cv2.boundingRect(c)[3] >= ms]

    def _auto_process(self):
        img = self.auto_orig
        if img is None: return
        tv = self.auto_thresh.get()
        ms = self.auto_min.get()
        contours = self._auto_contours(img, tv, ms)
        self.auto_lbl_cnt.config(text=f"Найдено объектов: {len(contours)}")

        vis = img.copy()
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            cv2.rectangle(vis, (x, y), (x+w, y+h), (0, 220, 80), 2)

        pil = self._cv2pil(vis)
        pw = self.auto_preview.winfo_width()
        ph = self.auto_preview.winfo_height()
        pil = self._fit(pil, pw, ph)
        self.auto_photo = ImageTk.PhotoImage(pil)
        self.auto_preview.config(image=self.auto_photo, text="")

    def auto_save(self):
        if not self.auto_paths or not self.auto_outdir:
            messagebox.showwarning("Ошибка", "Выберите файлы и папку сохранения")
            return
        tv = self.auto_thresh.get()
        ms = self.auto_min.get()
        pad = self.auto_pad.get()
        idx = self._next_idx(self.auto_outdir, "sprite_")
        saved = 0
        for path in self.auto_paths:
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is None: continue
            contours = self._auto_contours(img, tv, ms)
            ih, iw = img.shape[:2]
            rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA) if len(img.shape) == 3 and img.shape[2] == 3 else img.copy()
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(iw, x + w + pad)
                y2 = min(ih, y + h + pad)
                crop = rgba[y1:y2, x1:x2]
                cv2.imwrite(os.path.join(self.auto_outdir, f"sprite_{idx:04d}.png"), crop)
                idx += 1
                saved += 1
        messagebox.showinfo("Готово!", f"Сохранено {saved} спрайтов в:\n{self.auto_outdir}")

    # ═══════════════════════════════════════════════════════════════
    #  ВКЛАДКА 2 — ТАЙЛОВАЯ СЕТКА
    # ═══════════════════════════════════════════════════════════════

    def _build_tile(self):
        sb = self._sidebar(self.t_tile)
        area = self._area(self.t_tile)

        self._help_btn(sb, "tile")
        self._lbl(sb, "1. Открыть тайлсет", bold=True).pack(anchor=tk.W, pady=(0, 8))
        self._btn(sb, "Открыть тайлсет (PNG/JPG)", self.tile_open, GRN, h=2).pack(fill=tk.X, pady=3)
        self.tile_lbl_file = self._lbl(sb, "Файл не выбран", color=FG2)
        self.tile_lbl_file.pack(anchor=tk.W)

        self._sep(sb)
        self._lbl(sb, "2. Параметры сетки", bold=True).pack(anchor=tk.W, pady=(0, 6))

        self.tile_mode = tk.StringVar(value="size")
        tk.Radiobutton(sb, text="По размеру тайла (пикс)", variable=self.tile_mode,
                       value="size", bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._tile_update).pack(anchor=tk.W)
        tk.Radiobutton(sb, text="По количеству ячеек", variable=self.tile_mode,
                       value="count", bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._tile_update).pack(anchor=tk.W, pady=(0, 6))

        # Размер тайла
        sf = tk.Frame(sb, bg=BG)
        sf.pack(fill=tk.X, pady=2)
        self._lbl(sf, "Ш:").pack(side=tk.LEFT)
        self.tile_tw = tk.IntVar(value=32)
        self._spinbox(sf, self.tile_tw, 1, 2048, cmd=self._tile_update).pack(side=tk.LEFT, padx=2)
        self._lbl(sf, "  В:").pack(side=tk.LEFT)
        self.tile_th = tk.IntVar(value=32)
        self._spinbox(sf, self.tile_th, 1, 2048, cmd=self._tile_update).pack(side=tk.LEFT, padx=2)

        # Количество
        cf = tk.Frame(sb, bg=BG)
        cf.pack(fill=tk.X, pady=2)
        self._lbl(cf, "Стб:").pack(side=tk.LEFT)
        self.tile_cols = tk.IntVar(value=4)
        self._spinbox(cf, self.tile_cols, 1, 512, cmd=self._tile_update).pack(side=tk.LEFT, padx=2)
        self._lbl(cf, "  Стр:").pack(side=tk.LEFT)
        self.tile_rows = tk.IntVar(value=4)
        self._spinbox(cf, self.tile_rows, 1, 512, cmd=self._tile_update).pack(side=tk.LEFT, padx=2)

        # Отступ и зазор
        mf = tk.Frame(sb, bg=BG)
        mf.pack(fill=tk.X, pady=4)
        self._lbl(mf, "Отступ:").pack(side=tk.LEFT)
        self.tile_offset = tk.IntVar(value=0)
        self._spinbox(mf, self.tile_offset, 0, 512, cmd=self._tile_update).pack(side=tk.LEFT, padx=2)
        self._lbl(mf, "  Зазор:").pack(side=tk.LEFT)
        self.tile_spacing = tk.IntVar(value=0)
        self._spinbox(mf, self.tile_spacing, 0, 256, cmd=self._tile_update).pack(side=tk.LEFT, padx=2)

        self.tile_skip = tk.BooleanVar(value=True)
        tk.Checkbutton(sb, text="Пропускать пустые тайлы", variable=self.tile_skip,
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._tile_update).pack(anchor=tk.W, pady=4)

        self._btn(sb, "Обновить превью", self._tile_update).pack(fill=tk.X, pady=4)

        self.tile_lbl_cnt = self._lbl(sb, "Тайлов: —", color=GOLD, bold=True)
        self.tile_lbl_cnt.pack(anchor=tk.W, pady=4)

        self._sep(sb)
        self._btn(sb, "Папка сохранения", self.tile_out_dir).pack(fill=tk.X)
        self.tile_lbl_out = self._lbl(sb, "Папка не выбрана", color=FG2)
        self.tile_lbl_out.pack(anchor=tk.W, pady=(3, 0))

        self.tile_btn_save = self._btn(sb, "НАРЕЗАТЬ И СОХРАНИТЬ", self.tile_save,
                                       ACC, h=2, state=tk.DISABLED)
        self.tile_btn_save.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        self.tile_canvas = tk.Canvas(area, bg="#1e2124", highlightthickness=0)
        self.tile_canvas.pack(fill=tk.BOTH, expand=True)
        self.tile_canvas.bind("<Configure>", lambda _: self._tile_update())

        self.tile_img   = None
        self.tile_outdir = ""
        self.tile_photo = None

    def tile_open(self):
        path = filedialog.askopenfilename(
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if not path: return
        self.tile_img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        self.tile_lbl_file.config(text=f"{os.path.basename(path)}  "
                                       f"({self.tile_img.shape[1]}×{self.tile_img.shape[0]})")
        if not self.tile_outdir:
            self.tile_outdir = os.path.dirname(path)
            self.tile_lbl_out.config(text=self.tile_outdir)
        self._tile_update()
        self.tile_btn_save.config(state=tk.NORMAL if self.tile_outdir else tk.DISABLED)

    def tile_out_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.tile_outdir = d
            self.tile_lbl_out.config(text=d)
            if self.tile_img is not None:
                self.tile_btn_save.config(state=tk.NORMAL)

    def _tile_grid(self):
        if self.tile_img is None: return []
        ih, iw = self.tile_img.shape[:2]
        off = max(0, self.tile_offset.get())
        sp  = max(0, self.tile_spacing.get())

        if self.tile_mode.get() == "size":
            tw = max(1, self.tile_tw.get())
            th = max(1, self.tile_th.get())
            cols = max(1, (iw - 2*off + sp) // (tw + sp))
            rows = max(1, (ih - 2*off + sp) // (th + sp))
        else:
            cols = max(1, self.tile_cols.get())
            rows = max(1, self.tile_rows.get())
            avw = max(1, iw - 2*off - sp*(cols-1))
            avh = max(1, ih - 2*off - sp*(rows-1))
            tw  = max(1, avw // cols)
            th  = max(1, avh // rows)

        tiles = []
        for r in range(rows):
            for c in range(cols):
                x = off + c * (tw + sp)
                y = off + r * (th + sp)
                if x + tw > iw or y + th > ih:
                    continue
                tiles.append((x, y, tw, th))
        return tiles

    def _tile_is_empty(self, crop):
        if crop is None or crop.size == 0: return True
        if len(crop.shape) == 3 and crop.shape[2] == 4:
            return int(crop[:, :, 3].mean()) < 5
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        return float(gray.std()) < 3.0

    def _tile_update(self, *_):
        if self.tile_img is None: return
        tiles = self._tile_grid()
        skip  = self.tile_skip.get()
        img   = self.tile_img

        vis = self._cv2pil(img).convert("RGB")
        draw = ImageDraw.Draw(vis)
        count = 0
        for (x, y, tw, th) in tiles:
            crop = img[y:y+th, x:x+tw]
            empty = skip and self._tile_is_empty(crop)
            color = "#505050" if empty else "#00e050"
            draw.rectangle([x, y, x+tw-1, y+th-1], outline=color, width=1)
            if not empty:
                count += 1

        self.tile_lbl_cnt.config(text=f"Тайлов: {count}")
        cw = self.tile_canvas.winfo_width()  or 700
        ch = self.tile_canvas.winfo_height() or 600
        vis.thumbnail((cw, ch), Image.LANCZOS)
        self.tile_photo = ImageTk.PhotoImage(vis)
        self.tile_canvas.delete("all")
        self.tile_canvas.create_image(cw//2, ch//2, anchor=tk.CENTER, image=self.tile_photo)

    def tile_save(self):
        tiles = self._tile_grid()
        if not tiles or self.tile_img is None: return
        img  = self.tile_img
        skip = self.tile_skip.get()
        rgba = (cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                if len(img.shape) == 3 and img.shape[2] == 3 else img.copy())
        idx   = self._next_idx(self.tile_outdir, "tile_")
        saved = 0
        for (x, y, tw, th) in tiles:
            crop = rgba[y:y+th, x:x+tw]
            if skip and self._tile_is_empty(crop): continue
            cv2.imwrite(os.path.join(self.tile_outdir, f"tile_{idx:04d}.png"), crop)
            idx   += 1
            saved += 1
        messagebox.showinfo("Готово!", f"Сохранено {saved} тайлов в:\n{self.tile_outdir}")

    # ═══════════════════════════════════════════════════════════════
    #  ВКЛАДКА 3 — ВЫРЕЗАНИЕ ФИГУР
    # ═══════════════════════════════════════════════════════════════

    def _build_shape(self):
        sb = self._sidebar(self.t_shape)
        area = self._area(self.t_shape)

        self._help_btn(sb, "shape")
        self._lbl(sb, "1. Изображение", bold=True).pack(anchor=tk.W, pady=(0, 8))
        self._btn(sb, "Открыть изображение", self.shape_open, GRN, h=2).pack(fill=tk.X, pady=3)
        self.shape_lbl_file = self._lbl(sb, "Файл не выбран", color=FG2)
        self.shape_lbl_file.pack(anchor=tk.W)

        self._sep(sb)
        self._lbl(sb, "2. Инструмент", bold=True).pack(anchor=tk.W, pady=(0, 5))

        self.shape_tool = tk.StringVar(value="rect")
        tools = [("Прямоугольник (тяни мышью)", "rect"),
                 ("Многоугольник (клик→ПКМ)", "poly"),
                 ("Произвольная (тяни→ПКМ)", "lasso")]
        for txt, val in tools:
            tk.Radiobutton(sb, text=txt, variable=self.shape_tool, value=val,
                           bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                           command=self._shape_reset).pack(anchor=tk.W)

        self.shape_transp = tk.BooleanVar(value=True)
        tk.Checkbutton(sb, text="Прозрачный фон при вырезании",
                       variable=self.shape_transp, bg=BG, fg=FG,
                       selectcolor=BTN, activebackground=BG).pack(anchor=tk.W, pady=(10, 0))

        self._sep(sb)
        self._lbl(sb, "3. Выделения", bold=True).pack(anchor=tk.W, pady=(0, 5))

        lf = tk.Frame(sb, bg=BG2, bd=1, relief=tk.SUNKEN)
        lf.pack(fill=tk.BOTH, expand=True)
        self.shape_lb = tk.Listbox(lf, bg=BG2, fg=FG, selectbackground=ACC,
                                   height=7, font=("Arial", 9), relief=tk.FLAT,
                                   highlightthickness=0)
        self.shape_lb.pack(fill=tk.BOTH, expand=True)

        row = tk.Frame(sb, bg=BG)
        row.pack(fill=tk.X, pady=4)
        self._btn(row, "Удалить выбранное", self._shape_del_sel).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self._btn(row, "Очистить всё",      self._shape_clear).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        btm = tk.Frame(sb, bg=BG)
        btm.pack(side=tk.BOTTOM, fill=tk.X)
        self._btn(btm, "Папка сохранения", self.shape_out_dir).pack(fill=tk.X, pady=(0, 4))
        self.shape_lbl_out = self._lbl(btm, "Папка не выбрана", color=FG2)
        self.shape_lbl_out.pack(anchor=tk.W, pady=(0, 6))
        self.shape_btn_save = self._btn(btm, "ВЫРЕЗАТЬ И СОХРАНИТЬ", self.shape_save,
                                        ACC, h=2, state=tk.DISABLED)
        self.shape_btn_save.pack(fill=tk.X, pady=(0, 4))
        self._lbl(btm, "Esc — сброс  |  ПКМ — завершить фигуру", color=FG2, size=8).pack(anchor=tk.W)

        self.shape_cv = tk.Canvas(area, bg="#1e2124", cursor="crosshair", highlightthickness=0)
        self.shape_cv.pack(fill=tk.BOTH, expand=True)
        self.shape_cv.bind("<ButtonPress-1>",   self._sh_press)
        self.shape_cv.bind("<B1-Motion>",       self._sh_drag)
        self.shape_cv.bind("<ButtonRelease-1>", self._sh_release)
        self.shape_cv.bind("<ButtonPress-3>",   self._sh_finish)
        self.shape_cv.bind("<Motion>",          self._sh_move)
        self.shape_cv.bind("<Configure>",       lambda _: self._shape_render())
        self.root.bind("<Escape>", lambda _: self._shape_reset())

        self.shape_img    = None
        self.shape_pil    = None
        self.shape_outdir = ""
        self.shape_photo  = None
        self.shape_scale  = 1.0
        self.shape_ox     = 0
        self.shape_oy     = 0
        self.shape_sels   = []    # [(pts_img, tool_name)]
        self.shape_cur    = []    # текущие точки (img coords)
        self.shape_down   = False
        self.shape_start  = None
        self._shape_sel_colors = ["#e74c3c","#3498db","#2ecc71","#f39c12","#9b59b6","#1abc9c"]

    def shape_open(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(
                filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if not path: return
        self.shape_img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        self.shape_pil = self._cv2pil(self.shape_img).convert("RGBA")
        self.shape_lbl_file.config(text=f"{os.path.basename(path)}  "
                                        f"({self.shape_pil.width}×{self.shape_pil.height})")
        self.shape_sels.clear()
        self.shape_cur = []
        self.shape_lb.delete(0, tk.END)
        if not self.shape_outdir:
            self.shape_outdir = os.path.dirname(path)
            self.shape_lbl_out.config(text=self.shape_outdir)
        self._shape_render()

    def shape_out_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.shape_outdir = d
            self.shape_lbl_out.config(text=d)
            if self.shape_sels:
                self.shape_btn_save.config(state=tk.NORMAL)

    def _c2i(self, cx, cy):
        """Canvas coords → image coords."""
        return (cx - self.shape_ox) / self.shape_scale, (cy - self.shape_oy) / self.shape_scale

    def _i2c(self, pts):
        """Image coords → displayed image (scaled) coords."""
        return [(int(x * self.shape_scale), int(y * self.shape_scale)) for x, y in pts]

    def _shape_reset(self):
        self.shape_cur  = []
        self.shape_down = False
        self.shape_start = None
        self._shape_render()

    def _sh_press(self, e):
        if self.shape_img is None: return
        ix, iy = self._c2i(e.x, e.y)
        tool = self.shape_tool.get()
        if tool == "rect":
            self.shape_down  = True
            self.shape_start = (ix, iy)
        else:
            self.shape_cur.append((ix, iy))
            self.shape_down = True

    def _sh_drag(self, e):
        if not self.shape_down: return
        tool = self.shape_tool.get()
        if tool == "rect":
            self._shape_render(rect_end=(e.x, e.y))
        elif tool == "lasso":
            ix, iy = self._c2i(e.x, e.y)
            self.shape_cur.append((ix, iy))
            self._shape_render()

    def _sh_release(self, e):
        if self.shape_tool.get() == "rect" and self.shape_down:
            ix, iy = self._c2i(e.x, e.y)
            sx, sy = self.shape_start
            pts = [(sx, sy), (ix, sy), (ix, iy), (sx, iy)]
            self._shape_add(pts, "rect")
            self.shape_down  = False
            self.shape_start = None

    def _sh_finish(self, _=None):
        tool = self.shape_tool.get()
        if tool in ("poly", "lasso") and len(self.shape_cur) >= 3:
            self._shape_add(list(self.shape_cur), tool)
        self.shape_cur  = []
        self.shape_down = False

    def _sh_move(self, e):
        if self.shape_down and self.shape_tool.get() == "poly":
            self._shape_render(poly_cur=(e.x, e.y))

    def _shape_add(self, pts, stype):
        self.shape_sels.append((pts, stype))
        n = len(self.shape_sels)
        self.shape_lb.insert(tk.END, f"#{n}  {stype}  ({len(pts)} точек)")
        if self.shape_outdir:
            self.shape_btn_save.config(state=tk.NORMAL)
        self._shape_render()

    def _shape_del_sel(self):
        sel = self.shape_lb.curselection()
        if not sel: return
        i = sel[0]
        self.shape_sels.pop(i)
        self.shape_lb.delete(0, tk.END)
        for j, (pts, st) in enumerate(self.shape_sels):
            self.shape_lb.insert(tk.END, f"#{j+1}  {st}  ({len(pts)} точек)")
        if not self.shape_sels:
            self.shape_btn_save.config(state=tk.DISABLED)
        self._shape_render()

    def _shape_clear(self):
        self.shape_sels.clear()
        self.shape_cur = []
        self.shape_lb.delete(0, tk.END)
        self.shape_btn_save.config(state=tk.DISABLED)
        self._shape_render()

    def _shape_render(self, rect_end=None, poly_cur=None):
        if self.shape_pil is None: return
        iw, ih = self.shape_pil.size
        cw = self.shape_cv.winfo_width()  or 700
        ch = self.shape_cv.winfo_height() or 600

        scale = min(cw / iw, ch / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        self.shape_scale = scale
        self.shape_ox = (cw - nw) // 2
        self.shape_oy = (ch - nh) // 2

        vis = self.shape_pil.convert("RGB").resize((nw, nh), Image.LANCZOS)
        draw = ImageDraw.Draw(vis)

        for i, (pts, _) in enumerate(self.shape_sels):
            c = self._i2c(pts)
            col = self._shape_sel_colors[i % len(self._shape_sel_colors)]
            if len(c) >= 2:
                draw.polygon(c, outline=col)
            for p in c:
                draw.ellipse([p[0]-3, p[1]-3, p[0]+3, p[1]+3], fill=col)

        if self.shape_down:
            tool = self.shape_tool.get()
            if tool == "rect" and self.shape_start and rect_end:
                sx = int(self.shape_start[0] * scale)
                sy = int(self.shape_start[1] * scale)
                ex = rect_end[0] - self.shape_ox
                ey = rect_end[1] - self.shape_oy
                draw.rectangle([sx, sy, ex, ey], outline="#ffff00", width=2)
            elif tool in ("poly", "lasso") and self.shape_cur:
                c = self._i2c(self.shape_cur)
                if len(c) >= 2:
                    draw.line(c, fill="#ffff00", width=2)
                if poly_cur and len(c) >= 1:
                    pc = (poly_cur[0] - self.shape_ox, poly_cur[1] - self.shape_oy)
                    draw.line([c[-1], pc], fill="#ffff00", width=1)

        self.shape_photo = ImageTk.PhotoImage(vis)
        self.shape_cv.delete("all")
        self.shape_cv.create_image(self.shape_ox, self.shape_oy,
                                   anchor=tk.NW, image=self.shape_photo)

    def shape_save(self):
        if not self.shape_sels or self.shape_pil is None: return
        iw, ih = self.shape_pil.size
        idx   = self._next_idx(self.shape_outdir, "cut_")
        saved = 0
        base  = self.shape_pil.copy()

        for pts, _ in self.shape_sels:
            xs = [int(x) for x, _ in pts]
            ys = [int(y) for _, y in pts]
            x0 = max(0, min(xs)); y0 = max(0, min(ys))
            x1 = min(iw, max(xs)); y1 = min(ih, max(ys))
            if x1 <= x0 or y1 <= y0: continue

            if self.shape_transp.get():
                mask = Image.new("L", (iw, ih), 0)
                md   = ImageDraw.Draw(mask)
                md.polygon([(int(x), int(y)) for x, y in pts], fill=255)
                out  = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
                out.paste(base, mask=mask)
                crop = out.crop((x0, y0, x1, y1))
            else:
                crop = base.crop((x0, y0, x1, y1)).convert("RGBA")

            crop.save(os.path.join(self.shape_outdir, f"cut_{idx:04d}.png"))
            idx   += 1
            saved += 1
        messagebox.showinfo("Готово!", f"Вырезано {saved} фигур в:\n{self.shape_outdir}")

    # ═══════════════════════════════════════════════════════════════
    #  ВКЛАДКА 4 — МЕНЕДЖЕР СПРАЙТОВ
    # ═══════════════════════════════════════════════════════════════

    def _build_mgr(self):
        sb = self._sidebar(self.t_mgr)
        area = self._area(self.t_mgr)

        self._help_btn(sb, "mgr")
        self._lbl(sb, "1. Загрузка спрайтов", bold=True).pack(anchor=tk.W, pady=(0, 8))
        self._btn(sb, "Папка со спрайтами", self.mgr_open_folder, GRN, h=2).pack(fill=tk.X, pady=3)
        self._btn(sb, "Добавить отдельные файлы", self.mgr_add_files).pack(fill=tk.X, pady=3)
        self.mgr_lbl_loaded = self._lbl(sb, "Загружено: 0", color=FG2)
        self.mgr_lbl_loaded.pack(anchor=tk.W)

        self._sep(sb)
        self._lbl(sb, "2. Управление выборкой", bold=True).pack(anchor=tk.W, pady=(0, 5))

        row1 = tk.Frame(sb, bg=BG)
        row1.pack(fill=tk.X)
        self._btn(row1, "Выбрать все", self.mgr_sel_all).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self._btn(row1, "Снять все",   self.mgr_desel_all).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self._btn(row1, "Инверт.",     self.mgr_invert).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self._lbl(sb, "Мин. размер фильтр (пикс):", color=FG2).pack(anchor=tk.W, pady=(8, 0))
        self.mgr_minsize = tk.IntVar(value=1)
        tk.Scale(sb, from_=1, to=512, variable=self.mgr_minsize, orient=tk.HORIZONTAL,
                 bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0,
                 command=lambda _: self.mgr_auto_filter()).pack(fill=tk.X)

        self.mgr_lbl_sel = self._lbl(sb, "Выбрано: 0", color=GOLD, bold=True)
        self.mgr_lbl_sel.pack(anchor=tk.W, pady=6)

        self._sep(sb)
        self._lbl(sb, "3. Параметры спрайт-листа", bold=True).pack(anchor=tk.W, pady=(0, 5))

        g1 = tk.Frame(sb, bg=BG); g1.pack(fill=tk.X, pady=2)
        self._lbl(g1, "Столбцов:").pack(side=tk.LEFT)
        self.mgr_cols = tk.IntVar(value=8)
        self._spinbox(g1, self.mgr_cols, 1, 128).pack(side=tk.LEFT, padx=4)

        g2 = tk.Frame(sb, bg=BG); g2.pack(fill=tk.X, pady=2)
        self._lbl(g2, "Отступ (пикс):").pack(side=tk.LEFT)
        self.mgr_pad = tk.IntVar(value=4)
        self._spinbox(g2, self.mgr_pad, 0, 128).pack(side=tk.LEFT, padx=4)

        self.mgr_uniform = tk.BooleanVar(value=True)
        tk.Checkbutton(sb, text="Единый размер ячеек (выравнивание)",
                       variable=self.mgr_uniform, bg=BG, fg=FG,
                       selectcolor=BTN, activebackground=BG).pack(anchor=tk.W, pady=3)

        self._sep(sb)
        self._btn(sb, "Папка сохранения", self.mgr_out_dir).pack(fill=tk.X)
        self.mgr_lbl_out = self._lbl(sb, "Папка не выбрана", color=FG2)
        self.mgr_lbl_out.pack(anchor=tk.W, pady=(3, 0))

        btm = tk.Frame(sb, bg=BG)
        btm.pack(side=tk.BOTTOM, fill=tk.X)
        self.mgr_btn_sheet = self._btn(btm, "СОБРАТЬ СПРАЙТ-ЛИСТ", self.mgr_export,
                                       ACC, h=2, state=tk.DISABLED)
        self.mgr_btn_sheet.pack(fill=tk.X, pady=(0, 4))
        self._btn(btm, "Удалить незмеченные из списка", self.mgr_remove_unchecked,
                  RED).pack(fill=tk.X, pady=(0, 4))

        # Скроллируемая сетка превью
        self.mgr_canvas = tk.Canvas(area, bg=BG2, highlightthickness=0)
        vsb = ttk.Scrollbar(area, orient=tk.VERTICAL, command=self.mgr_canvas.yview)
        self.mgr_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.mgr_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.mgr_inner = tk.Frame(self.mgr_canvas, bg=BG2)
        self.mgr_win = self.mgr_canvas.create_window((0, 0), window=self.mgr_inner, anchor=tk.NW)
        self.mgr_inner.bind("<Configure>", self._mgr_frame_cfg)
        self.mgr_canvas.bind("<Configure>", self._mgr_canvas_cfg)
        self.mgr_canvas.bind("<Enter>",    lambda _: self.mgr_canvas.focus_set())
        self.mgr_canvas.bind("<MouseWheel>", self._mgr_scroll)
        self.mgr_canvas.bind("<Button-4>",  self._mgr_scroll)
        self.mgr_canvas.bind("<Button-5>",  self._mgr_scroll)
        self.mgr_inner.bind("<MouseWheel>", self._mgr_scroll)
        self.mgr_inner.bind("<Button-4>",   self._mgr_scroll)
        self.mgr_inner.bind("<Button-5>",   self._mgr_scroll)

        self.mgr_sprites = []   # [{"path", "img":PIL, "var":BoolVar, "thumb":PhotoImage}]
        self.mgr_outdir  = ""

    def _mgr_frame_cfg(self, _):
        self.mgr_canvas.configure(scrollregion=self.mgr_canvas.bbox("all"))

    def _mgr_canvas_cfg(self, e):
        self.mgr_canvas.itemconfig(self.mgr_win, width=e.width)

    def _mgr_scroll(self, e):
        if e.num == 4 or getattr(e, "delta", 0) > 0:
            self.mgr_canvas.yview_scroll(-1, "units")
        else:
            self.mgr_canvas.yview_scroll(1, "units")

    def mgr_open_folder(self):
        d = filedialog.askdirectory()
        if not d: return
        paths = sorted(
            os.path.join(d, f) for f in os.listdir(d)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")))
        if not paths:
            messagebox.showinfo("Пусто", "В папке нет изображений")
            return
        self.mgr_sprites.clear()
        for p in paths:
            self._mgr_add(p)
        if not self.mgr_outdir:
            self.mgr_outdir = d
            self.mgr_lbl_out.config(text=d)
        self._mgr_rebuild()
        self._mgr_upd()

    def mgr_add_files(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if not paths: return
        for p in paths:
            self._mgr_add(p)
        self._mgr_rebuild()
        self._mgr_upd()

    def _mgr_add(self, path):
        try:
            img = Image.open(path).convert("RGBA")
            self.mgr_sprites.append({
                "path": path,
                "img":  img,
                "var":  tk.BooleanVar(value=True),
                "thumb": None,
            })
        except Exception as ex:
            print(f"Не загружено: {path} — {ex}")

    def _mgr_rebuild(self):
        for w in self.mgr_inner.winfo_children():
            w.destroy()

        THUMB = 80
        COLS  = max(1, (self.mgr_canvas.winfo_width() or 700) // (THUMB + 12))

        for i, spr in enumerate(self.mgr_sprites):
            r, c = divmod(i, COLS)
            cell = tk.Frame(self.mgr_inner, bg=BG2, padx=2, pady=2)
            cell.grid(row=r, column=c, padx=4, pady=4, sticky="n")

            thumb = spr["img"].copy()
            thumb.thumbnail((THUMB, THUMB), Image.LANCZOS)
            bg_img = Image.new("RGBA", (THUMB, THUMB), (46, 46, 54, 255))
            ox = (THUMB - thumb.width)  // 2
            oy = (THUMB - thumb.height) // 2
            bg_img.paste(thumb, (ox, oy), thumb)
            photo = ImageTk.PhotoImage(bg_img)
            spr["thumb"] = photo

            lbl = tk.Label(cell, image=photo, bg=BG2)
            lbl.pack()

            name = os.path.basename(spr["path"])
            short = name[:13] + "…" if len(name) > 14 else name
            cb = tk.Checkbutton(cell, text=short, variable=spr["var"],
                                 bg=BG2, fg=FG, selectcolor=BTN, activebackground=BG2,
                                 font=("Arial", 7), command=self._mgr_upd, wraplength=THUMB+10)
            cb.pack()

            sz = f"{spr['img'].width}×{spr['img'].height}"
            tk.Label(cell, text=sz, bg=BG2, fg=FG2, font=("Arial", 6)).pack()

        self.mgr_lbl_loaded.config(text=f"Загружено: {len(self.mgr_sprites)} спрайтов")
        self._mgr_upd()

    def _mgr_upd(self):
        n = sum(1 for s in self.mgr_sprites if s["var"].get())
        self.mgr_lbl_sel.config(text=f"Выбрано: {n}")
        ok = n > 0 and bool(self.mgr_outdir)
        self.mgr_btn_sheet.config(state=tk.NORMAL if ok else tk.DISABLED)

    def mgr_sel_all(self):
        for s in self.mgr_sprites: s["var"].set(True)
        self._mgr_upd()

    def mgr_desel_all(self):
        for s in self.mgr_sprites: s["var"].set(False)
        self._mgr_upd()

    def mgr_invert(self):
        for s in self.mgr_sprites: s["var"].set(not s["var"].get())
        self._mgr_upd()

    def mgr_auto_filter(self):
        ms = self.mgr_minsize.get()
        for s in self.mgr_sprites:
            w, h = s["img"].size
            s["var"].set(w >= ms and h >= ms)
        self._mgr_upd()

    def mgr_out_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.mgr_outdir = d
            self.mgr_lbl_out.config(text=d)
            self._mgr_upd()

    def mgr_remove_unchecked(self):
        removed = sum(1 for s in self.mgr_sprites if not s["var"].get())
        if not removed:
            messagebox.showinfo("Ничего", "Нет снятых галочек")
            return
        if not messagebox.askyesno("Подтверждение",
                                   f"Убрать из списка {removed} незмеченных спрайтов?"):
            return
        self.mgr_sprites = [s for s in self.mgr_sprites if s["var"].get()]
        self._mgr_rebuild()

    def mgr_export(self):
        sel = [s for s in self.mgr_sprites if s["var"].get()]
        if not sel or not self.mgr_outdir: return

        cols = max(1, self.mgr_cols.get())
        pad  = max(0, self.mgr_pad.get())

        if self.mgr_uniform.get():
            cw = max(s["img"].width  for s in sel)
            ch = max(s["img"].height for s in sel)
        else:
            cw = max(s["img"].width  for s in sel)
            ch = max(s["img"].height for s in sel)

        rows     = (len(sel) + cols - 1) // cols
        sheet_w  = cols * (cw + pad) + pad
        sheet_h  = rows * (ch + pad) + pad
        sheet    = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

        for i, spr in enumerate(sel):
            r, c = divmod(i, cols)
            x = pad + c * (cw + pad)
            y = pad + r * (ch + pad)
            img = spr["img"]
            if self.mgr_uniform.get():
                ox = (cw - img.width)  // 2
                oy = (ch - img.height) // 2
            else:
                ox = oy = 0
            sheet.paste(img, (x + ox, y + oy), img)

        out = os.path.join(self.mgr_outdir, "spritesheet.png")
        sheet.save(out)
        messagebox.showinfo("Готово!",
                            f"Спрайт-лист {sheet_w}×{sheet_h} px, {len(sel)} спрайтов\n"
                            f"Сохранён: {out}")

    # ═══════════════════════════════════════════════════════════════
    #  ВКЛАДКА 5 — СБОРКА АТЛАСА
    # ═══════════════════════════════════════════════════════════════

    def _build_atlas(self):
        sb = self._sidebar(self.t_atlas)
        area = self._area(self.t_atlas)

        self._help_btn(sb, "atlas")
        self._lbl(sb, "1. Изображение", bold=True).pack(anchor=tk.W, pady=(0, 8))
        self._btn(sb, "Открыть картинку (без фона)", self.atlas_open, GRN, h=2).pack(fill=tk.X, pady=3)
        self.atlas_lbl_file = self._lbl(sb, "Файл не выбран", color=FG2)
        self.atlas_lbl_file.pack(anchor=tk.W)

        self._sep(sb)
        self._lbl(sb, "2. Поиск объектов", bold=True).pack(anchor=tk.W, pady=(0, 5))

        self._lbl(sb, "Порог фона (200–255):").pack(anchor=tk.W)
        self.atlas_thresh = tk.Scale(sb, from_=200, to=255, orient=tk.HORIZONTAL,
                                     bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self.atlas_thresh.set(245)
        self.atlas_thresh.pack(fill=tk.X)
        self.atlas_thresh.bind("<ButtonRelease-1>", lambda _: self._atlas_update())

        self._lbl(sb, "Мин. размер объекта (пикс):").pack(anchor=tk.W, pady=(8, 0))
        self.atlas_min = tk.Scale(sb, from_=5, to=150, orient=tk.HORIZONTAL,
                                  bg=BG, fg=FG, troughcolor=BTN, highlightthickness=0)
        self.atlas_min.set(12)
        self.atlas_min.pack(fill=tk.X)
        self.atlas_min.bind("<ButtonRelease-1>", lambda _: self._atlas_update())

        self.atlas_lbl_cnt = self._lbl(sb, "Найдено объектов: 0", color=GOLD, bold=True)
        self.atlas_lbl_cnt.pack(anchor=tk.W, pady=6)

        self._sep(sb)
        self._lbl(sb, "3. Размер одного объекта", bold=True).pack(anchor=tk.W, pady=(0, 5))

        pf = tk.Frame(sb, bg=BG)
        pf.pack(fill=tk.X, pady=2)
        for val in (16, 32, 64, 128, 256):
            self._btn(pf, str(val), lambda v=val: self._atlas_preset(v),
                      font_size=9).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        cf = tk.Frame(sb, bg=BG)
        cf.pack(fill=tk.X, pady=(6, 2))
        self._lbl(cf, "Ячейка (пикс):").pack(side=tk.LEFT)
        self.atlas_cell = tk.IntVar(value=64)
        self._spinbox(cf, self.atlas_cell, 4, 2048, cmd=self._atlas_update).pack(side=tk.LEFT, padx=4)
        self.atlas_cell.trace_add("write", lambda *_: self._atlas_update())

        self.atlas_scale_fit = tk.BooleanVar(value=True)
        tk.Checkbutton(sb, text="Масштабировать объект под ячейку", variable=self.atlas_scale_fit,
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._atlas_update).pack(anchor=tk.W, pady=(4, 0))

        self.atlas_no_upscale = tk.BooleanVar(value=True)
        tk.Checkbutton(sb, text="Не увеличивать мелкие объекты", variable=self.atlas_no_upscale,
                       bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                       command=self._atlas_update).pack(anchor=tk.W)

        self._sep(sb)
        self._lbl(sb, "4. Компоновка атласа", bold=True).pack(anchor=tk.W, pady=(0, 5))

        gf = tk.Frame(sb, bg=BG)
        gf.pack(fill=tk.X, pady=2)
        self._lbl(gf, "Столбцов:").pack(side=tk.LEFT)
        self.atlas_cols = tk.IntVar(value=8)
        self._spinbox(gf, self.atlas_cols, 1, 128, cmd=self._atlas_update).pack(side=tk.LEFT, padx=4)
        self.atlas_cols.trace_add("write", lambda *_: self._atlas_update())

        self._lbl(sb, "Ячейки без зазора — атлас точно кратен\nразмеру ячейки (для движков/тайлмапов).",
                  color=FG2, size=8).pack(anchor=tk.W, pady=(2, 0))

        self._btn(sb, "Обновить превью", self._atlas_update).pack(fill=tk.X, pady=(6, 4))

        self.atlas_lbl_size = self._lbl(sb, "Размер атласа: — (авторасчёт)", color=FG2)
        self.atlas_lbl_size.pack(anchor=tk.W)

        self._sep(sb)
        self._btn(sb, "Папка сохранения", self.atlas_out_dir).pack(fill=tk.X)
        self.atlas_lbl_out = self._lbl(sb, "Папка не выбрана", color=FG2)
        self.atlas_lbl_out.pack(anchor=tk.W, pady=(3, 0))

        self._lbl(sb, "Имя файла:").pack(anchor=tk.W, pady=(6, 0))
        self.atlas_name = tk.StringVar(value="atlas")
        self.atlas_name_entry = tk.Entry(sb, textvariable=self.atlas_name, bg=BTN, fg=FG,
                                         relief=tk.FLAT, insertbackground=FG)
        self.atlas_name_entry.pack(fill=tk.X, pady=(2, 0))
        self.atlas_name_entry.bind("<KeyRelease>", lambda _: setattr(self, "_atlas_name_manual", True))

        self.atlas_btn_save = self._btn(sb, "СОБРАТЬ И СОХРАНИТЬ АТЛАС", self.atlas_save,
                                        ACC, h=2, state=tk.DISABLED)
        self.atlas_btn_save.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        self.atlas_canvas = tk.Canvas(area, bg="#1e2124", highlightthickness=0)
        self.atlas_canvas.pack(fill=tk.BOTH, expand=True)
        self.atlas_canvas.bind("<Configure>", lambda _: self._atlas_update())

        self.atlas_img    = None
        self.atlas_outdir = ""
        self.atlas_photo  = None
        self.atlas_sheet  = None   # собранный атлас (PIL RGBA, полное разрешение)
        self.atlas_count  = 0
        self.atlas_src_path    = None
        self._atlas_name_manual = False

    def atlas_open(self):
        path = filedialog.askopenfilename(
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if not path: return
        self.atlas_img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        self.atlas_src_path = path
        self.atlas_lbl_file.config(text=f"{os.path.basename(path)}  "
                                        f"({self.atlas_img.shape[1]}×{self.atlas_img.shape[0]})")
        if not self.atlas_outdir:
            self.atlas_outdir = os.path.dirname(path)
            self.atlas_lbl_out.config(text=self.atlas_outdir)
            self._add_recent(self.atlas_outdir)
        self._atlas_name_manual = False
        self._atlas_suggest_name()
        self._atlas_update()

    def atlas_out_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.atlas_outdir = d
            self.atlas_lbl_out.config(text=d)
            self._add_recent(d)
            self._atlas_suggest_name()
            if self.atlas_sheet is not None:
                self.atlas_btn_save.config(state=tk.NORMAL)

    def _atlas_suggest_name(self):
        """Предлагает имя файла атласа, если пользователь не менял его вручную."""
        if self._atlas_name_manual:
            return
        base = (os.path.splitext(os.path.basename(self.atlas_src_path))[0] + "_atlas"
                if self.atlas_src_path else "atlas")
        name = base
        if self.atlas_outdir:
            n = 1
            while os.path.exists(os.path.join(self.atlas_outdir, name + ".png")):
                n += 1
                name = f"{base}_{n}"
        self.atlas_name.set(name)

    def _atlas_preset(self, v):
        self.atlas_cell.set(v)
        self._atlas_update()

    def _atlas_build(self):
        """Находит объекты, выравнивает каждый в ячейку и собирает атлас
        без зазоров — атлас строго кратен размеру ячейки (cols*cell × rows*cell).
        Возвращает (PIL RGBA атлас, кол-во объектов, ячейка, столбцы, строки)
        либо (None, 0, ..., ...) если объектов нет."""
        img = self.atlas_img
        cell0 = max(4, self.atlas_cell.get())
        if img is None: return None, 0, cell0, 0, 0
        tv = self.atlas_thresh.get()
        ms = self.atlas_min.get()
        contours = self._auto_contours(img, tv, ms)
        if not contours: return None, 0, cell0, 0, 0

        cell = cell0
        cols = max(1, self.atlas_cols.get())
        fit  = self.atlas_scale_fit.get()
        no_up = self.atlas_no_upscale.get()

        rgba = (cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                if len(img.shape) == 3 and img.shape[2] == 3 else img.copy())

        # сортировка объектов сверху-вниз, слева-направо (по строкам исходной картинки)
        boxes = [cv2.boundingRect(c) for c in contours]
        boxes.sort(key=lambda b: (b[1] // max(1, cell), b[0]))

        tiles = []
        for (x, y, w, h) in boxes:
            crop = rgba[y:y+h, x:x+w]
            pil = self._cv2pil(crop).convert("RGBA")
            if fit:
                scale = min(cell / pil.width, cell / pil.height)
                if no_up:
                    scale = min(scale, 1.0)
                if scale != 1.0:
                    nw = max(1, round(pil.width * scale))
                    nh = max(1, round(pil.height * scale))
                    pil = pil.resize((nw, nh), Image.LANCZOS)
            elif pil.width > cell or pil.height > cell:
                l = max(0, (pil.width  - cell) // 2)
                t = max(0, (pil.height - cell) // 2)
                pil = pil.crop((l, t, l + min(cell, pil.width), t + min(cell, pil.height)))
            tiles.append(pil)

        n = len(tiles)
        cols = min(cols, n)
        rows = (n + cols - 1) // cols
        sheet = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 0))

        for i, pil in enumerate(tiles):
            r, c = divmod(i, cols)
            cx = c * cell
            cy = r * cell
            ox = cx + (cell - pil.width)  // 2
            oy = cy + (cell - pil.height) // 2
            sheet.paste(pil, (ox, oy), pil)

        return sheet, n, cell, cols, rows

    def _atlas_update(self, *_):
        if self.atlas_img is None: return
        try:
            sheet, n, cell, cols, rows = self._atlas_build()
        except tk.TclError:
            # переменная спинбокса временно пуста/невалидна во время ручного ввода
            return
        self.atlas_lbl_cnt.config(text=f"Найдено объектов: {n}")
        self.atlas_sheet = sheet
        self.atlas_count = n

        if sheet is None:
            self.atlas_canvas.delete("all")
            self.atlas_lbl_size.config(text="Размер атласа: — (авторасчёт)")
            self.atlas_btn_save.config(state=tk.DISABLED)
            return

        self.atlas_lbl_size.config(text=f"Размер атласа: {sheet.width}×{sheet.height} (авторасчёт)")

        # рисуем сетку границ ячеек прямо на превью атласа
        vis = Image.new("RGB", sheet.size, (30, 33, 36))
        vis.paste(sheet, (0, 0), sheet)
        draw = ImageDraw.Draw(vis)
        for r in range(rows):
            for c in range(cols):
                x = c * cell
                y = r * cell
                draw.rectangle([x, y, x + cell - 1, y + cell - 1], outline="#00e050", width=1)

        cw = self.atlas_canvas.winfo_width()  or 700
        ch = self.atlas_canvas.winfo_height() or 600
        preview = vis
        preview.thumbnail((cw, ch), Image.LANCZOS)
        self.atlas_photo = ImageTk.PhotoImage(preview)
        self.atlas_canvas.delete("all")
        self.atlas_canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=self.atlas_photo)

        self.atlas_btn_save.config(state=tk.NORMAL if self.atlas_outdir else tk.DISABLED)

    def atlas_save(self):
        if self.atlas_img is None or not self.atlas_outdir:
            messagebox.showwarning("Ошибка", "Соберите атлас и выберите папку сохранения")
            return
        # пересобираем прямо перед сохранением — превью могло не обновиться,
        # если значение поля было введено вручную без потери фокуса
        sheet, n, *_ = self._atlas_build()
        if sheet is None:
            messagebox.showwarning("Ошибка", "Объекты не найдены")
            return
        self.atlas_sheet = sheet
        self.atlas_count = n

        name = self.atlas_name.get().strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите имя файла")
            return
        name = "".join(ch for ch in name if ch not in '\\/:*?"<>|')
        if not name.lower().endswith(".png"):
            name += ".png"
        out = os.path.join(self.atlas_outdir, name)
        if os.path.exists(out) and not messagebox.askyesno(
                "Файл существует", f"Файл «{name}» уже существует. Перезаписать?"):
            return
        self.atlas_sheet.save(out)
        messagebox.showinfo("Готово!",
                            f"Атлас {self.atlas_sheet.width}×{self.atlas_sheet.height} px, "
                            f"{self.atlas_count} объектов\n"
                            f"Сохранён: {out}")
        self._atlas_name_manual = False
        self._atlas_suggest_name()

    # ═══════════════════════════════════════════════════════════════
    #  ВКЛАДКА 6 — ТАЙЛ-ТЕСТ
    # ═══════════════════════════════════════════════════════════════

    def _build_tilecheck(self):
        sb   = self._sidebar(self.t_tilecheck)
        area = self._area(self.t_tilecheck)

        self._help_btn(sb, "tc")
        self._lbl(sb, "1. Изображение", bold=True).pack(anchor=tk.W, pady=(0, 8))
        self._btn(sb, "Открыть изображение", self.tc_open, GRN, h=2).pack(fill=tk.X, pady=3)
        self.tc_lbl_file = self._lbl(sb, "Файл не выбран", color=FG2)
        self.tc_lbl_file.pack(anchor=tk.W)

        self._sep(sb)
        self._lbl(sb, "2. Размер тайла превью (пикс)", bold=True).pack(anchor=tk.W, pady=(0, 6))
        self.tc_size = tk.IntVar(value=64)
        szf = tk.Frame(sb, bg=BG)
        szf.pack(fill=tk.X)
        for sz in (32, 64, 128, 256, 512):
            tk.Radiobutton(szf, text=str(sz), variable=self.tc_size, value=sz,
                           bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                           font=("Arial", 9, "bold"),
                           command=self._tc_size_changed).pack(side=tk.LEFT, padx=2)

        self._lbl(sb, "Размер выбора:", color=FG2).pack(anchor=tk.W, pady=(8, 2))
        slf = tk.Frame(sb, bg=BG)
        slf.pack(fill=tk.X)
        self._lbl(slf, "Ш:").pack(side=tk.LEFT)
        self.tc_sel_w = tk.IntVar(value=64)
        self._spinbox(slf, self.tc_sel_w, 1, 4096, w=5,
                      cmd=self._tc_render).pack(side=tk.LEFT, padx=(2, 8))
        self._lbl(slf, "В:").pack(side=tk.LEFT)
        self.tc_sel_h = tk.IntVar(value=64)
        self._spinbox(slf, self.tc_sel_h, 1, 4096, w=5,
                      cmd=self._tc_render).pack(side=tk.LEFT, padx=2)

        self._sep(sb)
        self._lbl(sb, "3. Размер сетки превью", bold=True).pack(anchor=tk.W, pady=(0, 6))
        self.tc_grid = tk.IntVar(value=3)
        grf = tk.Frame(sb, bg=BG)
        grf.pack(fill=tk.X)
        for n in (3, 4, 5, 6, 7):
            tk.Radiobutton(grf, text=f"{n}×{n}", variable=self.tc_grid, value=n,
                           bg=BG, fg=FG, selectcolor=BTN, activebackground=BG,
                           font=("Arial", 9, "bold"),
                           command=self._tc_render).pack(side=tk.LEFT, padx=2)

        self._sep(sb)
        self._lbl(sb, "4. Позиция среза", bold=True).pack(anchor=tk.W, pady=(0, 4))
        self.tc_lbl_offset = self._lbl(sb, "X: 0   Y: 0", color=GOLD)
        self.tc_lbl_offset.pack(anchor=tk.W)

        self.tc_snap = tk.BooleanVar(value=False)
        tk.Checkbutton(sb, text="Привязка к сетке тайлов",
                       variable=self.tc_snap, bg=BG, fg=FG,
                       selectcolor=BTN, activebackground=BG).pack(anchor=tk.W, pady=(6, 0))

        self._btn(sb, "Сброс позиции (0, 0)", self._tc_reset).pack(fill=tk.X, pady=(8, 4))

        zf = tk.Frame(sb, bg=BG)
        zf.pack(fill=tk.X)
        self._lbl(zf, "Зум:").pack(side=tk.LEFT)
        self.tc_lbl_zoom = self._lbl(zf, "100%", color=GOLD)
        self.tc_lbl_zoom.pack(side=tk.LEFT, padx=6)
        self._btn(zf, "↺", self._tc_zoom_reset, h=1).pack(side=tk.RIGHT)

        self._sep(sb)
        self._btn(sb, "Папка сохранения", self.tc_out_dir).pack(fill=tk.X)
        self.tc_lbl_out = self._lbl(sb, "Папка не выбрана", color=FG2)
        self.tc_lbl_out.pack(anchor=tk.W, pady=(3, 0))

        btm = tk.Frame(sb, bg=BG)
        btm.pack(side=tk.BOTTOM, fill=tk.X)

        self._lbl(btm, "Имя файла:").pack(anchor=tk.W, pady=(0, 2))
        self.tc_name = tk.Entry(btm, bg=BTN, fg=FG, insertbackground=FG,
                                relief=tk.FLAT, font=("Arial", 10))
        self.tc_name.insert(0, "tile")
        self.tc_name.pack(fill=tk.X, pady=(0, 6))

        self.tc_btn_save = self._btn(btm, "СОХРАНИТЬ ТАЙЛ", self.tc_save,
                                     ACC, h=2, state=tk.DISABLED)
        self.tc_btn_save.pack(fill=tk.X, pady=(0, 4))

        # ---- Рабочая область: две панели ----
        lp = tk.Frame(area, bg=BG2)
        lp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Separator(area, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=1)

        rp = tk.Frame(area, bg=BG2)
        rp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(lp, text="Исходное изображение  —  тяните мышью для выбора области",
                 bg=BG2, fg=FG2, font=("Arial", 8, "italic")).pack(pady=3)
        self.tc_lbl_grid = tk.Label(rp, text="Превью тайла  3 × 3  (видны стыки)",
                                    bg=BG2, fg=FG2, font=("Arial", 8, "italic"))
        self.tc_lbl_grid.pack(pady=3)

        self.tc_src_cv = tk.Canvas(lp, bg="#1e2124", highlightthickness=0, cursor="fleur")
        self.tc_src_cv.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        self.tc_prev_cv = tk.Canvas(rp, bg="#1e2124", highlightthickness=0)
        self.tc_prev_cv.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        self.tc_src_cv.bind("<ButtonPress-1>",   self._tc_press)
        self.tc_src_cv.bind("<B1-Motion>",       self._tc_drag)
        self.tc_src_cv.bind("<ButtonRelease-1>", self._tc_release)
        self.tc_src_cv.bind("<Configure>",       lambda _: self._tc_render())
        self.tc_prev_cv.bind("<Configure>",      lambda _: self._tc_render())

        for key in ("<Left>", "<Right>", "<Up>", "<Down>",
                    "<Shift-Left>", "<Shift-Right>", "<Shift-Up>", "<Shift-Down>"):
            self.tc_src_cv.bind(key, self._tc_arrow)

        self.tc_src_cv.bind("<MouseWheel>",      self._tc_wheel)
        self.tc_src_cv.bind("<Button-4>",        self._tc_wheel)
        self.tc_src_cv.bind("<Button-5>",        self._tc_wheel)
        self.tc_src_cv.bind("<ButtonPress-2>",   self._tc_pan_press)
        self.tc_src_cv.bind("<B2-Motion>",       self._tc_pan_drag)
        self.tc_src_cv.bind("<ButtonRelease-2>", self._tc_pan_release)

        self.tc_pil     = None
        self.tc_outdir  = ""
        self.tc_cx      = 0
        self.tc_cy      = 0
        self.tc_scale   = 1.0
        self.tc_ox      = 0
        self.tc_oy      = 0
        self.tc_zoom    = 1.0
        self.tc_view_x  = 0
        self.tc_view_y  = 0
        self.tc_drag0   = None
        self.tc_pan0    = None
        self.tc_src_ph  = None
        self.tc_prev_ph = None

    def tc_open(self):
        path = filedialog.askopenfilename(
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if not path:
            return
        self.tc_pil = Image.open(path).convert("RGBA")
        self.tc_lbl_file.config(
            text=f"{os.path.basename(path)}  ({self.tc_pil.width}×{self.tc_pil.height})")
        if not self.tc_outdir:
            self.tc_outdir = os.path.dirname(path)
            self.tc_lbl_out.config(text=self.tc_outdir)
            self._add_recent(self.tc_outdir)
        self.tc_cx = 0
        self.tc_cy = 0
        self.tc_zoom   = 1.0
        self.tc_view_x = 0
        self.tc_view_y = 0
        self.tc_lbl_offset.config(text="X: 0   Y: 0")
        self.tc_lbl_zoom.config(text="100%")
        self.tc_btn_save.config(state=tk.NORMAL)
        self._tc_render()

    def _tc_size_changed(self):
        sz = self.tc_size.get()
        self.tc_sel_w.set(sz)
        self.tc_sel_h.set(sz)
        if self.tc_pil is None:
            return
        iw, ih = self.tc_pil.size
        self.tc_cx = int(max(0, min(self.tc_cx, iw - sz)))
        self.tc_cy = int(max(0, min(self.tc_cy, ih - sz)))
        self.tc_lbl_offset.config(text=f"X: {self.tc_cx}   Y: {self.tc_cy}")
        self._tc_render()

    def _tc_reset(self):
        self.tc_cx = 0
        self.tc_cy = 0
        self.tc_lbl_offset.config(text="X: 0   Y: 0")
        self._tc_render()

    def _tc_press(self, e):
        self.tc_src_cv.focus_set()
        if self.tc_pil is None:
            return
        sw, sh = max(1, self.tc_sel_w.get()), max(1, self.tc_sel_h.get())
        iw, ih = self.tc_pil.size
        if iw < sw or ih < sh:
            return
        ix = (e.x - self.tc_ox) / self.tc_scale
        iy = (e.y - self.tc_oy) / self.tc_scale
        self.tc_cx = int(max(0, min(ix - sw / 2, iw - sw)))
        self.tc_cy = int(max(0, min(iy - sh / 2, ih - sh)))
        if self.tc_snap.get():
            sz = self.tc_size.get()
            self.tc_cx = (self.tc_cx // sz) * sz
            self.tc_cy = (self.tc_cy // sz) * sz
        self.tc_drag0 = (e.x, e.y, self.tc_cx, self.tc_cy)
        self.tc_lbl_offset.config(text=f"X: {self.tc_cx}   Y: {self.tc_cy}")
        self._tc_render()

    def _tc_arrow(self, e):
        if self.tc_pil is None:
            return
        sw, sh = max(1, self.tc_sel_w.get()), max(1, self.tc_sel_h.get())
        iw, ih = self.tc_pil.size
        step   = 10 if (e.state & 0x1) else 1
        dx, dy = 0, 0
        if   "Left"  in e.keysym: dx = -step
        elif "Right" in e.keysym: dx =  step
        elif "Up"    in e.keysym: dy = -step
        elif "Down"  in e.keysym: dy =  step
        self.tc_cx = int(max(0, min(self.tc_cx + dx, iw - sw)))
        self.tc_cy = int(max(0, min(self.tc_cy + dy, ih - sh)))
        self.tc_lbl_offset.config(text=f"X: {self.tc_cx}   Y: {self.tc_cy}")
        self._tc_render()

    def _tc_drag(self, e):
        if self.tc_drag0 is None or self.tc_pil is None:
            return
        sx, sy, cx0, cy0 = self.tc_drag0
        sw, sh = max(1, self.tc_sel_w.get()), max(1, self.tc_sel_h.get())
        iw, ih = self.tc_pil.size
        dx = (e.x - sx) / self.tc_scale
        dy = (e.y - sy) / self.tc_scale
        nx = cx0 + dx
        ny = cy0 + dy
        if self.tc_snap.get():
            sn = self.tc_size.get()
            nx = round(nx / sn) * sn
            ny = round(ny / sn) * sn
        self.tc_cx = int(max(0, min(nx, iw - sw)))
        self.tc_cy = int(max(0, min(ny, ih - sh)))
        self.tc_lbl_offset.config(text=f"X: {self.tc_cx}   Y: {self.tc_cy}")
        self._tc_render()

    def _tc_release(self, _=None):
        self.tc_drag0 = None

    def _tc_wheel(self, e):
        if self.tc_pil is None:
            return
        factor = 1.15 if (getattr(e, "delta", 0) > 0 or e.num == 4) else 1 / 1.15
        ix = (e.x - self.tc_ox) / self.tc_scale
        iy = (e.y - self.tc_oy) / self.tc_scale
        self.tc_zoom = max(0.1, min(30.0, self.tc_zoom * factor))
        cw = self.tc_src_cv.winfo_width() or 500
        ch = self.tc_src_cv.winfo_height() or 500
        iw, ih = self.tc_pil.size
        fit = min(cw / iw, ch / ih)
        ns  = fit * self.tc_zoom
        self.tc_view_x = int(e.x - ix * ns - (cw - int(iw * ns)) // 2)
        self.tc_view_y = int(e.y - iy * ns - (ch - int(ih * ns)) // 2)
        self.tc_lbl_zoom.config(text=f"{int(self.tc_zoom * 100)}%")
        self._tc_render_source()

    def _tc_zoom_reset(self):
        self.tc_zoom   = 1.0
        self.tc_view_x = 0
        self.tc_view_y = 0
        self.tc_lbl_zoom.config(text="100%")
        self._tc_render_source()

    def _tc_pan_press(self, e):
        self.tc_src_cv.focus_set()
        self.tc_pan0 = (e.x, e.y, self.tc_view_x, self.tc_view_y)

    def _tc_pan_drag(self, e):
        if self.tc_pan0 is None:
            return
        sx, sy, vx0, vy0 = self.tc_pan0
        self.tc_view_x = vx0 + (e.x - sx)
        self.tc_view_y = vy0 + (e.y - sy)
        self._tc_render_source()

    def _tc_pan_release(self, _=None):
        self.tc_pan0 = None

    def _tc_render(self):
        self._tc_render_source()
        self._tc_render_preview()

    def _tc_checker(self, w, h, cs=8):
        img  = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)
        for r in range((h + cs - 1) // cs):
            for c in range((w + cs - 1) // cs):
                col = "#666666" if (r + c) % 2 == 0 else "#999999"
                x0, y0 = c * cs, r * cs
                draw.rectangle([x0, y0,
                                 min(x0 + cs, w) - 1,
                                 min(y0 + cs, h) - 1], fill=col)
        return img

    def _tc_render_source(self):
        if self.tc_pil is None:
            return
        sz     = self.tc_size.get()
        iw, ih = self.tc_pil.size
        cw     = self.tc_src_cv.winfo_width()  or 500
        ch     = self.tc_src_cv.winfo_height() or 500

        fit    = min(cw / iw, ch / ih)
        scale  = fit * self.tc_zoom
        nw     = max(1, int(iw * scale))
        nh     = max(1, int(ih * scale))
        self.tc_scale = scale
        self.tc_ox    = (cw - nw) // 2 + self.tc_view_x
        self.tc_oy    = (ch - nh) // 2 + self.tc_view_y

        bg     = self._tc_checker(nw, nh, cs=8)
        scaled = self.tc_pil.resize((nw, nh), Image.LANCZOS)
        bg.paste(scaled.convert("RGB"), mask=scaled.split()[3])
        vis    = bg
        draw   = ImageDraw.Draw(vis)

        # Faint tile grid
        for gx in range(0, iw + 1, sz):
            cx = int(gx * scale)
            if 0 <= cx <= nw:
                draw.line([(cx, 0), (cx, nh - 1)], fill="#3a3a5e", width=1)
        for gy in range(0, ih + 1, sz):
            cy = int(gy * scale)
            if 0 <= cy <= nh:
                draw.line([(0, cy), (nw - 1, cy)], fill="#3a3a5e", width=1)

        sw = max(1, self.tc_sel_w.get())
        sh = max(1, self.tc_sel_h.get())
        if iw >= sw and ih >= sh:
            rx  = int(self.tc_cx * scale)
            ry  = int(self.tc_cy * scale)
            rw  = max(2, int(sw * scale))
            rh  = max(2, int(sh * scale))
            draw.rectangle([rx, ry, rx + rw - 1, ry + rh - 1],
                            outline="#ffff00", width=2)
            draw.rectangle([rx + 2, ry + 2, rx + rw - 3, ry + rh - 3],
                            outline="#ff6600", width=1)
        else:
            draw.text((4, 4), f"Изображение меньше {sw}×{sh}", fill="#e74c3c")

        self.tc_src_ph = ImageTk.PhotoImage(vis)
        self.tc_src_cv.delete("all")
        self.tc_src_cv.create_image(self.tc_ox, self.tc_oy,
                                    anchor=tk.NW, image=self.tc_src_ph)

    def _tc_render_preview(self):
        if self.tc_pil is None:
            return
        sz     = self.tc_size.get()
        n      = self.tc_grid.get()
        iw, ih = self.tc_pil.size
        cw     = self.tc_prev_cv.winfo_width()  or 500
        ch     = self.tc_prev_cv.winfo_height() or 500

        self.tc_lbl_grid.config(text=f"Превью тайла  {n} × {n}  (видны стыки)")

        sw = max(1, self.tc_sel_w.get())
        sh = max(1, self.tc_sel_h.get())

        if iw < sw or ih < sh:
            self.tc_prev_cv.delete("all")
            self.tc_prev_cv.create_text(
                cw // 2, ch // 2,
                text=f"Изображение меньше\nвыбранного размера ({sw}×{sh})",
                fill=RED, font=("Arial", 12), justify=tk.CENTER)
            return

        x    = max(0, min(self.tc_cx, iw - sw))
        y    = max(0, min(self.tc_cy, ih - sh))
        crop = self.tc_pil.crop((x, y, x + sw, y + sh))
        tile = crop.resize((sz, sz), Image.LANCZOS) if (sw != sz or sh != sz) else crop

        gp      = sz * n
        checker = self._tc_checker(gp, gp, cs=max(4, sz // 8))
        grid    = checker.convert("RGBA")
        for row in range(n):
            for col in range(n):
                grid.paste(tile, (col * sz, row * sz), tile)

        s      = min(cw / gp, ch / gp)
        nw     = max(1, int(gp * s))
        nh     = max(1, int(gp * s))
        resamp = Image.NEAREST if sz <= 64 else Image.LANCZOS
        disp   = grid.resize((nw, nh), resamp)

        self.tc_prev_ph = ImageTk.PhotoImage(disp)
        self.tc_prev_cv.delete("all")
        ox = (cw - nw) // 2
        oy = (ch - nh) // 2
        self.tc_prev_cv.create_image(ox, oy, anchor=tk.NW, image=self.tc_prev_ph)

    def tc_out_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.tc_outdir = d
            self.tc_lbl_out.config(text=d)
            self._add_recent(d)

    def tc_save(self):
        if self.tc_pil is None or not self.tc_outdir:
            messagebox.showwarning("Ошибка", "Выберите изображение и папку сохранения")
            return
        sw, sh = max(1, self.tc_sel_w.get()), max(1, self.tc_sel_h.get())
        iw, ih = self.tc_pil.size
        if iw < sw or ih < sh:
            messagebox.showwarning("Ошибка",
                                   f"Изображение меньше выбранного размера ({sw}×{sh})")
            return
        name   = self.tc_name.get().strip() or "tile"
        prefix = name + "_"
        x    = max(0, min(self.tc_cx, iw - sw))
        y    = max(0, min(self.tc_cy, ih - sh))
        tile = self.tc_pil.crop((x, y, x + sw, y + sh))
        idx  = self._next_idx(self.tc_outdir, prefix)
        out  = os.path.join(self.tc_outdir, f"{prefix}{idx:04d}.png")
        tile.save(out)
        messagebox.showinfo("Готово!", f"Кроп {sw}×{sh} сохранён:\n{out}")

    # ═══════════════════════════════════════════════════════════════
    #  ОБЩИЕ ДИАЛОГИ
    # ═══════════════════════════════════════════════════════════════

    def _gen_help_img(self, tab_id):
        W, H = 500, 220
        if tab_id == "auto":
            img = Image.new("RGB", (W, H), "#1a1c24")
            draw = ImageDraw.Draw(img)
            draw.rectangle([8, 8, W-8, H-8], fill="#26283a", outline="#3a3c54", width=2)
            blobs = [(38, 28, 118, 105), (135, 18, 240, 108), (258, 38, 340, 98),
                     (48, 128, 125, 205), (148, 118, 265, 208), (288, 125, 472, 208)]
            for x1, y1, x2, y2 in blobs:
                draw.ellipse([x1, y1, x2, y2], fill="#b0b8c8", outline="#d0d8e8")
                draw.rectangle([x1-4, y1-4, x2+4, y2+4], outline="#00dc50", width=2)
            return img

        elif tab_id == "tile":
            img = Image.new("RGB", (W, H), "#1a1c24")
            draw = ImageDraw.Draw(img)
            T = 42
            palette = ["#3a6a3a","#6a3a3a","#3a3a6a","#6a5a3a","#3a5a6a",
                       "#5a3a6a","#4a6a3a","#6a4a3a","#3a6a5a","#5a5a3a"]
            for row in range(5):
                for col in range(11):
                    x1, y1 = col * T + 4, row * T + 4
                    x2, y2 = x1 + T - 3, y1 + T - 3
                    if x2 > W-2 or y2 > H-2:
                        continue
                    draw.rectangle([x1, y1, x2, y2],
                                   fill=palette[(row * 11 + col) % len(palette)],
                                   outline="#00e050", width=1)
            return img

        elif tab_id == "shape":
            img = Image.new("RGB", (W, H), "#1a1c24")
            draw = ImageDraw.Draw(img)
            draw.rectangle([14, 14, W-14, H-14], fill="#26283a")
            draw.ellipse([50, 35, 195, 185], fill="#7878c0")
            draw.ellipse([230, 50, 380, 185], fill="#c07878")
            draw.ellipse([400, 60, 475, 185], fill="#78c078")
            draw.rectangle([46, 31, 199, 189], outline="#e74c3c", width=2)
            poly = [(230, 50), (335, 38), (385, 125), (305, 189), (218, 162)]
            draw.polygon(poly, outline="#3498db", width=2)
            for p in poly:
                draw.ellipse([p[0]-3, p[1]-3, p[0]+3, p[1]+3], fill="#3498db")
            lasso = [(400, 60), (472, 45), (480, 130), (455, 188), (398, 168), (388, 115)]
            draw.polygon(lasso, outline="#2ecc71", width=2)
            for p in lasso:
                draw.ellipse([p[0]-3, p[1]-3, p[0]+3, p[1]+3], fill="#2ecc71")
            return img

        elif tab_id == "mgr":
            img = Image.new("RGB", (W, H), "#1a1c24")
            draw = ImageDraw.Draw(img)
            T, PAD = 72, 10
            cols_n = 6
            colors = ["#c88840","#40c880","#4080c8","#c040c8","#c8c840","#40c8c8",
                      "#886040","#408860","#804088","#408080"]
            checked = [True, True, False, True, True, False, True, True, True, False, True, True]
            for i in range(12):
                col = i % cols_n
                row = i // cols_n
                x = PAD + col * (T + PAD)
                y = PAD + row * (T + PAD + 14)
                if x + T > W - 2 or y + T > H - 2:
                    continue
                draw.rectangle([x, y, x+T, y+T], fill=colors[i % len(colors)], outline="#555")
                cx, cy = x+2, y+T+2
                draw.rectangle([cx, cy, cx+10, cy+10], outline="#aaa", fill="#26283a")
                if checked[i % len(checked)]:
                    draw.line([(cx+2, cy+5), (cx+5, cy+8), (cx+9, cy+2)],
                              fill="#00e050", width=2)
            return img

        elif tab_id == "tc":
            img = Image.new("RGB", (W, H), "#1a1c24")
            draw = ImageDraw.Draw(img)
            draw.rectangle([8, 8, 238, H-8], fill="#26283a", outline="#3a3c54")
            for r in range(4):
                for c in range(4):
                    x1, y1 = 18 + c*52, 18 + r*46
                    h_ = (30 + r*10 + c*5) % 80 + 30
                    s_ = (50 + r*8) % 80 + 30
                    v_ = (40 + c*8) % 80 + 30
                    draw.rectangle([x1, y1, x1+50, y1+44], fill=(h_, s_, v_))
            draw.rectangle([18, 18, 70, 62], outline="#ffff00", width=2)
            draw.rectangle([20, 20, 68, 60], outline="#ff6600", width=1)
            draw.line([(244, 8), (244, H-8)], fill="#4f545c", width=2)
            draw.rectangle([250, 8, W-8, H-8], fill="#26283a", outline="#3a3c54")
            SZ = 60
            for r in range(3):
                for c in range(3):
                    x1, y1 = 254 + c*SZ, 12 + r*SZ
                    for cr in range(4):
                        for cc in range(4):
                            tc = "#505050" if (cr+cc) % 2 == 0 else "#707070"
                            draw.rectangle([x1+cc*15, y1+cr*15,
                                            x1+cc*15+14, y1+cr*15+14], fill=tc)
                    draw.rectangle([x1, y1, x1+SZ-1, y1+SZ-1], fill=(50,100,50,), outline="#3a3c54")
            return img

        elif tab_id == "atlas":
            img = Image.new("RGB", (W, H), "#1a1c24")
            draw = ImageDraw.Draw(img)
            draw.rectangle([8, 8, W-8, H-8], fill="#26283a", outline="#3a3c54", width=2)
            blobs = [(38, 28, 118, 105), (135, 18, 240, 108), (258, 38, 340, 98),
                     (48, 128, 125, 205), (148, 118, 265, 208), (288, 125, 472, 208)]
            for x1, y1, x2, y2 in blobs:
                draw.ellipse([x1, y1, x2, y2], fill="#b0b8c8", outline="#d0d8e8")
            CELL = 76
            cols_a, rows_a = 6, 3
            ox = (W - cols_a * CELL) // 2
            oy = (H - rows_a * CELL) // 2
            for r in range(rows_a):
                for c in range(cols_a):
                    x1 = ox + c * CELL
                    y1 = oy + r * CELL
                    draw.rectangle([x1, y1, x1+CELL-1, y1+CELL-1],
                                   fill="#2e3040", outline="#00e050", width=1)
                    idx = r * cols_a + c
                    if idx < len(blobs):
                        bx1, by1, bx2, by2 = blobs[idx]
                        bw, bh = bx2 - bx1, by2 - by1
                        scale = min((CELL - 8) / bw, (CELL - 8) / bh)
                        nw = max(1, int(bw * scale))
                        nh = max(1, int(bh * scale))
                        ex = x1 + (CELL - nw) // 2
                        ey = y1 + (CELL - nh) // 2
                        draw.ellipse([ex, ey, ex+nw, ey+nh], fill="#b0b8c8")
            return img

        return Image.new("RGB", (W, H), BG)

    def _show_tab_help(self, tab_id):
        descriptions = {
            "auto": (
                "Авто-нарезчик",
                "Автоматически находит объекты на изображении по цвету фона.\n\n"
                "• Работает с белым, чёрным фоном и PNG с прозрачностью\n"
                "• Порог — чувствительность определения фона (200–255)\n"
                "• Мин. размер — отфильтровывает мелкий шум\n"
                "• Отступ — добавляет рамку вокруг каждого спрайта\n"
                "• Зелёные рамки на превью — найденные объекты\n"
                "• Кнопка «Разделить и сохранить» обрабатывает все файлы сразу"
            ),
            "tile": (
                "Тайловая сетка",
                "Нарезает изображение по равномерной сетке тайлов.\n\n"
                "• Режим «По размеру» — задаёте ширину и высоту одного тайла\n"
                "• Режим «По количеству» — задаёте число строк и столбцов\n"
                "• Отступ — сдвиг сетки от края изображения\n"
                "• Зазор — расстояние между тайлами (для атласов с padding)\n"
                "• «Пропускать пустые» — не сохраняет прозрачные тайлы\n"
                "• Зелёные рамки = сохранятся, серые = пропустятся"
            ),
            "shape": (
                "Вырезание фигур",
                "Вырезает произвольные области вручную.\n\n"
                "• Прямоугольник — зажмите ЛКМ и тяните мышью\n"
                "• Многоугольник — кликайте по точкам, ПКМ для закрытия\n"
                "• Лассо — рисуйте произвольный контур, ПКМ для закрытия\n"
                "• Esc — сбросить текущий незаконченный контур\n"
                "• Можно создать несколько выделений и сохранить все сразу\n"
                "• «Прозрачный фон» — фон вне фигуры станет прозрачным"
            ),
            "mgr": (
                "Менеджер спрайтов",
                "Собирает отдельные PNG-файлы в один спрайт-лист.\n\n"
                "• Загрузите целую папку или отдельные файлы\n"
                "• Ставьте/снимайте галочки для выбора нужных спрайтов\n"
                "• Фильтр по мин. размеру — авто-снимает галочки с мелких\n"
                "• «Инверт.» — меняет выбор на противоположный\n"
                "• Столбцов — ширина итоговой таблицы спрайт-листа\n"
                "• «Единый размер» — все ячейки одного размера (по максимуму)"
            ),
            "atlas": (
                "Сборка атласа",
                "Автоматически находит объекты, выравнивает их в ячейки\nи собирает компактный атлас без зазоров.\n\n"
                "• Откройте картинку с несколькими объектами на фоне\n"
                "• Порог и мин. размер — как в Авто-нарезчике\n"
                "• Размер ячейки — все объекты вписываются в квадрат N×N\n"
                "• Масштабирование — большие объекты уменьшаются под ячейку\n"
                "• «Не увеличивать мелкие» — мелкие объекты не растягиваются\n"
                "• Атлас кратен размеру ячейки (удобно для движков и тайлмапов)"
            ),
            "tc": (
                "Тайл-тест",
                "Проверяет, насколько тайл выглядит «бесшовно» при мозаичном заполнении.\n\n"
                "• Левая панель — исходное изображение с выбором области\n"
                "• Правая панель — выбранный тайл повторяется N×N раз\n"
                "• Тяните мышью для перемещения области среза\n"
                "• Стрелки (±1 пикс) и Shift+стрелки (±10 пикс) для точного выравнивания\n"
                "• Колёсико + средняя кнопка — зум и перемещение по исходнику\n"
                "• «Привязка к сетке» — фиксирует позицию по шагу тайла"
            ),
        }

        title, text = descriptions.get(tab_id, ("Справка", "Нет описания."))

        top = tk.Toplevel(self.root)
        top.title(f"Справка — {title}")
        top.configure(bg=BG)
        top.resizable(False, False)
        top.transient(self.root)
        top.grab_set()

        pil_img = self._gen_help_img(tab_id)
        photo = ImageTk.PhotoImage(pil_img)
        top._photo = photo

        img_lbl = tk.Label(top, image=photo, bg="#1a1c24", bd=0)
        img_lbl.pack(padx=0, pady=0)

        tk.Frame(top, bg=ACC, height=2).pack(fill=tk.X)

        txt_frame = tk.Frame(top, bg=BG2, padx=18, pady=14)
        txt_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(txt_frame, text=title, fg=ACC, bg=BG2,
                 font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(0, 8))
        tk.Label(txt_frame, text=text, fg=FG, bg=BG2,
                 font=("Arial", 10), justify=tk.LEFT, anchor=tk.W).pack(anchor=tk.W)

        tk.Button(top, text="Закрыть", command=top.destroy,
                  bg=BTN, fg=FG, font=("Arial", 10, "bold"), relief=tk.FLAT,
                  cursor="hand2", padx=20, pady=6,
                  activebackground=ACC, activeforeground=FG).pack(pady=12)

        top.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width()  - top.winfo_width())  // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - top.winfo_height()) // 2
        top.geometry(f"+{x}+{y}")

    def _show_help(self):
        messagebox.showinfo("Инструкция", (
            "АВТО-НАРЕЗЧИК\n"
            "  Выберите PNG/JPG → настройте порог и мин. размер → сохраните.\n"
            "  Работает с белым, чёрным фоном и прозрачными спрайтами.\n\n"
            "ТАЙЛОВАЯ СЕТКА\n"
            "  Откройте тайлсет (Ground.png, атлас текстур).\n"
            "  Задайте размер тайла или количество строк/столбцов.\n"
            "  Укажите отступ от края и зазор между тайлами.\n"
            "  Галочка 'Пропускать пустые' убирает полностью прозрачные.\n\n"
            "ВЫРЕЗАНИЕ ФИГУР\n"
            "  Прямоугольник — зажмите ЛКМ и тяните.\n"
            "  Многоугольник — клики по точкам, ПКМ для закрытия.\n"
            "  Произвольная — рисуйте удерживая ЛКМ, ПКМ для закрытия.\n"
            "  Esc — сбросить текущее выделение.\n"
            "  Можно создать несколько выделений и сохранить все.\n\n"
            "МЕНЕДЖЕР СПРАЙТОВ\n"
            "  Загрузите папку со спрайтами или отдельные файлы.\n"
            "  Снимайте/ставьте галочки для выбора нужных.\n"
            "  Удалите незмеченных из списка если нужно.\n"
            "  Выберите количество столбцов и отступ → Собрать спрайт-лист.\n\n"
            "СБОРКА АТЛАСА\n"
            "  Откройте картинку без фона с несколькими объектами.\n"
            "  Программа находит объекты по контурам (порог/мин. размер).\n"
            "  Выберите размер ячейки (16/32/64/128/256 или свой) —\n"
            "  каждый объект масштабируется и выравнивается по центру ячейки.\n"
            "  Столбцы и зазор задают компоновку, размер атласа считается\n"
            "  автоматически. Собрать и сохранить — готовый atlas_XXXX.png.\n\n"
            "ЛИЦЕНЗИЯ: Разрешено использование при обязательном указании\n"
            "автора (Shtillgor) и ссылки https://midgro.uz/"
        ))

    def _show_author(self):
        messagebox.showinfo("Об авторе", (
            "Автор: Shtillgor\n"
            "Сайт: https://midgro.uz/\n"
            "Телефон: +998909603560\n\n"
            "Вы можете свободно использовать это ПО, но обязаны указывать\n"
            "автора и ссылку на сайт в заметном месте вашего проекта."
        ))


if __name__ == "__main__":
    root = tk.Tk()
    app = SpriteCutterApp(root)
    root.update()
    root.mainloop()
