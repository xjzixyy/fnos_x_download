import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class PackagingTest(unittest.TestCase):
    def test_fnos_icons_are_present_and_256_pngs(self):
        for name in ("ICON.PNG", "ICON_256.PNG"):
            icon_path = ROOT / "packaging" / "fnos-native" / name
            self.assertTrue(icon_path.exists(), f"{name} is missing")
            with icon_path.open("rb") as icon_file:
                self.assertEqual(icon_file.read(8), b"\x89PNG\r\n\x1a\n")
                icon_file.read(8)
                width, height = struct.unpack(">II", icon_file.read(8))
            self.assertEqual((width, height), (256, 256))

    def test_fnos_icon_svg_source_is_present(self):
        svg_path = ROOT / "packaging" / "fnos-native" / "ICON.svg"

        self.assertIn("<svg", svg_path.read_text(encoding="utf-8"))
