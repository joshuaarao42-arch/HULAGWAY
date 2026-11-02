# Hulagway – Image Optimization and Conversion Studio

*Hulagway* is Cebuano for "image" / "picture". Tagline: *Gamayon ang imong mga hulagway* ("make your images smaller").

A desktop app for compressing, converting, resizing, inspecting and comparing images.
Built with Python, CustomTkinter, Pillow and SQLite.

**Author:** Joshua Arao – University of Science and Technology of Southern Philippines

## Installation

1. Install **Python 3.9 or newer** (on Linux also install Tk: `sudo apt install python3-tk`).
2. Open a terminal in the `hulagway` folder and (recommended) create a virtual environment:

   ```bash
   python -m venv .venv
   # Windows:      .venv\Scripts\activate
   # macOS/Linux:  source .venv/bin/activate
   ```
3. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```
4. Start the app:

   ```bash
   python main.py
   ```

## Look and feel

The interface uses the **Soft Yellow Daydream Hues** palette: Vanilla Tint `#FFF9E3`, Lemon Cream `#FFF6C1`, Butter Yellow `#FFEDA8`, Pale Honey `#FBE7A1` and Sunlight Glow `#FFE18A`, with a dark brown for text. The logo (a picture frame squeezed by two chevrons) is drawn by `assets/generate_logo.py`, which writes `assets/logo.png` and `assets/icon.ico`.

## Modules

| Module | What it does |
|---|---|
| **Dashboard** | Storage saved, average reduction, totals, quick actions, recent operations, per-tool activity |
| **Compressor** | JPG / PNG / WebP with a quality slider; shows original size, new size and % saved per file. Files that would not get smaller are skipped |
| **Converter** | PNG, JPG, WebP, BMP, TIFF. Transparency is kept for PNG/WebP/TIFF; for JPG/BMP it is flattened onto a background colour you choose |
| **Resizer** | Percentage, custom width/height, or presets (HD, Full HD, 4K, Instagram, …); keep aspect ratio; optional "don't enlarge" |
| **Batch Processor** | Add files or whole folders (optionally with subfolders); compress + convert + resize in one pass on parallel workers, with a progress bar, cancel button and a summary |
| **Before & After** | Side-by-side view, 100 % crop, and an amplified difference map. Shows file sizes and a PSNR quality score. Generate a live preview at any quality, or compare two existing files |
| **Inspector** | Dimensions, format, colour mode, bit depth, transparency, DPI, ICC profile, EXIF/GPS metadata. Can save a metadata-free copy |
| **History** | Every operation stored in SQLite; search, filter, compare, open folder, export CSV |

## Behaviour you should know about

* **Originals are never overwritten.** Outputs go to the *Save to* folder (default `~/Pictures/Hulagway`) with a suffix such as `_compressed`. If a name already exists, `_1`, `_2`, … is appended.
* **Quality:** applies to JPG and WebP. WebP at 100 is lossless. PNG is always lossless unless *Allow lossy PNG* is ticked, which reduces the palette (quality 1–99 → 16–256 colours).
* **Metadata:** EXIF and colour profiles are kept by default; tick *Remove metadata* to strip them (including GPS location).
* **Errors:** corrupted or unsupported files are reported per file and never stop a batch.
* **Animated images:** only the first frame is processed (a note is shown in the results).
* Settings and history live in `~/.hulagway/history.db`.

## Project structure

```
main.py                  entry point
assets/                  logo.png, icon.ico and the script that draws them
core/                    image logic – no GUI imports
  image_ops.py           load / resize / convert / compress / inspect / compare
  batch.py               ThreadPoolExecutor batch engine with cancel + summary
  database.py            SQLite history and settings
  utils.py               formatting and file helpers
ui/                      CustomTkinter interface
  app.py                 main window and sidebar navigation
  theme.py, widgets.py   shared styling and components
  tool_page.py           Compressor, Converter, Resizer, Batch (shared layout)
  compare_page.py, inspector_page.py, history_page.py, dashboard_page.py
```

Long-running work always runs in background threads; results are handed back to the interface through a thread-safe queue, so the window never freezes.

## Optional: build a Windows .exe

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name Hulagway --icon assets/icon.ico --add-data "assets;assets" --collect-all customtkinter main.py
```
