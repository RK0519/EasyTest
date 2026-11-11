from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

COLS = ["id", "flow", "title", "type", "priority", "source", "preconditions",
        "steps", "test_data", "expected_result"]


def to_excel(cases: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Test cases"
    ws.append([c.replace("_", " ").title() for c in COLS])
    for c in cases:
        ws.append([("\n".join(f"{i}. {s}" for i, s in enumerate(c["steps"], 1))
                    if k == "steps" else c.get(k, "")) for k in COLS])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="14213D")
    widths = [9, 22, 40, 11, 10, 10, 30, 50, 28, 40]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
