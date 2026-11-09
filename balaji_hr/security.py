import frappe
from frappe.utils import getdate

ENTRY_ROLES = {"Balaji HR Entry", "Balaji HR All Categories"}
PRIVATE_ROLES = {"Balaji HR Confidential", "System Manager"}

def privileged():
    return frappe.session.user == "Administrator"

def private_access():
    return privileged() or bool(PRIVATE_ROLES.intersection(frappe.get_roles()))

def validate_employee(doc, method=None):
    old = doc.get_doc_before_save()
    category = doc.get("custom_balaji_category") or "Local"
    category_changed = old and (old.get("custom_balaji_category") or "Local") != category
    if doc.is_new() or category_changed:
        roles = set(frappe.get_roles())
        if not privileged() and not roles.intersection(ENTRY_ROLES):
            frappe.throw("Only authorised Balaji HR entry users can create employees or change their category.", frappe.PermissionError)
        if category not in {"Local", "Foreign", "Other"}:
            frappe.throw("Choose Local, Foreign or Other.")
        if category == "Other" and not privileged() and "Balaji HR All Categories" not in roles:
            frappe.throw("The Other category requires Balaji HR All Categories.", frappe.PermissionError)
    if old and not privileged() and not set(frappe.get_roles()).intersection(ENTRY_ROLES):
        for key in ("custom_balaji_leave_policy", "custom_balaji_leave_from", "custom_balaji_leave_to", "custom_balaji_auto_leave"):
            if doc.get(key) != old.get(key):
                frappe.throw("Only authorised entry users can change leave setup.", frappe.PermissionError)

def validate_private(doc, method=None):
    if not private_access():
        frappe.throw("Confidential employee access required.", frappe.PermissionError)
    frappe.get_doc("Employee", doc.employee).check_permission("read")
    for prefix in ("passport", "visa", "permit"):
        issued = doc.get(prefix + "_issue_date")
        expiry = doc.get(prefix + "_expiry_date")
        if issued and expiry and getdate(expiry) < getdate(issued):
            frappe.throw(prefix.title() + " expiry cannot precede its issue date.")
        url = doc.get(prefix + "_copy")
        if url:
            files = frappe.get_all("File", filters={"file_url": url}, fields=["is_private", "attached_to_doctype", "attached_to_name"])
            if not files or any(not row.is_private or row.attached_to_doctype != doc.doctype or row.attached_to_name != doc.name for row in files):
                frappe.throw("Save the confidential record first, then upload a private file attached to this record.")

def validate_file(doc, method=None):
    if doc.attached_to_doctype == "Balaji Employee Private":
        if not private_access():
            frappe.throw("Confidential employee access required.", frappe.PermissionError)
        if not doc.is_private:
            frappe.throw("Employee passport, visa and permit files must be private.")
        if doc.attached_to_name:
            frappe.get_doc(doc.attached_to_doctype, doc.attached_to_name).check_permission("write")
