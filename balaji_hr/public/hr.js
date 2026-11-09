(() => {
  const esc = value => frappe.utils.escape_html(String(value ?? ""));
  const state = {data: null, ready: null};
  function load() {
    if (!state.ready) state.ready = frappe.call("balaji_hr.api.bootstrap").then(r => {
      const data=r.message;
      const hidden=new Set(["Balaji Employee Private","Balaji Vault Employee","Balaji Vault Entry","Balaji Vault Audit"]);
      data.catalog=(data.catalog || []).filter(row=>!hidden.has(row.name));
      data.reports=(data.reports || []).filter(row=>!hidden.has(row.ref_doctype));
      data.expiry=[];
      return state.data=data;
    }).catch(e => {state.ready = null; throw e;});
    return state.ready;
  }
  function go(dt, filters = {}) {
    const item = state.data?.catalog.find(x => x.name === dt);
    if (item?.issingle) frappe.set_route("Form", dt, dt);
    else {frappe.route_options = filters; frappe.set_route("List", dt);}
  }
  function shell(data) {
    if (document.getElementById("balaji-shell")) return;
    const shell = $(`<div id="balaji-shell"><header><button class="balaji-menu" aria-label="Toggle HR navigation">☰</button><a class="balaji-brand" href="/app/balaji-hr"><b>B</b><span>BALAJI <strong>People</strong></span></a><span class="balaji-workspace">MALAYSIA HR WORKSPACE</span><button class="balaji-search">Search records <kbd>Ctrl + G</kbd></button><button class="balaji-help">Help</button><button class="balaji-account" title="Account">${esc(data.user)}</button></header><aside><a class="balaji-home" href="/app/balaji-hr">◈ &nbsp; Overview</a><div class="balaji-nav-groups"></div><footer><span class="balaji-live"></span> Connected to ERPNext HRMS<br><small>Permissions apply to every record</small></footer></aside></div>`).appendTo(document.body);
    shell.find(".balaji-menu").on("click", () => document.body.classList.toggle("balaji-nav-open"));
    shell.find(".balaji-search").on("click", () => {document.body.classList.remove("balaji-active"); $(".navbar .search-bar input, .navbar .awesomplete input").first().trigger("focus");});
    shell.find(".balaji-account").on("click", () => frappe.set_route("Form", "User", frappe.session.user));
    shell.find(".balaji-help").on("click", () => frappe.msgprint("Use the sidebar to open HR lists. New, Save, Submit, workflow actions and reports use your existing HRMS rules. Malaysia contribution rates and leave policies must be configured by your HR/payroll team."));
    const groups = {};
    for (const item of data.catalog) (groups[item.module] ||= []).push(item);
    const priorities = ["Employee", "Attendance", "Leave Application", "Salary Slip"];
    const fav = $("<section><h6>QUICK ACCESS</h6></section>").appendTo(shell.find(".balaji-nav-groups"));
    priorities.forEach(dt => {if (data.catalog.some(x => x.name === dt)) button(dt, fav);});
    Object.keys(groups).sort().forEach(group => {
      const section = $("<details><summary></summary><div></div></details>").appendTo(shell.find(".balaji-nav-groups"));
      section.find("summary").text(group);
      groups[group].sort((a,b) => a.name.localeCompare(b.name)).forEach(item => button(item.name, section.find("div")));
    });
    const reportButton = $("<button class='balaji-nav'>Reports directory</button>").appendTo(shell.find(".balaji-nav-groups"));
    reportButton.on("click", () => {frappe.set_route("balaji-hr"); setTimeout(() => document.querySelector("#balaji-reports")?.scrollIntoView({behavior:"smooth"}), 300);});
  }
  function button(dt, container) {
    $("<button class='balaji-nav'></button>").text(dt).attr("data-balaji-doctype", dt).appendTo(container).on("click", () => {go(dt); document.body.classList.remove("balaji-nav-open");});
  }
  async function route() {
    if (!frappe.session || frappe.session.user === "Guest") return;
    try {
      const data = await load();
      const r = frappe.get_route();
      const active = r[0] === "balaji-hr" || (["Form", "List", "Tree"].includes(r[0]) && data.catalog.some(x => x.name === r[1])) || (r[0] === "query-report" && (data.reports || []).some(x => x.name === r[1]));
      document.body.classList.toggle("balaji-active", active);
      if (!active) return;
      shell(data);
      document.querySelectorAll("[data-balaji-doctype]").forEach(el => el.classList.toggle("selected", el.dataset.balajiDoctype === r[1]));
    } catch(e) { console.warn("Balaji HR navigation unavailable", e); }
  }
  window.balajiHR = {
    async dashboard(container) {
      const target = $(container).empty();
      target.html("<div class='balaji-loading'>Loading your HR workspace…</div>");
      try {
        const data = await load();
        await route();
        target.empty();
        const welcome = $("<div class='balaji-welcome'><div><span class='balaji-eyebrow'>YOUR PEOPLE, IN ONE PLACE</span><h1>A clearer view of your workplace.</h1><p>Manage your team, time and HR operations.</p></div><button class='btn btn-primary balaji-new-employee'>Add employee ↗</button></div>").appendTo(target);
        welcome.find("button").on("click", () => frappe.new_doc("Employee"));
        if (!frappe.model.can_create("Employee")) welcome.find("button").hide();
        const cards = $("<div class='balaji-cards'></div>").appendTo(target);
        data.cards.forEach(card => $("<button class='balaji-card'><span></span><strong></strong><small>View records ↗</small></button>").appendTo(cards).on("click", () => go(card.doctype, card.filters)).find("span").text(card.label).end().find("strong").text(card.value));
        const row = $("<div class='balaji-columns'><section class='balaji-panel'><div class='balaji-panel-title'><h3>HR operations</h3><span>Quick actions</span></div><div class='balaji-action-grid'></div></section><section class='balaji-panel balaji-expiry'><div class='balaji-panel-title'><h3>Documents due soon</h3><span>Next 90 days</span></div></section></div>").appendTo(target);
        const actions = {"Employee":"Manage your people", "Attendance":"Daily attendance", "Leave Application":"Requests & approvals", "Salary Slip":"Payroll & payslips", "Shift Assignment":"Work schedules", "Expense Claim":"Claims & reimbursements"};
        Object.entries(actions).forEach(([dt, detail]) => {if(data.catalog.some(x => x.name === dt)) $("<button><b></b><span></span><i>↗</i></button>").appendTo(row.find(".balaji-action-grid")).on("click", () => go(dt)).find("b").text(dt).end().find("span").text(detail);});
        const expiry = row.find(".balaji-expiry");
        if (!data.expiry.length) expiry.append("<div class='balaji-empty'>No upcoming expiries available to your account.</div>");
        data.expiry.sort((a,b) => a.date.localeCompare(b.date)).slice(0,8).forEach(item => $("<button class='balaji-expiry-row'><b></b><span></span><time></time></button>").appendTo(expiry).on("click", () => frappe.set_route("Form", "Balaji Employee Private", item.name)).find("b").text(item.employee).end().find("span").text(item.kind).end().find("time").text(frappe.datetime.str_to_user(item.date)));
        const directory = $("<section class='balaji-panel'><div class='balaji-panel-title'><h3>All HR screens</h3><span>Available for your role</span></div><input class='form-control balaji-directory-search' placeholder='Find an HR screen…' aria-label='Find an HR screen'><div class='balaji-directory'></div></section>").appendTo(target);
        data.catalog.forEach(item => {const el = $("<button><b></b><small></small></button>").attr("data-search", item.name.toLowerCase()).appendTo(directory.find(".balaji-directory")).on("click", () => go(item.name));el.find("b").text(item.name);el.find("small").text(item.module + (item.issingle ? " · Settings" : " · List & form"));});
        directory.find("input").on("input", function(){const q=this.value.toLowerCase();directory.find("[data-search]").each(function(){$(this).toggle(this.dataset.search.includes(q));});});
        const reports = $("<section id='balaji-reports' class='balaji-panel'><div class='balaji-panel-title'><h3>Reports</h3><span>Report permissions are checked when opened</span></div><div class='balaji-directory'></div></section>").appendTo(target);
        (data.reports || []).forEach(report => $("<button><b></b><small></small></button>").appendTo(reports.find(".balaji-directory")).on("click", () => (report.report_type === "Report Builder" ? frappe.set_route("List", report.ref_doctype, "Report", report.name) : frappe.set_route("query-report", report.name))).find("b").text(report.name).end().find("small").text(report.ref_doctype || "HR report"));
        $("<button class='btn btn-default'>Refresh dashboard</button>").appendTo(target).on("click", () => {state.ready=null;window.balajiHR.dashboard(container);});
      } catch(e) {target.empty().append($("<p class='text-danger'></p>").text("Could not load the HR workspace. Check your access and browser console."));}
    }
  };
  frappe.router.on("change", route);
  $(document).ready(route);
})();
