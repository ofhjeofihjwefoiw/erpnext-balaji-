import frappe
from frappe.utils import getdate

def sync_assignment(doc, method=None):
    if not doc.get("custom_balaji_auto_leave"):
        return
    policy = doc.get("custom_balaji_leave_policy")
    start = doc.get("custom_balaji_leave_from")
    end = doc.get("custom_balaji_leave_to")
    if not all((policy, start, end)):
        frappe.throw("Automatic leave setup requires a policy, From Date and To Date.")
    if getdate(end) < getdate(start):
        frappe.throw("Leave To Date cannot precede From Date.")
    if not frappe.has_permission("Leave Policy Assignment", "create"):
        frappe.throw("Leave Policy Assignment create permission is required for automatic leave setup.", frappe.PermissionError)
    # Employee save serializes concurrent attempts for this employee.
    frappe.db.sql("select name from `tabEmployee` where name=%s for update", doc.name)
    assignments = frappe.get_all("Leave Policy Assignment", filters={"employee": doc.name, "docstatus": ["!=", 2]}, fields=["name", "leave_policy", "effective_from", "effective_to"])
    for row in assignments:
        if row.effective_from and row.effective_to and getdate(row.effective_from) <= getdate(end) and getdate(row.effective_to) >= getdate(start):
            if row.leave_policy == policy and getdate(row.effective_from) == getdate(start) and getdate(row.effective_to) == getdate(end):
                return
            frappe.throw("An overlapping leave assignment already exists: " + row.name)
    assignment = frappe.get_doc({"doctype": "Leave Policy Assignment", "employee": doc.name, "leave_policy": policy, "effective_from": start, "effective_to": end, "assignment_based_on": "Joining Date"})
    assignment.insert()
    # Draft by design: authorised HR reviews entitlement before submission.
    frappe.msgprint("Draft leave policy assignment created: " + assignment.name + ". Review and submit it to allocate leave.")
