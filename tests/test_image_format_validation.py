import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.image_ops import ImageError, inspect_image, load_image, make_thumbnail


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


if __name__ == "__main__":
    unittest.main()
