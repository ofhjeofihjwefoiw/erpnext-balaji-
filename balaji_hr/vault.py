"""Session-gated private HR register. No standard Employee rows are created."""
from pathlib import Path
import hashlib
import frappe
from frappe.utils import today, flt, getdate
from balaji_hr.vault_crypto import verify

ROLE = "Balaji HR Vault"
EMPLOYEE = "Balaji Vault Employee"
ENTRY = "Balaji Vault Entry"
IDLE_SECONDS = 300

def eligible():
    return frappe.session.user != "Guest" and (frappe.session.user == "Administrator" or ROLE in frappe.get_roles())

def key(kind):
    raw = frappe.session.user + ":" + (frappe.session.sid or "")
    return "balaji_vault:" + kind + ":" + hashlib.sha256(raw.encode()).hexdigest()

def require():
    if not eligible() or not frappe.cache().get_value(key("open")):
        frappe.throw("Vault is locked.", frappe.PermissionError)
    frappe.cache().set_value(key("open"), True, expires_in_sec=IDLE_SECONDS)

def audit(event, record_id=""):
    frappe.get_doc({"doctype":"Balaji Vault Audit", "actor":frappe.session.user, "event":event, "record_id":record_id}).insert(ignore_permissions=True)

def company_names():
    return frappe.get_list("Company", pluck="name", page_length=100)

def get_employee(name):
    doc=frappe.get_doc(EMPLOYEE,name)
    if not frappe.has_permission("Company","read",doc=doc.company):
        frappe.throw("Company access required.",frappe.PermissionError)
    return doc

def validate_document(doc, method=None):
    require()

def validate_file(doc, method=None):
    if doc.attached_to_doctype in (EMPLOYEE, ENTRY):
        require()
        if not doc.is_private:
            frappe.throw("Vault documents must be private.")

def setup():
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc({"doctype":"Role", "role_name":ROLE, "desk_access":1}).insert(ignore_permissions=True)
    for email in ("info@balaji.my", "admin@balaji.my"):
        if frappe.db.exists("User", email):
            user=frappe.get_doc("User", email)
            if ROLE not in [row.role for row in user.roles]:
                user.append("roles", {"role":ROLE})
                user.save(ignore_permissions=True)
    if not frappe.conf.get("balaji_vault_file_key"):
        from cryptography.fernet import Fernet
        from frappe.installer import update_site_config
        update_site_config("balaji_vault_file_key", Fernet.generate_key().decode())
    if not frappe.conf.get("balaji_vault_password_hash"):
        value=Path(frappe.get_app_path("balaji_hr", "vault_bootstrap_hash.txt")).read_text().strip()
        from frappe.installer import update_site_config
        update_site_config("balaji_vault_password_hash", value)

@frappe.whitelist(methods=["POST"])
def unlock(password):
    if not eligible():
        frappe.throw("Access denied.", frappe.PermissionError)
    # Failure counters are per account, independent of session changes.
    bucket="balaji_vault:fail:" + hashlib.sha256(frappe.session.user.encode()).hexdigest()
    attempts=int(frappe.cache().get(frappe.cache().make_key(bucket)) or 0)
    if attempts >= 5:
        frappe.throw("Too many attempts. Try again after 15 minutes.", frappe.AuthenticationError)
    if not verify(password, frappe.conf.get("balaji_vault_password_hash")):
        # Atomic Redis counter prevents concurrent attempts bypassing the limit.
        redis_key=frappe.cache().make_key(bucket)
        attempts=frappe.cache().incr(redis_key)
        if attempts == 1:
            frappe.cache().expire(redis_key, 900)
        frappe.throw("Incorrect password.", frappe.AuthenticationError)
    frappe.cache().delete_value(bucket)
    frappe.cache().set_value(key("open"), True, expires_in_sec=IDLE_SECONDS)
    audit("unlock")
    return {"idle_seconds":IDLE_SECONDS}

@frappe.whitelist(methods=["POST"])
def lock():
    frappe.cache().delete_value(key("open"))
    return True

@frappe.whitelist(methods=["POST"])
def keepalive():
    require()
    return True

@frappe.whitelist()
def overview():
    require()
    companies=company_names()
    rows=frappe.get_all(EMPLOYEE, filters={"company":["in",companies]}, fields=["name","employee_name","category","department","designation","company"], order_by="modified desc", limit_page_length=500) if companies else []
    return {"employees":rows, "companies":companies, "idle_seconds":IDLE_SECONDS}

@frappe.whitelist()
def employee(name):
    require()
    doc=get_employee(name)
    audit("read_employee", doc.name)
    fields=[df.fieldname for df in frappe.get_meta(EMPLOYEE).fields]
    return {"name":doc.name, "modified":doc.modified, **{k:doc.get(k) for k in fields}}

@frappe.whitelist(methods=["POST"])
def save_employee(data):
    require()
    data=frappe.parse_json(data)
    if not isinstance(data, dict):
        frappe.throw("Invalid employee data.")
    name=data.get("name")
    doc=get_employee(name) if name else frappe.new_doc(EMPLOYEE)
    if name and str(doc.modified) != str(data.get("modified")):
        frappe.throw("This employee changed. Reload before saving.")
    if data.get("category") == "Other" and frappe.session.user != "Administrator" and "Balaji HR All Categories" not in frappe.get_roles():
        frappe.throw("Other category access required.", frappe.PermissionError)
    if data.get("category") not in ("Local","Foreign","Other"):
        frappe.throw("Choose an employee category.")
    if not frappe.has_permission("Company", "read", doc=data.get("company")):
        frappe.throw("Company access required.", frappe.PermissionError)
    for df in frappe.get_meta(EMPLOYEE).fields:
        if df.fieldtype not in ("Section Break","Column Break","Attach") and df.fieldname in data:
            doc.set(df.fieldname,data[df.fieldname])
    if not (doc.employee_name or "").strip():
        frappe.throw("Employee Name is required.")
    if flt(doc.salary)<0 or flt(doc.leave_entitlement)<0:
        frappe.throw("Salary and leave entitlement cannot be negative.")
    doc.save(ignore_permissions=True)
    audit("save_employee",doc.name)
    return {"name":doc.name,"modified":doc.modified}

@frappe.whitelist()
def entries(employee_name=None, from_date=None, to_date=None, entry_type=None):
    require()
    companies=company_names()
    allowed_rows=frappe.get_all(EMPLOYEE,filters={"company":["in",companies]},fields=["name","employee_name"],limit_page_length=0) if companies else []
    names={row.name:row.employee_name for row in allowed_rows}
    if employee_name and employee_name not in names:
        frappe.throw("Employee access denied.",frappe.PermissionError)
    if not names:
        return {"rows":[],"limit":1000,"totals":{"days":0,"amount":0}}
    filters={"employee":["in",list(names)]}
    if employee_name:filters["employee"]=employee_name
    if entry_type:
        if entry_type not in ("Attendance","Leave","Salary","Note"):frappe.throw("Invalid entry type.")
        filters["entry_type"]=entry_type
    if from_date and to_date:
        if getdate(to_date)<getdate(from_date):frappe.throw("Invalid date range.")
        filters["entry_date"]=["between",[from_date,to_date]]
    elif from_date:filters["entry_date"]=[">=",from_date]
    elif to_date:filters["entry_date"]=["<=",to_date]
    rows=frappe.get_all(ENTRY, filters=filters, fields=["name","employee","entry_date","entry_type","status","days","amount","notes"],order_by="entry_date desc",limit_page_length=1000)
    for row in rows:row["employee_name"]=names.get(row.employee, "")
    audit("read_report")
    return {"rows":rows,"limit":1000,"totals":{"days":sum(flt(x.days) for x in rows),"amount":sum(flt(x.amount) for x in rows)}}

@frappe.whitelist(methods=["POST"])
def save_entry(data):
    require()
    data=frappe.parse_json(data)
    allowed={"employee","entry_date","entry_type","status","days","amount","notes"}
    if not isinstance(data,dict):frappe.throw("Invalid entry.")
    if data.get("entry_type") not in ("Attendance","Leave","Salary","Note"):frappe.throw("Invalid entry type.")
    if flt(data.get("days"))<0 or flt(data.get("amount"))<0:frappe.throw("Days and amount cannot be negative.")
    get_employee(data.get("employee"))
    doc=frappe.get_doc({"doctype":ENTRY, **{k:v for k,v in data.items() if k in allowed}})
    doc.insert(ignore_permissions=True)
    audit("save_entry",doc.name)
    return doc.name

@frappe.whitelist(methods=["POST"])
def upload_passport(employee_name):
    require()
    employee=get_employee(employee_name)
    file=frappe.request.files.get("file")
    if not file:frappe.throw("Choose a file.")
    content=file.read(10*1024*1024+1)
    if len(content)>10*1024*1024:frappe.throw("Maximum upload is 10 MB.")
    from werkzeug.utils import secure_filename
    name=secure_filename(file.filename or "passport")
    if not name.lower().endswith((".png",".jpg",".jpeg",".pdf")):
        frappe.throw("Choose a PNG, JPG or PDF.")
    if not (content.startswith(b"%PDF-") or content.startswith(b"\x89PNG\r\n\x1a\n") or content.startswith(b"\xff\xd8\xff")):
        frappe.throw("File content must be a PDF, PNG or JPEG.")
    from cryptography.fernet import Fernet
    from frappe.utils.file_manager import save_file
    # Even a native File-owner download yields ciphertext after the vault locks.
    encrypted=Fernet(frappe.conf.balaji_vault_file_key.encode()).encrypt(content)
    saved=save_file("vault-" + frappe.generate_hash(length=16) + ".bin",encrypted,EMPLOYEE,employee.name,is_private=1)
    employee.passport_copy=saved.file_url
    employee.save(ignore_permissions=True)
    audit("upload_passport",employee.name)
    return True

@frappe.whitelist()
def download_passport(employee_name):
    require()
    employee=get_employee(employee_name)
    if not employee.passport_copy:frappe.throw("No passport copy uploaded.")
    name=frappe.db.get_value("File", {"file_url":employee.passport_copy,"attached_to_doctype":EMPLOYEE,"attached_to_name":employee.name,"is_private":1},"name")
    if not name:frappe.throw("Private attachment not found.")
    file=frappe.get_doc("File",name)
    audit("download_passport",employee.name)
    frappe.db.commit()
    from cryptography.fernet import Fernet
    encrypted=file.get_content()
    if isinstance(encrypted,str):encrypted=encrypted.encode()
    content=Fernet(frappe.conf.balaji_vault_file_key.encode()).decrypt(encrypted)
    extension=".pdf" if content.startswith(b"%PDF-") else ".png" if content.startswith(b"\x89PNG") else ".jpg"
    frappe.local.response.filename="passport-copy" + extension
    frappe.local.response.filecontent=content
    frappe.local.response.type="download"
    frappe.local.response.display_content_as="attachment"
