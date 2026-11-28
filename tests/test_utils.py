import tempfile
import unittest
from pathlib import Path

from core.utils import collect_images, format_bytes, format_saved


class FormatBytesTests(unittest.TestCase):
    def test_formats_bytes_and_binary_units(self):
        cases = (
            (0, "0 B"),
            (1, "1 B"),
            (1024, "1.0 KB"),
            (1024**2, "1.0 MB"),
            (1024**3, "1.0 GB"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_bytes(value), expected)

    def test_preserves_negative_sign(self):
        self.assertEqual(format_bytes(-2048), "-2.0 KB")

    def test_accepts_numeric_strings(self):
        self.assertEqual(format_bytes("512"), "512 B")


class FormatSavedTests(unittest.TestCase):
    def test_reports_percent_saved(self):
        self.assertEqual(format_saved(100, 75), "25.0%")

    def test_reports_negative_savings_when_output_is_larger(self):
        self.assertEqual(format_saved(100, 125), "-25.0%")

    def test_zero_original_size_returns_dash(self):
        self.assertEqual(format_saved(0, 0), "-")


class CollectImagesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_matches_extensions_case_insensitively_and_sorts(self):
        (self.root / "z.PNG").write_bytes(b"")
        (self.root / "a.jpg").write_bytes(b"")
        (self.root / "ignore.txt").write_bytes(b"")
        found = collect_images(self.root, recursive=False, extensions={".png", ".jpg"})
        self.assertEqual([p.name for p in found], ["a.jpg", "z.PNG"])

    def test_recursive_flag_controls_nested_files(self):
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "inside.webp").write_bytes(b"")
        shallow = collect_images(self.root, recursive=False, extensions={".webp"})
        deep = collect_images(self.root, recursive=True, extensions={".webp"})
        self.assertEqual(shallow, [])
        self.assertEqual([p.name for p in deep], ["inside.webp"])

    def test_ignores_directories_with_image_suffix(self):
        (self.root / "folder.png").mkdir()
        found = collect_images(self.root, recursive=False, extensions={".png"})
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
