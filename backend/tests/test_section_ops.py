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



class SplicedSectionNumber(unittest.TestCase):
    def test_the_amending_acts_own_number_is_not_a_listed_section(self):
        from app.services.section_ops import _list_refs
        self.assertEqual(_list_refs(" 11, 6. The principal Act is amended by the repeal of sections 11, 12 and 13"), [])
        self.assertEqual(_list_refs(" 11, 12, 6. The principal Act"), ["11", "12"])
        self.assertEqual(_list_refs(" 11, 12 and 13. The principal Act is amended"), ["11", "12", "13"])
        self.assertEqual(_list_refs(" 303, 304, 305 and 306 and the substitution"), ["303", "304", "305", "306"])


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


def kinds(text):
    return {(o["op"], o["kind"], o["target"]) for o in extract_ops(text)}


class SectionNamedAfterTheVerb(unittest.TestCase):
    """ "The principal Act is amended in section ten, by—": 13 amending Acts
    drafted this way read as changing nothing until 12 Oct 2026."""

    def test_spelled_section(self):
        # High Court (Amendment) Act, 2002
        text = ("2. The principal Act is amended in section ten, by— Amendment 2. The principal Act is amended in "
                "section ten, by— Amendment of section 10 (a) the deletion of the full stop")
        self.assertEqual(ops(text), {("amended", "10")})

    def test_in_a_subsection_with_the_margin_spliced(self):
        # Value Added Tax (Amendment) Act, 2010
        text = ("3. The principal Act is amended in subsection (2) of section Amendment thirty-four by the deletion "
                "of the words “Commissioner of Value of section 34 Added Tax”")
        self.assertEqual(ops(text), {("amended", "34")})

    def test_hundreds_across_the_margin(self):
        # Criminal Procedure Code (Amendment) Act, 1997
        text = ("2. The principal Act is amended, in section two hundred and Amendment twenty-one, by the addition "
                "after paragraph (b) of the following new paragraph:")
        self.assertEqual(ops(text), {("amended", "221")})

    def test_a_hundred_cut_off_by_the_clause_number_is_not_section_100(self):
        # Mines and Minerals (Amendment) Act, 1997: the first copy stops at
        # "one hundred and"; the second says one hundred and eight.
        text = ("7. The principal Act is amended in section one hundred and 7. The principal Act is amended in "
                "section one hundred and eight by the deletion of subsection (3)")
        self.assertEqual(ops(text), {("amended", "108")})
        self.assertEqual(read_refs("one hundred and 7. The principal Act")[0], [])

    def test_ocr_that_is_not_a_number_is_not_two_sections(self):
        # Income Tax (Amendment) Act, 1997: "seventy-eighty" beside a margin
        # saying section 78. Read before as sections 70 and 80.
        text = "13. The principal Act is amended in section seventy-eighty by the of section 78 j subsection (1)"
        self.assertFalse({t for _, t in ops(text)} & {"70", "80"})
        self.assertEqual(read_refs("seventy-eighty by the")[0], [])


class DeletedAndSubstituted(unittest.TestCase):
    """ "the deletion of section replacement eight and the substitution
    therefor": spelled numbers with the margin note spliced in."""

    def test_spelled_with_the_margin_before_it(self):
        # Supreme Court (Amendment) Act, 2011. The first copy is cut off by
        # the amending Act's own "2. (1) The principal Act".
        text = ("2. (1) The principal Act is amended by the deletion of section Repeal and 2. (1) The principal Act "
                "is amended by the deletion of section replacement eight and the substitution therefor of the "
                "following new section: of section 8 Practice 8. (1) Subject to subsection (2)")
        self.assertEqual(ops(text), {("replaced", "8")})

    def test_digits_with_the_margin_after_them(self):
        # Judiciary Administration (Amendment) Act, 2018
        text = ("2. The principal Act is amended by the deletion of section 13 Amendment and substitution therefor "
                "of the following: of Section 13")
        self.assertEqual(ops(text), {("replaced", "13")})

    def test_spelled_tens(self):
        # Mines and Minerals Development (Amendment) Act, 2016
        text = ("2. (1) The principal Act is amended by the deletion of section Amendment 2. (1) The principal Act "
                "is amended by the deletion of section Amendment eighty-nine and the substitution therefor of the "
                "following: of section 89")
        self.assertEqual(ops(text), {("replaced", "89")})

    def test_the_amending_acts_own_number_is_not_a_repeal(self):
        # English Law (Extent of Application) (Amendment) Act, 2011. The first
        # copy ends "section two Repeal and 2." where "2." starts the clause
        # again; read as a deletion outright it repealed section 2.
        first_copy = ("2. The principal Act is amended by the deletion of section two Repeal and 2. The principal Act "
                      "is amended by the deletion")
        self.assertFalse([o for o in ops(first_copy) if o[0] == "repealed"])
        whole = first_copy + " of section two Repeal and and the substitution therefor of the following: replacement of section 2"
        self.assertEqual(ops(whole), {("replaced", "2")})

    def test_a_subsection_spliced_by_its_margin_is_not_the_section(self):
        # Public Procurement (Amendment) Act, 2023: section 29(2) with
        # "Amendment" between the number and the subsection.
        text = ("11. The principal Act is amended by the deletion of section 29 Amendment (2) and the substitution "
                "therefor of the following: of section 29 (2) A controlling officer")
        self.assertFalse([o for o in ops(text) if o[0] in ("repealed", "replaced")])

    def test_deleted_outright_is_a_repeal_when_words_and_margin_agree(self):
        # Income Tax (Amendment) Act No. 3 of 1997; the library's own Income
        # Tax Act reads "40. Repealed by Act No. 3 of 1997."
        text = ("Repeal of 7. The principal Act is amended by the deletion of section section 40 forty. Repeal of 8. "
                "The principal Act is amended by the deletion of section section 42 forty-two. Amendment 9.")
        self.assertEqual(ops(text), {("repealed", "40"), ("repealed", "42")})

    def test_the_clause_number_after_a_cut_number_is_not_the_target(self):
        # Financial Intelligence Centre (Amendment) Act, 2016: section five
        # was replaced; "3. (1) The principal Act" is the amending Act's own
        # section 3, and the old parser marked section 3 of the principal dead.
        text = ("Section 3. (1) The principal Act is amended by the repeal of section Repeal and 3. (1) The principal "
                "Act is amended by the repeal of section replacement five and the substitution therefor of the "
                "following: of section 5")
        self.assertEqual(ops(text), {("replaced", "5")})


class NewSectionAfterANamedOne(unittest.TestCase):
    def test_next_number(self):
        # Fees and Fines (Amendment) Act, 2013
        text = ("2. The principal Act is amended by the insertion, immediately after section eight, of the following "
                "new section: 9. The Minister may, by statutory instrument, make regulations")
        self.assertEqual(ops(text), {("inserted", "9")})

    def test_lettered_number_behind_margin_noise(self):
        # Zambia Tanzania Pipeline (Amendment) Act, 2009
        text = ("The principal Act is amended by the insertion immediately Insertion of after section eleven of the "
                "following new section: new section I IA 11A (1) Where any judgment order")
        self.assertEqual(ops(text), {("inserted", "11A")})

    def test_a_number_that_does_not_follow_is_not_taken(self):
        # Property Transfer Tax (Amendment) Act, 2012: "No. 13 of 2012" is the
        # page header, not a new section 13.
        text = ("6. The principal Act is amended by the insertion, immediately Amendment of section 9 after section "
                "twelve of the following new section: Property Transfer Tax (Amendment) [No. 13 of 2012 231 12A. (1) "
                "The President may")
        self.assertEqual(ops(text), {("inserted", "12A")})


class Schedules(unittest.TestCase):
    """A Schedule is recorded as its own kind and never as a section."""

    def test_replaced_with_the_margin_inside_the_name(self):
        # Road Traffic (Amendment) Act, 2021: licence taxes
        text = ("2. The principal Act is amended by the repeal of the Second Repeal and replacement Schedule and the "
                "substitution therefor of the Second Schedule set of Second Schedule out in the Appendix.")
        self.assertEqual(kinds(text), {("replaced", "schedule", "SECOND SCHEDULE")})

    def test_two_at_once(self):
        # Ministerial and Parliamentary Offices (Emoluments) (Amendment) Act, 2002
        text = ("2. The principal Act is amended by the repeal of the First and Repeal and Second Schedules and the "
                "substitution therefor of the First and replacement of the First Second Schedules set out in the Appendix.")
        self.assertEqual(kinds(text), {("replaced", "schedule", "FIRST SCHEDULE"),
                                       ("replaced", "schedule", "SECOND SCHEDULE")})

    def test_repealed_outright(self):
        # Roads and Road Traffic (Amendment) Act, 1997
        text = "Repeal of 4. The principal Act is amended by the repeal of the Third Third Schedule."
        self.assertEqual(kinds(text), {("repealed", "schedule", "THIRD SCHEDULE")})

    def test_amended(self):
        # Weights and Measures (Amendment) Act, 2013; Anti-Gender-Based Violence (Amendment) Act, 2026
        self.assertEqual(kinds("2. The Thirteenth Schedule to the principal Act is amended in paragraph 9 by the"),
                         {("amended", "schedule", "THIRTEENTH SCHEDULE")})
        self.assertEqual(kinds("Amendment 2. The Schedule to the principal Act is amended in — of Schedule (a) paragraph 1,"),
                         {("amended", "schedule", "SCHEDULE")})

    def test_a_new_heading_is_not_a_repealed_schedule(self):
        # Mental Health (Amendment) Act, 2026: "the repeal ... of the heading"
        text = ("4. The Schedule to the principal Act is amended by the repeal Repeal and of the heading and the "
                "substitution therefor of the following:")
        self.assertEqual(kinds(text), {("amended", "schedule", "SCHEDULE")})


class ConstitutionArticles(unittest.TestCase):
    def test_amended_and_replaced(self):
        # Constitution of Zambia (Amendment) Act, 2025
        self.assertEqual(ops("2. Article 47 of the Constitution is amended by the— Amendment"), {("amended", "47")})
        self.assertEqual(ops("9. Article 103 (2) of the Constitution is amended by the insertion"), {("amended", "103")})
        text = ("5. The Constitution is amended by the repeal of Article 68 Repeal and and the substitution therefor "
                "of the following: replacement of Article 68")
        self.assertEqual(ops(text), {("replaced", "68")})

    def test_a_range_is_not_read(self):
        # Constitution of Zambia (Amendment) Act, 2016, which the library's
        # "as amended to 2016" text already contains.
        text = ("6. The Constitution is amended by the repeal of Articles 62 to 78 inclusive and the substitution "
                "therefor of the following:")
        self.assertEqual(ops(text), set())


class PartsByName(unittest.TestCase):
    def test_part_repealed_before_the_verb(self):
        # Zambia National Broadcasting Corporation (Amendment) Act, 2017
        self.assertEqual(kinds("3. Part IV of the principal Act is repealed. Repeal of"), {("repealed", "part", "IV")})

    def test_new_part(self):
        # Customs and Excise (Amendment) (No. 2) Act, 2001
        text = ("2. The principal Act is amended by the insertion of the follow- Insertion of ing new part: new part "
                "VIA 70A (1) The Minister may")
        self.assertEqual(kinds(text), {("inserted", "part", "VIA")})
        self.assertEqual(kinds("(b) by the insertion of the following new part immediately after Part III:"), set())


if __name__ == "__main__":
    unittest.main()
