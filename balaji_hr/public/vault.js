(() => {
  "use strict";
  if(window.__balajiVaultInstalled)return;
  window.__balajiVaultInstalled=true;
  const standalone = document.querySelector("[data-balaji-vault-token]");
  const csrfToken = () => standalone?.dataset.balajiVaultToken || window.frappe?.csrf_token || "";
  const base = "/api/method/balaji_hr.vault.";
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  let presses=0, last=0, shiftDown=false, overlay=null, timer=null, employees=[], companies=[], current=null, opened=false;
  let generation=0, lastPing=0;
  async function rpc(method, data={}) {
    const response = await fetch(base+method, {method:"POST",credentials:"same-origin",cache:"no-store",headers:{"Content-Type":"application/json","X-Frappe-CSRF-Token":csrfToken()},body:JSON.stringify(data)});
    let result={};try{result=await response.json();}catch{}
    if(!response.ok || result.exc) {
      if(opened && response.status===403) close();
      let message="Request failed. Check your access and try again.";
      try{const parts=JSON.parse(result._server_messages || "[]");if(parts[0]) message=JSON.parse(parts[0]).message.replace(/<[^>]*>/g,"");}catch{}
      throw new Error(message);
    }
    return result.message;
  }
  function element(tag, attrs={}, text) {const el=document.createElement(tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));if(text!==undefined)el.textContent=text;return el;}
  function error(message) {const el=overlay?.querySelector(".bv-error");if(el)el.textContent=message;}
  function touch(){if(!opened)return;clearTimeout(timer);timer=setTimeout(close,300000);if(Date.now()-lastPing>45000){lastPing=Date.now();rpc("keepalive").catch(()=>close());}}
  function clearMemory(){employees=[];companies=[];current=null;}
  function close(){generation++;opened=false;clearTimeout(timer);overlay?.remove();overlay=null;clearMemory();fetch(base+"lock",{method:"POST",credentials:"same-origin",cache:"no-store",keepalive:true,headers:{"Content-Type":"application/json","X-Frappe-CSRF-Token":csrfToken()},body:"{}"}).catch(()=>{});}
  function openPrompt(){
    if(overlay || (!standalone && (!window.frappe || frappe.session?.user==="Guest")))return;
    overlay=element("div",{id:"balaji-vault-overlay"});
    overlay.innerHTML=`<div class="bv-unlock"><div class="bv-lock-symbol">◈</div><span class="bv-eyebrow">SECURE ACCESS</span><h1>Enter your password</h1><p>Unlock your private workspace.</p><form><label>Password<input type="password" name="password" required autocomplete="current-password" maxlength="200"></label><p class="bv-error" role="alert"></p><button class="bv-primary" type="submit">Unlock workspace →</button><button type="button" class="bv-cancel">Cancel</button></form></div>`;
    document.body.appendChild(overlay);
    overlay.querySelector(".bv-cancel").onclick=close;
    overlay.querySelector("input").focus();
    overlay.querySelector("form").onsubmit=async event=>{
      event.preventDefault();const input=overlay.querySelector("input");const button=overlay.querySelector(".bv-primary");button.disabled=true;
      let password=input.value;input.value="";const stamp=generation;
      try{await rpc("unlock",{password});password="";if(stamp!==generation){await rpc("lock");return;}opened=true;touch();await home();}
      catch(e){password="";if(stamp===generation){error(e.message);button.disabled=false;input.focus();}}
    };
  }
  function frame(title,subtitle){
    if(!overlay || !opened)return null;
    overlay.innerHTML=`<div class="bv-app"><aside class="bv-side"><div class="bv-wordmark"><b>B</b><span>BALAJI<strong>Private workspace</strong></span></div><div class="bv-access">SESSION UNLOCKED</div><nav><button data-view="home">Overview</button><button data-view="employees">Employees</button><button data-view="entries">Add HR entry</button><button data-view="reports">Employee reports</button></nav><div class="bv-side-bottom">Locks after 5 minutes of inactivity<br>or when this tab is hidden.<button class="bv-lock-now">Lock workspace</button></div></aside><main><header><div><span class="bv-eyebrow">PRIVATE COMPANY RECORDS</span><h1>${escape(title)}</h1><p>${escape(subtitle)}</p></div><button class="bv-lock-now bv-lock-top">Lock & close ↗</button></header><p class="bv-error" role="alert"></p><div class="bv-content"></div></main></div>`;
    overlay.querySelectorAll(".bv-lock-now").forEach(x=>x.onclick=close);
    overlay.querySelectorAll("[data-view]").forEach(x=>x.onclick=()=>guard(async()=>{current=null;const view=x.dataset.view;if(view==="home")await home();if(view==="employees")await employeeList();if(view==="entries")entryForm();if(view==="reports")await reports();}));
    overlay.onpointerdown=touch;overlay.onkeydown=touch;
    return overlay.querySelector(".bv-content");
  }
  async function guard(fn){try{touch();await fn();}catch(e){error(e.message);}}
  async function refresh(){const stamp=generation;const data=await rpc("overview");if(!opened || stamp!==generation)return false;employees=data.employees;companies=data.companies;return true;}
  async function home(){
    if(!await refresh())return;
    const root=frame("Your private HR overview","Employee details, HR entries and reports in one protected workspace.");if(!root)return;
    root.innerHTML=`<div class="bv-stats"><article><span>Private employees</span><strong>${employees.length}</strong><small>First 500 records maximum</small></article><article><span>Local employees</span><strong>${employees.filter(x=>x.category==="Local").length}</strong></article><article><span>Foreign employees</span><strong>${employees.filter(x=>x.category==="Foreign").length}</strong></article><article><span>Other employees</span><strong>${employees.filter(x=>x.category==="Other").length}</strong></article></div><section class="bv-panel"><h2>Quick access</h2><div class="bv-actions"><button data-action="new"><b>Add private employee</b><span>Only your requested details</span></button><button data-action="list"><b>Employee directory</b><span>Search and update private records</span></button><button data-action="entry"><b>Add HR entry</b><span>Attendance, leave, salary or note</span></button><button data-action="report"><b>Employee reports</b><span>Filter by employee, date and type</span></button></div></section><section class="bv-panel"><h2>Recent private employees</h2><div class="bv-recent"></div></section>`;
    root.querySelector('[data-action="new"]').onclick=()=>employeeForm();
    root.querySelector('[data-action="list"]').onclick=()=>guard(employeeList);
    root.querySelector('[data-action="entry"]').onclick=entryForm;
    root.querySelector('[data-action="report"]').onclick=()=>guard(reports);
    renderEmployees(root.querySelector(".bv-recent"),employees.slice(0,6));
  }
  function renderEmployees(root,rows){
    root.innerHTML=rows.length?`<div class="bv-table-scroll"><table><thead><tr><th>Employee</th><th>Category</th><th>Department</th><th>Position / designation</th><th></th></tr></thead><tbody>${rows.map(x=>`<tr><td><b>${escape(x.employee_name)}</b><small>${escape(x.company)}</small></td><td><span class="bv-pill">${escape(x.category)}</span></td><td>${escape(x.department)}</td><td>${escape(x.designation)}</td><td><button data-id="${escape(x.name)}">Open ↗</button></td></tr>`).join("")}</tbody></table></div>`:'<div class="bv-empty">No private employees yet. Add your first employee to begin.</div>';
    root.querySelectorAll("[data-id]").forEach(x=>x.onclick=()=>guard(async()=>{const stamp=generation;const record=await rpc("employee",{name:x.dataset.id});if(opened && stamp===generation)employeeForm(record);}));
  }
  async function employeeList(){
    if(!await refresh())return;
    const root=frame("Private employees","These records are stored separately from the normal HRMS Employee list.");
    root.innerHTML='<div class="bv-toolbar"><input placeholder="Search name, category or department" aria-label="Search private employees"><button class="bv-primary">Add employee +</button></div><section class="bv-panel"><div class="bv-list"></div></section>';
    renderEmployees(root.querySelector(".bv-list"),employees);
    root.querySelector("button").onclick=()=>employeeForm();
    root.querySelector("input").oninput=event=>renderEmployees(root.querySelector(".bv-list"),employees.filter(x=>[x.employee_name,x.category,x.department].join(" ").toLowerCase().includes(event.target.value.toLowerCase())));
  }
  const fields=[
    ["employee_name","Employee Name","text",true],["company","Company","company",true],["category","Employee Category","category",true],["department","Department"],["designation","Designation"],["position","Position"],["salary","Salary (MYR)","number"],
    ["permit_number","Permit Details"],["permit_expiry_date","Permit Expiry Date","date"],["visa_number","Visa Details"],["visa_expiry_date","Visa Expiry Date","date"],["passport_number","Passport Number"],["passport_expiry_date","Passport Expiry Date","date"],
    ["epf_no","EPF Number"],["eis_no","EIS Number"],["socso_no","SOCSO Number"],["pcb_no","PCB / Tax Reference"],["leave_policy","Leave Policy"],["leave_entitlement","Annual Leave Entitlement","number"]
  ];
  function employeeForm(record={}){
    current=record;const root=frame(record.name?record.employee_name:"New private employee","A simplified employee form. No extra ERPNext fields.");
    root.innerHTML=`<form class="bv-panel bv-employee-form"><h2>Employee details</h2><div class="bv-grid">${fields.map(([key,label,type="text",required=false])=>`<label>${escape(label)}${required?' <em>*</em>':''}${type==="company"||type==="category"?`<select name="${key}" ${required?'required':''}>${(type==="company"?companies:["Local","Foreign","Other"]).map(value=>`<option value="${escape(value)}" ${value===(record[key] || (type==="company"?companies[0]:"Local"))?'selected':''}>${escape(value)}</option>`).join("")}</select>`:`<input name="${key}" type="${type}" value="${escape(record[key])}" ${type==="number"?'step="0.01" min="0"':''} ${required?'required':''}>`}</label>`).join("")}</div><div class="bv-form-footer"><span>Only authorised vault users can save these records.</span><button class="bv-primary" type="submit">Save employee →</button></div></form><section class="bv-panel"><h2>Passport copy</h2>${record.name?'<label>Private image or PDF (maximum 10 MB)<input type="file" class="bv-upload" accept=".png,.jpg,.jpeg,.pdf"></label>':'<p>Save this employee first, then attach their passport copy.</p>'}${record.passport_copy?'<button class="bv-download">Download passport copy</button>':''}</section>`;
    root.querySelector("form").onsubmit=event=>{event.preventDefault();guard(async()=>{const data=Object.fromEntries(new FormData(event.target));if(current.name){data.name=current.name;data.modified=current.modified;}const stamp=generation;const saved=await rpc("save_employee",{data});if(!opened||stamp!==generation)return;const updated=await rpc("employee",{name:saved.name});if(opened&&stamp===generation)employeeForm(updated);});};
    const upload=root.querySelector(".bv-upload");if(upload)upload.onchange=()=>guard(async()=>{if(!upload.files[0])return;const stamp=generation;const form=new FormData();form.append("file",upload.files[0]);form.append("employee_name",current.name);const response=await fetch(base+"upload_passport",{method:"POST",credentials:"same-origin",cache:"no-store",headers:{"X-Frappe-CSRF-Token":csrfToken()},body:form});if(!response.ok)throw new Error("Upload failed. Check file type, size and vault access.");const record=await rpc("employee",{name:current.name});if(opened&&stamp===generation)employeeForm(record);});
    const download=root.querySelector(".bv-download");if(download)download.onclick=()=>guard(async()=>{const response=await fetch(base+"download_passport?employee_name="+encodeURIComponent(current.name),{credentials:"same-origin",cache:"no-store"});if(!response.ok)throw new Error("Download denied or vault locked.");const blob=await response.blob();const url=URL.createObjectURL(blob);const a=element("a",{href:url,download:"passport-copy"});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  }
  function employeeOptions(){return employees.map(x=>`<option value="${escape(x.name)}">${escape(x.employee_name)}</option>`).join("");}
  function entryForm(){
    const root=frame("Add private HR entry","Manual private attendance, leave, salary and notes. These do not post to standard HRMS payroll.");
    root.innerHTML=`<form class="bv-panel"><div class="bv-grid"><label>Employee<select name="employee" required><option value="">Choose employee</option>${employeeOptions()}</select></label><label>Date<input type="date" name="entry_date" required value="${new Date().toISOString().slice(0,10)}"></label><label>Entry Type<select name="entry_type"><option>Attendance</option><option>Leave</option><option>Salary</option><option>Note</option></select></label><label>Status<select name="status"><option></option><option>Present</option><option>Absent</option><option>Half Day</option><option>Approved</option><option>Pending</option><option>Paid</option></select></label><label>Days<input type="number" name="days" step="0.5" min="0"></label><label>Amount (MYR)<input type="number" name="amount" step="0.01" min="0"></label><label class="bv-wide">Notes<textarea name="notes" rows="4"></textarea></label></div><div class="bv-form-footer"><span>Stored only in the private register.</span><button class="bv-primary">Save entry →</button></div></form>`;
    root.querySelector("form").onsubmit=event=>{event.preventDefault();guard(async()=>{await rpc("save_entry",{data:Object.fromEntries(new FormData(event.target))});if(opened)await reports();});};
  }
  async function reports(){
    const root=frame("Private employee reports","Filter private HR entries. No data is exported automatically.");
    root.innerHTML=`<section class="bv-panel"><form class="bv-report-filters"><label>Employee<select name="employee_name"><option value="">All private employees</option>${employeeOptions()}</select></label><label>From<input type="date" name="from_date"></label><label>To<input type="date" name="to_date"></label><label>Type<select name="entry_type"><option value="">All types</option><option>Attendance</option><option>Leave</option><option>Salary</option><option>Note</option></select></label><button class="bv-primary">Show report</button></form></section><section class="bv-panel bv-report-results"></section>`;
    const form=root.querySelector("form");const results=root.querySelector(".bv-report-results");
    const run=async()=>{const stamp=generation;const data=await rpc("entries",Object.fromEntries(new FormData(form)));if(!opened||stamp!==generation)return;results.innerHTML=`<div class="bv-report-summary"><b>${data.rows.length} entries</b><span>Total recorded days: ${escape(data.totals.days)}</span><span>Total recorded amount: MYR ${Number(data.totals.amount).toFixed(2)}</span></div><p class="bv-report-note">Days/amount totals span the selected entry types. Choose a single type for a specific report. Maximum ${data.limit} rows.</p><div class="bv-table-scroll"><table><thead><tr><th>Date</th><th>Employee</th><th>Type</th><th>Status</th><th>Days</th><th>Amount</th><th>Notes</th></tr></thead><tbody>${data.rows.map(row=>`<tr><td>${escape(row.entry_date)}</td><td>${escape(row.employee_name)}</td><td>${escape(row.entry_type)}</td><td>${escape(row.status)}</td><td>${escape(row.days)}</td><td>${escape(row.amount)}</td><td>${escape(row.notes)}</td></tr>`).join("")}</tbody></table>${data.rows.length?'':'<div class="bv-empty">No entries for this selection.</div>'}</div>`;};
    form.onsubmit=event=>{event.preventDefault();guard(run);};await run();
  }
  // Shortcut v0.2.1: capture before Desk handlers, including when an input has focus.
  window.addEventListener("keydown",event=>{
    if(event.key==="Escape" && overlay){event.preventDefault();event.stopImmediatePropagation();close();return;}
    if(event.repeat || overlay)return;
    const key=event.key;
    const now=Date.now();
    if(key==="Shift" || event.code==="ShiftLeft" || event.code==="ShiftRight"){
      presses=now-last<8000?presses+1:1;
      last=now;
      if(presses>5)presses=1;
      return;
    }
    if(key==="Enter" && presses===5 && now-last<8000){
      presses=0;
      event.preventDefault();
      event.stopImmediatePropagation?.();
      openPrompt();
      return;
    }
    presses=0;
  },true);
  document.addEventListener("visibilitychange",()=>{if(document.hidden && overlay)close();});
  window.addEventListener("pagehide",()=>{if(overlay)close();});
})();
