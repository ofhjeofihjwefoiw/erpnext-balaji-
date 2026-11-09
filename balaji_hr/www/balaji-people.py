import frappe
from frappe.sessions import get_csrf_token

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/balaji-people"
        raise frappe.Redirect
    context.csrf_token = get_csrf_token()
    return context
