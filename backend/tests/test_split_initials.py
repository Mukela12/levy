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
        for text in ("A person may apply.", "I am satisfied.", "Order X and Order V", "A judge may order",
                     "a ward of the court: A ward", "Schedule A to this Act", "Form B under section 3"):
            self.assertEqual(fix(text), text)

    def test_plurals_and_archaic_fragments_are_rejoined(self):
        # The first pass missed these: plurals are not in the system list, and
        # it carries the archaic "stablishment".
        self.assertEqual(fix("27. E stablishment of National Parks"), "27. Establishment of National Parks")
        self.assertEqual(fix("O ffences and penalties"), "Offences and penalties")
        self.assertEqual(fix("2. D efinitions"), "2. Definitions")
        self.assertEqual(fix("R egulations"), "Regulations")
        self.assertEqual(fix("6. P owers of the Minister"), "6. Powers of the Minister")

    def test_only_valid_roman_numerals_are_joined(self):
        self.assertEqual(fix("Order V II"), "Order VII")
        self.assertEqual(fix("Order X IV"), "Order XIV")
        self.assertEqual(fix("Order V V"), "Order V V")


if __name__ == "__main__":
    unittest.main()
