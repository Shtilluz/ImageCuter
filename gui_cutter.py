import cv2
import numpy as np
import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

CONFIG_FILE = "config.json"

class SpriteCutterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ИИ Разделитель Спрайтов")
        self.root.geometry("1000x800")
        self.root.minsize(800, 600)

        # Переменные путей
        self.input_paths = []
        self.current_image_idx = 0
        self.output_dir = ""
        self.recent_dirs = self.load_config()
        self.contours = []
        self.orig_image = None
        self.preview_image = None

        self.setup_ui()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("recent_dirs", [])
            except:
                return []
        return []

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"recent_dirs": self.recent_dirs}, f, ensure_ascii=False, indent=4)

    def add_recent_dir(self, dir_path):
        if dir_path in self.recent_dirs:
            self.recent_dirs.remove(dir_path)
        self.recent_dirs.insert(0, dir_path)
        self.recent_dirs = self.recent_dirs[:5]
        self.save_config()
        self.update_recent_menu()

    def setup_ui(self):
        # Панель управления (Слева)
        sidebar = tk.Frame(self.root, width=300, bg="#2e3136", padx=10, pady=10)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # Кнопки выбора файлов
        tk.Label(sidebar, text="1. Настройка путей", fg="white", bg="#2e3136", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        self.btn_open = tk.Button(sidebar, text="Выбрать картинки (PNG/JPG)", command=self.load_images, bg="#43b581", fg="white", font=("Arial", 10, "bold"), height=2)
        self.btn_open.pack(fill=tk.X, pady=5)
        
        self.lbl_input = tk.Label(sidebar, text="Файлы не выбраны", fg="#b9bbbe", bg="#2e3136", wraplength=280, justify=tk.LEFT)
        self.lbl_input.pack(anchor=tk.W, pady=(0, 15))

        self.btn_dir = tk.Button(sidebar, text="Выбрать папку сохранения", command=self.choose_output_dir, bg="#4f545c", fg="white", font=("Arial", 10))
        self.btn_dir.pack(fill=tk.X, pady=5)
        
        # Выпадающий список последних папок
        tk.Label(sidebar, text="Недавние папки:", fg="white", bg="#2e3136", font=("Arial", 9)).pack(anchor=tk.W)
        self.recent_var = tk.StringVar()
        self.recent_menu = ttk.Combobox(sidebar, textvariable=self.recent_var, state="readonly")
        self.recent_menu.pack(fill=tk.X, pady=(0, 5))
        self.recent_menu.bind("<<ComboboxSelected>>", self.on_recent_selected)
        self.update_recent_menu()

        self.lbl_output = tk.Label(sidebar, text="Папка не выбрана", fg="#b9bbbe", bg="#2e3136", wraplength=280, justify=tk.LEFT)
        self.lbl_output.pack(anchor=tk.W, pady=(0, 20))

        ttk.Separator(sidebar, orient='horizontal').pack(fill=tk.X, pady=10)

        # Настройки чувствительности
        tk.Label(sidebar, text="2. Параметры нарезки", fg="white", bg="#2e3136", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=5)
        
        tk.Label(sidebar, text="Порог белого фона (200-255):", fg="white", bg="#2e3136").pack(anchor=tk.W)
        self.slider_thresh = tk.Scale(sidebar, from_=200, to=255, orient=tk.HORIZONTAL, bg="#2e3136", fg="white", highlightthickness=0)
        self.slider_thresh.set(245)
        self.slider_thresh.pack(fill=tk.X, pady=(0, 10))
        self.slider_thresh.bind("<ButtonRelease-1>", lambda event: self.process_image())

        tk.Label(sidebar, text="Мин. размер объекта (пикс):", fg="white", bg="#2e3136").pack(anchor=tk.W)
        self.slider_size = tk.Scale(sidebar, from_=5, to=50, orient=tk.HORIZONTAL, bg="#2e3136", fg="white", highlightthickness=0)
        self.slider_size.set(12)
        self.slider_size.pack(fill=tk.X, pady=(0, 20))
        self.slider_size.bind("<ButtonRelease-1>", lambda event: self.process_image())

        self.lbl_count = tk.Label(sidebar, text="Найдено объектов: 0", fg="#faa61a", bg="#2e3136", font=("Arial", 11, "bold"))
        self.lbl_count.pack(anchor=tk.W, pady=10)

        ttk.Separator(sidebar, orient='horizontal').pack(fill=tk.X, pady=10)

        # Навигация по файлам (если выбрано несколько)
        self.nav_frame = tk.Frame(sidebar, bg="#2e3136")
        self.nav_frame.pack(fill=tk.X, pady=5)
        
        self.btn_prev = tk.Button(self.nav_frame, text="<<", command=self.prev_image, bg="#4f545c", fg="white", state=tk.DISABLED)
        self.btn_prev.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        
        self.lbl_nav = tk.Label(self.nav_frame, text="0 / 0", fg="white", bg="#2e3136")
        self.lbl_nav.pack(side=tk.LEFT, padx=5)

        self.btn_next = tk.Button(self.nav_frame, text=">>", command=self.next_image, bg="#4f545c", fg="white", state=tk.DISABLED)
        self.btn_next.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # Финальная кнопка
        self.btn_save = tk.Button(sidebar, text="РАЗДЕЛИТЬ И СОХРАНИТЬ ВСЕ", command=self.save_sprites, bg="#7289da", fg="white", font=("Arial", 11, "bold"), height=2, state=tk.DISABLED)
        self.btn_save.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        # Область просмотра (Справа)
        self.preview_panel = tk.Label(self.root, text="Загрузите изображения для предпросмотра", bg="#36393f", fg="#72767d", font=("Arial", 14))
        self.preview_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    def update_recent_menu(self):
        self.recent_menu['values'] = self.recent_dirs
        if self.recent_dirs:
            self.recent_menu.current(0)

    def on_recent_selected(self, event):
        dir_path = self.recent_var.get()
        if os.path.isdir(dir_path):
            self.output_dir = dir_path
            self.lbl_output.config(text=dir_path)
            self.check_ready_to_save()
        else:
            messagebox.showwarning("Внимание", "Эта папка больше не существует")
            self.recent_dirs.remove(dir_path)
            self.save_config()
            self.update_recent_menu()

    def load_images(self):
        file_paths = filedialog.askopenfilenames(filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if file_paths:
            self.input_paths = list(file_paths)
            self.current_image_idx = 0
            self.update_image_display()
            
            # Если папка сохранения еще не выбрана, предлагаем ту же, где лежит первый оригинал
            if not self.output_dir:
                self.output_dir = os.path.dirname(self.input_paths[0])
                self.lbl_output.config(text=self.output_dir)
                self.add_recent_dir(self.output_dir)
                
            self.check_ready_to_save()

    def update_image_display(self):
        if not self.input_paths:
            return
        
        path = self.input_paths[self.current_image_idx]
        self.lbl_input.config(text=f"Выбрано файлов: {len(self.input_paths)}\nТекущий: {os.path.basename(path)}")
        self.lbl_nav.config(text=f"{self.current_image_idx + 1} / {len(self.input_paths)}")
        
        self.orig_image = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        
        if len(self.input_paths) > 1:
            self.btn_prev.config(state=tk.NORMAL if self.current_image_idx > 0 else tk.DISABLED)
            self.btn_next.config(state=tk.NORMAL if self.current_image_idx < len(self.input_paths) - 1 else tk.DISABLED)
        else:
            self.btn_prev.config(state=tk.DISABLED)
            self.btn_next.config(state=tk.DISABLED)

        self.process_image()

    def prev_image(self):
        if self.current_image_idx > 0:
            self.current_image_idx -= 1
            self.update_image_display()

    def next_image(self):
        if self.current_image_idx < len(self.input_paths) - 1:
            self.current_image_idx += 1
            self.update_image_display()

    def choose_output_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_dir = dir_path
            self.lbl_output.config(text=dir_path)
            self.add_recent_dir(dir_path)
            self.check_ready_to_save()

    def check_ready_to_save(self):
        if self.input_paths and self.output_dir:
            self.btn_save.config(state=tk.NORMAL)
        else:
            self.btn_save.config(state=tk.DISABLED)

    def process_image(self):
        if self.orig_image is None:
            return

        gray = cv2.cvtColor(self.orig_image, cv2.COLOR_BGR2GRAY)
        is_bg_dark = gray[0, 0] < 127
        thresh_val = self.slider_thresh.get()
        min_size = self.slider_size.get()

        if is_bg_dark:
            black_thresh = 255 - thresh_val 
            _, thresh = cv2.threshold(gray, black_thresh, 255, cv2.THRESH_BINARY)
        else:
            _, thresh = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY_INV)

        raw_contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        self.contours = []
        for cnt in raw_contours:
            _, _, w, h = cv2.boundingRect(cnt)
            if w >= min_size and h >= min_size:
                self.contours.append(cnt)

        self.lbl_count.config(text=f"Найдено объектов: {len(self.contours)}")

        preview_img = self.orig_image.copy()
        for cnt in self.contours:
            x, y, w, h = cv2.boundingRect(cnt)
            cv2.rectangle(preview_img, (x, y), (x + w, y + h), (0, 255, 0), 2)

        preview_rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(preview_rgb)
        
        panel_w = self.preview_panel.winfo_width()
        panel_h = self.preview_panel.winfo_height()
        if panel_w < 10: panel_w = 700
        if panel_h < 10: panel_h = 700

        pil_img.thumbnail((panel_w, panel_h))
        
        self.preview_image = ImageTk.PhotoImage(pil_img)
        self.preview_panel.config(image=self.preview_image, text="")
        
    def get_next_index(self):
        try:
            existing_files = os.listdir(self.output_dir)
        except:
            return 0
            
        indices = []
        for f in existing_files:
            if f.startswith("sprite_") and f.endswith(".png"):
                try:
                    # Извлекаем число между 'sprite_' и '.png'
                    num_part = f[7:-4]
                    idx = int(num_part)
                    indices.append(idx)
                except ValueError:
                    continue
        return max(indices) + 1 if indices else 0

    def save_sprites(self):
        if not self.input_paths or not self.output_dir:
            return

        total_saved = 0
        next_idx = self.get_next_index()

        # Сохраняем текущие настройки, чтобы применить их ко всем файлам
        thresh_val = self.slider_thresh.get()
        min_size = self.slider_size.get()

        for path in self.input_paths:
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is None: continue

            # Обработка для каждого файла
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            is_bg_dark = gray[0, 0] < 127
            if is_bg_dark:
                black_thresh = 255 - thresh_val 
                _, thresh = cv2.threshold(gray, black_thresh, 255, cv2.THRESH_BINARY)
            else:
                _, thresh = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY_INV)

            raw_contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if img.shape[2] == 3:
                rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            else:
                rgba = img.copy()

            for cnt in raw_contours:
                _, _, w, h = cv2.boundingRect(cnt)
                if w >= min_size and h >= min_size:
                    x, y, w, h = cv2.boundingRect(cnt)
                    crop = rgba[y:y+h, x:x+w]
                    output_file = os.path.join(self.output_dir, f'sprite_{next_idx:03d}.png')
                    cv2.imwrite(output_file, crop)
                    next_idx += 1
                    total_saved += 1

        messagebox.showinfo("Готово!", f"Успешно сохранено {total_saved} прозрачных спрайтов в папку:\n{self.output_dir}")

if __name__ == "__main__":
    root = tk.Tk()
    app = SpriteCutterApp(root)
    
    # Небольшой костыль, чтобы дождаться отрисовки окна и правильно подогнать масштаб превью
    root.update()
    root.mainloop()