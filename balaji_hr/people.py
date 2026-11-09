import frappe
from frappe.utils import add_days, cint, today

from balaji_hr.security import ENTRY_ROLES, private_access, privileged

PRIVATE = "Balaji Employee Private"
EMPLOYEE_FIELDS = (
    "first_name", "gender", "date_of_birth", "date_of_joining", "company",
    "department", "designation", "custom_balaji_position", "custom_balaji_category",
    "custom_balaji_leave_policy", "custom_balaji_leave_from", "custom_balaji_leave_to",
    "custom_balaji_auto_leave",
)
PRIVATE_FIELDS = (
    "passport_number", "passport_expiry_date", "permit_number", "permit_issue_date",
    "permit_expiry_date", "visa_number", "visa_expiry_date", "salary", "epf_no",
    "eis_no", "socso_no", "pcb_no", "custom_visa_details",
)
EXPIRIES = ("permit_expiry_date", "passport_expiry_date", "visa_expiry_date")
LIST_FIELDS = ("name", "employee_name", "department", "designation", "status", "custom_balaji_category")


def categories():
    roles = set(frappe.get_roles())
    if privileged() or "Balaji HR All Categories" in roles:
        return ["Local", "Foreign", "Other"]
    return ["Local", "Foreign"] if roles.intersection(ENTRY_ROLES) else []


def fields_for(doctype, names):
    meta = frappe.get_meta(doctype)
    return [meta.get_field(name) for name in names if meta.has_field(name)]


def read_fields(doc, fields):
    doc.apply_fieldlevel_read_permissions()
    return {field: doc.get(field) for field in fields if field in doc.as_dict()}


def private_record(employee):
    if not private_access() or not frappe.has_permission(PRIVATE, "read"):
        return None
    records = frappe.get_list(PRIVATE, filters={"employee": employee}, pluck="name", page_length=2)
    if len(records) > 1:
        frappe.throw("Multiple confidential records found. Contact your HR administrator.")
    if records:
        doc = frappe.get_doc(PRIVATE, records[0])
        doc.check_permission("read")
        return doc
    return None


@frappe.whitelist()
def overview():
    cards = []
    for label, dt, filters in (
        ("Active employees", "Employee", {"status": "Active"}),
        ("Local employees", "Employee", {"status": "Active", "custom_balaji_category": "Local"}),
        ("Foreign employees", "Employee", {"status": "Active", "custom_balaji_category": "Foreign"}),
        ("Present today", "Attendance", {"attendance_date": today(), "status": "Present", "docstatus": 1}),
        ("Open leave requests", "Leave Application", {"status": "Open"}),
    ):
        if frappe.has_permission(dt, "read"):
            count = frappe.get_list(dt, filters=filters, fields=["count(name) as total"])
            cards.append({"label": label, "value": count[0].total if count else 0})
    return {"cards": cards, "can_create": bool(categories()) and frappe.has_permission("Employee", "create"),
            "can_expiry": private_access() and frappe.has_permission(PRIVATE, "read")}


@frappe.whitelist()
def employees(search="", category="", offset=0):
    filters = {"custom_balaji_category": category} if category in ("Local", "Foreign", "Other") else {}
    query = {"employee_name": ["like", "%" + str(search)[:100] + "%"]} if search else {}
    return frappe.get_list("Employee", fields=list(LIST_FIELDS), filters=filters, or_filters=query,
                           order_by="employee_name asc, name asc", start=max(0, cint(offset)), page_length=26)


@frappe.whitelist()
def profile(employee=None):
    allowed = categories()
    doc = frappe.get_doc("Employee", employee) if employee else frappe.new_doc("Employee")
    doc.check_permission("read" if employee else "create")
    if not employee and not allowed:
        frappe.throw("Employee entry role required.", frappe.PermissionError)
    private = private_record(employee) if employee else None
    private_visible = private_access() and frappe.has_permission(PRIVATE, "read")
    schema = []
    for dt, names in (("Employee", EMPLOYEE_FIELDS), (PRIVATE, PRIVATE_FIELDS if private_visible else ())):
        for df in fields_for(dt, names):
            if df.permlevel:
                continue
            schema.append(dict(name=df.fieldname, label=df.label, type=df.fieldtype, options=df.options,
                               required=bool(df.reqd), private=dt == PRIVATE))
    return dict(schema=schema, values=read_fields(doc, EMPLOYEE_FIELDS),
                private=read_fields(private, PRIVATE_FIELDS) if private else {},
                attachments=read_fields(private, ("passport_copy", "permit_copy", "visa_copy")) if private else {},
                categories=allowed, can_write=doc.has_permission("write" if employee else "create"),
                can_private=private_visible and (private.has_permission("write") if private else frappe.has_permission(PRIVATE, "create")))


@frappe.whitelist()
def link_options(doctype, search=""):
    allowed = {df.options for df in fields_for("Employee", EMPLOYEE_FIELDS) if df.fieldtype == "Link"}
    if doctype not in allowed:
        frappe.throw("Unsupported selection.", frappe.PermissionError)
    return frappe.get_list(doctype, filters={"name": ["like", "%" + str(search)[:100] + "%"]},
                           pluck="name", order_by="name asc", page_length=25)


@frappe.whitelist(methods=["POST"])
def save(employee=None, values=None, confidential=None):
    values = frappe.parse_json(values) or {}
    confidential = frappe.parse_json(confidential) or {}
    if not isinstance(values, dict) or not isinstance(confidential, dict):
        frappe.throw("Expected employee field values.")
    doc = frappe.get_doc("Employee", employee, for_update=True) if employee else frappe.new_doc("Employee")
    doc.check_permission("write" if employee else "create")
    if not employee and not categories():
        frappe.throw("Employee entry role required.", frappe.PermissionError)
    employee_fields = {df.fieldname for df in fields_for("Employee", EMPLOYEE_FIELDS) if not df.permlevel}
    if values.keys() - employee_fields:
        frappe.throw("Unsupported employee field.")
    if confidential:
        private_fields = {df.fieldname for df in fields_for(PRIVATE, PRIVATE_FIELDS) if not df.permlevel}
        if not private_access() or not frappe.has_permission(PRIVATE, "read"):
            frappe.throw("Confidential employee access required.", frappe.PermissionError)
        if confidential.keys() - private_fields:
            frappe.throw("Unsupported confidential field.")
    doc.update(values)
    doc.save()
    if confidential:
        private = private_record(doc.name) or frappe.new_doc(PRIVATE)
        private.employee = doc.name
        private.update(confidential)
        private.save()
    return doc.name


@frappe.whitelist()
def expiry(kind="permit_expiry_date", days=30, offset=0):
    if kind not in EXPIRIES or not private_access():
        frappe.throw("Confidential employee access required.", frappe.PermissionError)
    days = min(90, max(1, cint(days)))
    rows = frappe.get_list(PRIVATE, fields=["employee", kind],
                           filters={kind: ["between", [today(), add_days(today(), days)]]},
                           order_by=kind + " asc, name asc", start=max(0, cint(offset)), page_length=26)
    if not rows:
        return {"rows": [], "has_more": False}
    has_more = len(rows) > 25
    rows = rows[:25]
    permitted = frappe.get_list("Employee", filters={"name": ["in", [row.employee for row in rows]]},
                                fields=["name", "employee_name"], page_length=26)
    names = {row.name: row.employee_name for row in permitted}
    return {"rows": [dict(employee=row.employee, name=names[row.employee], expiry=row.get(kind))
                     for row in rows if row.employee in names], "has_more": has_more}


@frappe.whitelist(methods=["POST"])
def upload(employee, field):
    from frappe.utils.file_manager import save_file

    allowed = {"passport_copy", "permit_copy", "visa_copy"}
    if field not in allowed or not private_access():
        frappe.throw("Confidential employee access required.", frappe.PermissionError)
    frappe.get_doc("Employee", employee, for_update=True).check_permission("read")
    doc = private_record(employee)
    if doc:
        doc = frappe.get_doc(PRIVATE, doc.name, for_update=True)
        doc.check_permission("write")
    else:
        doc = frappe.new_doc(PRIVATE)
        doc.employee = employee
        doc.check_permission("create")
        doc.insert()
    if doc.get(field):
        frappe.throw("A copy is already attached.")
    upload = frappe.request.files.get("file")
    if not upload:
        frappe.throw("Select a document.")
    extension = upload.filename.rsplit(".", 1)[-1].lower()
    signatures = {"pdf": b"%PDF-", "png": b"\x89PNG\r\n\x1a\n", "jpg": b"\xff\xd8\xff", "jpeg": b"\xff\xd8\xff"}
    content = upload.stream.read(10 * 1024 * 1024 + 1)
    if extension not in signatures or not content.startswith(signatures[extension]) or len(content) > 10 * 1024 * 1024:
        frappe.throw("Choose a PDF, JPG or PNG up to 10 MB.")
    attachment = save_file(field + "." + extension, content, PRIVATE, doc.name, is_private=1, df=field)
    doc.set(field, attachment.file_url)
    doc.save()
    return True
