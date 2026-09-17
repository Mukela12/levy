import unittest
from unittest.mock import patch

from app.services import parser

# Page 44 of the Urban and Regional Planning Act, 2015 as pdfplumber reads it:
# the margin note ("Planning") shares the line with the section number.
URPA_PAGES = [
    {"page_number": 43, "text": "48. (1) Where the owner of any land which is required\nfor a public purpose may apply."},
    {"page_number": 44, "text": "\n".join([
        "66 No. 3 of 2015] The Urban and Regional Planning",
        "PART VI",
        "PLANNING APPLICATIONS AND PERMISSION",
        "Planning 49. (1) A person shall not carry out any development on land,",
        "permission",
        "change the use of land or subdivide any land without planning",
        "permission.",
        "(2) A person who contravenes subsection (1) commits an",
        "offence and is liable, upon conviction, to a fine not exceeding three",
        "hundred penalty units.",
        "Powers of 50. (1) The Minister may direct a planning authority to refer",
        "Minister on an application made to that planning authority.",
        "Under section 12. The Minister shall consult the authority.",
    ])},
    {"page_number": 45, "text": "51. (1) The power to grant planning permission under this Part\nincludes the power to grant permission."},
]


def parse(pages):
    with patch.object(parser, "extract_text_from_pdf", return_value=pages), \
         patch.object(parser, "get_pdf_hash", return_value="x"):
        return parser.parse_legal_pdf("unused.pdf")["sections"]


class PartLossTest(unittest.TestCase):
    def test_sections_after_a_part_heading_are_kept(self):
        secs = parse(URPA_PAGES)
        numbers = [s.number for s in secs if s.level == "section"]
        self.assertEqual(numbers, ["48", "49", "50", "51"])
        s49 = next(s for s in secs if s.number == "49")
        self.assertIn("without planning", s49.content)
        self.assertIn("three", s49.content)
        self.assertEqual(s49.parent_number, "VI")

    def test_part_title_is_read_from_the_next_line(self):
        part = next(s for s in parse(URPA_PAGES) if s.level == "part")
        self.assertEqual(part.title, "PLANNING APPLICATIONS AND PERMISSION")

    def test_a_cross_reference_never_starts_a_section(self):
        s50 = next(s for s in parse(URPA_PAGES) if s.number == "50")
        self.assertIn("Under section 12. The Minister shall consult", s50.content)

    def test_no_body_line_is_dropped(self):
        kept = " ".join((s.title or "") + " " + s.content for s in parse(URPA_PAGES))
        for page in URPA_PAGES[1:]:
            for line in page["text"].split("\n")[3:]:
                self.assertIn(line.strip(), kept)

    def test_margin_noted_number_out_of_sequence_stays_in_its_section(self):
        pages = [{"page_number": 1, "text": "\n".join([
            "5. (1) A licence is valid for one year.",
            "Fees 40. (1) This line is not section 40.",
        ])}]
        secs = [s for s in parse(pages) if s.level == "section"]
        self.assertEqual([s.number for s in secs], ["5"])
        self.assertIn("not section 40", secs[0].content)


if __name__ == "__main__":
    unittest.main()
