from __future__ import annotations

import io
import math
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import (ExifTags, Image, ImageChops, ImageDraw, ImageOps, ImageStat,
                 UnidentifiedImageError)

Image.MAX_IMAGE_PIXELS = 200_000_000  # decompression-bomb guard (errors above 2x this)

SUPPORTED_INPUT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
COMPRESS_INPUT = {".jpg", ".jpeg", ".png", ".webp"}
FORMAT_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp", "TIFF": ".tiff"}
FORMAT_LABEL = {"JPEG": "JPG", "PNG": "PNG", "WEBP": "WEBP", "BMP": "BMP", "TIFF": "TIFF"}
LABEL_FORMAT = {v: k for k, v in FORMAT_LABEL.items()}
ALPHA_FORMATS = {"PNG", "WEBP", "TIFF"}
MAX_DIMENSION = 20000

PRESETS = {
    "Thumbnail": (150, 150),
    "Avatar": (400, 400),
    "Small": (640, 480),
    "Medium": (1024, 768),
    "HD": (1280, 720),
    "Full HD": (1920, 1080),
    "UHD": (3840, 2160),
    "Instagram Square": (1080, 1080),
    "Instagram Story": (1080, 1920),
    "Twitter Header": (1500, 500),
}
BACKGROUNDS = {"White": (255, 255, 255), "Black": (0, 0, 0), "Light gray": (220, 220, 220)}
_BAD_NAME_CHARS = set('\\/:*?"<>|')
_PATH_LOCK = threading.Lock()


class ImageError(Exception):
    """Raised when an image cannot be read, processed or written."""


class ValidationError(ValueError):
    """Raised when user-supplied settings are invalid."""


@dataclass
class ProcessOptions:
    output_format: Optional[str] = None      # None = keep the original format
    quality: int = 85                         # 1-100 (JPEG/WebP; PNG when png_lossy)
    resize_mode: str = "none"                 # none | percent | custom | preset
    percent: float = 100.0
    width: Optional[int] = None
    height: Optional[int] = None
    keep_aspect: bool = True
    no_upscale: bool = False
    strip_metadata: bool = False
    png_lossy: bool = False
    background: tuple = (255, 255, 255)       # used when flattening transparency
    skip_if_larger: bool = False
    suffix: str = "_optimized"

    def validate(self) -> None:
        if not isinstance(self.quality, int) or not 1 <= self.quality <= 100:
            raise ValidationError("Quality must be a whole number between 1 and 100.")
        if self.output_format is not None and self.output_format not in FORMAT_EXT:
            raise ValidationError("Unsupported output format.")
        if self.resize_mode not in ("none", "percent", "custom", "preset"):
            raise ValidationError("Unknown resize mode.")
        if self.resize_mode == "percent":
            if not (1 <= self.percent <= 500):
                raise ValidationError("Resize percentage must be between 1 and 500.")
        elif self.resize_mode in ("custom", "preset"):
            for name, val in (("Width", self.width), ("Height", self.height)):
                if val is not None and not (1 <= val <= MAX_DIMENSION):
                    raise ValidationError(f"{name} must be between 1 and {MAX_DIMENSION} pixels.")
            if self.width is None and self.height is None:
                raise ValidationError("Enter a width, a height, or both.")
            if not self.keep_aspect and (self.width is None or self.height is None):
                raise ValidationError("Enter both width and height, or enable 'Keep aspect ratio'.")
        if any(c in _BAD_NAME_CHARS for c in self.suffix):
            raise ValidationError("The filename suffix contains invalid characters.")


@dataclass
class ProcessResult:
    src: Path
    status: str = "pending"                   # success | skipped | failed | cancelled
    dest: Optional[Path] = None
    orig_size: int = 0
    new_size: int = 0
    orig_dims: tuple = (0, 0)
    new_dims: tuple = (0, 0)
    src_format: str = ""
    out_format: str = ""
    error: str = ""
    note: str = ""
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @property
    def saved_bytes(self) -> int:
        return self.orig_size - self.new_size

    @property
    def saved_pct(self) -> float:
        return (1 - self.new_size / self.orig_size) * 100 if self.orig_size else 0.0


def has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)


def normalize_mode(img: Image.Image) -> Image.Image:
    """Convert exotic modes into RGB / RGBA / L / LA so every format path is predictable."""
    mode = img.mode
    if mode in ("RGB", "RGBA", "L", "LA"):
        return img
    if mode == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    if mode == "1":
        return img.convert("L")
    if mode.startswith("I;16") or mode in ("I", "F"):
        try:
            return img.point(lambda i: i * (1 / 256)).convert("L")
        except Exception:
            return img.convert("RGB")
    return img.convert("RGBA" if "A" in mode or "a" in mode else "RGB")


def load_image(path: Path | str) -> tuple[Image.Image, str, str]:
    """Open an image fully into memory. Returns (image, source_format, note)."""
    p = Path(path)
    if not p.is_file():
        raise ImageError(f"File not found: {p.name}")
    note = ""
    try:
        with Image.open(p) as im:
            fmt = (im.format or "").upper()
            if getattr(im, "n_frames", 1) > 1:
                note = "Multi-frame image: only the first frame was processed."
            im.load()
            img = im.copy()
    except Image.DecompressionBombError:
        raise ImageError("The image is too large to process safely.") from None
    except UnidentifiedImageError:
        raise ImageError("Unsupported or corrupted image file.") from None
    except (OSError, SyntaxError, ValueError, EOFError) as exc:
        raise ImageError(f"Cannot read image ({exc}).") from None
    if fmt == "MPO":
        fmt = "JPEG"
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return normalize_mode(img), fmt, note


def make_thumbnail(path: Path | str, box=(320, 320)) -> tuple[Image.Image, tuple, str]:
    """Fast preview. Returns (thumbnail, original_size, format)."""
    p = Path(path)
    try:
        with Image.open(p) as im:
            fmt = (im.format or "").upper()
            size = im.size
            if fmt in ("JPEG", "MPO"):
                im.draft("RGB", (box[0] * 2, box[1] * 2))
            im.load()
            thumb = im.copy()
    except Image.DecompressionBombError:
        raise ImageError("The image is too large to preview.") from None
    except UnidentifiedImageError:
        raise ImageError("Unsupported or corrupted image file.") from None
    except (OSError, SyntaxError, ValueError, EOFError) as exc:
        raise ImageError(f"Cannot read image ({exc}).") from None
    try:
        thumb = ImageOps.exif_transpose(thumb)
    except Exception:
        pass
    thumb = normalize_mode(thumb)
    thumb.thumbnail(box, Image.Resampling.LANCZOS)
    return thumb, size, "JPEG" if fmt == "MPO" else fmt


def compute_size(size: tuple, opts: ProcessOptions) -> tuple:
    ow, oh = size
    mode = opts.resize_mode
    if mode == "none":
        return size
    if mode == "percent":
        f = opts.percent / 100.0
        nw, nh = round(ow * f), round(oh * f)
    else:
        w, h = opts.width, opts.height
        if opts.keep_aspect:
            if w and h:
                f = min(w / ow, h / oh)
            elif w:
                f = w / ow
            else:
                f = h / oh
            if opts.no_upscale:
                f = min(f, 1.0)
            nw, nh = round(ow * f), round(oh * f)
        else:
            nw, nh = w, h
            if opts.no_upscale:
                nw, nh = min(nw, ow), min(nh, oh)
    nw, nh = max(1, nw), max(1, nh)
    if max(nw, nh) > MAX_DIMENSION:
        raise ImageError(f"Resulting size {nw}×{nh} exceeds the {MAX_DIMENSION}px limit.")
    return nw, nh


def flatten(img: Image.Image, background=(255, 255, 255)) -> Image.Image:
    """Composite a transparent image onto a solid background (returns RGB)."""
    rgba = img.convert("RGBA")
    base = Image.new("RGB", rgba.size, background)
    base.paste(rgba, mask=rgba.getchannel("A"))
    return base


def _quantize_png(img: Image.Image, quality: int) -> Image.Image:
    """Lossy PNG: reduce the palette. quality 1-99 maps to 16-256 colours."""
    if img.mode in ("L", "LA"):
        return img
    colors = max(16, min(256, int(round(16 + quality / 100 * 240))))
    if img.mode == "RGBA":
        return img.quantize(colors=colors, method=Image.Quantize.FASTOCTREE)
    return img.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT,
                                       dither=Image.Dither.FLOYDSTEINBERG)


def _exif(img: Image.Image):
    try:
        ex = img.getexif()
        return ex if len(ex) else None
    except Exception:
        return None


def encode(img: Image.Image, fmt: str, opts: ProcessOptions, exif=None, icc=None) -> bytes:
    """Encode an image to bytes, handling transparency per target format."""
    buf = io.BytesIO()
    alpha = has_alpha(img)
    extra = {}
    if icc:
        extra["icc_profile"] = icc
    if fmt == "JPEG":
        im = flatten(img, opts.background) if alpha else img
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if exif is not None:
            extra["exif"] = exif
        im.save(buf, "JPEG", quality=opts.quality, optimize=True, progressive=True, **extra)
    elif fmt == "PNG":
        im = _quantize_png(img, opts.quality) if opts.png_lossy and opts.quality < 100 else img
        if exif is not None:
            extra["exif"] = exif
        im.save(buf, "PNG", optimize=True, compress_level=9, **extra)
    elif fmt == "WEBP":
        im = img.convert("RGBA" if alpha else "RGB")
        if exif is not None:
            extra["exif"] = exif
        im.save(buf, "WEBP", quality=opts.quality, method=6,
                lossless=opts.quality >= 100, **extra)
    elif fmt == "BMP":
        im = flatten(img, opts.background) if alpha else img
        im.save(buf, "BMP")
    elif fmt == "TIFF":
        try:
            img.save(buf, "TIFF", compression="tiff_adobe_deflate", **extra)
        except Exception:
            buf = io.BytesIO()
            img.save(buf, "TIFF", **extra)
    else:
        raise ImageError(f"Unsupported output format: {fmt}")
    return buf.getvalue()


def build_output(img: Image.Image, opts: ProcessOptions, src_format: str):
    """Apply resize + encode. Returns (bytes, output_format, output_size)."""
    fmt = opts.output_format or (src_format if src_format in FORMAT_EXT else "PNG")
    exif = None if opts.strip_metadata else _exif(img)
    icc = None if opts.strip_metadata else img.info.get("icc_profile")
    new_size = compute_size(img.size, opts)
    work = img if new_size == img.size else img.resize(new_size, Image.Resampling.LANCZOS)
    return encode(work, fmt, opts, exif, icc), fmt, new_size


def validate_output_dir(text: str) -> Path:
    if not text or not text.strip():
        raise ValidationError("Choose an output folder.")
    p = Path(text.strip()).expanduser()
    if p.exists() and not p.is_dir():
        raise ValidationError("The output path is a file, not a folder.")
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValidationError(f"Cannot create the output folder: {exc.strerror or exc}") from None
    if not os.access(p, os.W_OK):
        raise ValidationError("The output folder is not writable.")
    return p


def reserve_path(directory: Path, stem: str, ext: str) -> Path:
    """Atomically reserve a unique filename so existing files are never overwritten."""
    with _PATH_LOCK:
        directory.mkdir(parents=True, exist_ok=True)
        candidate, n = directory / f"{stem}{ext}", 0
        while True:
            try:
                with open(candidate, "xb"):
                    pass
                return candidate
            except FileExistsError:
                n += 1
                candidate = directory / f"{stem}_{n}{ext}"


def write_unique(directory: Path, stem: str, ext: str, data: bytes) -> Path:
    dest = reserve_path(directory, stem, ext)
    try:
        dest.write_bytes(data)
    except OSError:
        dest.unlink(missing_ok=True)
        raise
    return dest


def process_image(src: Path | str, out_dir: Path | str, opts: ProcessOptions,
                  cancel: Optional[threading.Event] = None) -> ProcessResult:
    """Process one image end-to-end. Never raises; errors are returned in the result."""
    src = Path(src)
    res = ProcessResult(src=src)
    t0 = time.perf_counter()
    try:
        if cancel is not None and cancel.is_set():
            res.status = "cancelled"
            return res
        res.orig_size = src.stat().st_size
        img, src_fmt, note = load_image(src)
        res.src_format, res.orig_dims, res.note = src_fmt, img.size, note
        data, fmt, new_size = build_output(img, opts, src_fmt)
        res.out_format, res.new_size, res.new_dims = fmt, len(data), new_size
        same = fmt == src_fmt and new_size == img.size
        if opts.skip_if_larger and same and len(data) >= res.orig_size:
            res.status = "skipped"
            res.note = "Already optimized – the new file would not be smaller."
        else:
            res.dest = write_unique(Path(out_dir), src.stem + opts.suffix, FORMAT_EXT[fmt], data)
            res.status = "success"
    except ImageError as exc:
        res.status, res.error = "failed", str(exc)
    except MemoryError:
        res.status, res.error = "failed", "Not enough memory to process this image."
    except OSError as exc:
        res.status, res.error = "failed", f"File error: {exc.strerror or exc}"
    except Exception as exc:  # noqa: BLE001 - one bad file must never stop a batch
        res.status, res.error = "failed", f"{type(exc).__name__}: {exc}"
    finally:
        res.elapsed = time.perf_counter() - t0
    return res


def psnr(a: Image.Image, b: Image.Image) -> float:
    """Peak signal-to-noise ratio in dB (higher = closer to the original)."""
    a = flatten(a, (128, 128, 128)) if has_alpha(a) else a.convert("RGB")
    b = flatten(b, (128, 128, 128)) if has_alpha(b) else b.convert("RGB")
    if b.size != a.size:
        b = b.resize(a.size, Image.Resampling.LANCZOS)
    st = ImageStat.Stat(ImageChops.difference(a, b))
    mse = sum(s / c for s, c in zip(st.sum2, st.count)) / 3
    return 99.0 if mse == 0 else min(99.0, 10 * math.log10(255 ** 2 / mse))


def quality_label(db: float) -> str:
    if db >= 99:
        return "Identical"
    if db >= 45:
        return "Excellent visually lossless"
    if db >= 38:
        return "Very good"
    if db >= 32:
        return "Good"
    if db >= 27:
        return "Fair differences may be visible"
    return "Low visible quality loss"


def diff_image(a: Image.Image, b: Image.Image, gain: int = 8) -> Image.Image:
    a = flatten(a, (128, 128, 128)) if has_alpha(a) else a.convert("RGB")
    b = flatten(b, (128, 128, 128)) if has_alpha(b) else b.convert("RGB")
    if b.size != a.size:
        b = b.resize(a.size, Image.Resampling.LANCZOS)
    return ImageChops.difference(a, b).point(lambda x: min(255, x * gain))


def checkerboard(size: tuple, tile: int = 12) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, (246, 238, 205))
    d = ImageDraw.Draw(img)
    for y in range(0, h, tile):
        for x in range((y // tile % 2) * tile, w, tile * 2):
            d.rectangle([x, y, x + tile - 1, y + tile - 1], fill=(232, 220, 176))
    return img


def over_checkerboard(img: Image.Image) -> Image.Image:
    """Show transparent images on a checkerboard so transparency is visible."""
    if not has_alpha(img):
        return img.convert("RGB") if img.mode != "RGB" else img
    bg = checkerboard(img.size).convert("RGBA")
    bg.alpha_composite(img.convert("RGBA"))
    return bg.convert("RGB")


def _fmt_value(v) -> str:
    if isinstance(v, bytes):
        try:
            s = v.decode("utf-8").strip("\x00 ")
            if s.isprintable():
                return s[:200]
        except UnicodeDecodeError:
            pass
        return f"<{len(v)} bytes>"
    if hasattr(v, "numerator") and hasattr(v, "denominator") and not isinstance(v, int):
        try:
            return f"{float(v):.4g}"
        except Exception:
            return str(v)
    s = str(v)
    return s if len(s) <= 200 else s[:197] + "..."


def inspect_image(path: Path | str) -> dict:
    """Collect dimensions, format, colour mode, file size and metadata."""
    p = Path(path)
    if not p.is_file():
        raise ImageError("File not found.")
    try:
        with Image.open(p) as im:
            info = dict(im.info)
            fmt, mode, size = im.format or "?", im.mode, im.size
            desc = getattr(im, "format_description", "") or ""
            frames = getattr(im, "n_frames", 1)
            alpha = has_alpha(im)
            exif = im.getexif()
            exif_rows, has_gps = [], False
            try:
                groups = [("", dict(exif)),
                          ("", dict(exif.get_ifd(0x8769))),
                          ("GPS ", dict(exif.get_ifd(0x8825)))]
            except Exception:
                groups = [("", dict(exif))]
            for prefix, tags in groups:
                table = ExifTags.GPSTAGS if prefix else ExifTags.TAGS
                for tid, val in tags.items():
                    if tid in (0x8769, 0x8825) and not prefix:
                        has_gps = has_gps or tid == 0x8825
                        continue
                    if prefix:
                        has_gps = True
                    exif_rows.append((prefix + str(table.get(tid, f"Tag {tid}")), _fmt_value(val)))
    except Image.DecompressionBombError:
        raise ImageError("The image is too large to inspect safely.") from None
    except UnidentifiedImageError:
        raise ImageError("Unsupported or corrupted image file.") from None
    except (OSError, SyntaxError, ValueError, EOFError) as exc:
        raise ImageError(f"Cannot read image ({exc}).") from None

    st = p.stat()
    g = math.gcd(size[0], size[1]) or 1
    depth = {"1": 1, "L": 8, "LA": 16, "P": 8, "RGB": 24, "RGBA": 32, "CMYK": 32,
             "I;16": 16, "I": 32, "F": 32}.get(mode)
    mode_names = {"RGB": "RGB (true colour)", "RGBA": "RGBA (colour + transparency)",
                  "L": "Grayscale", "LA": "Grayscale + alpha", "P": "Palette (indexed)",
                  "1": "Black & white", "CMYK": "CMYK"}
    basic = [
        ("File name", p.name),
        ("Location", str(p.parent)),
        ("Format", f"{fmt}" + (f" – {desc}" if desc else "")),
        ("Dimensions", f"{size[0]} × {size[1]} px"),
        ("Megapixels", f"{size[0] * size[1] / 1e6:.2f} MP"),
        ("Aspect ratio", f"{size[0] // g}:{size[1] // g}"),
        ("Colour mode", mode_names.get(mode, mode)),
        ("Bit depth", f"{depth}-bit per pixel" if depth else "-"),
        ("Transparency", "Yes" if alpha else "No"),
        ("Frames", str(frames)),
        ("File size", f"{st.st_size:,} bytes"),
        ("Modified", datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")),
    ]
    dpi = info.get("dpi")
    if dpi:
        try:
            basic.append(("Resolution", f"{float(dpi[0]):.0f} × {float(dpi[1]):.0f} DPI"))
        except Exception:
            pass
    basic.append(("ICC colour profile", "Embedded" if info.get("icc_profile") else "None"))
    skip = {"exif", "icc_profile", "dpi", "transparency", "xmp", "photoshop", "interlace", "progressive",
            "progression", "jfif", "jfif_version", "jfif_unit", "jfif_density", "adobe", "adobe_transform"}
    other = [(str(k), _fmt_value(v)) for k, v in info.items()
             if k not in skip and not isinstance(v, (tuple, dict)) and k != "icc_profile"]
    return {"basic": basic, "exif": sorted(exif_rows), "other": other,
            "has_gps": has_gps, "size": size, "format": fmt, "file_size": st.st_size}
