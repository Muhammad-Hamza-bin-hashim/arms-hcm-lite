"""Payslip PDF built only from the stored snapshot (reproducible after finalization)."""
import calendar
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from apps.org.models import CompanySettings

NAVY = colors.HexColor("#0F1E3A")
TEAL = colors.HexColor("#0E9384")
MUTED = colors.HexColor("#5B6577")
LINE = colors.HexColor("#DDE3EC")


def _fmt(value, currency):
    return f"{currency} {value:,.2f}"


def render_payslip(slip) -> bytes:
    s = CompanySettings.get()
    company = s.company_name or "AR&MS Management Company"
    cur = s.currency or "PKR"
    run = slip.run
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Payslip {slip.employee_code} {run.period_label}")
    width, height = A4

    # Header band
    c.setFillColor(NAVY)
    c.rect(0, height - 32 * mm, width, 32 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(18 * mm, height - 15 * mm, "AR&MS")
    c.setFillColor(TEAL)
    c.drawString(18 * mm + c.stringWidth("AR&MS ", "Helvetica-Bold", 18), height - 15 * mm, "HCM Lite")
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 10)
    c.drawString(18 * mm, height - 23 * mm, company)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 18 * mm, height - 15 * mm, "PAYSLIP")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 18 * mm, height - 23 * mm, f"{calendar.month_name[run.month]} {run.year}")
    status = "FINAL" if run.is_locked else "DRAFT - not final"
    c.drawRightString(width - 18 * mm, height - 28 * mm, status)

    y = height - 46 * mm
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, y, slip.employee_name)
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawString(18 * mm, y - 5 * mm, f"Code {slip.employee_code}  |  {slip.department_name}"
                 + (f"  |  {slip.designation_name}" if slip.designation_name else ""))
    c.drawRightString(width - 18 * mm, y, f"Working days: {slip.working_days}")
    c.drawRightString(width - 18 * mm, y - 5 * mm, f"Payable days: {slip.payable_days}")

    def table(title, rows, top):
        c.setFillColor(TEAL)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(18 * mm, top, title)
        yy = top - 7 * mm
        for label, value, bold in rows:
            c.setStrokeColor(LINE)
            c.line(18 * mm, yy - 2 * mm, width - 18 * mm, yy - 2 * mm)
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold" if bold else "Helvetica", 9.5)
            c.drawString(20 * mm, yy, label)
            c.drawRightString(width - 20 * mm, yy, value)
            yy -= 7 * mm
        return yy - 4 * mm

    y = table("Earnings", [
        ("Basic salary", _fmt(slip.basic, cur), False),
        ("House rent allowance (40%)", _fmt(slip.hra, cur), False),
        ("Medical allowance (10%)", _fmt(slip.medical, cur), False),
        ("Monthly gross (1.5 x basic)", _fmt(slip.gross, cur), True),
        (f"Prorated gross ({slip.payable_days}/{slip.working_days} days)", _fmt(slip.prorated_gross, cur), False),
    ], y - 16 * mm)
    y = table("Deductions", [
        (f"Absent days: {slip.absent_days}", "", False),
        (f"Unpaid leave days: {slip.unpaid_leave_days}", "", False),
        (f"Half days: {slip.half_days} (x 0.5)", "", False),
        (f"Late penalty days: {slip.late_penalty_days}", "", False),
        (f"Attendance deduction @ {_fmt(slip.per_day_rate, cur)}/day", _fmt(slip.deduction, cur), False),
        (f"Income tax (annual {_fmt(slip.annual_tax, cur)} on {_fmt(slip.annual_taxable, cur)})",
         _fmt(slip.tax, cur), False),
    ], y)

    c.setFillColor(colors.HexColor("#E7F6F4"))
    c.roundRect(18 * mm, y - 12 * mm, width - 36 * mm, 14 * mm, 3 * mm, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(22 * mm, y - 7 * mm, "Net pay")
    c.drawRightString(width - 22 * mm, y - 7 * mm, _fmt(slip.net, cur))

    c.setFont("Helvetica", 7.5)
    c.setFillColor(MUTED)
    c.drawString(18 * mm, 15 * mm, "Tax slabs are illustrative (challenge brief), not current tax law. "
                                   "Computer-generated payslip; no signature required.")
    c.showPage()
    c.save()
    return buf.getvalue()
