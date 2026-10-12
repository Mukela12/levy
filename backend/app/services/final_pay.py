"""Final pay when employment ends, and gratuity accrued to a date.

Week of 6 Oct 2026: an HR user spent ten turns on the final pay of an employee
who worked 1 to 15 January and resigned with immediate effect, then asked for
a citation to justify leaving those 15 days unpaid. Levy rightly found none and
found the notice set-off, but cited s.69 for it: a section that only bars
deductions taken for giving or keeping a job. Here each piece is code with the
provision it rests on, so the set-off, its cap and the tax cannot drift.

Read from the text in Levy's library:

  Employment Code Act No. 3 of 2019
    s.3      "long-term contract": over twelve months and renewable, or a task
             over a specified period. "gratuity": paid on the expiry of a
             long-term contract, on the basic pay earned during the term.
    s.36(5)  accumulated leave is paid in wages when a contract ends.
    s.38(6)  medical discharge: three months' basic pay for each completed year.
    s.51(1)  summary dismissal: wages and other accrued benefits up to the date
             of dismissal.
    s.53(2)  notice where the contract is silent: 24 hours (a contract of up to
             a month), 14 days (up to three months), 30 days (longer).
    s.53(4)  an employer who gives no notice pays the notice-period wages.
    s.53(5)  where an employee refuses to work the notice period, the employer
             may deduct, from money due on termination, what the employee
             would have earned in it. A deduction under a written law, so
             s.68(1)(a) allows it.
    s.53(6)  an employer ending a long-term contract pays prorated gratuity.
    s.54(1)  severance pay: (b) and (c) a fixed-duration contract, at least 25%
             of basic pay earned to the effective date of termination; (d)
             redundancy and (e) death in service, two months' basic pay for each
             year served. s.54(3): not for casual, temporary, long-term-contract
             or probationary employees.
    s.55(3)  redundancy: at least two months' pay for every year served.
    s.66     when wages fall due; s.66(3) accumulated wages are payable on
             demand when either party ends the contract.
    s.68(1)  the only deductions an employer may make; s.79(c) makes any other
             deduction an offence.
    s.69     NOT a general rule on deductions: it bars deductions taken as a
             reward for providing or keeping a job.
    s.73(1)  gratuity of at least 25% of basic pay earned, at the end of a
             long-term contract; s.73(2) prorated when the contract is
             terminated in accordance with the Code.
  ZRA Practice Note No. 1 of 2026
    para 38  gratuity, redundancy pay, severance pay and salary in lieu of
             notice are exempt pension benefits; salary and commutation of
             accrued leave days are taxed under the PAYE bands.
    para 39  payments on medical discharge are exempt.
    para 40  an advance against gratuity to someone still employed is exempt.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from .payroll import EC, NAPSA_CEILING, NAPSA_RATE, NHIMA_RATE, _k, _money, paye_bands_for, paye_monthly

GRATUITY_RATE = 0.25
PN = "ZRA Practice Note No. 1 of 2026"
SETOFF_NOTE = (
    "s.53(5): where an employee refuses to work the notice period, the employer may deduct, from money due on "
    "termination, what the employee would have earned in it. That is a deduction under a written law, so "
    "s.68(1)(a) allows it; s.79(c) makes any deduction outside s.68 an offence. s.69 is not the basis: it "
    "only bars deductions taken as a reward for providing or keeping a job. The set-off cannot exceed the money "
    "due on termination; anything beyond that is a debt the employer must claim, not a deduction.")

REASONS = {"resignation", "dismissal", "summary_dismissal", "redundancy", "end_of_contract",
           "medical_discharge", "death", "mutual_agreement"}
_REASON_ALIASES = {
    "end_of_fixed_term": "end_of_contract", "expiry": "end_of_contract", "contract_expiry": "end_of_contract",
    "contract_end": "end_of_contract", "dismissal_with_notice": "dismissal", "unfair_dismissal": "dismissal",
    "termination": "dismissal", "retrenchment": "redundancy", "resigned": "resignation",
    "resignation_without_notice": "resignation",
}
CONTRACT_TYPES = {"long_term", "fixed_term", "permanent", "casual", "temporary", "probation", "unspecified"}
_CONTRACT_ALIASES = {"long": "long_term", "fixed": "fixed_term", "fixed_duration": "fixed_term",
                     "short_term": "fixed_term", "indefinite": "permanent", "probationary": "probation"}
# Employment ended by the employer, for notice and gratuity.
EMPLOYER_ENDED = {"dismissal", "redundancy", "medical_discharge"}

# Employment dates as people type them: Zambia writes day-first.
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %B %Y", "%d %b %Y",
                 "%B %d, %Y", "%b %d, %Y", "%d/%m/%y")


def parse_date(raw) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", str(raw).strip().replace(",", ", ").replace("  ", " "), flags=re.I)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _day(d: date) -> str:
    return f"{d.day} {calendar.month_abbr[d.month]} {d.year}"


def _months(start: date, end: date):
    """(year, month, days in [start, end], days in that month) for each month touched."""
    cur = date(start.year, start.month, 1)
    while cur <= end:
        dim = calendar.monthrange(cur.year, cur.month)[1]
        lo, hi = max(start, cur), min(end, date(cur.year, cur.month, dim))
        if hi >= lo:
            yield cur.year, cur.month, (hi - lo).days + 1, dim
        cur = date(cur.year + cur.month // 12, cur.month % 12 + 1, 1)


def earned(monthly: float, start: date, end: date) -> tuple[float, float, str]:
    """Pay earned at `monthly` from start to end inclusive: (amount, months, description).

    Each calendar month counts in full when covered, otherwise by the share of
    its days covered, which is how a month's pay is usually prorated.
    """
    full, parts, months = 0, [], 0.0
    for y, m, days, dim in _months(start, end):
        if days == dim:
            full += 1
            months += 1
        else:
            months += days / dim
            parts.append(f"{days}/{dim} of {calendar.month_abbr[m]} {y}")
    bits = ([f"{full} full month{'s' if full != 1 else ''}"] if full else []) + parts
    return monthly * months, months, " + ".join(bits) or "no days"


def _completed_years(start: date | None, end: date) -> float | None:
    if not start or end < start:
        return None
    return round(((end - start).days + 1) / 365.25, 4)


@dataclass
class Item:
    item: str
    group: str      # due | deduction | setoff | employer | info
    status: str     # owed | conditional | contested | needs_input | not_applicable | deduction | setoff | employer | info
    basis: str
    amount: float | None = None
    formula: str = ""
    note: str = ""
    taxable: bool | None = None


@dataclass
class Flag:
    severity: str   # breach | check | info
    message: str
    basis: str = ""


@dataclass
class FinalPayResult:
    kind: str = "final_pay"
    currency: str = "ZMW"
    termination_reason: str = ""
    contract_type: str = ""
    termination_date: str = ""
    monthly_basic_pay: float = 0.0
    monthly_allowances: float = 0.0
    lines: list[dict] = field(default_factory=list)
    total_due: float = 0.0
    total_conditional: float = 0.0
    taxable_total: float = 0.0
    total_deductions: float = 0.0
    net_before_setoff: float = 0.0
    setoff: float = 0.0
    net_payable: float = 0.0
    balance_claimable: float = 0.0
    net_if_conditional_paid: float = 0.0
    flags: list[dict] = field(default_factory=list)
    needs_input: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    disclaimer: str = ""


def _norm(value: str | None, aliases: dict, allowed: set, default: str) -> str:
    v = re.sub(r"[\s-]+", "_", (value or "").strip().lower())
    v = aliases.get(v, v)
    return v if v in allowed else default


def _gratuity_status(ctype: str, reason: str, notice_walkout: bool) -> tuple[str, str, str]:
    """(status, basis, note) for gratuity or fixed-term severance on this ending."""
    if ctype == "long_term":
        basis = f"{EC}, s.73" + (" and s.53(6)" if reason in EMPLOYER_ENDED else "")
        if reason in ("end_of_contract",) or reason in EMPLOYER_ENDED or reason == "mutual_agreement":
            return "owed", basis, ""
        if reason == "resignation":
            if notice_walkout:
                return "contested", basis, (
                    "s.73(2) prorates gratuity when a contract 'is terminated in accordance with this Code'. A "
                    "resignation on the contract's notice terms is such a termination; one with no notice worked is "
                    "argued both ways, which the notice set-off already answers in money. Check the contract.")
            return "owed", basis, "Prorated under s.73(2): a resignation on the contract's terms ends it in accordance with the Code."
        if reason == "summary_dismissal":
            return "conditional", f"{EC}, s.51(1) and s.73(2)", (
                "s.51(1) pays wages 'and other accrued benefits' up to the date of dismissal. Whether accrued "
                "gratuity is one of them depends on the contract; it is shown as conditional.")
        if reason == "death":
            return "conditional", f"{EC}, s.52(7)(b) and s.73(2)", (
                "The contract expires on death (s.52(7)(b)); prorated gratuity is then usually paid to the estate. "
                "Check the contract.")
    if ctype == "fixed_term":
        basis = f"{EC}, s.54(1)(b)-(c)"
        note = ("Severance for a fixed-duration contract: a gratuity of at least 25% of basic pay earned to the "
                "effective date of termination, or the social security retirement benefits instead (s.54(1)(b)).")
        if reason == "resignation":
            return ("contested" if notice_walkout else "conditional"), basis, note + (
                " s.54(1)(c) does not say who must end the contract; on a resignation it is argued both ways.")
        if reason == "summary_dismissal":
            return "conditional", basis, note
        if reason == "redundancy":
            return "conditional", basis, note + (
                " On redundancy, s.54(1)(d) sets the severance (two months' basic pay a year); this gratuity is the "
                "other reading of s.54(1), not an addition to it.")
        return "owed", basis, note
    return "not_applicable", f"{EC}, s.73", ""


def calculate_final_pay(
    *,
    monthly_basic_pay: float,
    termination_reason: str,
    termination_date,
    monthly_allowances: float | None = None,
    contract_type: str | None = "unspecified",
    employment_start_date=None,
    contract_start_date=None,
    paid_through_date=None,
    accrued_leave_days: float | None = None,
    notice_months: float | None = None,
    notice_days: float | None = None,
    employer_gave_notice: bool | None = None,
    employee_worked_notice: bool | None = None,
    gratuity_rate: float | None = None,
    gratuity_paid_through=None,
    gratuity_advanced: float | None = None,
    basic_earned_in_period: float | None = None,
    outstanding_advance: float | None = None,
    other_deductions: list[dict] | None = None,
    napsa_ceiling: float | None = None,
    today: date | None = None,
) -> dict:
    """Everything payable when a job ends, what may come off it, and the net."""
    end = parse_date(termination_date)
    if end is None:
        raise ValueError(f"Could not read the last day of employment {termination_date!r}. "
                         "Use DD/MM/YYYY or '15 January 2026'.")
    reason = _norm(termination_reason, _REASON_ALIASES, REASONS, "")
    if not reason:
        raise ValueError(f"Unknown termination reason {termination_reason!r}. Use one of: {', '.join(sorted(REASONS))}.")
    ctype = _norm(contract_type, _CONTRACT_ALIASES, CONTRACT_TYPES, "unspecified")
    basic = max(0.0, float(monthly_basic_pay or 0))
    allowances = max(0.0, float(monthly_allowances or 0))
    wages = basic + allowances
    rate = float(gratuity_rate) if gratuity_rate else GRATUITY_RATE
    started = parse_date(employment_start_date)
    contract_started = parse_date(contract_start_date)
    service_years = _completed_years(started or contract_started, end)

    lines: list[Item] = []
    flags: list[Flag] = []
    needs: list[str] = []
    assumptions: list[str] = []
    res = FinalPayResult(termination_reason=reason, contract_type=ctype, termination_date=end.isoformat(),
                         monthly_basic_pay=_money(basic), monthly_allowances=_money(allowances))

    # 1) Wages for the days since the last pay day.
    paid_through = parse_date(paid_through_date)
    if paid_through is None:
        paid_through = date(end.year, end.month, 1) - timedelta(days=1)
        assumptions.append(f"Wages are taken as paid up to {_day(paid_through)}, the end of the month before the "
                           "last day. If they were paid to another date, say so.")
    salary_basic = salary = 0.0
    if paid_through < end:
        start = paid_through + timedelta(days=1)
        salary_basic, months, desc = earned(basic, start, end)
        salary = salary_basic + earned(allowances, start, end)[0]
        lines.append(Item(
            "Wages for days worked", "due", "owed", f"{EC}, s.66; contract of employment", _money(salary),
            f"{_k(wages)} a month x {desc} ({_day(start)} to {_day(end)})",
            (f"Basic {_k(salary_basic)}" + (f" + allowances {_k(salary - salary_basic)}" if allowances else "") +
             ". Earned and due: days worked are not forfeited by leaving, with or without notice."),
            taxable=True))
    elif paid_through > end:
        flags.append(Flag("info", f"Wages were paid up to {_day(paid_through)}, after the last day ({_day(end)}). "
                          "An overpayment made in error may be recovered (s.68(1)(e)).", f"{EC}, s.68(1)(e)"))

    # 2) Accrued leave.
    daily_basic = basic * 12 / 365
    if accrued_leave_days is not None and float(accrued_leave_days) > 0:
        days = float(accrued_leave_days)
        lines.append(Item("Accrued leave", "due", "owed", f"{EC}, s.36(5)", _money(days * daily_basic),
                          f"{days:g} days x {_k(daily_basic)} a day (basic x 12 / 365)",
                          "Taxable: commutation of accrued leave is an emolument (" + PN + ", para 38).", taxable=True))
    elif accrued_leave_days is None and reason != "death":
        needs.append("Accrued leave days")
        lines.append(Item("Accrued leave", "due", "needs_input", f"{EC}, s.36(5)", None, "",
                          "Untaken leave is paid when the contract ends. Leave accrues at at least 2 days a month (s.36(1)); give the days still owed."))

    # 3) Notice: pay in lieu owed by the employer, or a set-off against money due.
    def notice_amount() -> tuple[float | None, str]:
        if notice_months:
            return wages * float(notice_months), f"{float(notice_months):g} month{'s' if float(notice_months) != 1 else ''} x {_k(wages)}"
        if notice_days:
            return wages * 12 / 365 * float(notice_days), f"{float(notice_days):g} days x {_k(wages * 12 / 365)} a day"
        if service_years is None:
            return None, ""
        months_served = service_years * 12
        d = 1 if months_served <= 1 else 14 if months_served <= 3 else 30
        return wages * 12 / 365 * d, f"{d} days under s.53(2) x {_k(wages * 12 / 365)} a day"

    walkout = reason == "resignation" and employee_worked_notice is False
    setoff_wanted = 0.0
    setoff_formula = ""
    if reason in EMPLOYER_ENDED:
        if employer_gave_notice is False:
            amt, how = notice_amount()
            if amt is None:
                needs.append("Notice period")
            lines.append(Item("Pay in lieu of notice", "due", "owed" if amt is not None else "needs_input",
                              f"{EC}, s.53(4)", _money(amt) if amt is not None else None, how,
                              f"Exempt from tax (salary in lieu of notice, {PN}, para 38).", taxable=False))
        elif employer_gave_notice is None:
            amt, how = notice_amount()
            lines.append(Item("Pay in lieu of notice", "due", "conditional", f"{EC}, s.53(4)",
                              _money(amt) if amt is not None else None, how,
                              "Owed only if the employer did not give the notice period. Exempt from tax.", taxable=False))
    elif reason == "resignation":
        if employee_worked_notice is False:
            amt, how = notice_amount()
            if amt is None:
                needs.append("Notice period")
            else:
                setoff_wanted, setoff_formula = amt, how
        elif employee_worked_notice is None:
            needs.append("Whether the employee worked the notice period")
    elif reason == "summary_dismissal":
        lines.append(Item("Notice", "info", "not_applicable", f"{EC}, s.53(1) and s.51(1)", None, "",
                          "No notice or pay in lieu where the dismissal is for misconduct that justifies it; wages "
                          "and other accrued benefits are still due up to the date of dismissal."))

    # 4) Gratuity (long-term) or fixed-term severance.
    gstart = parse_date(gratuity_paid_through)
    gstart = gstart + timedelta(days=1) if gstart else (contract_started or (started if ctype in ("long_term", "fixed_term") else None))
    advanced = max(0.0, float(gratuity_advanced or 0))
    if ctype in ("long_term", "fixed_term", "unspecified"):
        status, basis, note = _gratuity_status(ctype if ctype != "unspecified" else "long_term", reason, walkout)
        label = "Gratuity" if ctype != "fixed_term" else "Severance gratuity (fixed-term contract)"
        if ctype == "unspecified":
            status = "conditional"
            note = ("Statutory gratuity attaches to a long-term contract (over twelve months, s.3) and severance "
                    "gratuity to a fixed-duration one (s.54(1)(b)-(c)); a permanent contract has neither. Confirm "
                    "the contract type.")
            needs.append("Contract type")
        if basic_earned_in_period is not None:
            base, desc = float(basic_earned_in_period), "basic pay earned in the period, as given"
        elif gstart and gstart <= end:
            base, _, desc = earned(basic, gstart, end)
            desc = f"{_k(basic)} x {desc}, {_day(gstart)} to {_day(end)}"
        else:
            base, desc = None, ""
        if base is None:
            if gstart and gstart > end:
                lines.append(Item(label, "due", "info", basis, 0.0, "",
                                  f"Gratuity was already paid up to {_day(gstart - timedelta(days=1))}."))
            else:
                needs.append("Contract start date (or the date gratuity was last paid up to)")
                lines.append(Item(label, "due", "needs_input", basis, None, "",
                                  "Give the date the contract (or the unpaid gratuity period) started."))
        else:
            amount = max(0.0, rate * base - advanced)
            formula = f"{rate * 100:g}% x {_k(base)} basic earned ({desc})"
            if advanced:
                formula += f", less {_k(advanced)} already advanced"
            lines.append(Item(label, "due", status, basis, _money(amount), formula,
                              (note + " " if note else "") + f"Exempt from tax ({PN}, para 38).", taxable=False))
            if gratuity_paid_through:
                flags.append(Flag("info", (
                    f"Gratuity runs to the last day of employment ({_day(end)}), not to the last month end: it is "
                    "computed on basic pay earned 'as at the effective date of termination' (s.54(1)(c)) or "
                    "prorated 'in accordance with the period of employment' (s.73(2))."), f"{EC}, s.73(2)"))
    elif ctype == "permanent":
        lines.append(Item("Gratuity", "due", "not_applicable", f"{EC}, s.73", None, "",
                          "Statutory gratuity attaches to long-term contracts. A permanent contract has none unless the "
                          "contract or a collective agreement provides it."))

    # 5) Severance for redundancy, death and medical discharge.
    years = service_years
    if reason in ("redundancy", "death", "medical_discharge"):
        if years is None:
            needs.append("Employment start date")
        if reason == "redundancy":
            if years is not None:
                status = "contested" if years < 1 else ("conditional" if ctype == "long_term" else "owed")
                note = ("Exempt from tax (" + PN + ", para 38)." +
                        (" Under one completed year, whether s.55(3) prorates a part-year is not settled." if years < 1 else "") +
                        (" s.54(3) excludes long-term contracts from s.54 severance; check whether s.55 pay is due "
                         "alongside the prorated gratuity." if ctype == "long_term" else ""))
                lines.append(Item("Redundancy pay", "due", status, f"{EC}, s.54(1)(d) and s.55(3)",
                                  _money(2 * basic * years), f"2 months x {_k(basic)} x {years:g} years served",
                                  note, taxable=False))
        elif reason == "death" and ctype != "long_term":
            if years is not None:
                lines.append(Item("Severance pay (death in service)", "due", "owed", f"{EC}, s.54(1)(e) and s.54(2)",
                                  _money(2 * basic * years), f"2 months x {_k(basic)} x {years:g} years served",
                                  "Paid to the estate. Exempt from tax (" + PN + ", para 38).", taxable=False))
        elif reason == "medical_discharge" and years is not None:
            lines.append(Item("Medical discharge lump sum", "due", "owed", f"{EC}, s.38(6)",
                              _money(3 * basic * int(years)), f"3 months x {_k(basic)} x {int(years)} completed years",
                              f"In addition to other accrued benefits. Exempt from tax ({PN}, para 39).", taxable=False))

    # 6) Deductions from what is paid.
    owed = [li for li in lines if li.group == "due" and li.status == "owed"]
    maybe = [li for li in lines if li.group == "due" and li.status in ("conditional", "contested")]
    taxable = sum(li.amount or 0 for li in owed if li.taxable)
    napsa_ceiling = napsa_ceiling or NAPSA_CEILING.get(end.year)
    napsa_base = salary if not napsa_ceiling else min(salary, float(napsa_ceiling))
    bands, paye_source, bands_year = paye_bands_for(end.year)
    deductions = [
        Item("PAYE", "deduction", "deduction", f"{paye_source}; {PN}, para 38", paye_monthly(taxable, bands),
             f"{bands_year} monthly bands on {_k(taxable)} taxable (wages and leave pay)",
             "Gratuity, redundancy and severance pay and pay in lieu of notice are exempt. Treated as one month's "
             "emoluments; a cumulative PAYE adjustment for the year can differ."),
    ]
    if salary:
        deductions += [
            Item("NAPSA (employee 5%)", "deduction", "deduction", "National Pension Scheme Act, Cap. 256, s.14",
                 _money(NAPSA_RATE * napsa_base), f"5% x {_k(napsa_base)} wages for days worked",
                 "Taken on the wages for days worked. Whether NAPSA treats leave commutation as earnings is not "
                 "settled in Levy's library; confirm with NAPSA."),
            Item("NHIMA (employee 1%)", "deduction", "deduction", "National Health Insurance Act No. 2 of 2018, s.15",
                 _money(NHIMA_RATE * salary_basic), f"1% x {_k(salary_basic)} basic for days worked"),
        ]
    if outstanding_advance:
        deductions.append(Item("Salary advance recovered", "deduction", "deduction", f"{EC}, s.68(1)(c)",
                               _money(outstanding_advance), "as given",
                               "Only on the terms the employer and employee agreed for the advance."))
    for d in other_deductions or []:
        if isinstance(d, dict) and d.get("amount"):
            deductions.append(Item(str(d.get("label") or "Other deduction"), "deduction", "check",
                                   f"{EC}, s.68 and s.79(c)", _money(d["amount"]), "as given",
                                   "Lawful only if s.68(1) allows it; any other deduction is an offence (s.79(c))."))
    lines += deductions
    employer = []
    if salary:
        employer = [
            Item("NAPSA (employer 5%)", "employer", "employer", "National Pension Scheme Act, Cap. 256, s.14",
                 _money(NAPSA_RATE * napsa_base), f"5% x {_k(napsa_base)}"),
            Item("NHIMA (employer 1%)", "employer", "employer", "National Health Insurance Act No. 2 of 2018, s.15",
                 _money(NHIMA_RATE * salary_basic), f"1% x {_k(salary_basic)}"),
        ]
    lines += employer

    total_due = sum(li.amount or 0 for li in owed)
    total_maybe = sum(li.amount or 0 for li in maybe)
    total_ded = sum(li.amount or 0 for li in deductions)
    net_before = max(0.0, total_due - total_ded)

    # 7) The notice set-off, capped at what is due.
    setoff = min(setoff_wanted, net_before)
    if setoff_wanted:
        lines.append(Item("Notice not worked (set-off)", "setoff", "setoff", f"{EC}, s.53(5) and s.68(1)(a)",
                          _money(setoff),
                          f"{setoff_formula} = {_k(setoff_wanted)}" + (f", capped at the {_k(net_before)} due" if setoff < setoff_wanted else ""),
                          SETOFF_NOTE))
        flags.append(Flag("check", (
            "Whether s.53(5) reaches an employee who resigns without notice, rather than one who refuses to work a "
            "notice period the employer gave, is not settled by its text. A contract clause requiring notice or pay "
            "in lieu gives the employer a claim, but taking it from final pay still needs s.53(5): s.68(1) lists no "
            "other route."), f"{EC}, s.53(5)"))
        flags.insert(0, Flag("info", (
            "The days worked are earned wages and go into the final pay. Leaving them off is lawful only as part of "
            f"the notice set-off, and only up to the money due ({_k(net_before)} here)."), f"{EC}, s.53(5) and s.66"))
    balance = setoff_wanted - setoff
    if balance > 0.005:
        flags.append(Flag("info", f"The set-off exceeds the money due by {_k(balance)}. That balance is a debt the "
                          "employer can claim; it cannot be deducted from anything else (s.68, s.79(c)).", f"{EC}, s.68"))

    # Paying the conditional items too: the set-off absorbs them first.
    if total_maybe:
        net_before_all = max(0.0, total_due + total_maybe - total_ded)
        res.net_if_conditional_paid = _money(net_before_all - min(setoff_wanted, net_before_all))
        assumptions.append(f"{_k(total_maybe)} of items are conditional or contested and are left out of the net; "
                           f"if they are paid, the net is {_k(res.net_if_conditional_paid)}.")
    else:
        res.net_if_conditional_paid = _money(net_before - setoff)

    if wages and (salary or setoff_wanted):
        assumptions.append(f"Monthly wages {_k(wages)} = basic {_k(basic)}" + (f" + allowances {_k(allowances)}" if allowances else "") +
                           ". Wages for part of a month are prorated by calendar days; gratuity and leave use basic pay only.")
    if accrued_leave_days:
        assumptions.append("Leave is valued at basic x 12 / 365 a day. An employer that divides by 26 working days pays more.")
    if end.year > bands_year:
        flags.append(Flag("check", f"PAYE uses the {bands_year} bands; confirm the {end.year} bands with ZRA."))
    if reason != "death":
        flags.append(Flag("info", (
            "Give the employee ZRA Form ITF/P13(2), Particulars of Employee Leaving, showing the year's payroll "
            "details, so the next employer deducts PAYE correctly; without it the next employer may deduct more."),
            "ZRA, Tax information: 'What should I do if I leave employment?'"))

    res.lines = [asdict(li) for li in lines]
    res.total_due = _money(total_due)
    res.total_conditional = _money(total_maybe)
    res.taxable_total = _money(taxable)
    res.total_deductions = _money(total_ded)
    res.net_before_setoff = _money(net_before)
    res.setoff = _money(setoff)
    res.net_payable = _money(net_before - setoff)
    res.balance_claimable = _money(max(0.0, balance))
    rank = {"breach": 0, "check": 1, "info": 2}
    res.flags = [asdict(f) for f in sorted(flags, key=lambda f: rank.get(f.severity, 3))]
    res.needs_input = list(dict.fromkeys(needs))
    res.assumptions = assumptions
    res.disclaimer = ("Statutory minimums from the Employment Code Act 2019 and ZRA's 2026 rules, applied to the "
                      "figures given. A contract or collective agreement can improve on them. Legal information, "
                      "not legal advice.")
    return asdict(res)


@dataclass
class GratuityResult:
    kind: str = "gratuity"
    currency: str = "ZMW"
    contract_type: str = ""
    monthly_basic_pay: float = 0.0
    rate: float = GRATUITY_RATE
    period_start: str = ""
    as_of: str = ""
    months: float = 0.0
    basic_earned: float = 0.0
    accrued: float = 0.0
    advanced: float = 0.0
    balance: float = 0.0
    projected_at_end: float | None = None
    lines: list[dict] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)
    needs_input: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    disclaimer: str = ""


def calculate_gratuity(
    *,
    monthly_basic_pay: float,
    contract_start_date=None,
    as_of_date=None,
    contract_end_date=None,
    contract_type: str | None = "long_term",
    gratuity_rate: float | None = None,
    gratuity_paid_through=None,
    gratuity_advanced: float | None = None,
    basic_earned_in_period: float | None = None,
    today: date | None = None,
) -> dict:
    """Gratuity accrued from the contract start (or last payment) to a date."""
    ctype = _norm(contract_type, _CONTRACT_ALIASES, CONTRACT_TYPES, "long_term")
    basic = max(0.0, float(monthly_basic_pay or 0))
    rate = float(gratuity_rate) if gratuity_rate else GRATUITY_RATE
    as_of = parse_date(as_of_date) or (today or date.today())
    paid = parse_date(gratuity_paid_through)
    start = paid + timedelta(days=1) if paid else parse_date(contract_start_date)
    res = GratuityResult(contract_type=ctype, monthly_basic_pay=_money(basic), rate=rate, as_of=as_of.isoformat())
    flags: list[Flag] = []
    lines: list[Item] = []
    basis = f"{EC}, s.73" if ctype != "fixed_term" else f"{EC}, s.54(1)(b)-(c)"

    if ctype in ("permanent", "casual", "temporary", "probation"):
        flags.append(Flag("check", (
            "Statutory gratuity attaches to a long-term contract (s.73) or a fixed-duration one (s.54(1)(b)-(c)). "
            f"A {ctype} contract has none unless the contract or a collective agreement provides it; the figure "
            "below is what a 25% contractual gratuity would come to."), basis))
    if start is None:
        res.needs_input = ["Contract start date (or the date gratuity was last paid up to)"]
        res.flags = [asdict(f) for f in flags]
        res.disclaimer = "Gratuity needs the date the contract, or the unpaid period, started."
        return asdict(res)
    if as_of < start:
        raise ValueError(f"The date {as_of.isoformat()} is before the gratuity period starts ({start.isoformat()}).")

    if basic_earned_in_period is not None:
        base, months, desc = float(basic_earned_in_period), 0.0, "basic pay earned, as given"
    else:
        base, months, desc = earned(basic, start, as_of)
        desc = f"{_k(basic)} x {desc}"
    accrued = rate * base
    advanced = max(0.0, float(gratuity_advanced or 0))
    lines.append(Item("Basic pay earned", "due", "info", basis, _money(base),
                      f"{desc} ({_day(start)} to {_day(as_of)})"))
    lines.append(Item("Gratuity accrued", "due", "owed", basis, _money(accrued),
                      f"{rate * 100:g}% x {_k(base)}", f"Exempt from tax ({PN}, para 38)."))
    if advanced:
        lines.append(Item("Already advanced", "setoff", "setoff", f"{PN}, para 40", _money(advanced), "as given",
                          "Advances against gratuity reduce what is paid at the end."))
    end = parse_date(contract_end_date)
    if end and end > as_of and basic_earned_in_period is None:
        full, _, _ = earned(basic, start, end)
        res.projected_at_end = _money(rate * full - advanced)
        flags.append(Flag("info", f"At the end of the contract ({_day(end)}), on the same basic pay, the gratuity "
                          f"would be {_k(rate * full)}" + (f" ({_k(rate * full - advanced)} after advances)." if advanced else "."), basis))
    flags.append(Flag("info", (
        "Paying gratuity before the contract ends is not required, and the Code does not bar it: s.73(1) fixes when "
        "it falls due. Pay it as an advance against the gratuity, agreed in writing, and deduct it from the final "
        f"figure. ZRA treats an advance against gratuity to an employee still in employment as exempt ({PN}, "
        "para 40). An advance is not a salary advance under s.68(1)(c), so it is settled against the gratuity, not "
        "recovered from wages."), f"{EC}, s.73(1); {PN}, para 40"))

    res.period_start = start.isoformat()
    res.months = round(months, 4)
    res.basic_earned = _money(base)
    res.accrued = _money(accrued)
    res.advanced = _money(advanced)
    res.balance = _money(max(0.0, accrued - advanced))
    res.lines = [asdict(li) for li in lines]
    res.flags = [asdict(f) for f in flags]
    res.assumptions = [f"Basic pay of {_k(basic)} a month throughout; partial months prorated by calendar days. If "
                       "basic pay changed, give the total basic earned in the period."] if basic_earned_in_period is None else []
    res.disclaimer = ("At least 25% of basic pay earned (s.73(1)); a contract may give more. Legal information, not "
                      "legal advice.")
    return asdict(res)
