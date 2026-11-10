import frappe
from frappe.sessions import get_csrf_token

from balaji_hr.vault import eligible

no_cache = True


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/balaji-login?redirect-to=/balaji-private"
        raise frappe.Redirect
    if not eligible():
        frappe.throw("Private workspace access required.", frappe.PermissionError)
    context.csrf_token = get_csrf_token()
    return context
