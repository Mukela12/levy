"""The payroll calculator holds the statutory floors that HR users tried to talk Levy below.

Each expected figure was worked by hand from the statute text in the library:
Employment Code s.75, SI 48 and SI 50 of 2023, SI 3 of 2025, NPS Act s.14,
NHI Act s.15 and ZRA Practice Note No. 1 of 2026.
"""
import sys
import types
import unittest
from datetime import date

sys.modules.setdefault("weasyprint", types.SimpleNamespace(HTML=None, CSS=None))

from app.services.payroll import calculate_payroll, match_category, paye_monthly  # noqa: E402


def line(result, item, group="earnings"):
    return next((li for li in result[group] if li["item"] == item), None)


def check(result, item):
    return next((c for c in result["audit"] if c["item"] == item), None)


def severities(result):
    return [f["severity"] for f in result["flags"]]


TODAY = date(2026, 10, 6)


class Overtime(unittest.TestCase):
    def test_208_is_a_divisor_not_a_trigger(self):
        # 205 hours in the month, under 208, yet three weeks ran past 48 hours.
        r = calculate_payroll(monthly_basic_pay=1487, wage_order="general", category=1,
                              weekly_hours=[55, 50, 48, 52], accommodation_provided=True,
                              lives_beyond_3km=False, free_meals_provided=True, today=TODAY)
        self.assertEqual(r["overtime_hours"], 13)
        self.assertEqual(r["hourly_rate"], 7.15)                 # the Order's printed hourly minimum
        self.assertEqual(line(r, "Overtime")["amount"], 139.43)  # 13 x 1.5 x 7.15
        self.assertIn("not an overtime threshold", line(r, "Overtime")["note"])

    def test_a_contract_cannot_raise_the_weekly_trigger(self):
        r = calculate_payroll(monthly_basic_pay=3000, weekly_hours=[52, 52], weekly_overtime_threshold=52, today=TODAY)
        self.assertEqual(r["overtime_hours"], 8)                 # counted over 48, not 52
        self.assertIn("breach", severities(r))

    def test_a_contract_can_lower_it(self):
        r = calculate_payroll(monthly_basic_pay=3120, weekly_hours=[45, 40], weekly_overtime_threshold=40, today=TODAY)
        self.assertEqual(r["overtime_hours"], 5)
        self.assertEqual(line(r, "Overtime")["amount"], 112.5)   # 5 x 1.5 x (3120 / 208 = 15)

    def test_a_guard_uses_240_and_60(self):
        r = calculate_payroll(monthly_basic_pay=2400, employee_type="guard", weekly_hours=[72, 60, 66, 58], today=TODAY)
        self.assertEqual(r["hourly_rate"], 10.0)                 # 2400 / 240
        self.assertEqual(r["overtime_hours"], 18)                # 12 + 0 + 6 + 0
        self.assertEqual(line(r, "Overtime")["amount"], 270.0)

    def test_rest_day_and_holiday_hours_are_double(self):
        r = calculate_payroll(monthly_basic_pay=2080, rest_day_or_holiday_hours=8, today=TODAY)
        self.assertEqual(line(r, "Public holiday / rest day work")["amount"], 160.0)  # 8 x 2 x 10


class WageOrders(unittest.TestCase):
    def test_the_waiter_case(self):
        # 2 October: a waiter on K1,650 under SI 50 Category II (K8.66 / K1,801.98).
        r = calculate_payroll(monthly_basic_pay=1650, wage_order="shop_workers", occupation="waiter",
                              night_hours=40, accommodation_provided=False, lives_beyond_3km=True,
                              transport_provided=False, free_meals_provided=False, today=TODAY)
        self.assertEqual(r["category"], 2)
        self.assertEqual(r["required_basic"], 1801.98)
        self.assertEqual(r["hourly_rate"], 8.6634)               # 1801.98 / 208
        self.assertEqual(line(r, "Night shift differential")["amount"], 51.98)
        self.assertEqual(line(r, "Housing allowance")["amount"], 540.59)
        self.assertEqual(r["minimum_gross"], 2774.55)            # 1801.98 + 51.98 + 540.59 + 200 + 180
        self.assertEqual(severities(r)[:2], ["breach", "breach"])
        self.assertIn("days off in lieu do not discharge it", line(r, "Night shift differential")["note"])

    def test_longest_job_title_wins(self):
        self.assertEqual([c.number for c in match_category("shop_workers", "shelf packer")], [3])
        self.assertEqual([c.number for c in match_category("shop_workers", "assistant dispatch clerk")], [3])
        self.assertEqual([c.number for c in match_category("general", "assistant sales person")], [3])
        self.assertEqual(len(match_category("shop_workers", "driver")), 3)

    def test_an_ambiguous_driver_asks(self):
        r = calculate_payroll(monthly_basic_pay=2000, wage_order="shop_workers", occupation="driver", today=TODAY)
        self.assertIsNone(r["category"])
        self.assertIn("Wage order category", r["needs_input"])
        self.assertTrue(any("heavy duty" in f["message"] for f in r["flags"]))

    def test_roman_numeral_category(self):
        r = calculate_payroll(monthly_basic_pay=3000, wage_order="shop_workers", category="VII", today=TODAY)
        self.assertEqual(r["minimum_basic"], 3142.26)

    def test_unknown_facts_are_not_counted(self):
        r = calculate_payroll(monthly_basic_pay=1801.98, wage_order="shop_workers", category=2, today=TODAY)
        self.assertEqual(line(r, "Housing allowance")["status"], "needs_input")
        self.assertEqual(r["minimum_gross"], 1801.98)
        self.assertIn("Lunch allowance", r["needs_input"])

    def test_a_package_above_the_orders_gross_makes_order_items_conditional(self):
        r = calculate_payroll(monthly_basic_pay=6000, wage_order="general", occupation="machine operator",
                              night_hours=20, other_allowances=2500, accommodation_provided=False,
                              lives_beyond_3km=True, transport_provided=False, free_meals_provided=False, today=TODAY)
        self.assertEqual(r["order_applies"], "conditional")
        self.assertEqual(line(r, "Night shift differential")["status"], "conditional")
        self.assertEqual(r["minimum_gross"], 8500.0)

    def test_exempt_staff_keep_the_code_floors(self):
        r = calculate_payroll(monthly_basic_pay=1200, wage_order="general", category=1,
                              order_exemption="management", weekly_hours=[50, 50], today=TODAY)
        self.assertEqual(r["order_applies"], "no")
        self.assertEqual(r["required_basic"], 1200.0)
        self.assertEqual(r["overtime_hours"], 4)

    def test_part_time_is_paid_in_proportion_to_208_hours(self):
        r = calculate_payroll(monthly_basic_pay=600, employee_type="casual", wage_order="shop_workers",
                              category=2, hours_worked_in_month=80, today=TODAY)
        self.assertEqual(r["required_basic"], 693.07)            # 1801.98 x 80 / 208
        self.assertEqual(line(r, "Casual loading")["amount"], 173.27)

    def test_truck_driver_minimum(self):
        r = calculate_payroll(monthly_basic_pay=3500, wage_order="truck_driver", today=TODAY)
        self.assertEqual(r["required_basic"], 4000.0)
        self.assertIn("breach", severities(r))


class Deductions(unittest.TestCase):
    def test_paye_2026_bands(self):
        self.assertEqual(paye_monthly(5100), 0.0)
        self.assertEqual(paye_monthly(6000), 180.0)
        self.assertEqual(paye_monthly(10000), 1326.0)            # 400 + 630 + 296
        self.assertEqual(paye_monthly(12000), 2066.0)

    def test_napsa_on_gross_nhima_on_basic(self):
        r = calculate_payroll(monthly_basic_pay=4000, other_allowances=1000, today=TODAY)
        self.assertEqual(line(r, "NAPSA (employee 5%)", "deductions")["amount"], 250.0)
        self.assertEqual(line(r, "NHIMA (employee 1%)", "deductions")["amount"], 40.0)

    def test_napsa_ceiling(self):
        r = calculate_payroll(monthly_basic_pay=50000, napsa_ceiling=30000, today=TODAY)
        self.assertEqual(line(r, "NAPSA (employee 5%)", "deductions")["amount"], 1500.0)

    def test_later_years_are_told_to_confirm_the_bands(self):
        r = calculate_payroll(monthly_basic_pay=4000, today=date(2027, 2, 1))
        self.assertTrue(any("2027" in f["message"] for f in r["flags"]))


class PayslipCheck(unittest.TestCase):
    def run_slip(self, **slip):
        return calculate_payroll(
            monthly_basic_pay=1650, wage_order="shop_workers", occupation="waiter", weekly_hours=[52, 50, 48, 47],
            night_hours=40, accommodation_provided=False, lives_beyond_3km=True, transport_provided=False,
            free_meals_provided=False, payslip=slip, today=TODAY)

    def test_every_shortfall_is_found_and_totalled(self):
        r = self.run_slip(basic=1650, overtime=0, night_differential=0, housing_allowance=0, transport_allowance=200,
                          lunch_allowance=180, gross=2030, napsa=82.5, nhima=20.3, paye=0, net=1927.2)
        self.assertEqual(check(r, "Basic pay")["status"], "underpaid")
        self.assertEqual(check(r, "Overtime")["difference"], -77.97)
        self.assertEqual(check(r, "Housing allowance")["difference"], -540.59)
        # NAPSA taken on basic (5% of 1,650) instead of gross (5% of 2,030).
        self.assertEqual(check(r, "NAPSA deducted")["status"], "check")
        self.assertEqual(check(r, "NAPSA deducted")["required"], 101.5)
        # NHIMA taken on gross instead of basic: K3.80 too much.
        self.assertEqual(check(r, "NHIMA deducted")["status"], "over_deducted")
        self.assertEqual(r["total_underpaid"], 826.32)
        self.assertEqual(r["flags"][0]["severity"], "breach")
        self.assertFalse(any("net" in f["message"] and "not its gross" in f["message"] for f in r["flags"]))

    def test_a_line_left_out_is_not_assumed_to_be_zero(self):
        r = self.run_slip(basic=1801.98)
        self.assertEqual(check(r, "Overtime")["status"], "check")
        self.assertEqual(r["total_underpaid"], 0.0)

    def test_lines_left_out_still_give_the_whole_figure(self):
        # The production QA case: basic, transport and lunch given; overtime,
        # night pay and housing left out rather than passed as 0.
        r = self.run_slip(basic=1650, transport_allowance=200, lunch_allowance=180, nhima=20.3)
        self.assertEqual(r["total_underpaid"], 155.78)                  # 151.98 basic + 3.80 NHIMA
        self.assertEqual(r["total_if_unpaid"], 826.32)                  # + 77.97 + 51.98 + 540.59
        self.assertTrue(any("826.32" in f["message"] for f in r["flags"]))

    def test_a_payslip_that_adds_up_to_its_gross_is_complete(self):
        # Basic 1,650 + transport 200 + lunch 180 = gross 2,030: nothing else was paid.
        r = self.run_slip(basic=1650, transport_allowance=200, lunch_allowance=180, gross=2030, nhima=20.3)
        self.assertEqual(check(r, "Housing allowance")["status"], "underpaid")
        self.assertEqual(r["total_underpaid"], 826.32)

    def test_unauthorised_deductions_are_flagged_with_s68(self):
        r = self.run_slip(basic=1801.98, other_deductions=[{"label": "Breakages", "amount": 50}])
        self.assertEqual(check(r, "Breakages")["status"], "check")
        self.assertIn("s.79(c)", check(r, "Breakages")["note"])

    def test_payslip_arithmetic_is_checked(self):
        r = self.run_slip(basic=1650, gross=2030, napsa=101.5, nhima=16.5, paye=0, net=1950)
        self.assertTrue(any("not its gross less its deductions" in f["message"] for f in r["flags"]))


if __name__ == "__main__":
    unittest.main()
