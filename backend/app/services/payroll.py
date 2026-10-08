"""Deterministic Zambian payroll calculator and payslip check.

Both HR users who brought payroll to Levy probed, turn after turn, for a basis
to pay less: a "208-hour overtime threshold", night work "rostered away" with
days off, NAPSA on basic only, rates re-pegged below the derived one. Levy held
most of those lines by reading the statute back, and once it did not. Here the
rate derivation and the floors are code, so they cannot be negotiated in chat,
and the arithmetic cannot slip.

Every rule below was read from the text in Levy's library:

  Employment Code Act No. 3 of 2019
    s.3      "basic pay": the standard rate before allowances and bonuses;
             "casual loading": an extra 25% of the hourly rate.
    s.36(1)  annual leave accrues at at least 2 days per month.
    s.68     the only deductions an employer may make; s.79(c) makes any
             other deduction an offence.
    s.74     a normal day is 8 hours; unpaid extra hours may be agreed only
             while the week stays within 48 hours.
    s.75(1)  1.5x the hourly rate for hours over 48 in a WEEK.
    s.75(2)  a watchperson or guard: 1.5x for hours over 60 in a week.
    s.75(3)  2x the hourly rate on a public holiday or weekly rest day that is
             not part of the normal working week.
    s.75(4)  hourly rate = basic wages for the month / 208 (/ 240 for a
             watchperson or guard). 208 is a DIVISOR, not an overtime trigger.
  SI No. 48 of 2023, General Order (in force 1 January 2024), Schedule:
    minimum basic pay by category (para 1), transport K200 (para 3), lunch
    K180 (para 4), tool K150 (para 6), housing 30% of basic (para 8), night
    work 18:00-06:00 at a 15% shift differential; exclusions in para 2(2).
  SI No. 50 of 2023, Shop Workers Order (in force 1 January 2024), Schedule:
    categories (para 1), night differential (para 2), transport (para 4),
    lunch (para 5), tool (para 8), housing (para 10), part-time and casual
    pay in proportion to 208 hours a month (para 12(4)), pay statement
    contents (para 12(5)); exclusions in para 2(2).
  SI No. 3 of 2025, Truck and Bus Drivers (Amendment) Order: minimum monthly
    basic K4,000 (truck) and K3,000 (bus). The principal Order (SI No. 106 of
    2020) is not in the library, so its other terms are not checked.
  National Pension Scheme Act, Cap. 256, s.14: contributions on the member's
    EARNINGS at the prescribed percentage (5% employee + 5% employer), with a
    maximum insurable earnings ceiling NAPSA sets each year.
  National Health Insurance Act No. 2 of 2018, s.15: contributions at the
    prescribed percentage (1% employee + 1% employer of BASIC pay).
  ZRA Practice Note No. 1 of 2026, Table 13: PAYE bands for the 2026 charge
    year, K61,200 / K85,200 / K110,400 a year, i.e. K5,100 / K7,100 / K9,200 a
    month at 0% / 20% / 30% / 37%.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

EC = "Employment Code Act No. 3 of 2019"
NAPSA_RATE = 0.05          # employee share; the employer pays the same again
NHIMA_RATE = 0.01          # employee share of basic pay; employer matches
HOURS_DIVISOR = 208        # s.75(4)(a)
GUARD_HOURS_DIVISOR = 240  # s.75(4)(b)
WEEKLY_OT_TRIGGER = 48     # s.75(1)
GUARD_WEEKLY_OT_TRIGGER = 60  # s.75(2)
CASUAL_LOADING = 0.25      # s.3 "casual loading"
NIGHT_DIFFERENTIAL = 0.15  # SI 48/2023 and SI 50/2023
HOUSING_RATE = 0.30
TRANSPORT_ALLOWANCE = 200.0
LUNCH_ALLOWANCE = 180.0
TOOL_ALLOWANCE = 150.0
TOLERANCE = 1.00           # kwacha: rounding on a real payslip is not a breach

PAYE_YEAR = 2026
PAYE_SOURCE = "ZRA Practice Note No. 1 of 2026, Table 13 (2026 charge year)"
# (upper bound of the monthly band, rate). The last band has no upper bound.
PAYE_MONTHLY_BANDS = ((5_100.0, 0.0), (7_100.0, 0.20), (9_200.0, 0.30), (None, 0.37))


@dataclass(frozen=True)
class Category:
    order: str
    number: int
    hourly: float
    monthly: float
    occupations: tuple[str, ...]


# Text of each Schedule, para 1, as printed. The monthly figures are the
# printed ones; they are not always hourly x 208 to the ngwee.
GENERAL = "general"
SHOP = "shop_workers"
CATEGORIES: tuple[Category, ...] = (
    Category(GENERAL, 1, 7.15, 1_487.00, (
        "general worker", "cleaner", "helper", "food preparation assistant",
        "garbage collector", "recycling collector", "handy person", "handyman",
        "office orderly", "service station attendant")),
    Category(GENERAL, 2, 7.15, 1_487.00, ("security guard", "guard", "watchman", "watchperson")),
    Category(GENERAL, 3, 8.66, 1_801.98, (
        "assistant sales person", "assistant salesperson", "packer", "book binder",
        "bookbinder", "printer", "print finisher")),
    Category(GENERAL, 4, 10.19, 2_119.23, ("driver", "pump attendant", "craft certificate")),
    Category(GENERAL, 5, 11.04, 2_296.89, ("typist", "receptionist", "telephonist")),
    Category(GENERAL, 6, 12.89, 2_680.92, ("sales person", "salesperson")),
    Category(GENERAL, 7, 13.76, 2_861.36, ("qualified clerk", "clerk", "machine operator")),
    Category(SHOP, 1, 7.15, 1_487.00, (
        "baling", "bailing", "wrapping", "delivery vehicle assistant", "general worker",
        "handy person", "handyman", "office orderly", "cleaner", "helper",
        "security guard", "guard")),
    Category(SHOP, 2, 8.66, 1_801.98, (
        "lift operator", "motor cycle", "motorcycle", "scooter", "three wheel", "driver",
        "sales assistant", "waiter", "waitress", "bartender", "barman",
        "hair dresser", "hairdresser", "beautician", "ticket clerk", "shopkeeper",
        "packer")),
    Category(SHOP, 3, 10.19, 2_121.35, (
        "assistant bicycle assembler", "assistant dispatch clerk", "ordinary driving licence", "driver",
        "ordinary licence", "shelf packer", "shoe repairer", "tailor's assistant",
        "tailors assistant", "window dresser's assistant")),
    Category(SHOP, 4, 11.04, 2_296.89, (
        "bicycle assembler", "check out operator", "checkout operator", "till operator",
        "heavy duty", "public service vehicle", "psv", "driver", "telephone operator",
        "phone repairer", "typist", "picture framer")),
    Category(SHOP, 5, 12.89, 2_680.92, (
        "dispatch clerk", "order person", "sales person", "salesperson", "tailor",
        "upholsterer")),
    Category(SHOP, 6, 13.76, 2_861.50, (
        "audio visual", "audio-visual", "machine operator", "watch repairer")),
    Category(SHOP, 7, 15.10, 3_142.26, ("supervisor", "window dresser", "stenographer", "cashier")),
)

ORDER_LABEL = {
    GENERAL: "SI No. 48 of 2023 (General Order)",
    SHOP: "SI No. 50 of 2023 (Shop Workers Order)",
    "truck_driver": "SI No. 3 of 2025 (Truck and Bus Drivers)",
    "bus_driver": "SI No. 3 of 2025 (Truck and Bus Drivers)",
}
# Schedule paragraphs, per Order.
PARA = {
    GENERAL: {"basic": "para 1", "transport": "para 3", "lunch": "para 4", "tool": "para 6",
              "housing": "para 8", "night": "night work paragraph", "exempt": "para 2(2)"},
    SHOP: {"basic": "para 1", "night": "para 2", "transport": "para 4", "lunch": "para 5",
           "tool": "para 8", "housing": "para 10", "exempt": "para 2(2)", "part_time": "para 12(4)"},
}
DRIVER_MINIMUM = {"truck_driver": 4_000.0, "bus_driver": 3_000.0}

# Where a job title alone cannot pick the category.
AMBIGUITY_HINTS = {
    (SHOP, "driver"): ("Category 2 drives a motor cycle, scooter or three-wheeler; Category 3 holds an "
                       "ordinary driving licence; Category 4 a heavy duty or public service vehicle licence."),
}

EXEMPTIONS = {
    "management": "an employee in management",
    "collective_agreement": "a unionised employee whose pay is set by collective bargaining",
    "civil_service": "an employee in the civil service",
    "local_authority": "an employee of a local authority",
}

EMPLOYEE_TYPES = {"full_time", "guard", "part_time", "casual"}

# s.68(1) in brief, for the deductions check.
S68 = ("Lawful only if s.68(1) allows it: tax or another deduction under a written law, a statutory or "
       "agreed fund contribution, an agreed salary advance, a third-party debt the employee consented to in "
       "writing or a court ordered, an overpayment made in error, or damage, loss or a shortage proved "
       "through the disciplinary process. Any other deduction is an offence (s.79(c)).")


@dataclass
class Line:
    item: str
    status: str   # required | contractual | conditional | needs_input | deduction | employer | info
    basis: str
    amount: float | None = None
    formula: str = ""
    note: str = ""


@dataclass
class Check:
    item: str
    paid: float | None
    required: float | None
    difference: float | None   # paid - required
    status: str                # ok | underpaid | over_deducted | check
    basis: str = ""
    note: str = ""


@dataclass
class Flag:
    severity: str  # breach | check | info
    message: str
    basis: str = ""


@dataclass
class PayrollResult:
    kind: str = "payroll"
    currency: str = "ZMW"
    employee_type: str = "full_time"
    wage_order: str = "none"
    wage_order_label: str = ""
    category: int | None = None
    category_occupations: list[str] = field(default_factory=list)
    order_applies: str = "no"          # yes | conditional | no | unknown
    minimum_basic: float | None = None
    minimum_hourly: float | None = None
    basic_paid: float = 0.0
    required_basic: float = 0.0
    hourly_rate: float = 0.0
    hourly_rate_formula: str = ""
    overtime_hours: float = 0.0
    earnings: list[dict] = field(default_factory=list)
    deductions: list[dict] = field(default_factory=list)
    employer_costs: list[dict] = field(default_factory=list)
    minimum_gross: float = 0.0
    total_deductions: float = 0.0
    net_pay: float = 0.0
    audit: list[dict] = field(default_factory=list)
    total_underpaid: float = 0.0
    total_if_unpaid: float = 0.0   # also counting required lines the payslip does not show
    flags: list[dict] = field(default_factory=list)
    needs_input: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    disclaimer: str = ""


def _money(x: float) -> float:
    return round(float(x) + 1e-9, 2)


def _k(x: float) -> str:
    return f"K{x:,.2f}"


def _rate(x: float) -> str:
    """An hourly rate, with enough decimals to reproduce the arithmetic."""
    return _k(x) if abs(x - round(x, 2)) < 1e-6 else f"K{x:,.4f}"


def _norm(s: str | None) -> str:
    return re.sub(r"[\s-]+", "_", (s or "").strip().lower())


def paye_monthly(taxable: float) -> float:
    """PAYE on one month's taxable emoluments, 2026 monthly bands."""
    tax, lower = 0.0, 0.0
    for upper, rate in PAYE_MONTHLY_BANDS:
        top = taxable if upper is None else min(taxable, upper)
        if top > lower:
            tax += (top - lower) * rate
        if upper is None or taxable <= upper:
            break
        lower = upper
    return _money(tax)


def match_category(order: str, occupation: str | None) -> list[Category]:
    """Categories in `order` whose listed occupations appear in `occupation`.

    The longest matching phrase wins, so "assistant dispatch clerk" is not
    read as "dispatch clerk" and "shelf packer" is not read as "packer".
    """
    occ = " " + re.sub(r"[^a-z' ]+", " ", (occupation or "").lower()) + " "
    best: dict[int, int] = {}
    for c in CATEGORIES:
        if c.order != order:
            continue
        for phrase in c.occupations:
            if f" {phrase} " in occ or (len(phrase) > 6 and phrase in occ):
                best[c.number] = max(best.get(c.number, 0), len(phrase))
    if not best:
        return []
    top = max(best.values())
    return [c for c in CATEGORIES if c.order == order and best.get(c.number) == top]


def _category(order: str, number: int) -> Category | None:
    return next((c for c in CATEGORIES if c.order == order and c.number == number), None)


_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7}


def _category_number(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = re.sub(r"(?i)category|cat\.?", "", str(value)).strip().lower()
    if text.isdigit():
        return int(text)
    return _ROMAN.get(text)


def _overtime_hours(weekly_hours, overtime_hours, trigger) -> tuple[float, str]:
    if weekly_hours:
        weeks = [max(0.0, float(h or 0)) for h in weekly_hours]
        ot = sum(max(0.0, h - trigger) for h in weeks)
        detail = ", ".join(f"{h:g}" for h in weeks)
        return ot, f"weeks of {detail} hours; hours over {trigger:g} in each week"
    if overtime_hours:
        return max(0.0, float(overtime_hours)), "overtime hours as given"
    return 0.0, ""


def calculate_payroll(
    *,
    monthly_basic_pay: float,
    employee_type: str = "full_time",
    wage_order: str = "none",
    category: int | str | None = None,
    occupation: str | None = None,
    order_exemption: str | None = None,
    hours_worked_in_month: float | None = None,
    weekly_hours: list[float] | None = None,
    overtime_hours: float | None = None,
    weekly_overtime_threshold: float | None = None,
    rest_day_or_holiday_hours: float | None = None,
    night_hours: float | None = None,
    accommodation_provided: bool | None = None,
    lives_beyond_3km: bool | None = None,
    transport_provided: bool | None = None,
    free_meals_provided: bool | None = None,
    provides_own_tools: bool | None = None,
    other_allowances: float | None = None,
    other_earnings: float | None = None,
    napsa_ceiling: float | None = None,
    payslip: dict | None = None,
    today: date | None = None,
) -> dict:
    """One month's statutory minimum pay, deductions and (optionally) a payslip check."""
    etype = _norm(employee_type) or "full_time"
    if etype in {"watchperson", "security_guard", "watchman"}:
        etype = "guard"
    if etype not in EMPLOYEE_TYPES:
        etype = "full_time"
    order = _norm(wage_order) or "none"
    if order in {"shop", "shop_worker", "shops"}:
        order = SHOP
    if order in {"general_order", "si_48"}:
        order = GENERAL
    exemption = _norm(order_exemption) if order_exemption else ""
    if exemption in {"none", "no"}:
        exemption = ""
    basic_paid = max(0.0, float(monthly_basic_pay or 0))
    slip = {k: v for k, v in (payslip or {}).items() if v is not None}
    flags: list[Flag] = []
    needs: list[str] = []
    assumptions: list[str] = []
    earnings: list[Line] = []
    res = PayrollResult(employee_type=etype, wage_order=order, wage_order_label=ORDER_LABEL.get(order, ""),
                        basic_paid=_money(basic_paid))

    # 1) Which wage order, which category, and whether it binds.
    cat: Category | None = None
    minimum_basic: float | None = None
    minimum_hourly: float | None = None
    order_status = "no"
    if order in (GENERAL, SHOP):
        number = _category_number(category)
        if number:
            cat = _category(order, number)
        if not cat and not occupation and etype == "guard":
            cat = _category(order, 2 if order == GENERAL else 1)
        if not cat and occupation:
            found = match_category(order, occupation)
            if len(found) == 1:
                cat = found[0]
                assumptions.append(f'Category {cat.number} chosen from the occupation "{occupation}". '
                                   "Confirm it against the Schedule.")
            elif found:
                needs.append("Wage order category")
                hint = next((h for (o, word), h in AMBIGUITY_HINTS.items()
                             if o == order and word in occupation.lower()), "")
                flags.append(Flag("check", (
                    f'"{occupation}" fits more than one category of {ORDER_LABEL[order]}: '
                    + (hint or ", ".join(f"Category {c.number} ({', '.join(c.occupations[:4])})" for c in found) + ".")
                    + " Say which applies."), f"{ORDER_LABEL[order]}, Schedule, para 1"))
        if not cat and "Wage order category" not in needs:
            needs.append("Wage order category")
            flags.append(Flag("check", f"Give the employee's category under {ORDER_LABEL[order]} "
                              "(or the job title) to check the minimum wage.",
                              f"{ORDER_LABEL[order]}, Schedule, para 1"))
        if cat:
            minimum_basic, minimum_hourly = cat.monthly, cat.hourly
            res.category = cat.number
            res.category_occupations = list(cat.occupations)
            order_status = "yes"
        else:
            order_status = "unknown"
        if exemption in EXEMPTIONS:
            order_status = "no"
            minimum_basic = minimum_hourly = None
            flags.append(Flag("info", f"The Order does not apply to {EXEMPTIONS[exemption]}, so its minimum "
                              "wage, allowances and night differential are not checked. The Employment Code "
                              "floors (overtime, rest days, leave, deductions) still apply.",
                              f"{ORDER_LABEL[order]}, {PARA[order]['exempt']}"))
    elif order in DRIVER_MINIMUM:
        minimum_basic = DRIVER_MINIMUM[order]
        order_status = "yes"
        flags.append(Flag("info", "Only the minimum basic pay is checked. The driver's other conditions "
                          "(allowances, subsistence) are in the Truck and Bus Drivers Order, SI No. 106 of "
                          "2020, which Levy's library does not hold; cross-border subsistence is at least "
                          "US$30 a night where no accommodation or sleeping cab is provided.",
                          "SI No. 3 of 2025, paras 4 and 15"))
    elif order == "domestic":
        order_status = "unknown"
        flags.append(Flag("check", "Domestic workers have their own minimum wage order (2023), which Levy's "
                          "library does not hold, so the minimum wage cannot be checked here. The "
                          "Employment Code floors below still apply.", "SI No. 48 of 2023, para 2(2)(c)"))

    part_time = etype in {"part_time", "casual"}
    hours_in_month = float(hours_worked_in_month or 0)
    if part_time and not hours_in_month:
        needs.append("Hours worked in the month")

    # 2) The basic the law requires for this month.
    floor_basis = "Contract of employment"
    if minimum_basic is not None and order_status == "yes":
        if part_time and hours_in_month:
            floor = minimum_basic * hours_in_month / HOURS_DIVISOR
            floor_formula = f"{_k(minimum_basic)} x {hours_in_month:g} / {HOURS_DIVISOR} hours"
            floor_basis = (f"{ORDER_LABEL[order]}, Schedule, {PARA[order]['part_time']}" if order == SHOP
                           else f"{ORDER_LABEL.get(order, '')}, Schedule, para 1, prorated over 208 hours")
        else:
            floor, floor_formula = minimum_basic, f"Category {res.category} minimum" if cat else "Order minimum"
            floor_basis = f"{ORDER_LABEL[order]}, Schedule, {PARA[order]['basic']}" if order in PARA \
                else ORDER_LABEL[order]
        required_basic = max(basic_paid, floor)
        if basic_paid + TOLERANCE < floor:
            flags.append(Flag("breach", f"Basic pay of {_k(basic_paid)} is below the minimum of {_k(floor)} "
                              f"({floor_formula}). The shortfall is {_k(floor - basic_paid)} a month, and every "
                              "rate built on basic pay is understated with it.", floor_basis))
    else:
        required_basic = basic_paid
    res.minimum_basic = _money(minimum_basic) if minimum_basic is not None else None
    res.minimum_hourly = minimum_hourly

    # Para 2(2)(f): an employee whose conditions beat the Order's gross pay is outside it.
    if order in (GENERAL, SHOP) and order_status == "yes" and not part_time and minimum_basic:
        order_gross = minimum_basic + LUNCH_ALLOWANCE + TRANSPORT_ALLOWANCE + HOUSING_RATE * minimum_basic
        package = basic_paid + float(other_allowances or 0) + sum(
            float(slip.get(k) or 0) for k in ("housing_allowance", "transport_allowance", "lunch_allowance"))
        if basic_paid >= minimum_basic and package > order_gross + TOLERANCE:
            order_status = "conditional"
            flags.append(Flag("check", (
                f"This employee's package ({_k(package)} a month before overtime) is above the Order's own "
                f"gross pay ({_k(order_gross)}: minimum basic, 30% housing, transport and lunch). The Order "
                "excludes 'an employee whose conditions of service are more favourable than the applicable "
                "gross pay in this Order', so its allowances and night differential may not bind here. "
                "They are shown as conditional. The Employment Code floors still apply."),
                f"{ORDER_LABEL[order]}, {PARA[order]['exempt']}(f)"))
    res.order_applies = order_status

    # 3) Hourly rate: s.75(4), never below the Order's hourly minimum.
    if part_time:
        divisor_text = "part-time / casual"
        base = (required_basic / hours_in_month) if hours_in_month else 0.0
        hourly = max(base, minimum_hourly or 0.0) if order_status == "yes" else base
        res.hourly_rate_formula = (f"basic {_k(required_basic)} / {hours_in_month:g} hours worked"
                                   if hours_in_month else "needs the hours worked")
    else:
        divisor = GUARD_HOURS_DIVISOR if etype == "guard" else HOURS_DIVISOR
        divisor_text = f"/ {divisor}"
        hourly = required_basic / divisor if divisor else 0.0
        res.hourly_rate_formula = f"basic {_k(required_basic)} / {divisor} hours (s.75(4)({'b' if etype == 'guard' else 'a'}))"
        if order_status == "yes" and minimum_hourly and minimum_hourly > hourly + 1e-9:
            res.hourly_rate_formula += f", raised to the Order's hourly minimum {_k(minimum_hourly)}"
            hourly = minimum_hourly
    res.hourly_rate = round(hourly, 4)
    res.required_basic = _money(required_basic)
    if not part_time and basic_paid and required_basic > basic_paid + TOLERANCE:
        employer_rate = basic_paid / (GUARD_HOURS_DIVISOR if etype == "guard" else HOURS_DIVISOR)
        flags.append(Flag("breach", (
            f"An hourly rate built on the basic actually paid ({_rate(employer_rate)}) is below the statutory "
            f"{_rate(hourly)}. Overtime, rest-day and night pay must use {_rate(hourly)}."), f"{EC}, s.75(4)"))

    earnings.append(Line("Basic pay", "required", floor_basis, _money(required_basic),
                         f"{_k(basic_paid)} paid" + (f", raised to the {_k(required_basic)} minimum" if required_basic > basic_paid + TOLERANCE else "")))
    if etype == "casual" and hourly and hours_in_month:
        loading = hourly * CASUAL_LOADING * hours_in_month
        earnings.append(Line("Casual loading", "required", f"{EC}, s.3 ('casual employee', 'casual loading')",
                             _money(loading), f"25% x {_rate(hourly)} x {hours_in_month:g} hours"))

    # 4) Overtime: per WEEK, over 48 hours (60 for a guard). Never per month.
    statutory_trigger = GUARD_WEEKLY_OT_TRIGGER if etype == "guard" else WEEKLY_OT_TRIGGER
    trigger = statutory_trigger
    if weekly_overtime_threshold:
        asked = float(weekly_overtime_threshold)
        if asked > statutory_trigger:
            flags.append(Flag("breach", (
                f"An overtime threshold of {asked:g} hours a week is not lawful: s.75 requires 1.5x pay for "
                f"every hour over {statutory_trigger} in a week, and a contract cannot raise that. Levy used "
                f"{statutory_trigger}."), f"{EC}, s.75({'2' if etype == 'guard' else '1'})"))
        else:
            trigger = asked
    ot_hours, ot_detail = _overtime_hours(weekly_hours, overtime_hours, trigger)
    res.overtime_hours = round(ot_hours, 2)
    if ot_hours:
        earnings.append(Line("Overtime", "required", f"{EC}, s.75({'2' if etype == 'guard' else '1'}) and s.75(4)",
                             _money(ot_hours * 1.5 * hourly),
                             f"{ot_hours:g} h x 1.5 x {_rate(hourly)} ({ot_detail})",
                             "208 is the divisor that turns monthly basic into an hourly rate (s.75(4)). "
                             "It is not an overtime threshold: overtime is counted week by week."))
    elif weekly_hours is None and overtime_hours is None and not part_time:
        assumptions.append("No weekly hours were given, so no overtime is included. Overtime is every hour "
                           f"over {statutory_trigger} in a week (s.75), whatever the monthly total.")

    if rest_day_or_holiday_hours:
        h = float(rest_day_or_holiday_hours)
        earnings.append(Line("Public holiday / rest day work", "required", f"{EC}, s.75(3)",
                             _money(h * 2 * hourly), f"{h:g} h x 2 x {_rate(hourly)}",
                             "For work on a holiday or rest day outside the normal working week."))

    # 5) Order-specific pay: night differential and allowances.
    order_items = order in (GENERAL, SHOP) and order_status in ("yes", "conditional")
    order_line = "required" if order_status == "yes" else "conditional"
    if night_hours:
        h = float(night_hours)
        if order_items:
            earnings.append(Line("Night shift differential", order_line,
                                 f"{ORDER_LABEL[order]}, Schedule, {PARA[order]['night']}",
                                 _money(h * NIGHT_DIFFERENTIAL * hourly), f"{h:g} h x 15% x {_rate(hourly)}",
                                 "Due for every hour worked between 18:00 and 06:00. The Order says the employee "
                                 "'shall be paid' it: days off in lieu do not discharge it, and it applies even "
                                 "where night work is the normal pattern of the job."))
        else:
            flags.append(Flag("info", "No wage order with a night differential was applied, so night hours "
                              "carry no statutory premium here. Check the contract or collective agreement."))

    def allowance(name, key, amount, applies, formula, unknown_note):
        basis = f"{ORDER_LABEL[order]}, Schedule, {PARA[order][key]}"
        if applies is True:
            earnings.append(Line(name, order_line, basis, _money(amount), formula))
        elif applies is None:
            earnings.append(Line(name, "needs_input", basis, _money(amount), formula, unknown_note))
            needs.append(name)

    if order_items:
        if part_time:
            flags.append(Flag("check", "The Orders do not say how the monthly allowances apply to part-time or "
                              "casual work; they are not computed here."))
        else:
            allowance("Housing allowance", "housing", HOUSING_RATE * required_basic,
                      None if accommodation_provided is None else not accommodation_provided,
                      f"30% x {_k(required_basic)}", "Owed unless the employer accommodates the employee.")
            beyond = lives_beyond_3km
            transport = (None if beyond is None or (beyond and transport_provided is None)
                         else bool(beyond and not transport_provided))
            allowance("Transport allowance", "transport", TRANSPORT_ALLOWANCE, transport, "K200 a month",
                      "Owed where the employee lives more than 3 km from work and no transport is provided.")
            allowance("Lunch allowance", "lunch", LUNCH_ALLOWANCE,
                      None if free_meals_provided is None else not free_meals_provided, "K180 a month",
                      "Owed unless free, wholesome and adequate meals are provided.")
            if provides_own_tools:
                allowance("Tool allowance", "tool", TOOL_ALLOWANCE, True, "K150 a month", "")

    if other_allowances:
        earnings.append(Line("Other allowances (contract)", "contractual", "Contract of employment",
                             _money(other_allowances), "as given"))
    if other_earnings:
        earnings.append(Line("Bonus / commission / other earnings", "contractual", "Contract of employment",
                             _money(other_earnings), "as given"))

    # 6) Gross, deductions, net.
    counted = [li for li in earnings if li.status in ("required", "contractual")]
    gross = sum(li.amount or 0 for li in counted)
    conditional_total = sum(li.amount or 0 for li in earnings if li.status == "conditional")
    if conditional_total:
        assumptions.append(f"Gross excludes {_k(conditional_total)} of conditional Order items; if the Order "
                           f"applies, gross is {_k(gross + conditional_total)}.")
    napsa_base = gross if not napsa_ceiling else min(gross, float(napsa_ceiling))
    napsa = _money(NAPSA_RATE * napsa_base)
    nhima = _money(NHIMA_RATE * required_basic)
    paye = paye_monthly(gross)
    deductions = [
        Line("NAPSA (employee 5%)", "deduction", "National Pension Scheme Act, Cap. 256, s.14", napsa,
             f"5% x {_k(napsa_base)} " + ("(earnings capped at the ceiling given)" if napsa_ceiling and gross > float(napsa_ceiling)
                                          else "(gross earnings)"),
             "On earnings, not basic pay." + ("" if napsa_ceiling else
             " NAPSA caps contributions at a maximum insurable earnings figure it sets each year; "
             "on a high salary, check that figure.")),
        Line("NHIMA (employee 1%)", "deduction", "National Health Insurance Act No. 2 of 2018, s.15", nhima,
             f"1% x basic {_k(required_basic)}", "On basic pay, not gross."),
        Line("PAYE", "deduction", PAYE_SOURCE, paye, f"2026 monthly bands on {_k(gross)}",
             "No pension relief applied. Bands change with each Budget."),
    ]
    other_deds = [d for d in (slip.get("other_deductions") or []) if isinstance(d, dict)]
    for d in other_deds:
        deductions.append(Line(str(d.get("label") or "Other deduction"), "deduction", f"{EC}, s.68",
                               _money(d.get("amount") or 0), "from the payslip", S68))
    total_ded = sum(li.amount or 0 for li in deductions)
    employer_costs = [
        Line("NAPSA (employer 5%)", "employer", "National Pension Scheme Act, Cap. 256, s.14", napsa,
             f"5% x {_k(napsa_base)}", "Paid by the employer on top of pay; may not be recovered from the employee (s.14(3))."),
        Line("NHIMA (employer 1%)", "employer", "National Health Insurance Act No. 2 of 2018, s.15", nhima,
             f"1% x basic {_k(required_basic)}"),
    ]

    # 7) Payslip check.
    audit: list[Check] = []
    underpaid = 0.0
    unconfirmed: list[tuple[str, float]] = []   # required lines the payslip passed over
    if slip:
        req = {li.item: li for li in earnings}

        def compare(label, slip_key, line_name):
            nonlocal underpaid, unconfirmed
            li = req.get(line_name)
            paid = slip.get(slip_key)
            if li is None and paid is None:
                return
            need = li.amount if li else 0.0
            paid_f = float(paid) if paid is not None else 0.0
            diff = _money(paid_f - (need or 0))
            if li and li.status in ("conditional", "needs_input"):
                status, note = "check", li.note or "Owed only if the condition applies."
            elif paid is None:
                # Absent from what was passed is not the same as K0 on the payslip.
                status, note, diff = "check", (f"Not on the payslip given. If it was not paid, "
                                               f"{_k(need or 0)} is owed."), None
                if need:
                    unconfirmed.append((label, need))
            elif diff < -TOLERANCE:
                status, note = "underpaid", f"Short by {_k(-diff)}."
                underpaid += -diff
            else:
                status, note = "ok", ""
            audit.append(Check(label, _money(paid_f) if paid is not None else None, need, diff, status,
                               li.basis if li else "", note))

        compare("Basic pay", "basic", "Basic pay")
        compare("Overtime", "overtime", "Overtime")
        compare("Holiday / rest day pay", "holiday_pay", "Public holiday / rest day work")
        compare("Night shift differential", "night_differential", "Night shift differential")
        compare("Housing allowance", "housing_allowance", "Housing allowance")
        compare("Transport allowance", "transport_allowance", "Transport allowance")
        compare("Lunch allowance", "lunch_allowance", "Lunch allowance")
        compare("Tool allowance", "tool_allowance", "Tool allowance")

        def compare_deduction(label, key, computed, basis, wrong_basis_hint):
            nonlocal underpaid
            if key not in slip:
                return
            taken = float(slip[key])
            diff = _money(taken - computed)
            if diff > TOLERANCE:
                status, note = "over_deducted", f"{_k(diff)} more than the law requires. {wrong_basis_hint}"
                underpaid += diff
            elif diff < -TOLERANCE:
                status, note = "check", f"{_k(-diff)} less than computed: the employer may be under-remitting. {wrong_basis_hint}"
            else:
                status, note = "ok", ""
            audit.append(Check(label, _money(taken), computed, diff, status, basis, note))

        # Deductions follow what was actually paid: an underpaid gross is caught
        # on the earnings lines, not again as an "under-remitted" deduction.
        slip_gross = float(slip["gross"]) if "gross" in slip else gross
        slip_basic = float(slip["basic"]) if "basic" in slip else required_basic
        napsa_slip_base = slip_gross if not napsa_ceiling else min(slip_gross, float(napsa_ceiling))
        compare_deduction("NAPSA deducted", "napsa", _money(NAPSA_RATE * napsa_slip_base),
                          "National Pension Scheme Act, Cap. 256, s.14",
                          f"NAPSA is 5% of gross earnings ({_k(napsa_slip_base)}), not of basic pay.")
        compare_deduction("NHIMA deducted", "nhima", _money(NHIMA_RATE * slip_basic),
                          "National Health Insurance Act No. 2 of 2018, s.15",
                          f"NHIMA is 1% of basic pay ({_k(slip_basic)}), not of gross.")
        if "paye" in slip:
            taken = float(slip["paye"])
            paye_slip = paye_monthly(slip_gross)
            diff = _money(taken - paye_slip)
            audit.append(Check("PAYE deducted", _money(taken), paye_slip, diff,
                               "ok" if abs(diff) <= TOLERANCE else "check", PAYE_SOURCE,
                               "" if abs(diff) <= TOLERANCE else
                               f"Differs from the 2026 bands on a gross of {_k(slip_gross)}. Pension relief or "
                               "other taxable benefits can explain a difference; confirm with ZRA."))
        for d in other_deds:
            audit.append(Check(str(d.get("label") or "Other deduction"), _money(d.get("amount") or 0), None, None,
                               "check", f"{EC}, s.68 and s.79(c)", S68))
        if "gross" in slip:
            parts = sum(float(slip.get(k) or 0) for k in (
                "basic", "overtime", "holiday_pay", "night_differential", "housing_allowance",
                "transport_allowance", "lunch_allowance", "tool_allowance", "other_earnings"))
            if parts and abs(parts - float(slip["gross"])) > TOLERANCE:
                flags.append(Flag("check", f"The payslip's gross ({_k(float(slip['gross']))}) does not equal the "
                                  f"sum of its own components ({_k(parts)})."))
        if "gross" in slip and "net" in slip:
            taken_total = sum(float(slip.get(k) or 0) for k in ("napsa", "nhima", "paye")) + sum(
                float(d.get("amount") or 0) for d in other_deds)
            if abs(float(slip["gross"]) - taken_total - float(slip["net"])) > TOLERANCE:
                flags.append(Flag("check", f"The payslip's net ({_k(float(slip['net']))}) is not its gross less "
                                  f"its deductions ({_k(float(slip['gross']) - taken_total)})."))
        if "net" in slip:
            audit.append(Check("Net pay", _money(float(slip["net"])), _money(gross - total_ded),
                               _money(float(slip["net"]) - (gross - total_ded)),
                               "ok" if float(slip["net"]) + TOLERANCE >= gross - total_ded else "check",
                               "", "Follows from the lines above."))
        if unconfirmed:
            # QA 8 Oct 2026: a payslip with no overtime or night line was passed
            # without zeros, and the answer led with the confirmed K155.78 when
            # K826 was owed. Give the whole figure alongside the confirmed one.
            extra = sum(v for _, v in unconfirmed)
            flags.insert(0, Flag("check", (
                f"Lines not on the payslip ({', '.join(n.lower() for n, _ in unconfirmed)}) are owed if they were not "
                f"paid: {_k(extra)} more, {_k(underpaid + extra)} in all for the month."), f"{EC}, Part IV"))
        if underpaid > TOLERANCE:
            flags.insert(0, Flag("breach", f"This payslip is {_k(underpaid)} short of what the law requires "
                                 "for the month (underpayments plus over-deductions)" +
                                 (", before the lines it does not show." if unconfirmed else "."), f"{EC}, Part IV"))

    # 8) Standing notes.
    assumptions += [
        "A full calendar month of work, unless hours worked were given.",
        f"Hourly rate {_rate(hourly)} ({res.hourly_rate_formula}).",
        "Annual leave accrues at at least 2 days per month of service (s.36(1)).",
    ]
    if order in (GENERAL, SHOP):
        assumptions.append(f"Rates are those of {ORDER_LABEL[order]}, in force from 1 January 2024. If a later "
                           "order has been gazetted, its figures replace these.")
    year = (today or date.today()).year
    if year > PAYE_YEAR:
        flags.append(Flag("check", f"PAYE uses the {PAYE_YEAR} bands; confirm the {year} bands with ZRA."))

    res.earnings = [asdict(li) for li in earnings]
    res.deductions = [asdict(li) for li in deductions]
    res.employer_costs = [asdict(li) for li in employer_costs]
    res.minimum_gross = _money(gross)
    res.total_deductions = _money(total_ded)
    res.net_pay = _money(gross - total_ded)
    res.audit = [asdict(c) for c in audit]
    res.total_underpaid = _money(underpaid)
    res.total_if_unpaid = _money(underpaid + sum(v for _, v in unconfirmed))
    order_rank = {"breach": 0, "check": 1, "info": 2}
    res.flags = [asdict(f) for f in sorted(flags, key=lambda f: order_rank.get(f.severity, 3))]
    res.needs_input = needs
    res.assumptions = assumptions
    res.disclaimer = ("Statutory minimums from the Employment Code Act 2019, the 2023 minimum wage orders, the "
                      "NAPSA and NHIMA Acts and ZRA's 2026 bands, applied to the figures given. A contract or "
                      "collective agreement can only improve on them. Legal information, not legal advice.")
    return asdict(res)
