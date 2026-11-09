app_name = "balaji_hr"
app_title = "Balaji HR"
app_publisher = "Balaji HR"
app_description = "Custom Malaysia HR workspace"
app_email = ""
app_license = "MIT"
required_apps = ["erpnext", "hrms"]
app_include_js = ["/assets/balaji_hr/desk_v021.js"]
app_include_css = ["/assets/balaji_hr/desk_v021.css"]
after_install = "balaji_hr.setup.install"
after_migrate = "balaji_hr.setup.install"
doc_events = {
    "Employee": {"validate": "balaji_hr.security.validate_employee",
                 "on_update": "balaji_hr.leave.sync_assignment"},
    "Balaji Employee Private": {"validate": "balaji_hr.security.validate_private"},
    "File": {"validate": ["balaji_hr.security.validate_file", "balaji_hr.vault.validate_file"]},
    "Balaji Vault Employee": {"validate": "balaji_hr.vault.validate_document"},
    "Balaji Vault Entry": {"validate": "balaji_hr.vault.validate_document"},
}

# Vault intentionally has no native DocType role permissions.
