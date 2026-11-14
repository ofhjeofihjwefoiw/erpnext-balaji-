import re

import frappe
from frappe.www.login import get_context as native_login_context

no_cache = True
COMPANY = "Balaji Enterprise Sdn Bhb"


def get_context(context):
    native_login_context(context)
    logo = frappe.db.get_value("Company", COMPANY, "company_logo")
    context.logo = logo if isinstance(logo, str) and re.fullmatch(r"/files/[^?#]+\.(?:png|jpe?g|webp|gif)", logo, re.I) else ""
    context.app_name = "Balaji Enterprises"
    return context
