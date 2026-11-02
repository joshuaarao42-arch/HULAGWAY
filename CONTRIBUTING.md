# Contributing to Hulagway

Hulagway is a desktop image optimization and conversion studio for compression, conversion, resizing, batch processing, image inspection, and comparison.

## Clone
```bash
git clone https://github.com/joshuaarao42-arch/HULAGWAY.git
cd HULAGWAY
```
Install dependencies and run the application using the README instructions.

## Project-specific contributions
- JPG, PNG, WebP, BMP, and TIFF conversion.
- Compression quality and file-size reporting.
- Resizing presets, custom dimensions, and aspect-ratio controls.
- Batch processing, progress, cancellation, and per-file errors.
- Before/after previews, difference maps, and image inspection.
- SQLite processing history and interface improvements.

## Image-processing checks
Test transparent images, unusual dimensions, large files, and corrupted inputs. Confirm transparency is preserved where supported and flattened intentionally otherwise. Verify batch summaries report skipped and failed files correctly. Keep the interface responsive during long jobs and preserve source files unless the user explicitly chooses to overwrite them. Do not commit private photos or images containing personal metadata.

Use branches such as `feature/batch-cancel` or `fix/transparency-conversion`. Include input/output formats, settings, and before/after results.
