"""Pure payroll arithmetic (Decimal only, never float). See README 'Payroll assumptions'."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
HRA_RATE = Decimal("0.40")
MEDICAL_RATE = Decimal("0.10")

# Illustrative annual slabs from the challenge brief: (lower bound, base tax, marginal rate).
TAX_SLABS = [
    (Decimal("3600000"), Decimal("510000"), Decimal("0.35")),
    (Decimal("2400000"), Decimal("210000"), Decimal("0.25")),
    (Decimal("1200000"), Decimal("30000"), Decimal("0.15")),
    (Decimal("600000"), Decimal("0"), Decimal("0.05")),
]


def money(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def salary_components(basic) -> dict:
    """Gross = 1.5 x basic: basic + HRA (40%) + medical (10%)."""
    basic = money(basic)
    hra = money(basic * HRA_RATE)
    medical = money(basic * MEDICAL_RATE)
    return {"basic": basic, "hra": hra, "medical": medical, "gross": basic + hra + medical}


def annual_tax(annual_income) -> Decimal:
    """0 up to 600k; 5% of the amount above 600k up to 1.2M; 30k + 15% above 1.2M up to 2.4M;
    210k + 25% above 2.4M up to 3.6M; 510k + 35% above 3.6M."""
    income = Decimal(annual_income)
    for lower, base, rate in TAX_SLABS:
        if income > lower:
            return money(base + (income - lower) * rate)
    return Decimal("0.00")


def compute_pay(*, gross, working_days, payable_days, absent_days=0, unpaid_leave_days=0, half_days=0,
                late_penalty_days=0) -> dict:
    """Monthly pay for one employee.

    per_day      = gross / working_days
    prorated     = gross * payable_days / working_days       (joiners / leavers)
    deduction    = (absent + unpaid + 0.5 * half_days + late_penalty) * per_day   (capped at prorated)
    earned_gross = prorated - deduction
    tax          = slab(gross * 12) / 12, prorated by payable_days / working_days (capped at earned)
    net          = earned_gross - tax
    """
    gross = money(gross)
    if working_days <= 0:
        zero = Decimal("0.00")
        return {"per_day_rate": zero, "prorated_gross": zero, "deduction": zero, "earned_gross": zero,
                "annual_taxable": money(gross * 12), "annual_tax": annual_tax(gross * 12), "tax": zero, "net": zero}
    wd = Decimal(working_days)
    share = Decimal(payable_days) / wd
    per_day = gross / wd
    prorated = money(gross * share)
    deduction_days = (Decimal(absent_days) + Decimal(unpaid_leave_days) + Decimal("0.5") * Decimal(half_days)
                      + Decimal(late_penalty_days))
    deduction = min(money(per_day * deduction_days), prorated)
    earned = prorated - deduction
    annual_taxable = money(gross * 12)
    yearly_tax = annual_tax(annual_taxable)
    tax = min(money(yearly_tax / 12 * share), earned)
    return {
        "per_day_rate": money(per_day),
        "prorated_gross": prorated,
        "deduction": deduction,
        "earned_gross": earned,
        "annual_taxable": annual_taxable,
        "annual_tax": yearly_tax,
        "tax": tax,
        "net": earned - tax,
    }
