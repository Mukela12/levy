"""The Domestic Workers Order, SI No. 49 of 2023, in the three pay calculators.

Figures worked by hand from the Order as printed (Gazette No. 7522 supplement,
pp. 299-300): K5.29 an hour or K1,100.00 a month, excluding money paid in lieu
of rations (para 4(1)); separation benefits of one month's basic pay for every
two completed years of service, never together with gratuity (para 5); K200 a
month for transport beyond 3 km unless the employer provides it (para 6). The
first case is the user's own from 31 October 2026: a domestic worker with four
years' service on K1,050 basic.
"""
import asyncio
import sys
import types
import unittest
from datetime import date

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services.entitlements import calculate_entitlements  # noqa: E402
from app.services.final_pay import calculate_final_pay  # noqa: E402
from app.services.payroll import (DOMESTIC_HOURLY, DOMESTIC_MONTHLY, DOMESTIC_TEXT, DOMESTIC_TRANSPORT, _k,  # noqa: E402
                                  calculate_payroll, completed_years)

TODAY = date(2026, 11, 2)
SEPARATION = "Separation benefits (domestic worker)"


def earning(r, item):
    return next((li for li in r["earnings"] if li["item"] == item), None)


def final_line(r, item):
    return next((li for li in r["lines"] if li["item"] == item), None)


def entitlement(r, item):
    return next((li for li in r["line_items"] if li["item"] == item), None)


class TheOrdersWords(unittest.TestCase):
    def test_the_quoted_words_carry_the_coded_figures(self):
        self.assertIn(f"({_k(DOMESTIC_HOURLY)}) per hour", DOMESTIC_TEXT["minimum"])
        self.assertIn(f"({_k(DOMESTIC_MONTHLY)}) per month", DOMESTIC_TEXT["minimum"])
        self.assertIn("excluding an amount paid in lieu of rations", DOMESTIC_TEXT["minimum"])
        self.assertIn(f"({_k(DOMESTIC_TRANSPORT)}) for transport", DOMESTIC_TEXT["transport"])
        self.assertIn("one month's basic pay for every two completed years of service", DOMESTIC_TEXT["separation"])
        self.assertIn("shall not be entitled to both separation benefits and gratuity", DOMESTIC_TEXT["not_both"])

    def test_completed_years_count_anniversaries_to_the_last_day(self):
        self.assertEqual(completed_years(date(2022, 1, 1), date(2025, 12, 31)), 4)
        self.assertEqual(completed_years(date(2021, 3, 1), date(2023, 2, 28)), 2)
        self.assertEqual(completed_years(date(2021, 3, 1), date(2023, 2, 27)), 1)
        self.assertEqual(completed_years(date(2022, 3, 1), date(2024, 2, 28)), 1)   # 29 February still to work
        self.assertEqual(completed_years(date(2022, 3, 1), date(2024, 2, 29)), 2)


class MonthlyPay(unittest.TestCase):
    def test_the_31_october_case_is_below_the_minimum(self):
        r = calculate_payroll(monthly_basic_pay=1050, wage_order="domestic", today=TODAY)
        self.assertEqual(r["wage_order_label"], "SI No. 49 of 2023 (Domestic Workers Order)")
        self.assertEqual(r["order_applies"], "yes")
        self.assertEqual(r["minimum_basic"], 1100.0)
        self.assertEqual(r["required_basic"], 1100.0)
        self.assertEqual(r["hourly_rate"], 5.29)                       # 1,100 / 208 = 5.288, raised to K5.29
        breach = r["flags"][0]
        self.assertEqual(breach["severity"], "breach")
        self.assertIn("K50.00 a month", breach["message"])
        self.assertIn("in lieu of rations", breach["message"])
        self.assertEqual(breach["basis"], "SI No. 49 of 2023 (Domestic Workers Order), para 4(1)")
        self.assertEqual(earning(r, "Basic pay")["amount"], 1100.0)
        self.assertEqual(earning(r, "Transport allowance")["status"], "needs_input")
        self.assertEqual(r["net_pay"], 1034.0)                         # 1,100 - 55.00 NAPSA - 11.00 NHIMA
        self.assertFalse(any("does not hold" in f["message"] for f in r["flags"]))

    def test_transport_beyond_3km(self):
        r = calculate_payroll(monthly_basic_pay=1200, wage_order="domestic", lives_beyond_3km=True,
                              transport_provided=False, today=TODAY)
        transport = earning(r, "Transport allowance")
        self.assertEqual((transport["status"], transport["amount"]), ("required", 200.0))
        self.assertEqual(transport["basis"], "SI No. 49 of 2023 (Domestic Workers Order), para 6")
        self.assertEqual(r["minimum_gross"], 1400.0)
        self.assertEqual(r["net_pay"], 1318.0)                         # 1,400 - 70.00 - 12.00
        self.assertNotIn("breach", [f["severity"] for f in r["flags"]])

    def test_a_live_in_worker_has_no_transport_allowance_and_nothing_else(self):
        r = calculate_payroll(monthly_basic_pay=1100, wage_order="domestic", lives_beyond_3km=False,
                              accommodation_provided=False, free_meals_provided=False, today=TODAY)
        self.assertEqual([li["item"] for li in r["earnings"]], ["Basic pay"])   # no housing or lunch in SI 49

    def test_part_time_uses_the_printed_hourly_minimum(self):
        r = calculate_payroll(monthly_basic_pay=400, wage_order="domestic", employee_type="part_time",
                              hours_worked_in_month=80, today=TODAY)
        self.assertEqual(r["required_basic"], 423.2)                   # 80 x K5.29
        self.assertIn("K5.29 an hour x 80 hours", r["flags"][0]["message"])

    def test_piece_work_is_outside_the_order(self):
        r = calculate_payroll(monthly_basic_pay=500, wage_order="domestic", order_exemption="piece_work", today=TODAY)
        self.assertEqual(r["order_applies"], "no")
        self.assertIsNone(r["minimum_basic"])
        self.assertTrue(any(f["basis"].endswith("para 2(2)(c)") for f in r["flags"]))

    def test_no_night_differential(self):
        r = calculate_payroll(monthly_basic_pay=1100, wage_order="domestic", night_hours=20, today=TODAY)
        self.assertIsNone(earning(r, "Night shift differential"))
        self.assertTrue(any("no night shift differential" in f["message"] for f in r["flags"]))

    def test_a_maid_under_the_general_order_is_pointed_to_si_49(self):
        r = calculate_payroll(monthly_basic_pay=1500, wage_order="general", occupation="house maid", today=TODAY)
        self.assertTrue(any("SI No. 49 of 2023" in f["message"] and f["basis"].endswith("para 2(2)(c)")
                            for f in r["flags"]))


class FinalPay(unittest.TestCase):
    def run_final(self, **kw):
        args = dict(monthly_basic_pay=1100, termination_reason="dismissal", termination_date="31/12/2025",
                    employment_start_date="01/01/2022", paid_through_date="31/12/2025", contract_type="permanent",
                    accrued_leave_days=0, employer_gave_notice=True, wage_order="domestic", today=TODAY)
        args.update(kw)
        return calculate_final_pay(**args)

    def test_four_years_earn_two_months(self):
        r = self.run_final()
        sep = final_line(r, SEPARATION)
        self.assertEqual((sep["status"], sep["amount"], sep["taxable"]), ("owed", 2200.0, False))
        self.assertIn(DOMESTIC_TEXT["separation"], sep["note"])
        self.assertEqual(sep["basis"], "SI No. 49 of 2023 (Domestic Workers Order), para 5")
        self.assertEqual(r["net_payable"], 2200.0)

    def test_the_31_october_case_is_raised_to_the_minimum(self):
        r = self.run_final(monthly_basic_pay=1050)
        self.assertEqual(r["monthly_basic_pay"], 1100.0)
        self.assertEqual(r["flags"][0]["severity"], "breach")
        self.assertIn("K50.00 for each month", r["flags"][0]["message"])
        self.assertEqual(final_line(r, SEPARATION)["amount"], 2200.0)

    def test_a_gratuity_that_is_due_displaces_it(self):
        r = self.run_final(monthly_basic_pay=1500, termination_reason="end_of_contract", contract_type="long_term",
                           employment_start_date="01/01/2021", contract_start_date="01/01/2023")
        self.assertEqual(final_line(r, "Gratuity")["status"], "owed")
        self.assertEqual(final_line(r, "Gratuity")["amount"], 13500.0)   # 25% x 1,500 x 36 months
        sep = final_line(r, SEPARATION)
        self.assertEqual((sep["status"], sep["amount"]), ("not_applicable", None))
        self.assertIn(DOMESTIC_TEXT["not_both"], sep["note"])

    def test_redundancy_pay_does_not_displace_it(self):
        r = self.run_final(termination_reason="redundancy")
        self.assertEqual(final_line(r, "Redundancy pay")["amount"], 8800.0)   # 2 x 1,100 x 4
        sep = final_line(r, SEPARATION)
        self.assertEqual((sep["status"], sep["amount"]), ("owed", 2200.0))
        self.assertIn("rules out only gratuity", sep["note"])
        self.assertEqual(r["total_due"], 11000.0)

    def test_under_two_completed_years_earns_none(self):
        r = self.run_final(employment_start_date="01/01/2025")
        self.assertEqual(final_line(r, SEPARATION)["status"], "not_applicable")

    def test_summary_dismissal_is_contested(self):
        r = self.run_final(termination_reason="summary_dismissal")
        self.assertEqual(final_line(r, SEPARATION)["status"], "contested")
        self.assertEqual(r["total_conditional"], 2200.0)

    def test_without_a_start_date_it_is_asked_for(self):
        r = self.run_final(employment_start_date=None)
        self.assertEqual(final_line(r, SEPARATION)["status"], "needs_input")
        self.assertIn("Employment start date", r["needs_input"])

    def test_other_workers_have_no_separation_line(self):
        r = self.run_final(wage_order=None)
        self.assertIsNone(final_line(r, SEPARATION))


class Entitlements(unittest.TestCase):
    def test_the_31_october_case(self):
        # 1 January 2022 to 31 December 2025 is 1,460 days, 3.9973 years by 365.25.
        r = calculate_entitlements(monthly_basic_pay=1050, years_of_service=3.9973, termination_reason="resignation",
                                   contract_type="permanent", wage_order="domestic")
        self.assertEqual(r["monthly_basic_pay"], 1100.0)
        self.assertEqual(r["daily_rate"], 36.16)                       # 1,100 x 12 / 365
        self.assertIn("K1,050.00", r["assumptions"][0])
        self.assertEqual(entitlement(r, "Minimum wage shortfall")["status"], "needs_input")
        sep = entitlement(r, SEPARATION)
        self.assertEqual((sep["status"], sep["amount"]), ("owed", 2200.0))
        self.assertIn("does not limit it to a contract the employer ends", sep["note"])
        self.assertEqual(r["total_clearly_owed"], 2200.0)

    def test_a_long_term_gratuity_displaces_it(self):
        r = calculate_entitlements(monthly_basic_pay=1500, years_of_service=5, termination_reason="dismissal_with_notice",
                                   contract_type="long_term", wage_order="domestic")
        self.assertEqual(entitlement(r, "Gratuity (long-term contract)")["status"], "owed")
        self.assertEqual(entitlement(r, SEPARATION)["status"], "not_applicable")

    def test_the_tool_counts_completed_years_from_the_dates(self):
        from app.services.tools import build_tool_registry
        handler = build_tool_registry(web_enabled=False)["calculate_entitlements"].handler
        out = asyncio.run(handler(monthly_basic_pay=1050, termination_reason="resignation", start_date="01/01/2022",
                                  termination_date="31/12/2025", contract_type="permanent", wage_order="domestic"))
        self.assertEqual(entitlement(out["entitlement_breakdown"], SEPARATION)["amount"], 2200.0)

    def test_other_workers_are_unchanged(self):
        r = calculate_entitlements(monthly_basic_pay=1050, years_of_service=4, termination_reason="resignation",
                                   contract_type="permanent")
        self.assertEqual(r["monthly_basic_pay"], 1050.0)
        self.assertIsNone(entitlement(r, SEPARATION))


if __name__ == "__main__":
    unittest.main()
