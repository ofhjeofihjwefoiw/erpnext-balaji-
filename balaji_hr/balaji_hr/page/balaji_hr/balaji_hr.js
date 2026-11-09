frappe.pages["balaji-hr"].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: "People & workplace", single_column: true});
    page.main.addClass("balaji-dashboard");
    window.balajiHR.dashboard(page.main);
};
