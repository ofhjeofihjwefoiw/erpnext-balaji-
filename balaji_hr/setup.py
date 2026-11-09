import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ROLES = ("Balaji HR Entry", "Balaji HR All Categories", "Balaji HR Confidential")

def install():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
    fields = [
        dict(fieldname="custom_balaji_section", label="Malaysia HR", fieldtype="Section Break", insert_after="employment_type"),
        dict(fieldname="custom_balaji_category", label="Employee Category", fieldtype="Select", options="Local\nForeign\nOther", default="Local", insert_after="custom_balaji_section", in_list_view=1),
        dict(fieldname="custom_balaji_position", label="Position", fieldtype="Data", insert_after="custom_balaji_category"),
        dict(fieldname="custom_balaji_auto_leave", label="Create Draft Leave Assignment Automatically", fieldtype="Check", insert_after="custom_balaji_position"),
        dict(fieldname="custom_balaji_leave_policy", label="Malaysia Leave Policy", fieldtype="Link", options="Leave Policy", insert_after="custom_balaji_auto_leave"),
        dict(fieldname="custom_balaji_leave_from", label="Leave Effective From", fieldtype="Date", insert_after="custom_balaji_leave_policy"),
        dict(fieldname="custom_balaji_leave_to", label="Leave Effective To", fieldtype="Date", insert_after="custom_balaji_leave_from"),
    ]
    # Never overwrite existing site custom fields.
    missing = [f for f in fields if not frappe.get_meta("Employee").get_field(f["fieldname"])]
    if missing:
        create_custom_fields({"Employee": missing}, update=False)
    from balaji_hr.vault import setup as setup_vault
    setup_vault()
    frappe.clear_cache()

def configure_users(user_one, user_two, allow_other_for_user_two=False):
    """Explicit bench execute setup; creates login accounts without passwords or email sends.
    Existing accounts are refused to avoid modifying someone else's access.
    """
    if frappe.session.user != "Administrator":
        frappe.throw("Run as Administrator.", frappe.PermissionError)
    from frappe.utils import validate_email_address
    users = [validate_email_address(x.strip(), throw=True) for x in (user_one, user_two)]
    if users[0] == users[1]:
        frappe.throw("Use two different email addresses.")
    for email in users:
        if frappe.db.exists("User", email):
            frappe.throw("Account already exists; assign roles manually after review: " + email)
    for index, email in enumerate(users):
        role = "Balaji HR All Categories" if index == 1 and allow_other_for_user_two else "Balaji HR Entry"
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Balaji HR " + str(index + 1), "user_type": "System User", "send_welcome_email": 0})
        user.append("roles", {"role": "HR User"})
        user.append("roles", {"role": role})
        user.append("roles", {"role": "Balaji HR Confidential"})
        user.insert(ignore_permissions=True)
    print("Created two HR accounts. No passwords set and no email sent. Configure login/reset securely in User settings.")
