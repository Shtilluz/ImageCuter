import cv2
import numpy as np
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

class SpriteCutterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ИИ Разделитель Спрайтов")
        self.root.geometry("1000x750")
        self.root.minsize(800, 600)

        # Переменные путей
        self.input_path = ""
        self.output_dir = ""
        self.contours = []
        self.orig_image = None
        self.preview_image = None

        self.setup_ui()

    def setup_ui(self):
        # Панель управления (Слева)
        sidebar = tk.Frame(self.root, width=280, bg="#2e3136", padx=10, pady=10)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # Кнопки выбора файлов
        tk.Label(sidebar, text="1. Настройка путей", fg="white", bg="#2e3136", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        self.btn_open = tk.Button(sidebar, text="Выбрать картинку", command=self.load_image, bg="#43b581", fg="white", font=("Arial", 10, "bold"), height=2)
        self.btn_open.pack(fill=tk.X, pady=5)
        
        self.lbl_input = tk.Label(sidebar, text="Файл не выбран", fg="#b9bbbe", bg="#2e3136", wraplength=250, justify=tk.LEFT)
        self.lbl_input.pack(anchor=tk.W, pady=(0, 15))

        self.btn_dir = tk.Button(sidebar, text="Выбрать папку сохранения", command=self.choose_output_dir, bg="#4f545c", fg="white", font=("Arial", 10))
        self.btn_dir.pack(fill=tk.X, pady=5)
        
        self.lbl_output = tk.Label(sidebar, text="Папка не выбрана", fg="#b9bbbe", bg="#2e3136", wraplength=250, justify=tk.LEFT)
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

        # Финальная кнопка
        self.btn_save = tk.Button(sidebar, text="РАЗДЕЛИТЬ И СОХРАНИТЬ", command=self.save_sprites, bg="#7289da", fg="white", font=("Arial", 11, "bold"), height=2, state=tk.DISABLED)
        self.btn_save.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        # Область просмотра (Справа)
        self.preview_panel = tk.Label(self.root, text="Загрузите изображение для предпросмотра", bg="#36393f", fg="#72767d", font=("Arial", 14))
        self.preview_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    def load_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if file_path:
            self.input_path = file_path
            self.lbl_input.config(text=os.path.basename(file_path))
            self.orig_image = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)  # Загрузка со всеми каналами (включая альфа)
            
            # Если папка сохранения еще не выбрана, предлагаем ту же, где лежит оригинал
            if not self.output_dir:
                self.output_dir = os.path.dirname(file_path)
                self.lbl_output.config(text=self.output_dir)
                
            self.process_image()
            self.check_ready_to_save()

    def choose_output_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_dir = dir_path
            self.lbl_output.config(text=dir_path)
            self.check_ready_to_save()

    def check_ready_to_save(self):
        if self.input_path and self.output_dir and len(self.contours) > 0:
            self.btn_save.config(state=tk.NORMAL)
        else:
            self.btn_save.config(state=tk.DISABLED)

    def process_image(self):
        if self.orig_image is None:
            return

        # 1. Переводим в градации серого
        gray = cv2.cvtColor(self.orig_image, cv2.COLOR_BGR2GRAY)
        
        # [АВТО-ОПРЕДЕЛЕНИЕ ФОНА] Смотрим на цвет пикселя в верхнем левом углу (0, 0)
        # Если он темный (меньше 127), значит фон черный. Если светлый — белый.
        is_bg_dark = gray[0, 0] < 127

        thresh_val = self.slider_thresh.get()
        min_size = self.slider_size.get()

        # Меняем логику бинаризации в зависимости от фона
        if is_bg_dark:
            # Для черного фона: инвертируем ползунок (чем левее, тем чувствительнее к темноте)
            # Переводим ползунок 200-255 в диапазон 0-55 для черного цвета
            black_thresh = 255 - thresh_val 
            _, thresh = cv2.threshold(gray, black_thresh, 255, cv2.THRESH_BINARY)
        else:
            # Для белого фона (как было раньше)
            _, thresh = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY_INV)

        # 2. Находим ТОЛЬКО внешние контуры объектов
        raw_contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Отсеиваем по размеру
        self.contours = []
        for cnt in raw_contours:
            _, _, w, h = cv2.boundingRect(cnt)
            if w >= min_size and h >= min_size:
                self.contours.append(cnt)

        self.lbl_count.config(text=f"Найдено объектов: {len(self.contours)}")

        # 3. Создание предпросмотра с рамками
        preview_img = self.orig_image.copy()
        for cnt in self.contours:
            x, y, w, h = cv2.boundingRect(cnt)
            cv2.rectangle(preview_img, (x, y), (x + w, y + h), (0, 255, 0), 2)

        # Конвертируем для отображения в Tkinter с сохранением пропорций
        preview_rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(preview_rgb)
        
        panel_w = self.preview_panel.winfo_width()
        panel_h = self.preview_panel.winfo_height()
        if panel_w < 10: panel_w = 700
        if panel_h < 10: panel_h = 700

        pil_img.thumbnail((panel_w, panel_h))
        
        self.preview_image = ImageTk.PhotoImage(pil_img)
        self.preview_panel.config(image=self.preview_image, text="")
        self.check_ready_to_save()
    def save_sprites(self):
        if self.orig_image is None or not self.output_dir:
            return

        # Если в картинке изначально не было альфа-канала (3 канала вместо 4), добавляем его
        if self.orig_image.shape[2] == 3:
            rgba = cv2.cvtColor(self.orig_image, cv2.COLOR_BGR2BGRA)
        else:
            rgba = self.orig_image.copy()

        idx = 0
        for cnt in self.contours:
            x, y, w, h = cv2.boundingRect(cnt)
            
            # Вырезаем объект из уже прозрачного оригинала
            crop = rgba[y:y+h, x:x+w]
            
            output_file = os.path.join(self.output_dir, f'sprite_{idx:03d}.png')
            cv2.imwrite(output_file, crop)
            idx += 1

        messagebox.showinfo("Готово!", f"Успешно сохранено {idx} прозрачных спрайтов в папку:\n{self.output_dir}")

if __name__ == "__main__":
    root = tk.Tk()
    app = SpriteCutterApp(root)
    
    # Небольшой костыль, чтобы дождаться отрисовки окна и правильно подогнать масштаб превью
    root.update()
    root.mainloop()