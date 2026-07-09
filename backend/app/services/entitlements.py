"""Deterministic Zambian employment entitlement calculator.

Grounded in the Employment Code Act No. 3 of 2019 (verified against the
ingested Act text):

  s.36     Annual leave — at least 2 days/month; on termination the employer
           pays wages for accrued, untaken leave (s.36(4)-(5)).
  s.53     Notice of termination — where the contract is silent: 24h (<=1mo),
           14 days (1-3mo), 30 days (>3mo). An employer who skips notice pays
           the wages the employee would have earned in the notice period
           (s.53(4)). Only the *employer* owes this; a resigning employee does
           not receive pay in lieu.
  s.54     Severance pay — fixed-term contract: a gratuity of >=25% of basic
           pay earned (s.54(b)-(c)); redundancy or death in service: 2 months'
           basic pay for each year served (s.54(d)-(e)).
  s.55     Redundancy — minimum 2 months' pay for every year served.
  s.73     Gratuity — end of a long-term contract: >=25% of basic pay earned
           during the contract, prorated if terminated mid-contract.
  s.38(6)  Medical discharge — lump sum of >=3 months' basic pay for each
           completed year of service, plus other accrued benefits.

The arithmetic is deterministic Python (no model maths). Every figure carries
its statutory basis and the formula used. Items that are fact-dependent or
legally contested (notably gratuity on resignation) are flagged, never
asserted as a fixed entitlement.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

# NAPSA + NHIMA statutory contribution rates (employer share), used only to
# give an INDICATIVE figure of what an employer that never remitted may owe the
# scheme — this is not money paid to the employee.
NAPSA_EMPLOYER_RATE = 0.05  # 5% of earnings (capped in practice)
NHIMA_EMPLOYER_RATE = 0.01  # 1% of basic pay

# Termination reasons the calculator understands.
EMPLOYER_INITIATED = {
    "dismissal_with_notice",
    "summary_dismissal",
    "redundancy",
    "unfair_dismissal",
    "medical_discharge",
}


@dataclass
class LineItem:
    item: str
    status: str  # owed | conditional | contested | not_applicable | compliance | needs_input
    basis: str   # statutory citation
    amount: float | None = None  # ZMW, None when it can't be computed yet
    formula: str = ""
    note: str = ""


@dataclass
class EntitlementResult:
    currency: str = "ZMW"
    monthly_basic_pay: float = 0.0
    years_of_service: float = 0.0
    termination_reason: str = ""
    contract_type: str = ""
    daily_rate: float = 0.0
    line_items: list[dict] = field(default_factory=list)
    total_clearly_owed: float = 0.0
    needs_input: list[str] = field(default_factory=list)
    contested: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    disclaimer: str = ""


def _money(x: float) -> float:
    return round(float(x), 2)


def calculate_entitlements(
    *,
    monthly_basic_pay: float,
    years_of_service: float,
    termination_reason: str,
    contract_type: str = "unspecified",
    notice_given_by_employer: bool | None = None,
    accrued_leave_days: float | None = None,
    unpaid_salary_amount: float | None = None,
    napsa_contributed: bool | None = None,
    nhima_contributed: bool | None = None,
) -> dict:
    """Compute an itemized Zambian employment-exit entitlement estimate.

    Returns a plain dict (see EntitlementResult) ready to serialize to the
    frontend card and to feed back to the model as a tool result.
    """
    reason = (termination_reason or "").strip().lower().replace(" ", "_")
    ctype = (contract_type or "unspecified").strip().lower().replace(" ", "_")
    pay = max(0.0, float(monthly_basic_pay or 0))
    years = max(0.0, float(years_of_service or 0))

    # Transparent daily rate: annual basic / 365. Stated as an assumption so the
    # user can reconcile it with an employer that divides by 26 working days.
    daily_rate = _money(pay * 12 / 365) if pay else 0.0

    items: list[LineItem] = []
    assumptions: list[str] = [
        f"Daily rate computed as annual basic pay / 365 = K{daily_rate:,.2f}. "
        "Some employers use a 26-working-day divisor, which yields a higher daily rate.",
        "Figures use basic pay only; allowances and contractual top-ups are excluded.",
    ]

    # 1) Salary arrears — always owed if any wages are outstanding.
    if unpaid_salary_amount and unpaid_salary_amount > 0:
        items.append(LineItem(
            item="Outstanding salary / wage arrears",
            status="owed",
            basis="Wages due under the contract; Employment Code Act 2019, Part IV",
            amount=_money(unpaid_salary_amount),
            formula="As provided",
        ))
    else:
        items.append(LineItem(
            item="Outstanding salary / wage arrears",
            status="needs_input",
            basis="Wages due under the contract",
            note="Provide any unpaid salary up to the last day worked.",
        ))

    # 2) Accrued leave pay (s.36) — owed on exit regardless of how it ended.
    if accrued_leave_days is not None and accrued_leave_days > 0:
        items.append(LineItem(
            item="Accrued (untaken) leave pay",
            status="owed",
            basis="Employment Code Act 2019, s.36(4)-(5)",
            amount=_money(accrued_leave_days * daily_rate),
            formula=f"{accrued_leave_days:g} untaken days x K{daily_rate:,.2f}/day",
        ))
    else:
        items.append(LineItem(
            item="Accrued (untaken) leave pay",
            status="needs_input",
            basis="Employment Code Act 2019, s.36(4)-(5)",
            note=(
                "Owed on exit for any untaken leave (accrues at 2 days/month). "
                "Provide the number of untaken leave days to compute this."
            ),
        ))

    # 3) Notice / pay in lieu of notice (s.53) — only the employer owes this.
    notice_days = 30 if years * 12 > 3 else (14 if years * 12 > 1 else 1)
    if reason == "resignation":
        items.append(LineItem(
            item="Pay in lieu of notice",
            status="not_applicable",
            basis="Employment Code Act 2019, s.53",
            note="On resignation the employee gives notice; no pay in lieu is owed to the employee.",
        ))
    elif reason == "summary_dismissal":
        items.append(LineItem(
            item="Pay in lieu of notice",
            status="not_applicable",
            basis="Employment Code Act 2019, s.53(1)",
            note="Summary dismissal for gross misconduct does not attract notice or pay in lieu (if the misconduct is proven).",
        ))
    elif reason in EMPLOYER_INITIATED or reason in {"end_of_fixed_term", "mutual_agreement"}:
        if notice_given_by_employer is False:
            items.append(LineItem(
                item="Pay in lieu of notice",
                status="owed",
                basis="Employment Code Act 2019, s.53(2),(4)",
                amount=_money(notice_days * daily_rate),
                formula=f"{notice_days} days notice x K{daily_rate:,.2f}/day",
            ))
        else:
            items.append(LineItem(
                item="Pay in lieu of notice",
                status="conditional",
                basis="Employment Code Act 2019, s.53(2),(4)",
                amount=_money(notice_days * daily_rate),
                formula=f"{notice_days} days x K{daily_rate:,.2f}/day (only if proper notice was NOT given)",
                note="Owed only if the employer failed to give the required notice period.",
            ))

    # 4) Severance pay (s.54) + redundancy (s.55) + medical (s.38(6)).
    if reason == "redundancy":
        items.append(LineItem(
            item="Redundancy / severance pay",
            status="owed",
            basis="Employment Code Act 2019, s.54(d) & s.55(3)",
            amount=_money(2 * pay * years),
            formula=f"2 months x K{pay:,.2f} x {years:g} years served",
        ))
    elif reason == "death":
        items.append(LineItem(
            item="Severance pay (death in service)",
            status="owed",
            basis="Employment Code Act 2019, s.54(e)",
            amount=_money(2 * pay * years),
            formula=f"2 months x K{pay:,.2f} x {years:g} years served (payable to the estate)",
        ))
    elif reason == "medical_discharge":
        items.append(LineItem(
            item="Medical discharge lump sum",
            status="owed",
            basis="Employment Code Act 2019, s.38(6)",
            amount=_money(3 * pay * int(years)),
            formula=f"3 months x K{pay:,.2f} x {int(years)} completed years",
            note="In addition to other accrued benefits.",
        ))
    elif reason in {"end_of_fixed_term"} and ctype in {"fixed_term", "long_term"}:
        items.append(LineItem(
            item="Severance pay (fixed-term gratuity)",
            status="owed",
            basis="Employment Code Act 2019, s.54(b)-(c)",
            amount=_money(0.25 * pay * 12 * years),
            formula=f"25% x basic earned (K{pay:,.2f} x 12 x {years:g} years)",
            note="For a fixed-term contract this is the statutory minimum gratuity; the social-security alternative under s.54(b) may apply instead.",
        ))
    else:
        items.append(LineItem(
            item="Severance / redundancy pay",
            status="not_applicable",
            basis="Employment Code Act 2019, s.54-55",
            note="Severance and redundancy pay arise on redundancy, death, medical discharge or end of a fixed term. They do not arise on ordinary resignation or dismissal.",
        ))

    # 5) Gratuity (s.73) — long-term contracts. Contested on resignation.
    gratuity_amount = _money(0.25 * pay * 12 * years)
    if ctype == "long_term" and reason not in {"resignation", "summary_dismissal"}:
        items.append(LineItem(
            item="Gratuity (long-term contract)",
            status="owed",
            basis="Employment Code Act 2019, s.73",
            amount=gratuity_amount,
            formula=f"25% x basic earned (K{pay:,.2f} x 12 x {years:g} years), prorated",
        ))
    elif reason == "resignation":
        items.append(LineItem(
            item="Gratuity (long-term contract)",
            status="contested",
            basis="Employment Code Act 2019, s.73",
            amount=gratuity_amount,
            formula=f"If payable: 25% x basic earned (~K{gratuity_amount:,.2f})",
            note="Whether gratuity is payable on resignation (rather than employer-initiated termination) is contested and turns on the contract terms and case law. Treat the figure as indicative only.",
        ))
    elif ctype in {"permanent", "unspecified"}:
        items.append(LineItem(
            item="Gratuity (long-term contract)",
            status="conditional",
            basis="Employment Code Act 2019, s.73",
            amount=gratuity_amount,
            formula=f"If a long-term contract: 25% x basic earned (~K{gratuity_amount:,.2f})",
            note="s.73 gratuity attaches to long-term contracts. Confirm the contract type; a permanent/indefinite contract may not attract statutory gratuity.",
        ))

    # 6) NAPSA / NHIMA — compliance, not a payout to the employee.
    if napsa_contributed is False:
        indicative = _money(NAPSA_EMPLOYER_RATE * pay * 12 * years)
        items.append(LineItem(
            item="NAPSA (unremitted contributions)",
            status="compliance",
            basis="National Pension Scheme Act",
            amount=indicative,
            formula=f"Indicative employer share ~5% x K{pay:,.2f} x 12 x {years:g} years",
            note="This is owed by the employer to NAPSA (with penalties), not paid to the employee directly. The employee can report non-remittance to NAPSA; unremitted contributions plus penalties are recoverable.",
        ))
    if nhima_contributed is False:
        items.append(LineItem(
            item="NHIMA (unremitted contributions)",
            status="compliance",
            basis="National Health Insurance Act",
            note="Employer non-remittance is a compliance breach reportable to NHIMA; not a direct payment to the employee.",
        ))

    # Roll-ups.
    total_owed = _money(sum(li.amount or 0 for li in items if li.status == "owed"))
    needs_input = [li.item for li in items if li.status == "needs_input"]
    contested = [li.item for li in items if li.status in {"contested", "conditional"}]

    result = EntitlementResult(
        monthly_basic_pay=_money(pay),
        years_of_service=years,
        termination_reason=reason,
        contract_type=ctype,
        daily_rate=daily_rate,
        line_items=[asdict(li) for li in items],
        total_clearly_owed=total_owed,
        needs_input=needs_input,
        contested=contested,
        assumptions=assumptions,
        disclaimer=(
            "Estimate based on the Employment Code Act No. 3 of 2019 statutory minimums "
            "and the inputs provided. Actual entitlements depend on the written contract, "
            "the true reason for termination, and applicable case law. This is legal "
            "information, not legal advice. Confirm with a qualified practitioner."
        ),
    )
    return asdict(result)
