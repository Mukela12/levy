"""Final pay and gratuity to date (services/final_pay.py).

Figures worked by hand from the Employment Code Act 2019 (ss.36, 38, 53, 54,
55, 68, 73) and ZRA Practice Note No. 1 of 2026 (paras 38 to 40). The first
case is the HR user's own from the week of 6 October 2026.
"""
import asyncio
import sys
import types
import unittest
from datetime import date

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services.entitlements import calculate_entitlements  # noqa: E402
from app.services.final_pay import calculate_final_pay, calculate_gratuity, earned, parse_date  # noqa: E402

TODAY = date(2026, 10, 12)


def line(r, item):
    return next((li for li in r["lines"] if li["item"] == item), None)


class TheResignationWithImmediateEffect(unittest.TestCase):
    """Basic K2,000 + K700 allowances; worked 1 to 15 January 2026; resigned with
    immediate effect on a contract with one month's notice; gratuity paid to December."""

    def setUp(self):
        self.r = calculate_final_pay(
            monthly_basic_pay=2000, monthly_allowances=700, termination_reason="resignation",
            termination_date="15/01/2026", paid_through_date="31/12/2025", contract_type="long_term",
            contract_start_date="01/02/2024", gratuity_paid_through="31/12/2025", accrued_leave_days=8,
            notice_months=1, employee_worked_notice=False, today=TODAY)

    def test_days_worked_are_earned(self):
        self.assertEqual(line(self.r, "Wages for days worked")["amount"], 1306.45)    # 2,700 x 15/31
        self.assertEqual(line(self.r, "Wages for days worked")["status"], "owed")
        self.assertEqual(line(self.r, "Accrued leave")["amount"], 526.03)            # 8 x 2,000 x 12 / 365

    def test_gratuity_runs_to_the_last_day(self):
        g = line(self.r, "Gratuity")
        self.assertEqual(g["amount"], 241.94)                                        # 25% x 967.74
        self.assertEqual(g["status"], "contested")                                   # resigned without notice
        self.assertTrue(any("effective date of termination" in f["message"] for f in self.r["flags"]))

    def test_tax_falls_on_wages_and_leave_only(self):
        self.assertEqual(self.r["taxable_total"], 1832.48)
        self.assertEqual(line(self.r, "PAYE")["amount"], 0.0)                        # under K5,100
        self.assertEqual(line(self.r, "NAPSA (employee 5%)")["amount"], 65.32)
        self.assertEqual(line(self.r, "NHIMA (employee 1%)")["amount"], 9.68)

    def test_the_setoff_is_capped_at_the_money_due(self):
        self.assertEqual(self.r["net_before_setoff"], 1757.48)
        self.assertEqual(self.r["setoff"], 1757.48)                                  # not the full K2,700
        self.assertEqual(self.r["net_payable"], 0.0)
        self.assertEqual(self.r["balance_claimable"], 942.52)

    def test_the_setoff_cites_s53_5_and_never_s69_as_its_basis(self):
        s = line(self.r, "Notice not worked (set-off)")
        self.assertIn("s.53(5)", s["basis"])
        self.assertIn("s.68(1)(a)", s["basis"])
        self.assertNotIn("s.69", s["basis"])
        self.assertIn("s.69 is not the basis", s["note"])


class OtherEndings(unittest.TestCase):
    def test_a_resignation_on_notice_gets_its_gratuity_and_no_setoff(self):
        r = calculate_final_pay(monthly_basic_pay=2000, termination_reason="resignation", termination_date="31/01/2026",
                                paid_through_date="31/12/2025", contract_type="long_term",
                                gratuity_paid_through="31/12/2025", accrued_leave_days=0, employee_worked_notice=True,
                                today=TODAY)
        self.assertEqual(line(r, "Gratuity")["status"], "owed")
        self.assertEqual(line(r, "Gratuity")["amount"], 500.0)                       # 25% x one full month
        self.assertEqual(r["setoff"], 0.0)

    def test_dismissal_without_notice_pays_in_lieu_tax_free(self):
        r = calculate_final_pay(monthly_basic_pay=3000, termination_reason="dismissal", termination_date="20/03/2026",
                                employment_start_date="01/03/2023", contract_type="permanent", accrued_leave_days=0,
                                employer_gave_notice=False, today=TODAY)
        pilon = line(r, "Pay in lieu of notice")
        self.assertEqual(pilon["amount"], 2958.9)                                    # 30 days x 3,000 x 12 / 365
        self.assertFalse(pilon["taxable"])
        self.assertEqual(line(r, "Wages for days worked")["amount"], 1935.48)        # 3,000 x 20/31
        self.assertEqual(r["taxable_total"], 1935.48)
        self.assertEqual(line(r, "Gratuity")["status"], "not_applicable")

    def test_redundancy_on_a_permanent_contract(self):
        r = calculate_final_pay(monthly_basic_pay=4000, termination_reason="redundancy", termination_date="30/06/2026",
                                paid_through_date="30/06/2026", employment_start_date="01/01/2024",
                                contract_type="permanent", accrued_leave_days=0, employer_gave_notice=True, today=TODAY)
        pay = line(r, "Redundancy pay")
        self.assertEqual(pay["status"], "owed")
        self.assertAlmostEqual(pay["amount"], 2 * 4000 * 2.5, delta=25)             # 2.5 years served
        self.assertFalse(pay["taxable"])
        self.assertEqual(r["taxable_total"], 0.0)

    def test_end_of_a_long_term_contract(self):
        r = calculate_final_pay(monthly_basic_pay=5000, termination_reason="end_of_contract",
                                termination_date="31/12/2026", paid_through_date="31/12/2026",
                                contract_start_date="01/01/2025", contract_type="long_term", accrued_leave_days=0,
                                today=TODAY)
        self.assertEqual(line(r, "Gratuity")["amount"], 30000.0)                     # 25% x 24 x 5,000
        self.assertEqual(line(r, "Gratuity")["status"], "owed")
        self.assertEqual(r["net_payable"], 30000.0)                                  # exempt, nothing deducted

    def test_fixed_term_redundancy_does_not_pay_severance_twice(self):
        r = calculate_final_pay(monthly_basic_pay=3000, termination_reason="redundancy", termination_date="30/06/2026",
                                paid_through_date="30/06/2026", employment_start_date="01/01/2026",
                                contract_type="fixed_term", accrued_leave_days=0, employer_gave_notice=True,
                                today=TODAY)
        self.assertEqual(line(r, "Severance gratuity (fixed-term contract)")["status"], "conditional")

    def test_missing_facts_are_asked_for_not_assumed(self):
        r = calculate_final_pay(monthly_basic_pay=2500, termination_reason="resignation", termination_date="10/02/2026",
                                today=TODAY)
        self.assertIn("Accrued leave days", r["needs_input"])
        self.assertIn("Contract type", r["needs_input"])
        self.assertIn("Whether the employee worked the notice period", r["needs_input"])
        self.assertTrue(any("paid up to 31 Jan 2026" in a for a in r["assumptions"]))

    def test_an_unreadable_date_is_refused(self):
        with self.assertRaises(ValueError):
            calculate_final_pay(monthly_basic_pay=2000, termination_reason="resignation", termination_date="sometime")


class GratuityToDate(unittest.TestCase):
    def test_mr_brights_gratuity_to_the_end_of_october(self):
        g = calculate_gratuity(monthly_basic_pay=6000, contract_start_date="1 November 2025", as_of_date="31/10/2026",
                               contract_end_date="31/10/2027", gratuity_advanced=5000, today=TODAY)
        self.assertEqual(g["months"], 12.0)
        self.assertEqual(g["accrued"], 18000.0)
        self.assertEqual(g["balance"], 13000.0)
        self.assertEqual(g["projected_at_end"], 31000.0)                             # 36,000 less the advance
        self.assertTrue(any("para 40" in f["message"] for f in g["flags"]))

    def test_a_permanent_contract_has_no_statutory_gratuity(self):
        g = calculate_gratuity(monthly_basic_pay=6000, contract_start_date="01/01/2026", as_of_date="30/06/2026",
                               contract_type="permanent", today=TODAY)
        self.assertEqual(g["flags"][0]["severity"], "check")
        self.assertIn("has none", g["flags"][0]["message"])


class Helpers(unittest.TestCase):
    def test_day_first_dates(self):
        self.assertEqual(parse_date("04/09/2026"), date(2026, 9, 4))
        self.assertEqual(parse_date("4th September 2026"), date(2026, 9, 4))

    def test_partial_months_prorate_by_calendar_days(self):
        amount, months, desc = earned(3100, date(2026, 1, 1), date(2026, 2, 14))
        self.assertAlmostEqual(months, 1.5)                                          # Jan + 14/28 of Feb
        self.assertAlmostEqual(amount, 4650)
        self.assertEqual(desc, "1 full month + 14/28 of Feb 2026")


class EntitlementsNoLongerPayGratuityTwice(unittest.TestCase):
    def test_end_of_a_long_term_contract_has_one_25_percent_line(self):
        r = calculate_entitlements(monthly_basic_pay=4000, years_of_service=2, termination_reason="end_of_fixed_term",
                                   contract_type="long_term")
        quarter = [li for li in r["line_items"] if li["amount"] == 24000.0 and li["status"] == "owed"]
        self.assertEqual(len(quarter), 1)
        self.assertEqual(r["total_clearly_owed"], 24000.0)


class ToolDispatch(unittest.TestCase):
    def test_calculate_payroll_routes_the_modes(self):
        from app.services.tools import build_tool_registry
        handler = build_tool_registry(web_enabled=False)["calculate_payroll"].handler
        out = asyncio.run(handler(monthly_basic_pay=2000, mode="final_pay", termination_reason="resignation",
                                  termination_date="15/01/2026", other_allowances=700, contract_type="long_term",
                                  employee_worked_notice=True, accrued_leave_days=0))
        self.assertEqual(out["entitlement_breakdown"]["kind"], "final_pay")
        self.assertEqual(out["entitlement_breakdown"]["monthly_allowances"], 700.0)
        out = asyncio.run(handler(monthly_basic_pay=6000, mode="gratuity", contract_start_date="01/11/2025",
                                  as_of_date="31/10/2026"))
        self.assertEqual(out["entitlement_breakdown"]["accrued"], 18000.0)
        out = asyncio.run(handler(monthly_basic_pay=2000, mode="final_pay", termination_reason="quit",
                                  termination_date="15/01/2026"))
        self.assertIn("Unknown termination reason", out["result"]["error"])


if __name__ == "__main__":
    unittest.main()
