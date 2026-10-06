"""Reading what an amending Act does to each section of its principal Act.

Every clause below is copied from the corpus as extraction really left it,
margin notes spliced into the middle of numbers and all. Several of them broke
the first version of the parser, in ways that would have told Levy a live
section was dead; those are the tests that matter most.
"""
import sys
import types
import unittest

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services.section_ops import extract_ops, normalise_section, read_refs, words_to_int


def ops(text):
    return {(o["op"], o["target"]) for o in extract_ops(text)}


class Numbers(unittest.TestCase):
    def test_spelled_out(self):
        self.assertEqual(words_to_int(["twenty", "four"]), 24)
        self.assertEqual(words_to_int(["three", "hundred", "and", "sixty", "seven"]), 367)
        self.assertIsNone(words_to_int(["twenty", "principal"]))

    def test_a_list_is_not_one_number(self):
        # Summed, this was "section 63". It is sections 31 and 32.
        refs, _ = read_refs("thirty- sections 31 and 32 one and thirty-two.")
        self.assertEqual(refs, ["31", "32"])

    def test_a_cut_off_number_is_not_guessed(self):
        refs, _ = read_refs("twenty- Repeal of 9. The principal Act is amended")
        self.assertEqual(refs, [])


class TheImmigrationRepeal(unittest.TestCase):
    """Section 9 of Act No. 19 of 2016, the clause the first benchmark caught."""

    CLAUSE = ("Immigration and Deportation (Amendment) (No. 19 of 2016) - Section 9. The principal Act "
              "is amended by the repeal of section twenty- Repeal of 9. The principal Act is amended by "
              "the repeal of section twenty- section 24 four.")

    def test_section_24_is_repealed(self):
        self.assertIn(("repealed", "24"), ops(self.CLAUSE))

    def test_the_amending_acts_own_number_is_not_a_repeal(self):
        # "Repeal of 9." is the margin beside the amending Act's section 9.
        # The first parser read it as a repeal of the principal's section 9.
        self.assertNotIn(("repealed", "9"), ops(self.CLAUSE))

    def test_confidence_is_high_when_the_margin_agrees(self):
        o = next(x for x in extract_ops(self.CLAUSE) if x["target"] == "24")
        self.assertEqual(o["confidence"], "high")


class RepealedOrReplaced(unittest.TestCase):
    def test_substitution_means_the_section_still_exists(self):
        text = ("3. The principal Act is amended by the repeal of section seventy- Repeal and seven and "
                "the substitution therefor of the following new section: replacement of section 77")
        self.assertEqual(ops(text), {("replaced", "77")})

    def test_the_next_clauses_replacement_does_not_leak_back(self):
        # Section 22 is repealed outright; "substitution therefor" belongs to
        # section 23 in the clause after it.
        text = ("Repeal and of 12. The principal Act is amended by the repeal of section 22. section 22 "
                "Repeal and 13. The principal Act is amended by the repeal of section 23 replacement and "
                "the substitution therefor of the following: of section 23 Prohibition 23. (1)")
        got = ops(text)
        self.assertIn(("repealed", "22"), got)
        self.assertIn(("replaced", "23"), got)
        self.assertNotIn(("replaced", "22"), got)

    def test_spliced_hundreds(self):
        text = ("The principal Act is amended by the repeal of section three Repeal and hundred and sixty "
                "seven and the substitution therefor of the following:")
        self.assertIn(("replaced", "367"), ops(text))


class OtherDrafting(unittest.TestCase):
    def test_section_named_before_the_verb(self):
        text = ("Road Traffic (Amendment) Act, 2022 (No. 8 of 2022) - Section 15. Section 38 of the "
                "principal Act is repealed. Repeal of 15. Section 38 of the principal Act is repealed.")
        self.assertIn(("repealed", "38"), ops(text))

    def test_a_digit_list(self):
        text = "Repeal of sections 303, 304, 305 and 306. 304, 305 and 306"
        self.assertTrue({("repealed", s) for s in ("303", "304", "305", "306")} <= ops(text))

    def test_a_list_the_margin_completes(self):
        text = ("Section 4. The principal Act is amended by the repeal of sections 11 Repeal of 4. The "
                "principal Act is amended by the repeal of sections 11 Repeal of and 12. sections 11 and 12")
        got = ops(text)
        self.assertIn(("repealed", "11"), got)
        self.assertIn(("repealed", "12"), got)

    def test_a_spelled_list_with_a_margin_range(self):
        text = ("principal Act is amended by the repeal of sections Amendment thirty-two, thirty-three, "
                "thirty-four, thirty-five, thirty-six and of sections 32 to 37 thirty-seven.")
        self.assertEqual({t for o, t in ops(text) if o == "repealed"}, {"32", "33", "34", "35", "36", "37"})

    def test_amended_with_a_letter_suffix(self):
        text = ("Section 4. Section sixty-four A of the principal Act is amended in 4. Section sixty-four A "
                "of the principal Act is amended in of section subsection (2)")
        self.assertIn(("amended", "64A"), ops(text))

    def test_text_that_lost_its_spaces(self):
        text = "Section 2. Sectionfouroftheprincipal Actisamended— Amendment of section4 (a)"
        self.assertIn(("amended", "4"), ops(text))

    def test_an_inserted_section(self):
        text = ("13. The principal Act is amended by the insertion, immediately after section 56, of the "
                "following new section: Insertion of section 56A")
        self.assertIn(("inserted", "56A"), ops(text))

    def test_a_part(self):
        text = "4. The principal Act is amended by the repeal of Part IV. Repeal of"
        got = extract_ops(text)
        self.assertTrue(any(o["kind"] == "part" and o["target"] == "IV" and o["op"] == "repealed" for o in got))


class Normalise(unittest.TestCase):
    def test_forms_a_user_or_model_writes(self):
        for raw, want in [("24", "24"), ("s. 24", "24"), ("section 24(1)(a)", "24"),
                          ("64 A", "64A"), ("Section twenty-four", "24"), ("s.077", "77")]:
            self.assertEqual(normalise_section(raw), want, raw)
        self.assertIsNone(normalise_section(None))


if __name__ == "__main__":
    unittest.main()


class SubsectionForms(unittest.TestCase):
    """Most 2021-2026 amending Acts write "Section 6(1) of the principal Act
    is amended"; 24 of them read as changing nothing until 6 Oct 2026."""

    def ops(self, text):
        from app.services.section_ops import extract_ops
        return [(o["op"], o["target"]) for o in extract_ops(text)]

    def test_a_subsection_amendment_amends_the_section(self):
        self.assertEqual(self.ops("2. Section 6(1) of the principal Act is amended by the deletion of paragraph (a)"), [("amended", "6")])
        self.assertEqual(self.ops("2. Section 6 (1)(c) of the principal Act is amended by the deletion of the word"), [("amended", "6")])
        self.assertEqual(self.ops("3. Section23(3)oftheprincipal Act is amended bythedeleti on of"), [("amended", "23")])

    def test_a_repealed_subsection_does_not_kill_the_section(self):
        self.assertEqual(self.ops("4. Section 7(1) of the principal Act is repealed."), [("amended", "7")])
        self.assertEqual(self.ops("9. Section 24 of the principal Act is repealed."), [("repealed", "24")])

    def test_deleting_a_section_repeals_or_replaces_it(self):
        self.assertEqual(self.ops("5. The principal Act is amended by the deletion of section 12."), [("repealed", "12")])
        self.assertEqual(self.ops("2. (1) The principal Act is amended by the deletion of section 7 and the substitution "
                                  "therefor of the following:"), [("replaced", "7")])
        # Deleting part of a section is an amendment, read by the other patterns.
        self.assertNotIn(("repealed", "7"), self.ops("The principal Act is amended by the deletion of section 7(2)."))

    def test_a_spliced_margin_note_is_not_a_whole_section_deletion(self):
        # OCR puts the margin "Amendment of section 14" inside the sentence.
        for text in ("Section 14 of the principal Act is amended by the deletion of section 14 of subsection (2).",
                     "Section 8(4) of the principal Act is amended by the deletion of section 8 of the word eight"):
            self.assertFalse([o for o in self.ops(text) if o[0] == "repealed"], text)
