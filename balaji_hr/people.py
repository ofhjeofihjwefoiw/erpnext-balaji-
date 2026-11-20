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
    can_read_employee = frappe.has_permission("Employee", "read")
    recent = frappe.get_list("Employee", fields=["name", "employee_name", "designation", "date_of_joining"],
                             filters={"date_of_joining": ["<=", today()]}, order_by="date_of_joining desc",
                             page_length=5) if can_read_employee else []
    requests = frappe.get_list("Leave Application", filters={"status": "Open", "docstatus": ["<", 2]},
                               fields=["employee_name", "leave_type", "from_date", "to_date"],
                               order_by="modified desc", page_length=4) if frappe.has_permission("Leave Application", "read") else []
    can_expiry = private_access() and frappe.has_permission(PRIVATE, "read") and can_read_employee
    upcoming = []
    if can_expiry:
        for field in EXPIRIES:
            upcoming.extend(dict(row, document=field.split("_")[0].title()) for row in expiry(field)["rows"][:3])
        upcoming = sorted(upcoming, key=lambda row: str(row["expiry"]))[:5]
    user = frappe.get_cached_value("User", frappe.session.user, "full_name") or frappe.session.user
    company = "Balaji Enterprise Sdn Bhb"
    settings = company if frappe.db.exists("Company", company) and frappe.has_permission("Company", "write", doc=company) else None
    return {"cards": cards, "recent": recent, "requests": requests, "upcoming": upcoming,
            "user": user, "date": today(), "can_payroll": frappe.has_permission("Salary Slip", "read"), "settings_company": settings, "operations": [dt for dt in OPERATIONS if frappe.has_permission(dt, "read")],
            "operation_create": [dt for dt in OPERATIONS if frappe.has_permission(dt, "create")], "can_create": bool(categories()) and frappe.has_permission("Employee", "create"),
            "can_expiry": can_expiry}


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
    attachments = read_fields(private, ("passport_copy", "permit_copy", "visa_copy")) if private else {}
    if employee and private_visible:
        doc.apply_fieldlevel_read_permissions()
        for field in ("passport_copy", "permit_copy", "visa_copy"):
            if not attachments.get(field):
                document = field.removesuffix("_copy")
                candidates = [df.fieldname for df in doc.meta.fields if df.fieldtype in ("Attach", "Attach Image")
                              and document in df.fieldname.lower()]
                for candidate in candidates:
                    url = doc.get(candidate)
                    if not isinstance(url, str) or not url.startswith("/private/files/"):
                        continue
                    file_id = frappe.db.get_value("File", {
                        "file_url": url, "is_private": 1,
                        "attached_to_doctype": "Employee", "attached_to_name": employee,
                    }, "name")
                    if file_id and frappe.get_doc("File", file_id).has_permission("read"):
                        attachments[field] = url
                        break
    private_values = read_fields(private, PRIVATE_FIELDS) if private else {}
    if employee and private_visible:
        for field in ("passport_number", "passport_expiry_date", "permit_number", "permit_expiry_date",
                      "permit_issue_date", "visa_number", "visa_expiry_date"):
            if not private_values.get(field):
                for candidate in (field, "custom_" + field, "custom_balaji_" + field,
                                  "valid_upto" if field == "passport_expiry_date" else field):
                    if doc.get(candidate):
                        private_values[field] = doc.get(candidate)
                        break
    schema = []
    for dt, names in (("Employee", EMPLOYEE_FIELDS), (PRIVATE, PRIVATE_FIELDS if private_visible else ())):
        for df in fields_for(dt, names):
            if df.permlevel:
                continue
            schema.append(dict(name=df.fieldname, label=df.label, type=df.fieldtype, options=df.options,
                               required=bool(df.reqd), private=dt == PRIVATE))
    resignation = read_fields(doc, ("resignation_letter_date", "relieving_date"))
    company_info = frappe.db.get_value("Company", doc.get("company"), ["company_name", "email", "phone_no", "website"], as_dict=True) \
        if doc.get("company") and frappe.has_permission("Company", "read") else {}
    return dict(full_name=doc.get("employee_name"), company_info=company_info or {}, can_view_private=private_visible,
                resignation=dict(letter_date=resignation.get("resignation_letter_date"),
                                 last_day=resignation.get("relieving_date")),
                can_record_resignation=bool(employee and doc.has_permission("write") and
                                            all(df.permlevel == 0 for df in fields_for("Employee", ("resignation_letter_date", "relieving_date"))) and
                                            len(fields_for("Employee", ("resignation_letter_date", "relieving_date"))) == 2),
                schema=schema, values=read_fields(doc, EMPLOYEE_FIELDS),
                private=private_values,
                attachments=attachments,
                categories=allowed, can_write=doc.has_permission("write" if employee else "create"),
                can_private=private_visible and (private.has_permission("write") if private else frappe.has_permission(PRIVATE, "create")))


@frappe.whitelist()
def link_options(doctype, search=""):
    allowed = {df.options for df in fields_for("Employee", EMPLOYEE_FIELDS) if df.fieldtype == "Link"}
    allowed.update(df.options for dt in OPERATIONS if frappe.has_permission(dt, "read")
                   for df in operation_fields(dt) if df.fieldtype == "Link")
    if frappe.has_permission("Shift Assignment", "read"):
        allowed.add("Department")
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


OPERATIONS = {
    "Attendance": ("employee", "attendance_date", "status", "shift", "leave_type"),
    "Employee Checkin": ("employee", "log_type", "time", "device_id"),
    "Shift Assignment": ("employee", "shift_type", "start_date", "end_date", "status"),
    "Holiday List": ("holiday_list_name", "from_date", "to_date", "weekly_off"),
    "Leave Policy Assignment": (
        "employee", "leave_policy", "assignment_based_on", "leave_period",
        "effective_from", "effective_to",
    ),
}
HOLIDAY_FIELDS = ("holiday_date", "description", "weekly_off")


def operation_fields(doctype):
    if doctype not in OPERATIONS:
        frappe.throw("Unsupported HR operation.", frappe.PermissionError)
    return [df for df in fields_for(doctype, OPERATIONS[doctype]) if not df.permlevel]


@frappe.whitelist()
def operation_list(doctype, offset=0):
    fields = [df.fieldname for df in operation_fields(doctype)]
    return frappe.get_list(doctype, fields=["name", "docstatus", *fields],
                           order_by="modified desc, name desc", start=max(0, cint(offset)),
                           page_length=26)


@frappe.whitelist()
def operation_form(doctype, name=None):
    fields = operation_fields(doctype)
    doc = frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
    doc.check_permission("read" if name else "create")
    child_fields = []
    holidays = []
    if doctype == "Holiday List":
        child_fields = [df for df in fields_for("Holiday", HOLIDAY_FIELDS) if not df.permlevel]
        holidays = [{df.fieldname: row.get(df.fieldname) for df in child_fields}
                    for row in doc.get("holidays", [])]
    return dict(
        schema=[dict(name=df.fieldname, label=df.label, type=df.fieldtype,
                     options=df.options, required=bool(df.reqd)) for df in fields],
        child_schema=[dict(name=df.fieldname, label=df.label, type=df.fieldtype,
                           options=df.options, required=bool(df.reqd)) for df in child_fields],
        holidays=holidays,
        values=read_fields(doc, [df.fieldname for df in fields]),
        can_write=doc.docstatus == 0 and doc.has_permission("write" if name else "create"),
        can_submit=bool(name and doc.docstatus == 0 and doc.meta.is_submittable and doc.has_permission("submit")),
    )


@frappe.whitelist(methods=["POST"])
def operation_save(doctype, name=None, values=None, holidays=None, submit=False):
    fields = {df.fieldname for df in operation_fields(doctype)}
    values = frappe.parse_json(values) or {}
    if not isinstance(values, dict) or values.keys() - fields:
        frappe.throw("Unsupported field.")
    doc = frappe.get_doc(doctype, name, for_update=True) if name else frappe.new_doc(doctype)
    if doc.docstatus != 0:
        frappe.throw("Only draft records can be edited.")
    doc.check_permission("write" if name else "create")
    doc.update(values)
    if holidays is not None:
        rows = frappe.parse_json(holidays)
        allowed = {df.fieldname for df in fields_for("Holiday", HOLIDAY_FIELDS) if not df.permlevel}
        if doctype != "Holiday List" or not isinstance(rows, list) or any(
            not isinstance(row, dict) or row.keys() - allowed for row in rows
        ):
            frappe.throw("Invalid holiday rows.")
        doc.set("holidays", rows)
    if cint(submit):
        if not name or not doc.meta.is_submittable:
            frappe.throw("Save the draft before submitting.")
        doc.check_permission("submit")
        doc.submit()
    else:
        doc.save()
    return doc.name


@frappe.whitelist(methods=["POST"])
def save_resignation(employee, letter_date, last_day):
    from frappe.utils import getdate

    doc = frappe.get_doc("Employee", employee, for_update=True)
    doc.check_permission("write")
    fields = fields_for("Employee", ("resignation_letter_date", "relieving_date"))
    if len(fields) != 2 or any(df.permlevel for df in fields):
        frappe.throw("Resignation date fields are unavailable.", frappe.PermissionError)
    if not letter_date or not last_day:
        frappe.throw("Enter both resignation dates.")
    letter_date, last_day = getdate(letter_date), getdate(last_day)
    if last_day < letter_date:
        frappe.throw("Last working day cannot precede the letter date.")
    doc.resignation_letter_date = letter_date
    doc.relieving_date = last_day
    doc.save()
    return dict(letter_date=doc.resignation_letter_date, last_day=doc.relieving_date)


@frappe.whitelist()
def print_document_copies(employee):
    from io import BytesIO

    from PIL import Image, ImageOps

    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        from PyPDF2 import PdfReader, PdfWriter

    data = profile(employee)
    if not data["can_view_private"]:
        frappe.throw("Confidential employee access required.", frappe.PermissionError)
    private = private_record(employee)
    parents = {("Employee", employee)}
    if private:
        parents.add((PRIVATE, private.name))
    writer = PdfWriter()
    for field in ("passport_copy", "permit_copy"):
        url = data["attachments"].get(field)
        if not isinstance(url, str) or not url.startswith("/private/files/"):
            frappe.throw("Both private copies are required for the combined PDF.")
        for parent_type, parent_name in parents:
            file_id = frappe.db.get_value("File", {
                "file_url": url, "is_private": 1, "attached_to_doctype": parent_type,
                "attached_to_name": parent_name,
            }, "name")
            if file_id:
                break
        else:
            frappe.throw("A document copy could not be verified.")
        file = frappe.get_doc("File", file_id)
        file.check_permission("read")
        content = file.get_content()
        if isinstance(content, str):
            content = content.encode()
        stream = BytesIO(content)
        if not content.startswith(b"%PDF-"):
            image = ImageOps.exif_transpose(Image.open(stream)).convert("RGB")
            image.thumbnail((1600, 2200))
            stream = BytesIO()
            image.save(stream, format="PDF")
            stream.seek(0)
        for page in PdfReader(stream).pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    frappe.local.response.update(filename="passport-and-permit.pdf", filecontent=output.getvalue(),
                                 type="download", display_content_as="inline")


@frappe.whitelist()
def attendance_calendar(month, offset=0):
    from calendar import monthrange
    from datetime import date

    try:
        year, number = map(int, month.split("-"))
        start = date(year, number, 1)
        days = monthrange(year, number)[1]
    except (ValueError, AttributeError):
        frappe.throw("Choose a valid month.")
    if not frappe.has_permission("Attendance", "read"):
        frappe.throw("Attendance access required.", frappe.PermissionError)
    employees = frappe.get_list("Employee", filters={"date_of_joining": ["<=", date(year, number, days)]},
                                fields=["name", "employee_name", "department"],
                                order_by="employee_name asc, name asc", start=max(0, cint(offset)), page_length=26)
    roster = employees[:25]
    entries = frappe.get_list("Attendance", filters={
        "employee": ["in", [row.name for row in roster]],
        "attendance_date": ["between", [start, date(year, number, days)]],
        "docstatus": 1,
    }, fields=["employee", "attendance_date", "status"], page_length=0) if roster else []
    return dict(employees=roster, entries=entries, days=days, has_more=len(employees) > 25)


@frappe.whitelist()
def shift_week(start=None, department=None, offset=0):
    from datetime import timedelta

    from frappe.utils import getdate

    if not frappe.has_permission("Shift Assignment", "read"):
        frappe.throw("Shift assignment access required.", frappe.PermissionError)
    start = getdate(start or today())
    start -= timedelta(days=start.weekday())
    end = start + timedelta(days=6)
    filters = {"status": "Active", "date_of_joining": ["<=", end]}
    if department:
        filters["department"] = department
    people = frappe.get_list("Employee", filters=filters,
                             fields=["name", "employee_name", "department", "designation"],
                             order_by="employee_name asc, name asc", start=max(0, cint(offset)), page_length=26)
    roster = people[:25]
    assignments = frappe.get_list("Shift Assignment", filters={
        "employee": ["in", [row.name for row in roster]], "start_date": ["<=", end],
        "docstatus": 1, "status": "Active",
    }, or_filters=[["end_date", ">=", start], ["end_date", "is", "not set"]],
        fields=["name", "employee", "shift_type", "start_date", "end_date"],
        order_by="start_date asc", page_length=0) if roster else []
    return dict(start=start, days=[start + timedelta(days=i) for i in range(7)], employees=roster,
                assignments=assignments, has_more=len(people) > 25)


@frappe.whitelist()
def payroll_register(month, offset=0):
    from calendar import monthrange
    from datetime import date

    try:
        year, number = map(int, month.split("-"))
        start = date(year, number, 1)
        end = date(year, number, monthrange(year, number)[1])
    except (AttributeError, ValueError):
        frappe.throw("Choose a valid month.")
    if not frappe.has_permission("Salary Slip", "read"):
        frappe.throw("Payroll access required.", frappe.PermissionError)
    filters = {"end_date": ["between", [start, end]], "docstatus": ["<", 2]}
    slips = frappe.get_list("Salary Slip", filters=filters,
                            fields=["name", "employee", "employee_name", "department", "currency",
                                    "gross_pay", "total_deduction", "net_pay", "docstatus"],
                            order_by="employee_name asc, name asc", start=max(0, cint(offset)), page_length=26)
    runs = frappe.get_list("Payroll Entry", filters=filters,
                           fields=["name", "company", "start_date", "end_date", "docstatus"],
                           order_by="start_date desc", page_length=15) if frappe.has_permission("Payroll Entry", "read") else []
    totals = frappe.get_list("Salary Slip", filters=filters, group_by="currency", fields=[
        "currency", "count(name) as slips", "sum(gross_pay) as gross", "sum(total_deduction) as deductions",
        "sum(net_pay) as net"], page_length=10)
    return dict(slips=slips, runs=runs, totals=totals)


# ---------------------------------------------------------------------------
# Bulk attendance, shift matching and salary slip detail
# ---------------------------------------------------------------------------
ATTENDANCE_STATUSES = ("Present", "Absent", "Half Day", "Work From Home")


@frappe.whitelist()
def attendance_sheet(date=None, department=""):
    from frappe.utils import getdate

    if not frappe.has_permission("Attendance", "read"):
        frappe.throw("Attendance access required.", frappe.PermissionError)
    day = getdate(date or today())
    filters = {"status": "Active", "date_of_joining": ["<=", day]}
    if department:
        filters["department"] = department
    people = frappe.get_list("Employee", filters=filters,
                             fields=["name", "employee_name", "department", "designation"],
                             order_by="employee_name asc, name asc", page_length=500)
    marked = {}
    if people:
        for row in frappe.get_list("Attendance", filters={
            "employee": ["in", [p.name for p in people]], "attendance_date": day, "docstatus": ["<", 2],
        }, fields=["employee", "status", "docstatus"], page_length=0):
            marked[row.employee] = dict(status=row.status, docstatus=row.docstatus)
    return dict(date=day, employees=[dict(p, marked=marked.get(p.name)) for p in people],
                can_create=frappe.has_permission("Attendance", "create"))


@frappe.whitelist(methods=["POST"])
def attendance_bulk_save(date, rows):
    from frappe.utils import getdate

    rows = frappe.parse_json(rows) or []
    if not isinstance(rows, list) or not rows:
        frappe.throw("Mark at least one employee.")
    if len(rows) > 500:
        frappe.throw("Too many rows in one save.")
    day = getdate(date)
    if day > getdate(today()):
        frappe.throw("Attendance cannot be marked for a future date.")
    frappe.has_permission("Attendance", "create", throw=True)
    can_submit = frappe.has_permission("Attendance", "submit")
    created, skipped, errors = 0, 0, []
    for row in rows:
        employee, status = row.get("employee"), row.get("status")
        if status not in ATTENDANCE_STATUSES:
            errors.append(dict(employee=employee, error="Invalid status."))
            continue
        if frappe.db.exists("Attendance", {"employee": employee, "attendance_date": day, "docstatus": ["<", 2]}):
            skipped += 1
            continue
        frappe.db.savepoint("balaji_att")
        try:
            doc = frappe.get_doc({"doctype": "Attendance", "employee": employee,
                                  "attendance_date": day, "status": status})
            doc.insert()
            if can_submit:
                doc.submit()
            created += 1
        except Exception as exc:
            frappe.db.rollback(save_point="balaji_att")
            errors.append(dict(employee=employee, error=str(exc)[:200]))
    return dict(created=created, skipped=skipped, errors=errors)


@frappe.whitelist()
def shift_match_data():
    if not frappe.has_permission("Shift Assignment", "read"):
        frappe.throw("Shift assignment access required.", frappe.PermissionError)
    people = frappe.get_list("Employee", filters={"status": "Active"},
                             fields=["name", "employee_name", "department", "designation"],
                             order_by="employee_name asc, name asc", page_length=500)
    shifts = frappe.get_list("Shift Type", fields=["name", "start_time", "end_time"],
                             order_by="name asc", page_length=50)
    return dict(employees=people, shifts=[dict(s, start_time=str(s.start_time), end_time=str(s.end_time)) for s in shifts],
                can_create=frappe.has_permission("Shift Assignment", "create"))


@frappe.whitelist(methods=["POST"])
def shift_match_save(pairs, start_date, end_date=None, submit=1):
    from frappe.utils import getdate

    pairs = frappe.parse_json(pairs) or []
    if not isinstance(pairs, list) or not pairs:
        frappe.throw("Match at least one employee with a shift.")
    if len(pairs) > 500:
        frappe.throw("Too many matches in one save.")
    if not start_date:
        frappe.throw("Choose a start date.")
    if end_date and getdate(end_date) < getdate(start_date):
        frappe.throw("End date cannot precede the start date.")
    frappe.has_permission("Shift Assignment", "create", throw=True)
    do_submit = cint(submit) and frappe.has_permission("Shift Assignment", "submit")
    created, errors = 0, []
    for pair in pairs:
        frappe.db.savepoint("balaji_shift")
        try:
            doc = frappe.get_doc({"doctype": "Shift Assignment", "employee": pair.get("employee"),
                                  "shift_type": pair.get("shift_type"), "start_date": start_date,
                                  "end_date": end_date or None, "status": "Active"})
            doc.insert()
            if do_submit:
                doc.submit()
            created += 1
        except Exception as exc:
            frappe.db.rollback(save_point="balaji_shift")
            errors.append(dict(employee=pair.get("employee"), error=str(exc)[:200]))
    return dict(created=created, errors=errors, submitted=bool(do_submit))


@frappe.whitelist()
def salary_slip_detail(name):
    from frappe.utils import money_in_words

    doc = frappe.get_doc("Salary Slip", name)
    doc.check_permission("read")
    company = frappe.db.get_value("Company", doc.company, ["company_name", "email", "phone_no", "website"], as_dict=True) \
        if frappe.has_permission("Company", "read") else None
    rows = lambda table: [dict(component=r.salary_component, amount=r.amount) for r in doc.get(table, [])]
    return dict(
        name=doc.name, docstatus=doc.docstatus, company=doc.company, company_info=company or {},
        employee=doc.employee, employee_name=doc.employee_name, department=doc.get("department"),
        designation=doc.get("designation"), start_date=doc.start_date, end_date=doc.end_date,
        posting_date=doc.get("posting_date"), currency=doc.get("currency") or "MYR",
        payment_days=doc.get("payment_days"), working_days=doc.get("total_working_days"),
        lwp=doc.get("leave_without_pay"), absent_days=doc.get("absent_days"),
        bank_name=doc.get("bank_name"), bank_account=doc.get("bank_account_no"),
        earnings=rows("earnings"), deductions=rows("deductions"),
        gross_pay=doc.gross_pay, total_deduction=doc.total_deduction, net_pay=doc.net_pay,
        in_words=money_in_words(doc.net_pay, doc.get("currency") or "MYR"),
    )
