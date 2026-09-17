# Sprite Manufacturer

[![Download for Windows](https://img.shields.io/github/v/release/Shtilluz/ImageCuter?label=Download%20for%20Windows&style=for-the-badge&logo=windows&color=0078d4)](https://github.com/Shtilluz/ImageCuter/releases/latest/download/gui_cutter.exe)

[Русский](#russian) | [English](#english)

---

<a name="russian"></a>
## Русский

### Описание

**Sprite Manufacturer** — профессиональный инструмент для работы со спрайтами и атласами текстур. Единое рабочее пространство в стиле TexturePacker/Photoshop: левая панель инструментов, центральный холст с зумом и панорамой, правая панель настроек, нижний трей спрайтов.

Цветовая схема: тёмный чарколь + янтарный акцент.

### Возможности

#### 🔍 Авто-детекция
- Автоматический поиск объектов на однотонном фоне (светлом или тёмном)
- Настраиваемый порог фона, минимальный размер объекта, морфологическое разделение касающихся спрайтов (эрозия)
- Предпросмотр найденных контуров прямо на холсте

#### ✏️ Вырезание фигур
- Три режима: прямоугольник, произвольный многоугольник, лассо
- Вырезание с прозрачным или непрозрачным фоном
- Несколько выделений за один сеанс

#### 📐 Сетка тайлов
- Нарезка по заданному размеру тайла или количеству ячеек
- Смещение сетки по X/Y
- Пропуск пустых тайлов

#### 📦 Сборка атласа
- Автоматическая сборка атласа текстур из обнаруженных спрайтов
- Режимы подгонки: **обрезка** (tight bbox) или **масштабирование**
- Выравнивание ячеек по ширине и/или высоте
- Удаление дубликатов с настраиваемым порогом схожести
- Пресеты размера ячейки: 16 / 32 / 64 / 128 / 256 px
- Сохранение атласа в PNG + экспорт спрайтов по отдельным файлам

#### 🎮 Тайл-тест
- Проверка бесшовности тайла — предпросмотр NxN-сетки
- Настраиваемый размер тайла и зоны выбора
- Привязка к сетке

### Общие возможности
- **Drag & Drop** — перетащите изображение прямо в окно
- **Ctrl+V** — вставка из буфера обмена
- **Трей спрайтов** — все нарезанные спрайты отображаются в нижней полосе; клик — включить/исключить из атласа
- **Зум и панорама** — колёсико мыши + перетаскивание средней кнопкой
- **Сохранение проекта** — формат `.smproj` (JSON + встроенное изображение base64), позволяет продолжить работу в любой момент

### Требования

- Python 3.9+
- `opencv-python`
- `numpy`
- `Pillow`
- `tkinterdnd2`

```bash
pip install opencv-python numpy Pillow tkinterdnd2
```

### Запуск

```bash
python gui_cutter.py
```

### Лицензия

Условия использования описаны в файле [LICENSE_RU.md](LICENSE_RU.md).

### Автор

- **Shtillgor**
- Сайт: [midgro.uz](https://midgro.uz/)

---

<a name="english"></a>
## English

### Description

**Sprite Manufacturer** is a professional tool for working with sprites and texture atlases. A unified workspace inspired by TexturePacker/Photoshop: left toolbar, center canvas with zoom & pan, right properties panel, bottom sprite tray.

Color scheme: dark charcoal + amber accent.

### Features

#### 🔍 Auto Detection
- Automatically finds objects on a solid background (light or dark)
- Adjustable background threshold, minimum object size, and morphological separation of touching sprites (erosion)
- Live contour preview directly on the canvas

#### ✏️ Shape Cutter
- Three modes: rectangle, polygon, lasso
- Cut with transparent or solid background
- Multiple selections per session

#### 📐 Grid Slicer
- Slice by tile size or cell count
- X/Y offset support
- Skip empty tiles

#### 📦 Atlas Builder
- Automatically assembles a texture atlas from detected sprites
- Fitting modes: **trim** (tight bbox) or **scale**
- Per-axis alignment (width and/or height)
- Duplicate removal with configurable similarity threshold
- Cell size presets: 16 / 32 / 64 / 128 / 256 px
- Save atlas as PNG + export sprites as individual files

#### 🎮 Tile Tester
- Check tile seamlessness with an NxN grid preview
- Configurable tile and selection size
- Grid snapping

### General Features
- **Drag & Drop** — drop an image directly into the window
- **Ctrl+V** — paste from clipboard
- **Sprite Tray** — all sliced sprites appear in the bottom strip; click to include/exclude from the atlas
- **Zoom & Pan** — mouse wheel + middle-button drag
- **Project Save** — `.smproj` format (JSON + embedded base64 image), resume work at any time

### Requirements

- Python 3.9+
- `opencv-python`
- `numpy`
- `Pillow`
- `tkinterdnd2`

```bash
pip install opencv-python numpy Pillow tkinterdnd2
```

### Run

```bash
python gui_cutter.py
```

### License

See [LICENSE_EN.md](LICENSE_EN.md) for terms of use.

### Author

- **Shtillgor**
- Website: [midgro.uz](https://midgro.uz/)
