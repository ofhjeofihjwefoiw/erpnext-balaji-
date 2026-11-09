from pathlib import Path
import frappe
from frappe.utils import add_days, today
from balaji_hr.security import private_access

HIDDEN_TYPES = {"Balaji Employee Private", "Balaji Vault Employee", "Balaji Vault Entry", "Balaji Vault Audit"}

EXTRA = {"Employee", "Department", "Designation", "Branch", "Employment Type", "Holiday List", "Company", "Balaji Employee Private"}

def modules():
    return [line.strip() for line in Path(frappe.get_app_path("hrms", "modules.txt")).read_text().splitlines() if line.strip()]

def catalog():
    rows = frappe.get_all("DocType", filters={"module": ["in", modules()]}, fields=["name", "module", "istable", "issingle", "is_submittable"])
    existing = {row.name for row in rows}
    for name in EXTRA - existing:
        if frappe.db.exists("DocType", name):
            meta = frappe.get_meta(name)
            rows.append(frappe._dict(name=name, module=meta.module, istable=meta.istable, issingle=meta.issingle, is_submittable=meta.is_submittable))
    return [row for row in rows if row.name not in HIDDEN_TYPES]

@frappe.whitelist()
def bootstrap():
    if frappe.session.user == "Guest":
        frappe.throw("Please sign in.", frappe.PermissionError)
    allowed = [row for row in catalog() if not row.istable and frappe.has_permission(row.name, "read") and (row.name != "Balaji Employee Private" or private_access())]
    names = {row.name for row in allowed}
    cards = []
    for label, dt, filters in [
        ("Active employees", "Employee", {"status": "Active"}),
        ("Present today", "Attendance", {"attendance_date": today(), "status": "Present", "docstatus": 1}),
        ("Open leave requests", "Leave Application", {"status": "Open", "docstatus": ["<", 2]}),
        ("Draft salary slips", "Salary Slip", {"docstatus": 0}),
    ]:
        if dt in names:
            count = frappe.get_list(dt, filters=filters, fields=["count(name) as total"])[0].total
            cards.append(dict(label=label, doctype=dt, filters=filters, value=count))
    expiry = []
    if "Balaji Employee Private" in names:
        for field in ["passport_expiry_date", "visa_expiry_date", "permit_expiry_date"]:
            for row in frappe.get_list("Balaji Employee Private", filters={field: ["between", [today(), add_days(today(), 90)]]}, fields=["name", "employee", field], page_length=20, order_by=field + " asc"):
                expiry.append(dict(employee=row.employee, kind=field.replace("_expiry_date", "").title(), date=row.get(field), name=row.name))
    reports = frappe.get_all("Report", filters={"disabled": 0, "ref_doctype": ["in", list(names)]}, fields=["name", "ref_doctype", "report_type"], order_by="name") if names else []
    return dict(catalog=allowed, cards=cards, expiry=expiry, reports=reports, user=frappe.session.user)
