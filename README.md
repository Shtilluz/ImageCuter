# ImageCuter - ИИ Разделитель Спрайтов / AI Sprite Cutter

[Russian](#russian) | [English](#english)

---

<a name="russian"></a>
## Русский (Russian)

### Описание
**ImageCuter** — это удобное графическое приложение для автоматической нарезки спрайтов и объектов из изображений. Программа находит объекты на однотонном фоне (светлом или темном) и сохраняет их как отдельные прозрачные PNG-файлы.

### Основные возможности
*   **Автоматическое обнаружение:** Использование OpenCV для поиска контуров объектов.
*   **Пакетная обработка:** Возможность выбрать сразу несколько файлов для нарезки.
*   **Гибкая настройка:**
    *   Регулировка порога чувствительности для работы с разными фонами.
    *   Фильтрация по минимальному размеру объекта, чтобы избежать сохранения "мусора".
*   **Предпросмотр:** Визуальное выделение найденных объектов перед сохранением.
*   **Сохранение прозрачности:** Все вырезанные спрайты сохраняются в формате PNG с прозрачным фоном.
*   **История папок:** Запоминает последние использованные папки для сохранения.

### Как использовать
1.  **Выбрать картинки:** Нажмите кнопку "Выбрать картинки" и выберите один или несколько файлов (PNG, JPG, JPEG, WebP, BMP).
2.  **Настроить папку сохранения:** Выберите папку, куда будут сохраняться готовые спрайты.
3.  **Отрегулировать параметры:**
    *   **Порог белого фона:** Настройте ползунок так, чтобы зеленые рамки четко охватывали нужные объекты.
    *   **Мин. размер объекта:** Увеличьте, если программа находит слишком мелкие точки (шум).
4.  **Проверить результат:** Используйте кнопки навигации `<<` и `>>`, если выбрано несколько файлов.
5.  **Сохранить:** Нажмите "РАЗДЕЛИТЬ И СОХРАНИТЬ ВСЕ".

### Требования для запуска (из исходников)
*   Python 3.x
*   Библиотеки: `opencv-python`, `numpy`, `Pillow`

Установка зависимостей:
```bash
pip install opencv-python numpy Pillow
```

### Автор
*   **Автор:** Shtillgor
*   **Сайт:** [midgro.uz](https://midgro.uz/)
*   **Связь:** +998909603560

---

<a name="english"></a>
## English

### Description
**ImageCuter** is a user-friendly GUI application designed for automatic sprite and object extraction from images. The program identifies objects on a solid background (light or dark) and saves them as individual transparent PNG files.

### Key Features
*   **Automatic Detection:** Utilizes OpenCV for object contour detection.
*   **Batch Processing:** Ability to select multiple image files at once.
*   **Flexible Configuration:**
    *   Adjustable sensitivity threshold for various backgrounds.
    *   Minimum object size filtering to prevent saving "noise".
*   **Live Preview:** Visual highlighting of detected objects before saving.
*   **Transparency Support:** All extracted sprites are saved in PNG format with a transparent background.
*   **Directory History:** Remembers recently used output folders.

### How to Use
1.  **Select Images:** Click "Select Images" and choose one or more files (PNG, JPG, JPEG, WebP, BMP).
2.  **Set Output Directory:** Choose the folder where the extracted sprites will be saved.
3.  **Adjust Parameters:**
    *   **Background Threshold:** Move the slider until the green boxes accurately wrap around the desired objects.
    *   **Min Object Size:** Increase this value if the program detects tiny dots or noise.
4.  **Review Results:** Use the `<<` and `>>` navigation buttons if multiple files are selected.
5.  **Save:** Click "SPLIT AND SAVE ALL".

### Requirements (from source)
*   Python 3.x
*   Libraries: `opencv-python`, `numpy`, `Pillow`

Install dependencies:
```bash
pip install opencv-python numpy Pillow
```

### Author
*   **Author:** Shtillgor
*   **Website:** [midgro.uz](https://midgro.uz/)
*   **Contact:** +998909603560
