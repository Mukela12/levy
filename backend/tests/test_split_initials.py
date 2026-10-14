"""Drop-cap letters split off by the text layer are rejoined, and nothing else is."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from fix_split_initials import fix  # noqa: E402


class SplitInitials(unittest.TestCase):
    def test_headings_are_rejoined(self):
        self.assertEqual(fix("Order XI. A ppearance Order X II. D efault of Appearance"),
                         "Order XI. Appearance Order XII. Default of Appearance")
        self.assertEqual(fix("Order I. G eneral Forms of Process"), "Order I. General Forms of Process")

    def test_real_words_are_left_alone(self):
        for text in ("A person may apply.", "I am satisfied.", "Order X and Order V", "A judge may order"):
            self.assertEqual(fix(text), text)

    def test_only_valid_roman_numerals_are_joined(self):
        self.assertEqual(fix("Order V II"), "Order VII")
        self.assertEqual(fix("Order X IV"), "Order XIV")
        self.assertEqual(fix("Order V V"), "Order V V")


if __name__ == "__main__":
    unittest.main()
