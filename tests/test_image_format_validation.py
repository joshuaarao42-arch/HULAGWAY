import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.image_ops import (ImageError, ProcessOptions, ValidationError, compute_size,
                             inspect_image, load_image, make_thumbnail)


class ImageFormatValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def save_image(self, name, image_format):
        path = self.root / name
        Image.new("RGB", (8, 8), "white").save(path, format=image_format)
        return path

    def test_supported_png_is_accepted(self):
        path = self.save_image("valid.png", "PNG")
        image, fmt, _ = load_image(path)
        self.assertEqual(fmt, "PNG")
        self.assertEqual(image.size, (8, 8))

    def test_unsupported_gif_is_rejected_by_loader(self):
        path = self.save_image("unsupported.gif", "GIF")
        with self.assertRaisesRegex(ImageError, "Unsupported image format: GIF"):
            load_image(path)

    def test_unsupported_gif_is_rejected_by_preview(self):
        path = self.save_image("unsupported.gif", "GIF")
        with self.assertRaisesRegex(ImageError, "Unsupported image format: GIF"):
            make_thumbnail(path)

    def test_unsupported_gif_is_rejected_by_inspector(self):
        path = self.save_image("unsupported.gif", "GIF")
        with self.assertRaisesRegex(ImageError, "Unsupported image format: GIF"):
            inspect_image(path)

    def test_corrupted_file_is_rejected(self):
        path = self.root / "broken.png"
        path.write_bytes(b"not an image")
        with self.assertRaises(ImageError):
            load_image(path)

    def test_percent_resize_rounds_tiny_images_to_one_pixel(self):
        options = ProcessOptions(resize_mode="percent", percent=1)
        self.assertEqual(compute_size((1, 1), options), (1, 1))

    def test_aspect_ratio_resize_never_exceeds_requested_bounds(self):
        options = ProcessOptions(resize_mode="custom", width=400, height=300)
        self.assertEqual(compute_size((1600, 900), options), (400, 225))

    def test_rejects_non_positive_resize_dimensions(self):
        with self.assertRaises(ValidationError):
            ProcessOptions(resize_mode="custom", width=0, height=100).validate()

    def test_rejects_resize_percent_outside_supported_range(self):
        for percent in (0, 501):
            with self.subTest(percent=percent), self.assertRaises(ValidationError):
                ProcessOptions(resize_mode="percent", percent=percent).validate()


if __name__ == "__main__":
    unittest.main()
