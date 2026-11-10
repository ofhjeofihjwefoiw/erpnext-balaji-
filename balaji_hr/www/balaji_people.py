import frappe
from frappe.sessions import get_csrf_token

from balaji_hr.vault import eligible

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/balaji-login?redirect-to=/balaji-people"
        raise frappe.Redirect
    context.csrf_token = get_csrf_token()
    context.vault_eligible = eligible()
    return context
