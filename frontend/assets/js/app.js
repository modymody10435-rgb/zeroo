const API = "/api";

const state = {
  user: null,
  meta: null,
  route: "dashboard",
  params: {},
  products: [],
  categoryItems: [],
  categoryConfig: null,
  orders: [],
  selectedOrderNo: "",
  currentOrder: null,
  authority: null,
  authorityTab: "overview",
  reportKind: "movements",
  reportFilters: { date_from: "", date_to: "", category: "", search: "" },
};

const ROUTES = {
  dashboard: { title: "الرئيسية", subtitle: "نظرة عامة على حركة المخزن", icon: "dashboard", render: renderDashboard },
  withdraw: { title: "صرف صنف", subtitle: "تسجيل عملية صرف وخصمها من الرصيد", icon: "arrow", render: renderWithdraw },
  orders: { title: "طلبات المعمل", subtitle: "إنشاء الطلبات وصرف بنودها على دفعات", icon: "orders", render: renderOrders },
  inventory: { title: "كل الأصناف", subtitle: "إدارة المخزون والأصناف", icon: "box", render: (p) => renderCategoryPage(p, { category: "", title: "كل الأصناف", subtitle: "إدارة المخزون والأصناف", addLabel: "إضافة صنف" }) },
  pcr: { title: "قسم PCR", subtitle: "أجهزة ومستلزمات PCR", icon: "pcr", render: (p) => renderCategoryPage(p, { category: "PCR", title: "قسم PCR", subtitle: "أجهزة ومستلزمات PCR", addLabel: "إضافة جهاز PCR" }) },
  chemicals: { title: "قسم الكيماويات", subtitle: "المواد الكيميائية وتواريخ الانتهاء", icon: "chemical", render: (p) => renderCategoryPage(p, { category: "كيماويات", title: "قسم الكيماويات", subtitle: "المواد الكيميائية وتواريخ الانتهاء", addLabel: "إضافة مادة كيميائية" }) },
  office: { title: "قسم المكتبية", subtitle: "الأصناف المكتبية والكراتين", icon: "office", render: (p) => renderCategoryPage(p, { category: "المكتبية", title: "قسم المكتبية", subtitle: "الأصناف المكتبية والكراتين", addLabel: "إضافة صنف مكتبي" }) },
  computer: { title: "مستلزمات الكمبيوتر", subtitle: "الأجهزة والملحقات ومكان التخزين", icon: "computer", render: (p) => renderCategoryPage(p, { category: "مستلزمات الكمبيوتر", title: "مستلزمات الكمبيوتر", subtitle: "الأجهزة والملحقات ومكان التخزين", addLabel: "إضافة مستلزم" }) },
  authority: { title: "استمارات الهيئة", subtitle: "الوارد والصرف والرصيد المتاح", icon: "authority", render: renderAuthority },
  decommission: { title: "تكهين الأجهزة", subtitle: "تسجيل الأجهزة المكهنة", icon: "trash", render: renderDecommission },
  reports: { title: "التقارير", subtitle: "حركة المخزن والسحوبات والأرصدة", icon: "report", render: renderReports },
  users: { title: "إدارة المستخدمين", subtitle: "الحسابات والصلاحيات", icon: "users", render: renderUsers },
};

const CATEGORY_CLASS = {
  "عام": "badge",
  "PCR": "badge badge-blue",
  "كيماويات": "badge badge-amber",
  "المكتبية": "badge badge-teal",
  "مستلزمات الكمبيوتر": "badge badge-green",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

function fmtNum(value, digits = 2) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "0";
  return parsed.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function fmtDate(value) {
  const text = String(value || "").trim();
  if (!text) return "—";
  return text.replace("T", " ").slice(0, 16);
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function badge(text, cls = "") {
  return `<span class="badge ${cls}">${esc(text)}</span>`;
}

function categoryBadge(category) {
  return `<span class="${CATEGORY_CLASS[category] || "badge"}">${esc(category || "عام")}</span>`;
}

function productStateBadge(product) {
  if (product.device_status === "مكهن") return badge("مكهّن", "badge-red");
  if (Number(product.current_stock) <= 0) return badge("نافد", "badge-red");
  if (product.is_low) return badge("مخزون منخفض", "badge-amber");
  return badge("متاح", "badge-green");
}

function icon(name) {
  const paths = {
    dashboard: '<path d="M4 13h6V4H4zm10 7h6V11h-6zM4 20h6v-4H4zm10-9h6V4h-6z"/>',
    box: '<path d="m21 8-9-5-9 5 9 5 9-5Z"/><path d="m3 8 9 5 9-5"/><path d="M12 13v8"/><path d="M3 8v8l9 5 9-5V8"/>',
    arrow: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
    orders: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
    pcr: '<path d="M9 3h6"/><path d="M10 3v6l-4 9a3 3 0 0 0 2.7 4.3h6.6A3 3 0 0 0 18 18l-4-9V3"/><path d="M7.5 15h9"/>',
    chemical: '<path d="M9 3h6"/><path d="M10 3v6L5 19a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 19l-5-10V3"/><path d="M7 16h10"/>',
    office: '<path d="M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><path d="M8 9h8M8 13h5"/>',
    computer: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    authority: '<path d="M6 3h9l3 3v15H6z"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2M19 6l-1 15H6L5 6"/><path d="M10 11v6M14 11v6"/>',
    report: '<path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 16v-5M12 16V7M16 16v-8"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    close: '<path d="M18 6 6 18M6 6l12 12"/>',
    check: '<path d="m20 6-11 11-5-5"/>',
    download: '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
    warning: '<path d="M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
    refresh: '<path d="M20 11a8.1 8.1 0 0 0-15.5-2M4 4v5h5"/><path d="M4 13a8.1 8.1 0 0 0 15.5 2M20 20v-5h-5"/>',
    arrowLeft: '<path d="M19 12H5"/><path d="m11 18-6-6 6-6"/>',
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.box}</svg>`;
}

async function api(path, options = {}) {
  const method = options.method || "GET";
  const headers = { "X-Requested-With": "XMLHttpRequest" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`${API}${path}`, {
    method,
    credentials: "same-origin",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  const text = await response.text();
  let data = {};
  if (text) {
    try { data = JSON.parse(text); } catch { data = { detail: text }; }
  }
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/login")) showLogin();
    throw new Error(data.detail || `تعذر تنفيذ الطلب (${response.status})`);
  }
  return data;
}

function toast(message, type = "success") {
  const root = $("#toast-root");
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  root.appendChild(node);
  window.setTimeout(() => node.remove(), 4200);
}

function loadingHTML(message = "جارٍ تحميل البيانات...") {
  return `<div class="loading"><span class="spinner"></span><span>${esc(message)}</span></div>`;
}

function closeModal() {
  const root = $("#modal-root");
  root.hidden = true;
  root.innerHTML = "";
}

function openModal({ title, body, submitText = "حفظ", cancelText = "إلغاء", onSubmit, wide = false, danger = false, hideSubmit = false }) {
  const root = $("#modal-root");
  root.hidden = false;
  root.innerHTML = `
    <div class="modal ${wide ? "modal-wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <form id="modal-form">
        <div class="modal-header">
          <h2>${esc(title)}</h2>
          <button type="button" class="modal-close" id="modal-close" aria-label="إغلاق">×</button>
        </div>
        <div class="modal-body">
          ${body}
          <p id="modal-error" class="form-error" hidden></p>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" id="modal-cancel">${esc(cancelText)}</button>
          ${hideSubmit ? "" : `<button type="submit" class="btn ${danger ? "btn-danger" : "btn-primary"}" id="modal-submit">${esc(submitText)}</button>`}
        </div>
      </form>
    </div>
  `;
  $("#modal-close").onclick = closeModal;
  $("#modal-cancel").onclick = closeModal;
  root.onclick = (event) => { if (event.target === root) closeModal(); };
  const form = $("#modal-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = $("#modal-error");
    const button = $("#modal-submit");
    error.hidden = true;
    if (button) { button.disabled = true; button.dataset.label = button.textContent; button.textContent = "جارٍ التنفيذ..."; }
    try {
      await onSubmit(new FormData(form), form);
      closeModal();
    } catch (err) {
      error.textContent = err.message || "تعذر تنفيذ العملية.";
      error.hidden = false;
    } finally {
      if (button) { button.disabled = false; button.textContent = button.dataset.label || submitText; }
    }
  });
}

function confirmModal({ title, message, confirmText = "تأكيد", onConfirm, danger = true }) {
  openModal({
    title,
    body: `<div class="alert ${danger ? "alert-danger" : "alert-warning"}">${esc(message)}</div>`,
    submitText: confirmText,
    danger,
    onSubmit: async () => { await onConfirm(); },
  });
}

function setPage(title, subtitle) {
  $("#page-title").textContent = title;
  $("#page-subtitle").textContent = subtitle;
}

function buildNav() {
  const groups = [
    {
      label: "الرئيسية",
      items: [
        { route: "dashboard", label: "لوحة التحكم", icon: "dashboard" },
        { route: "withdraw", label: "صرف صنف", icon: "arrow" },
        { route: "orders", label: "طلبات المعمل", icon: "orders" },
      ],
    },
    {
      label: "الأقسام",
      items: [
        { route: "inventory", label: "كل الأصناف", icon: "box" },
        { route: "pcr", label: "قسم PCR", icon: "pcr" },
        { route: "chemicals", label: "الكيماويات", icon: "chemical" },
        { route: "office", label: "المكتبية", icon: "office" },
        { route: "computer", label: "مستلزمات الكمبيوتر", icon: "computer" },
        { route: "authority", label: "استمارات الهيئة", icon: "authority" },
        { route: "decommission", label: "تكهين الأجهزة", icon: "trash" },
      ],
    },
    {
      label: "النظام",
      items: [
        { route: "reports", label: "التقارير", icon: "report" },
        ...(state.user?.role === "admin" ? [{ route: "users", label: "المستخدمون", icon: "users" }] : []),
      ],
    },
  ];
  $("#nav").innerHTML = groups.map((group) => `
    <div class="nav-section">${esc(group.label)}</div>
    ${group.items.map((item) => `
      <button type="button" class="nav-link ${state.route === item.route ? "active" : ""}" data-nav="${item.route}">
        ${icon(item.icon)}<span>${esc(item.label)}</span>
      </button>
    `).join("")}
  `).join("");
}

function updateActiveNav() {
  $$(".nav-link").forEach((link) => {
    const active = link.dataset.nav === state.route;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [route, query] = raw.split("?");
  return { route: route || "dashboard", params: Object.fromEntries(new URLSearchParams(query || "")) };
}

function navigate(route, params = {}) {
  const query = new URLSearchParams(params).toString();
  const target = `#/${route}${query ? `?${query}` : ""}`;
  if (location.hash === target) renderRoute();
  else location.hash = target;
}

function handleNavigation(event) {
  const link = event.target.closest("[data-nav]");
  if (!link) return;
  event.preventDefault();
  document.body.classList.remove("sidebar-open");
  navigate(link.dataset.nav);
}

function showLogin() {
  state.user = null;
  $("#app-view").hidden = true;
  $("#login-view").hidden = false;
  $("#login-error").hidden = true;
  $("#login-username").focus();
}

function showApp() {
  $("#login-view").hidden = true;
  $("#app-view").hidden = false;
  const username = state.user?.username || "";
  $("#user-name").textContent = username || "-";
  $("#user-role").textContent = state.user?.role === "admin" ? "مدير النظام" : "مستخدم";
  $("#user-avatar").textContent = username.slice(0, 1).toUpperCase() || "م";
}

async function enterApp() {
  if (!state.meta) state.meta = await api("/meta");
  showApp();
  buildNav();
  await renderRoute();
}

async function renderRoute() {
  const parsed = parseHash();
  let route = ROUTES[parsed.route] ? parsed.route : "dashboard";
  if (route === "users" && state.user?.role !== "admin") {
    toast("إدارة المستخدمين متاحة للمدير فقط.", "warn");
    route = "dashboard";
  }
  state.route = route;
  state.params = parsed.params;
  updateActiveNav();
  const definition = ROUTES[route];
  setPage(definition.title, definition.subtitle);
  $("#page-content").innerHTML = loadingHTML();
  try {
    await definition.render(parsed.params);
  } catch (err) {
    $("#page-content").innerHTML = `
      <div class="card">
        <div class="empty-state">
          <strong>تعذر تحميل الصفحة</strong>
          <p>${esc(err.message || "حدث خطأ غير متوقع.")}</p>
          <button type="button" class="btn btn-primary" data-action="refresh-page">إعادة المحاولة</button>
        </div>
      </div>`;
    if (err.message) toast(err.message, "error");
  }
}

function productByCode(code) {
  return state.products.find((item) => String(item.product_code).toLowerCase() === String(code).toLowerCase());
}

function categoryStorage(category) {
  return state.meta?.category_storage?.[category] || "";
}

function productOptions(products, selected = "", includeEmpty = true) {
  const options = products.map((product) => `
    <option value="${esc(product.product_code)}" ${String(product.product_code) === String(selected) ? "selected" : ""}>
      ${esc(product.product_name)} — ${esc(product.product_code)} (${fmtNum(product.current_stock)})
    </option>
  `).join("");
  return `${includeEmpty ? '<option value="">اختر الصنف...</option>' : ""}${options}`;
}

function statusOptions(selected = "") {
  return `<option value="">بدون حالة</option>${(state.meta?.device_statuses || []).map((status) => `<option value="${esc(status)}" ${status === selected ? "selected" : ""}>${esc(status)}</option>`).join("")}`;
}

function conditionOptions(selected = "") {
  return `<option value="">بدون تصنيف</option>${(state.meta?.device_conditions || []).map((condition) => `<option value="${esc(condition)}" ${condition === selected ? "selected" : ""}>${esc(condition)}</option>`).join("")}`;
}

function field(label, name, value = "", options = {}) {
  const type = options.type || "text";
  const attrs = [
    `name="${esc(name)}"`,
    `id="${esc(options.id || `field-${name}`)}"`,
    type ? `type="${esc(type)}"` : "",
    options.required ? "required" : "",
    options.disabled ? "disabled" : "",
    options.readonly ? "readonly" : "",
    options.min !== undefined ? `min="${esc(options.min)}"` : "",
    options.max !== undefined ? `max="${esc(options.max)}"` : "",
    options.step !== undefined ? `step="${esc(options.step)}"` : "",
    options.placeholder ? `placeholder="${esc(options.placeholder)}"` : "",
    options.autocomplete ? `autocomplete="${esc(options.autocomplete)}"` : "",
  ].filter(Boolean).join(" ");
  if (options.selectOptions !== undefined) {
    return `<label class="field"><span>${esc(label)}</span><select ${attrs}>${options.selectOptions}</select>${options.hint ? `<small>${esc(options.hint)}</small>` : ""}</label>`;
  }
  if (type === "textarea") {
    return `<label class="field"><span>${esc(label)}</span><textarea ${attrs}>${esc(value)}</textarea>${options.hint ? `<small>${esc(options.hint)}</small>` : ""}</label>`;
  }
  return `<label class="field"><span>${esc(label)}</span><input ${attrs} value="${esc(value ?? "")}">${options.hint ? `<small>${esc(options.hint)}</small>` : ""}</label>`;
}

async function renderDashboard() {
  const data = await api("/dashboard");
  const categoryEntries = Object.entries(data.category_counts || {}).sort((a, b) => b[1] - a[1]);
  const maxCategory = Math.max(1, ...categoryEntries.map(([, count]) => count));
  $("#page-content").innerHTML = `
    <div class="page-stack">
      <div class="grid grid-4">
        <article class="stat-card">
          <span class="stat-icon">${icon("box")}</span>
          <div><span class="stat-value">${fmtNum(data.total_products, 0)}</span><span class="stat-label">إجمالي الأصناف</span><div class="stat-hint">${fmtNum(data.total_stock)} وحدة في المخزن</div></div>
        </article>
        <article class="stat-card">
          <span class="stat-icon warn">${icon("warning")}</span>
          <div><span class="stat-value">${fmtNum(data.low_stock_count, 0)}</span><span class="stat-label">أصناف منخفضة</span><div class="stat-hint">تحتاج إعادة طلب</div></div>
        </article>
        <article class="stat-card">
          <span class="stat-icon info">${icon("orders")}</span>
          <div><span class="stat-value">${fmtNum(data.open_orders, 0)}</span><span class="stat-label">طلبات مفتوحة</span><div class="stat-hint">${fmtNum(data.pending_items, 0)} بند قيد الصرف</div></div>
        </article>
        <article class="stat-card">
          <span class="stat-icon">${icon("authority")}</span>
          <div><span class="stat-value">${fmtNum(data.authority_forms_count)}</span><span class="stat-label">رصيد استمارات الهيئة</span><div class="stat-hint">إجمالي العدد المتاح</div></div>
        </article>
      </div>

      <div class="grid grid-2">
        <section class="card">
          <div class="section-head"><div><h2>توزيع الأصناف</h2><p>عدد الأصناف داخل كل قسم</p></div><button class="btn btn-secondary btn-sm" data-nav="inventory">عرض المخزون</button></div>
          ${categoryEntries.length ? `<div class="progress-list">${categoryEntries.map(([category, count]) => `
            <div class="progress-row">
              <div class="progress-row-head"><span>${esc(category)}</span><strong>${fmtNum(count, 0)}</strong></div>
              <div class="progress-track"><div class="progress-fill" style="width:${Math.max(4, (count / maxCategory) * 100)}%"></div></div>
            </div>`).join("")}</div>` : `<div class="empty-state"><strong>لا توجد أصناف بعد</strong><p>ابدأ بإضافة أول صنف إلى المخزن.</p></div>`}
        </section>
        <section class="card">
          <div class="section-head"><div><h2>إجراءات سريعة</h2><p>الوصول المباشر للعمليات المتكررة</p></div></div>
          <div class="grid grid-2">
            <button class="btn btn-primary" type="button" data-nav="withdraw">${icon("arrow")} صرف صنف</button>
            <button class="btn btn-secondary" type="button" data-nav="orders">${icon("orders")} طلبية جديدة</button>
            <button class="btn btn-secondary" type="button" data-nav="authority">${icon("authority")} استمارات الهيئة</button>
            <button class="btn btn-secondary" type="button" data-nav="reports">${icon("report")} التقارير</button>
          </div>
          <div class="alert" style="margin-top:16px">واجهة مستقلة تعتمد على SQLite. جميع العمليات تُسجّل فوراً في قاعدة البيانات المحلية على الخادم.</div>
        </section>
      </div>

      <section class="card card-flush">
        <div class="card-header"><div><h2>آخر الحركات</h2><p class="small muted">أحدث العمليات المسجلة في المخزن</p></div><button class="btn btn-secondary btn-sm" data-nav="reports">كل الحركات</button></div>
        <div class="table-wrap">${movementsTable(data.recent_movements || [])}</div>
      </section>
    </div>`;
}

function movementsTable(items) {
  if (!items.length) return `<div class="table-empty"><strong>لا توجد حركات</strong>لم تُسجّل أي حركة مخزن بعد.</div>`;
  return `<table>
    <thead><tr><th>الحركة</th><th>التاريخ</th><th>النوع</th><th>الصنف</th><th class="num">الكمية</th><th class="num">الرصيد</th><th>الشخص</th></tr></thead>
    <tbody>${items.map((item) => `
      <tr>
        <td class="mono">${esc(item.movement_no)}</td>
        <td class="small">${esc(fmtDate(item.movement_date))}</td>
        <td>${badge(item.movement_type, "badge-teal")}</td>
        <td><div class="cell-main"><strong>${esc(item.product_name)}</strong><small>${esc(item.product_code)}</small></div></td>
        <td class="num">${fmtNum(item.qty)}</td>
        <td class="num">${fmtNum(item.balance_after)}</td>
        <td class="small">${esc(item.person || "—")}</td>
      </tr>`).join("")}</tbody>
  </table>`;
}

async function renderCategoryPage(params, config) {
  const query = config.category ? `?category=${encodeURIComponent(config.category)}` : "";
  const data = await api(`/products${query}`);
  state.categoryConfig = config;
  state.categoryItems = data.items || [];
  const addCategory = config.category || "عام";
  $("#page-content").innerHTML = `
    <div class="page-stack">
      <div class="page-actions">
        <button class="btn btn-primary" type="button" data-action="add-product">${icon("plus")} ${esc(config.addLabel || "إضافة صنف")}</button>
        <button class="btn btn-secondary" type="button" data-action="refresh-page">${icon("refresh")} تحديث</button>
      </div>
      <section class="card card-flush">
        <div class="card-header">
          <div><h2>${esc(config.title)}</h2><p class="small muted" id="products-count">${fmtNum(state.categoryItems.length, 0)} صنف</p></div>
          <div class="toolbar">
            <label class="search-field">${icon("search")}<input id="product-search" type="search" placeholder="بحث بالاسم أو الكود..."></label>
            ${config.category ? "" : `<label class="field" style="min-width:170px"><span>القسم</span><select id="category-filter"><option value="">كل الأقسام</option>${(state.meta?.categories || []).map((category) => `<option value="${esc(category)}">${esc(category)}</option>`).join("")}</select></label>`}
            <label class="checkbox" style="padding-top:22px"><input id="low-filter" type="checkbox"> منخفض فقط</label>
          </div>
        </div>
        <div class="table-wrap" id="products-table-wrap">${productsTable(state.categoryItems, config)}</div>
      </section>
    </div>`;
  const applyFilters = () => {
    const search = ($("#product-search")?.value || "").trim().toLowerCase();
    const lowOnly = Boolean($("#low-filter")?.checked);
    const category = $("#category-filter")?.value || "";
    const filtered = state.categoryItems.filter((item) => {
      const matchesSearch = !search || [item.product_name, item.product_code, item.serial_number, item.notes, item.storage_location].some((value) => String(value || "").toLowerCase().includes(search));
      const matchesLow = !lowOnly || item.is_low;
      const matchesCategory = !category || item.category === category;
      return matchesSearch && matchesLow && matchesCategory;
    });
    $("#products-table-wrap").innerHTML = productsTable(filtered, config);
    $("#products-count").textContent = `${fmtNum(filtered.length, 0)} صنف`;
  };
  $("#product-search")?.addEventListener("input", applyFilters);
  $("#low-filter")?.addEventListener("change", applyFilters);
  $("#category-filter")?.addEventListener("change", applyFilters);
  state.categoryConfig = { ...config, addCategory };
}

function productsTable(items, config) {
  if (!items.length) {
    const messages = {
      "PCR": "أضف أجهزة PCR من زر الإضافة أعلى الصفحة.",
      "كيماويات": "أضف المواد الكيميائية وتواريخ انتهائها.",
      "المكتبية": "أضف الأصناف المكتبية وعدد الوحدات داخل الكرتونة.",
      "مستلزمات الكمبيوتر": "أضف الأجهزة والملحقات مع المواصفات أو الرقم التسلسلي.",
    };
    return `<div class="table-empty"><strong>لا توجد أصناف في هذا القسم</strong>${esc(messages[config.category] || "ابدأ بإضافة صنف جديد إلى المخزن.")}</div>`;
  }
  const isAll = !config.category;
  return `<table>
    <thead><tr>
      <th>الصنف</th>${isAll ? "<th>القسم</th>" : ""}<th class="num">الرصيد</th><th>الوحدة</th><th>الموقع</th>
      ${config.category === "PCR" ? "<th>الحالة</th><th>الرقم التسلسلي</th>" : ""}
      ${config.category === "كيماويات" ? "<th>الشركة</th><th>الانتهاء</th>" : ""}
      ${config.category === "المكتبية" ? "<th class=\"num\">وحدات/كرتونة</th><th>آخر سحب</th>" : ""}
      ${config.category === "مستلزمات الكمبيوتر" ? "<th>الحالة</th><th>الرقم التسلسلي</th>" : ""}
      <th>الوضع</th><th>إجراءات</th>
    </tr></thead>
    <tbody>${items.map((item) => `
      <tr>
        <td><div class="cell-main"><strong>${esc(item.product_name)}</strong><small class="mono">${esc(item.product_code)}</small></div></td>
        ${isAll ? `<td>${categoryBadge(item.category)}</td>` : ""}
        <td class="num"><strong>${fmtNum(item.current_stock)}</strong></td>
        <td class="small">${esc(item.unit || "—")}</td>
        <td class="small">${esc(item.storage_location || "—")}</td>
        ${config.category === "PCR" ? `<td>${badge(item.device_status || "—", item.device_status === "مكهن" ? "badge-red" : "badge-teal")}</td><td class="small mono">${esc(item.serial_number || "—")}</td>` : ""}
        ${config.category === "كيماويات" ? `<td class="small">${esc(item.manufacturer || "—")}</td><td class="small">${esc(item.expiry_date || "—")}</td>` : ""}
        ${config.category === "المكتبية" ? `<td class="num">${fmtNum(item.units_per_carton)}</td><td class="small">${esc(item.last_withdraw_date ? fmtDate(item.last_withdraw_date) : "—")}</td>` : ""}
        ${config.category === "مستلزمات الكمبيوتر" ? `<td>${badge(item.device_status || "—", "badge-blue")}</td><td class="small mono">${esc(item.serial_number || "—")}</td>` : ""}
        <td>${productStateBadge(item)}</td>
        <td class="actions">
          <button class="btn btn-secondary btn-icon" type="button" title="تعديل" data-action="edit-product" data-code="${esc(item.product_code)}">${icon("edit")}</button>
          ${item.current_stock > 0 ? `<button class="btn btn-soft btn-icon" type="button" title="صرف" data-action="withdraw-product" data-code="${esc(item.product_code)}">${icon("arrow")}</button>` : ""}
          <button class="btn btn-danger btn-icon" type="button" title="حذف" data-action="delete-product" data-code="${esc(item.product_code)}">${icon("trash")}</button>
        </td>
      </tr>`).join("")}</tbody>
  </table>`;
}

function openProductModal(product = null, category = "") {
  const isEdit = Boolean(product);
  const value = product || {};
  const selectedCategory = value.category || category || "عام";
  const body = `
    <div class="stack">
      <div class="field-row">
        ${field("كود الصنف", "product_code", value.product_code || "", { required: true, disabled: isEdit, placeholder: "مثال: 4021" })}
        ${field("اسم الصنف", "product_name", value.product_name || "", { required: true, placeholder: "اسم الصنف" })}
      </div>
      <div class="field-row">
        ${field("القسم", "category", selectedCategory, { selectOptions: (state.meta?.categories || []).map((item) => `<option value="${esc(item)}" ${item === selectedCategory ? "selected" : ""}>${esc(item)}</option>`).join("") })}
        ${field("الوحدة", "unit", value.unit || "", { placeholder: "علبة / كيس / جهاز..." })}
      </div>
      <div class="field-row-3">
        ${field("الرصيد الحالي", "current_stock", value.current_stock ?? 0, { type: "number", min: 0, step: "any", hint: isEdit ? "تعديل الرصيد يسجل حركة تسوية." : "" })}
        ${field("الحد الأدنى", "min_stock", value.min_stock ?? 0, { type: "number", min: 0, step: "any" })}
        ${field("الرقم التسلسلي", "serial_number", value.serial_number || "", { placeholder: "اختياري" })}
      </div>
      <div class="field-row">
        ${field("مكان التخزين", "storage_location", value.storage_location || "", { placeholder: categoryStorage(selectedCategory) || "مكان التخزين" })}
        ${field("تاريخ الإضافة", "date_added", (value.date_added || today()).slice(0, 10), { type: "date" })}
      </div>
      <div class="field-row">
        ${field("الشركة المصنعة", "manufacturer", value.manufacturer || "")}
        ${field("المورد", "supplier", value.supplier || "")}
      </div>
      <div class="field-row">
        ${field("تاريخ الانتهاء", "expiry_date", (value.expiry_date || "").slice(0, 10), { type: "date" })}
        ${field("تاريخ الشراء", "purchase_date", (value.purchase_date || "").slice(0, 10), { type: "date" })}
      </div>
      <div class="field-row-3">
        ${field("حالة الجهاز", "device_status", value.device_status || "", { selectOptions: statusOptions(value.device_status || "") })}
        ${field("تصنيف الجهاز", "device_condition", value.device_condition || "", { selectOptions: conditionOptions(value.device_condition || "") })}
        ${field("وحدات داخل الكرتونة", "units_per_carton", value.units_per_carton ?? 0, { type: "number", min: 0, step: "any" })}
      </div>
      <div class="field-row">
        ${field("آخر تاريخ سحب", "last_withdraw_date", (value.last_withdraw_date || "").slice(0, 10), { type: "date" })}
        ${field("ملاحظات", "notes", value.notes || "", { type: "textarea" })}
      </div>
    </div>`;
  openModal({
    title: isEdit ? `تعديل ${value.product_name}` : "إضافة صنف جديد",
    body,
    wide: true,
    submitText: isEdit ? "حفظ التعديل" : "إضافة الصنف",
    onSubmit: async (formData) => {
      const payload = {};
      for (const [key, raw] of formData.entries()) payload[key] = raw;
      ["current_stock", "min_stock", "units_per_carton"].forEach((key) => { payload[key] = Number(payload[key] || 0); });
      if (isEdit) {
        await api(`/products/${encodeURIComponent(value.product_code)}`, { method: "PUT", body: payload });
        toast("تم حفظ تعديلات الصنف.");
      } else {
        await api("/products", { method: "POST", body: payload });
        toast("تمت إضافة الصنف إلى المخزن.");
      }
      await renderRoute();
    },
  });
}

function deleteProduct(code) {
  const product = productByCode(code) || state.categoryItems.find((item) => item.product_code === code);
  confirmModal({
    title: "حذف الصنف",
    message: `سيتم حذف «${product?.product_name || code}» نهائياً من المخزن. ستبقى سجلات الحركة والسحب التاريخية محفوظة.`,
    confirmText: "حذف نهائي",
    onConfirm: async () => {
      await api(`/products/${encodeURIComponent(code)}?force=true`, { method: "DELETE" });
      toast("تم حذف الصنف.");
      await renderRoute();
    },
  });
}

async function renderWithdraw(params) {
  const [productsData, withdrawalsData] = await Promise.all([
    api("/products"),
    api("/withdrawals?limit=20"),
  ]);
  state.products = productsData.items || [];
  const preselected = params.code || "";
  const selected = productByCode(preselected);
  $("#page-content").innerHTML = `
    <div class="split">
      <section class="card">
        <div class="section-head"><div><h2>تسجيل عملية صرف</h2><p>اختر الصنف أو أدخل الاسم والكود يدوياً.</p></div></div>
        <form id="withdraw-form" class="stack" novalidate>
          ${field("اختيار سريع للصنف", "quick_product", selected?.product_code || "", { selectOptions: productOptions(state.products, selected?.product_code || "") })}
          <div class="field-row">
            ${field("اسم الصنف", "product_name", selected?.product_name || "", { required: true, placeholder: "اسم الصنف" })}
            ${field("كود الصنف", "product_code", selected?.product_code || "", { required: true, placeholder: "كود الصنف" })}
          </div>
          <div class="product-picker" id="withdraw-preview">
            <div class="product-preview"><div><strong>لم يتم اختيار صنف</strong><small>سيظهر الرصيد المتاح هنا.</small></div><span class="preview-stock">—</span></div>
          </div>
          <div class="field-row-3">
            ${field("الكمية", "qty", "", { type: "number", min: 0.01, step: "any", required: true })}
            ${field("تاريخ السحب", "withdraw_date", today(), { type: "date" })}
            ${field("اسم الساحب / المستخدم", "person", state.user?.username || "", { required: true })}
          </div>
          <div class="field-row">
            ${field("المسؤول / المشرف", "supervisor", "", { placeholder: "اختياري" })}
            ${field("ملاحظات", "notes", "", { type: "textarea" })}
          </div>
          <p id="withdraw-error" class="form-error" hidden></p>
          <button class="btn btn-primary btn-block" type="submit">${icon("check")} تأكيد الصرف</button>
        </form>
      </section>
      <section class="card card-flush">
        <div class="card-header"><div><h2>آخر عمليات الصرف</h2><p class="small muted">أحدث 20 عملية مسجلة</p></div></div>
        <div class="table-wrap">${withdrawalsTable(withdrawalsData.items || [])}</div>
      </section>
    </div>`;
  const form = $("#withdraw-form");
  const nameInput = form.elements.product_name;
  const codeInput = form.elements.product_code;
  const quick = form.elements.quick_product;
  const preview = $("#withdraw-preview");
  const renderPreview = () => {
    const code = codeInput.value.trim();
    const name = nameInput.value.trim();
    const product = state.products.find((item) => String(item.product_code).toLowerCase() === code.toLowerCase())
      || state.products.find((item) => String(item.product_name).toLowerCase() === name.toLowerCase());
    if (!product) {
      preview.innerHTML = `<div class="product-preview"><div><strong>${esc(name || "لم يتم اختيار صنف")}</strong><small>${esc(code || "أدخل الكود أو اختر من القائمة")}</small></div><span class="preview-stock">—</span></div>`;
      return;
    }
    preview.innerHTML = `
      <div class="product-preview">
        <div><strong>${esc(product.product_name)}</strong><small>${esc(product.category)} · ${esc(product.storage_location || "بدون موقع")} · ${esc(product.product_code)}</small></div>
        <span class="preview-stock">${fmtNum(product.current_stock)}</span>
      </div>
      ${product.is_low ? '<div class="alert alert-warning">هذا الصنف عند الحد الأدنى أو أقل.</div>' : ""}`;
    const qty = form.elements.qty;
    qty.max = String(product.current_stock);
  };
  const applyProduct = (product) => {
    if (!product) return;
    nameInput.value = product.product_name;
    codeInput.value = product.product_code;
    quick.value = product.product_code;
    renderPreview();
  };
  quick.addEventListener("change", () => applyProduct(productByCode(quick.value)));
  codeInput.addEventListener("input", () => {
    const match = state.products.find((item) => String(item.product_code).toLowerCase() === codeInput.value.trim().toLowerCase());
    if (match) { nameInput.value = match.product_name; quick.value = match.product_code; }
    renderPreview();
  });
  nameInput.addEventListener("input", () => {
    const matches = state.products.filter((item) => String(item.product_name).toLowerCase() === nameInput.value.trim().toLowerCase());
    if (matches.length === 1) { codeInput.value = matches[0].product_code; quick.value = matches[0].product_code; }
    renderPreview();
  });
  renderPreview();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = $("#withdraw-error");
    error.hidden = true;
    const payload = {
      product_name: nameInput.value.trim(),
      product_code: codeInput.value.trim(),
      qty: Number(form.elements.qty.value || 0),
      person: form.elements.person.value.trim(),
      supervisor: form.elements.supervisor.value.trim(),
      withdraw_date: form.elements.withdraw_date.value,
      notes: form.elements.notes.value.trim(),
    };
    try {
      const result = await api("/withdrawals", { method: "POST", body: payload });
      toast(`تم صرف ${fmtNum(result.qty)} من ${result.product_name}. الرصيد: ${fmtNum(result.balance_after)}${result.is_low ? " (مخزون منخفض)" : ""}`, result.is_low ? "warn" : "success");
      await renderRoute();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  });
}

function withdrawalsTable(items) {
  if (!items.length) return `<div class="table-empty"><strong>لا توجد سحوبات</strong>لم تُسجّل أي عملية صرف بعد.</div>`;
  return `<table>
    <thead><tr><th>التاريخ</th><th>الصنف</th><th class="num">الكمية</th><th>الساحب</th><th>المسؤول</th><th>ملاحظات</th><th></th></tr></thead>
    <tbody>${items.map((item) => `
      <tr>
        <td class="small">${esc(fmtDate(item.withdraw_date))}</td>
        <td><div class="cell-main"><strong>${esc(item.product_name)}</strong><small>${esc(item.product_code)}</small></div></td>
        <td class="num">${fmtNum(item.qty)}</td>
        <td class="small">${esc(item.withdrawn_by || "—")}</td>
        <td class="small">${esc(item.supervisor_name || "—")}</td>
        <td class="small">${esc(item.notes || "—")}</td>
        <td class="actions"><button class="btn btn-danger btn-icon" type="button" title="إلغاء السحب" data-action="delete-withdrawal" data-id="${esc(item.withdrawal_id)}">${icon("trash")}</button></td>
      </tr>`).join("")}</tbody>
  </table>`;
}

async function renderOrders(params) {
  const [data, productData] = await Promise.all([api("/orders"), api("/products")]);
  state.orders = data.items || [];
  state.products = productData.items || [];
  const requested = params.order || state.selectedOrderNo;
  const selected = state.orders.find((order) => order.order_no === requested) || state.orders[0];
  state.selectedOrderNo = selected?.order_no || "";
  $("#page-content").innerHTML = `
    <div class="page-stack">
      <div class="page-actions">
        <button class="btn btn-primary" type="button" data-action="add-order">${icon("plus")} طلبية جديدة</button>
        <button class="btn btn-secondary" type="button" data-action="refresh-page">${icon("refresh")} تحديث</button>
      </div>
      <div class="order-layout">
        <section class="card">
          <div class="section-head"><div><h2>الطلبات</h2><p>${fmtNum(state.orders.length, 0)} طلبية</p></div></div>
          <div class="order-list">
            ${state.orders.length ? state.orders.map((order) => `
              <button class="order-item ${order.order_no === state.selectedOrderNo ? "active" : ""}" type="button" data-action="open-order" data-order="${esc(order.order_no)}">
                <div class="order-item-top"><strong>${esc(order.order_no)}</strong>${badge(order.status, order.status === "مكتملة" ? "badge-green" : "badge-amber")}</div>
                <small>${esc(order.factory_name)} · ${esc(order.order_date)}</small>
                <small>${fmtNum(order.items_count, 0)} بند · متبقي ${fmtNum(order.remaining_qty)}</small>
              </button>`).join("") : `<div class="empty-state"><strong>لا توجد طلبات</strong><p>أنشئ أول طلبية للمعمل.</p></div>`}
          </div>
        </section>
        <section id="order-detail" class="card"><div class="loading"><span class="spinner"></span><span>اختر طلبية...</span></div></section>
      </div>
    </div>`;
  if (state.selectedOrderNo) await loadOrderDetail(state.selectedOrderNo);
}

async function loadOrderDetail(orderNo) {
  const order = await api(`/orders/${encodeURIComponent(orderNo)}`);
  state.currentOrder = order;
  state.selectedOrderNo = order.order_no;
  const detail = $("#order-detail");
  if (!detail) return;
  const completed = order.status === "مكتملة";
  detail.innerHTML = `
    <div class="card-header" style="padding:0 0 14px;border-bottom:0">
      <div><h2>${esc(order.order_no)} ${badge(order.status, completed ? "badge-green" : "badge-amber")}</h2><p class="small muted">${esc(order.factory_name)} · ${esc(order.order_date)} · المسؤول: ${esc(order.responsible_person)}</p></div>
      <div class="page-actions">
        ${completed ? `<button class="btn btn-secondary btn-sm" type="button" data-action="reopen-order" data-order="${esc(order.order_no)}">إعادة فتح</button>` : `<button class="btn btn-primary btn-sm" type="button" data-action="complete-order" data-order="${esc(order.order_no)}">إتمام الطلبية</button>`}
        <button class="btn btn-danger btn-sm" type="button" data-action="delete-order" data-order="${esc(order.order_no)}">حذف</button>
      </div>
    </div>
    ${order.notes ? `<div class="alert">${esc(order.notes)}</div>` : ""}
    <div class="table-wrap" style="margin-top:12px">${orderItemsTable(order)}</div>
    ${completed ? "" : `
      <form id="add-order-item-form" class="card" style="margin-top:16px;background:var(--surface-soft)">
        <div class="section-head"><h3>إضافة بند للطلبية</h3></div>
        <div class="field-row-3">
          ${field("الصنف", "product_code", "", { selectOptions: productOptions(state.products, "") })}
          ${field("الكمية المطلوبة", "required_qty", "", { type: "number", min: 0.01, step: "any", required: true })}
          ${field("الوحدة", "unit", "", { placeholder: "اختياري" })}
        </div>
        <p id="order-item-error" class="form-error" hidden style="margin-top:10px"></p>
        <button class="btn btn-primary btn-sm" type="submit" style="margin-top:10px">${icon("plus")} إضافة البند</button>
      </form>`}
  `;
  const addForm = $("#add-order-item-form");
  addForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = $("#order-item-error");
    error.hidden = true;
    try {
      await api(`/orders/${encodeURIComponent(order.order_no)}/items`, {
        method: "POST",
        body: {
          product_code: addForm.elements.product_code.value,
          required_qty: Number(addForm.elements.required_qty.value || 0),
          unit: addForm.elements.unit.value.trim(),
        },
      });
      toast("تمت إضافة البند للطلبية.");
      await renderRoute();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  });
}

function orderItemsTable(order) {
  if (!order.items.length) return `<div class="table-empty"><strong>لا توجد بنود</strong>أضف الأصناف المطلوبة لهذه الطلبية.</div>`;
  return `<table>
    <thead><tr><th>الصنف</th><th class="num">المطلوب</th><th class="num">المسحوب</th><th class="num">المتبقي</th><th>آخر سحب</th><th>إجراءات</th></tr></thead>
    <tbody>${order.items.map((item) => `
      <tr>
        <td><div class="cell-main"><strong>${esc(item.product_name)}</strong><small class="mono">${esc(item.product_code)}</small></div></td>
        <td class="num">${fmtNum(item.required_qty)}</td>
        <td class="num">${fmtNum(item.withdrawn_qty)}</td>
        <td class="num"><strong>${fmtNum(item.remaining_qty)}</strong></td>
        <td class="small">${esc(item.last_withdraw_date ? fmtDate(item.last_withdraw_date) : "—")}</td>
        <td class="actions">
          ${item.remaining_qty > 0 && order.status !== "مكتملة" ? `<button class="btn btn-soft btn-sm" type="button" data-action="withdraw-order-item" data-order="${esc(order.order_no)}" data-item="${esc(item.item_id)}">صرف</button>` : ""}
          ${item.withdrawn_qty === 0 && order.status !== "مكتملة" ? `<button class="btn btn-danger btn-icon" type="button" title="حذف البند" data-action="remove-order-item" data-order="${esc(order.order_no)}" data-item="${esc(item.item_id)}">${icon("trash")}</button>` : ""}
        </td>
      </tr>`).join("")}</tbody>
  </table>`;
}

function openOrderWithdrawModal(order, item) {
  const body = `
    <div class="stack">
      <div class="alert">المتبقي في الطلبية: <strong>${fmtNum(item.remaining_qty)}</strong></div>
      <div class="field-row">
        ${field("اسم الصنف", "product_name", item.product_name, { readonly: true })}
        ${field("كود الصنف", "product_code", item.product_code, { readonly: true })}
      </div>
      <div class="field-row-3">
        ${field("الكمية", "qty", "", { type: "number", min: 0.01, max: item.remaining_qty, step: "any", required: true })}
        ${field("تاريخ السحب", "withdraw_date", today(), { type: "date" })}
        ${field("اسم الساحب", "person", state.user?.username || "", { required: true })}
      </div>
      <div class="field-row">
        ${field("المسؤول / المشرف", "supervisor", "")}
        ${field("ملاحظات", "notes", "", { type: "textarea" })}
      </div>
    </div>`;
  openModal({
    title: `صرف من ${order.order_no}`,
    body,
    submitText: "تأكيد الصرف",
    onSubmit: async (formData) => {
      await api("/withdrawals", {
        method: "POST",
        body: {
          product_name: formData.get("product_name"),
          product_code: formData.get("product_code"),
          qty: Number(formData.get("qty") || 0),
          person: formData.get("person"),
          supervisor: formData.get("supervisor"),
          withdraw_date: formData.get("withdraw_date"),
          notes: formData.get("notes"),
          order_no: order.order_no,
          item_id: item.item_id,
        },
      });
      toast("تم تسجيل الصرف من الطلبية.");
      await renderRoute();
    },
  });
}

function openCreateOrderModal() {
  const body = `<div class="stack">
    <div class="field-row">
      ${field("تاريخ الطلبية", "order_date", today(), { type: "date" })}
      ${field("اسم المصنع / الجهة", "factory_name", "", { required: true })}
    </div>
    <div class="field-row">
      ${field("المسؤول", "responsible_person", "", { required: true })}
      ${field("ملاحظات", "notes", "", { type: "textarea" })}
    </div>
  </div>`;
  openModal({
    title: "طلبية جديدة",
    body,
    submitText: "إنشاء الطلبية",
    onSubmit: async (formData) => {
      const order = await api("/orders", {
        method: "POST",
        body: {
          order_date: formData.get("order_date"),
          factory_name: formData.get("factory_name"),
          responsible_person: formData.get("responsible_person"),
          notes: formData.get("notes"),
        },
      });
      state.selectedOrderNo = order.order_no;
      toast(`تم إنشاء الطلبية ${order.order_no}.`);
      await renderRoute();
    },
  });
}

async function renderAuthority() {
  state.authority = await api("/authority");
  const tabs = [
    ["overview", "نظرة عامة"],
    ["receipt", "تسجيل وارد"],
    ["withdraw", "تسجيل صرف"],
    ["logs", "السجلات"],
    ["delete", "حذف صنف"],
  ];
  $("#page-content").innerHTML = `
    <div class="page-stack">
      <div class="grid grid-3">
        <article class="stat-card"><span class="stat-icon">${icon("authority")}</span><div><span class="stat-value">${fmtNum(state.authority.count)}</span><span class="stat-label">إجمالي الرصيد</span><div class="stat-hint">استمارات الهيئة</div></div></article>
        <article class="stat-card"><span class="stat-icon info">${icon("box")}</span><div><span class="stat-value">${fmtNum(state.authority.items.length, 0)}</span><span class="stat-label">أصناف مسجلة</span><div class="stat-hint">في سجل الوارد</div></div></article>
        <article class="stat-card"><span class="stat-icon warn">${icon("orders")}</span><div><span class="stat-value">${fmtNum(state.authority.withdrawals.length, 0)}</span><span class="stat-label">عمليات صرف</span><div class="stat-hint">من إجمالي السجل</div></div></article>
      </div>
      <section class="card">
        <div class="tabs">${tabs.map(([key, label]) => `<button type="button" class="tab-button ${state.authorityTab === key ? "active" : ""}" data-action="authority-tab" data-tab="${key}">${esc(label)}</button>`).join("")}</div>
        <div id="authority-panel" class="tab-panel"></div>
      </section>
    </div>`;
  renderAuthorityPanel();
}

function renderAuthorityPanel() {
  const panel = $("#authority-panel");
  if (!panel) return;
  const tab = state.authorityTab;
  const snapshot = state.authority;
  if (tab === "overview") {
    panel.innerHTML = `
      <div class="section-head"><div><h2>أصناف استمارات الهيئة</h2><p>المتاح لكل صنف بعد خصم عمليات الصرف.</p></div><button class="btn btn-primary btn-sm" type="button" data-action="authority-tab" data-tab="receipt">${icon("plus")} تسجيل وارد</button></div>
      <div class="table-wrap">${authorityItemsTable(snapshot.items)}</div>`;
    return;
  }
  if (tab === "receipt") {
    panel.innerHTML = `<form id="authority-receipt-form" class="stack" style="max-width:760px">
      <div class="field-row">
        ${field("اسم الصنف", "item_name", "", { required: true })}
        ${field("كود الصنف", "item_code", "", { placeholder: "اختياري — سيُستخدم AUTHORITY_FORMS" })}
      </div>
      <div class="field-row-3">
        ${field("الكمية المستلمة", "qty", "", { type: "number", min: 0.01, step: "any", required: true })}
        ${field("تاريخ الاستلام", "receipt_date", today(), { type: "date" })}
        ${field("اسم المستلم", "receiver", state.user?.username || "", { required: true })}
      </div>
      ${field("ملاحظات", "notes", "", { type: "textarea" })}
      <p id="authority-error" class="form-error" hidden></p>
      <button class="btn btn-primary" type="submit">${icon("check")} تسجيل الوارد</button>
    </form>`;
    $("#authority-receipt-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const error = $("#authority-error");
      error.hidden = true;
      try {
        await api("/authority/receipts", {
          method: "POST",
          body: {
            item_name: form.elements.item_name.value,
            item_code: form.elements.item_code.value,
            qty: Number(form.elements.qty.value || 0),
            receipt_date: form.elements.receipt_date.value,
            receiver: form.elements.receiver.value,
            notes: form.elements.notes.value,
          },
        });
        toast("تم تسجيل وارد استمارات الهيئة.");
        await renderRoute();
      } catch (err) {
        error.textContent = err.message;
        error.hidden = false;
      }
    });
    return;
  }
  if (tab === "withdraw") {
    panel.innerHTML = `<form id="authority-withdraw-form" class="stack" style="max-width:760px">
      ${field("اختيار صنف متاح", "quick_item", "", { selectOptions: `<option value="">اختر الصنف...</option>${snapshot.items.filter((item) => item.available_qty > 0).map((item) => `<option value="${esc(`${item.item_name}|${item.item_code}`)}">${esc(item.item_name)} — ${esc(item.item_code)} (${fmtNum(item.available_qty)})</option>`).join("")}` })}
      <div class="field-row">
        ${field("اسم الصنف", "item_name", "", { required: true })}
        ${field("كود الصنف", "item_code", "", { required: true })}
      </div>
      <div class="field-row-3">
        ${field("الكمية المصروفة", "qty", "", { type: "number", min: 0.01, step: "any", required: true })}
        ${field("تاريخ الصرف", "withdrawal_date", today(), { type: "date" })}
        ${field("اسم المستخدم", "username", state.user?.username || "", { required: true })}
      </div>
      ${field("ملاحظات", "notes", "", { type: "textarea" })}
      <p id="authority-error" class="form-error" hidden></p>
      <button class="btn btn-primary" type="submit">${icon("arrow")} تسجيل الصرف</button>
    </form>`;
    const form = $("#authority-withdraw-form");
    form.elements.quick_item.addEventListener("change", () => {
      const [name, code] = form.elements.quick_item.value.split("|");
      if (name) form.elements.item_name.value = name;
      if (code) form.elements.item_code.value = code;
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const error = $("#authority-error");
      error.hidden = true;
      try {
        await api("/authority/withdrawals", {
          method: "POST",
          body: {
            item_name: form.elements.item_name.value,
            item_code: form.elements.item_code.value,
            qty: Number(form.elements.qty.value || 0),
            username: form.elements.username.value,
            withdrawal_date: form.elements.withdrawal_date.value,
            notes: form.elements.notes.value,
          },
        });
        toast("تم صرف استمارات الهيئة.");
        await renderRoute();
      } catch (err) {
        error.textContent = err.message;
        error.hidden = false;
      }
    });
    return;
  }
  if (tab === "logs") {
    panel.innerHTML = `
      <div class="page-stack">
        <section><div class="section-head"><h2>سجل الوارد</h2><span class="badge">${fmtNum(snapshot.receipts.length, 0)}</span></div><div class="table-wrap">${authorityMovementsTable(snapshot.receipts, "لا توجد عمليات وارد.")}</div></section>
        <section><div class="section-head"><h2>سجل الصرف</h2><span class="badge">${fmtNum(snapshot.withdrawals.length, 0)}</span></div><div class="table-wrap">${authorityMovementsTable(snapshot.withdrawals, "لا توجد عمليات صرف.")}</div></section>
      </div>`;
    return;
  }
  panel.innerHTML = `<div style="max-width:620px">
    <div class="alert alert-warning">حذف الصنف يحذف سجلات الوارد والصرف المرتبطة به ويعدّل إجمالي الرصيد. لا يمكن التراجع.</div>
    <div class="stack" style="margin-top:14px">
      <label class="field"><span>اختر الصنف</span><select id="authority-delete-item">${snapshot.items.map((item) => `<option value="${esc(`${item.item_name}|${item.item_code}`)}">${esc(item.item_name)} — ${esc(item.item_code)} (${fmtNum(item.available_qty)})</option>`).join("")}</select></label>
      <button class="btn btn-danger" type="button" id="authority-delete-button">${icon("trash")} حذف الصنف نهائياً</button>
    </div>
  </div>`;
  $("#authority-delete-button")?.addEventListener("click", () => {
    const value = $("#authority-delete-item").value;
    const [name, code] = value.split("|");
    if (!name) return;
    confirmModal({
      title: "حذف صنف استمارات الهيئة",
      message: `سيتم حذف «${name}» وكود «${code}» مع كل سجلات الوارد والصرف وتعديل الرصيد الإجمالي.`,
      confirmText: "حذف نهائي",
      onConfirm: async () => {
        await api(`/authority/items?item_name=${encodeURIComponent(name)}&item_code=${encodeURIComponent(code)}`, { method: "DELETE" });
        toast("تم حذف صنف استمارات الهيئة.");
        await renderRoute();
      },
    });
  });
}

function authorityItemsTable(items) {
  if (!items.length) return `<div class="table-empty"><strong>لا توجد أصناف</strong>سجّل أول عملية وارد من تبويب «تسجيل وارد».</div>`;
  return `<table><thead><tr><th>الصنف</th><th>الكود</th><th class="num">الوارد</th><th class="num">المصروف</th><th class="num">المتاح</th></tr></thead>
    <tbody>${items.map((item) => `<tr><td><strong>${esc(item.item_name)}</strong></td><td class="mono">${esc(item.item_code)}</td><td class="num">${fmtNum(item.received_qty)}</td><td class="num">${fmtNum(item.withdrawn_qty)}</td><td class="num"><strong>${fmtNum(item.available_qty)}</strong></td></tr>`).join("")}</tbody></table>`;
}

function authorityMovementsTable(items, emptyMessage) {
  if (!items.length) return `<div class="table-empty"><strong>لا توجد سجلات</strong>${esc(emptyMessage)}</div>`;
  return `<table><thead><tr><th>الحركة</th><th>التاريخ</th><th>الصنف</th><th>الكود</th><th class="num">الكمية</th><th>الشخص</th><th>ملاحظات</th></tr></thead>
    <tbody>${items.map((item) => `<tr><td class="mono">${esc(item.movement_no)}</td><td class="small">${esc(fmtDate(item.movement_date))}</td><td>${esc(item.product_name)}</td><td class="mono">${esc(item.product_code)}</td><td class="num">${fmtNum(item.qty)}</td><td class="small">${esc(item.person || "—")}</td><td class="small">${esc(item.notes || "—")}</td></tr>`).join("")}</tbody></table>`;
}

async function renderDecommission() {
  const [doneData, productData] = await Promise.all([
    api("/decommissioned"),
    api("/products?decommissioned=false"),
  ]);
  const devices = (productData.items || []).filter((item) => item.category === "PCR" || item.category === "مستلزمات الكمبيوتر");
  $("#page-content").innerHTML = `
    <div class="split">
      <section class="card">
        <div class="section-head"><div><h2>تسجيل تكهين جهاز</h2><p>تحديث حالة الجهاز إلى «مكهن» وحفظ سجل التكهين.</p></div></div>
        <form id="decommission-form" class="stack">
          <div class="field-row">
            ${field("المصدر", "source", "PCR", { selectOptions: `<option value="PCR">أجهزة PCR</option><option value="مستلزمات الكمبيوتر">مستلزمات الكمبيوتر</option>` })}
            ${field("الجهاز", "product_code", "", { selectOptions: "" })}
          </div>
          <div class="field-row">
            ${field("تاريخ التكهين", "decommission_date", today(), { type: "date" })}
            ${field("القائم بالتكهين", "person", state.user?.username || "", { required: true })}
          </div>
          ${field("سبب التكهين", "reason", "", { type: "textarea", required: true })}
          <p id="decommission-error" class="form-error" hidden></p>
          <button class="btn btn-danger" type="submit">${icon("trash")} تأكيد التكهين</button>
        </form>
      </section>
      <section class="card card-flush">
        <div class="card-header"><div><h2>سجل الأجهزة المكهنة</h2><p class="small muted">${fmtNum(doneData.count, 0)} جهاز</p></div></div>
        <div class="table-wrap">${decommissionedTable(doneData.items || [])}</div>
      </section>
    </div>`;
  const form = $("#decommission-form");
  const source = form.elements.source;
  const device = form.elements.product_code;
  const fillDevices = () => {
    const filtered = devices.filter((item) => item.category === source.value);
    device.innerHTML = `<option value="">اختر الجهاز...</option>${filtered.map((item) => `<option value="${esc(item.product_code)}">${esc(item.product_name)} — ${esc(item.product_code)}</option>`).join("")}`;
  };
  fillDevices();
  source.addEventListener("change", fillDevices);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = $("#decommission-error");
    error.hidden = true;
    try {
      await api(`/products/${encodeURIComponent(device.value)}/decommission`, {
        method: "POST",
        body: {
          source: source.value,
          decommission_date: form.elements.decommission_date.value,
          reason: form.elements.reason.value,
          person: form.elements.person.value,
        },
      });
      toast("تم تسجيل تكهين الجهاز.");
      await renderRoute();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  });
}

function decommissionedTable(items) {
  if (!items.length) return `<div class="table-empty"><strong>لا توجد أجهزة مكهنة</strong>سجّل أول عملية تكهين من النموذج.</div>`;
  return `<table><thead><tr><th>الجهاز</th><th>القسم</th><th>تاريخ التكهين</th><th>السبب</th><th>القائم به</th><th></th></tr></thead>
    <tbody>${items.map((item) => `<tr>
      <td><div class="cell-main"><strong>${esc(item.product_name)}</strong><small class="mono">${esc(item.product_code)}</small></div></td>
      <td>${categoryBadge(item.category)}</td>
      <td class="small">${esc(item.decommission_date || "—")}</td>
      <td class="small">${esc(item.decommission_reason || "—")}</td>
      <td class="small">${esc(item.decommissioned_by || "—")}</td>
      <td class="actions"><button class="btn btn-danger btn-icon" type="button" title="حذف" data-action="delete-decommissioned" data-code="${esc(item.product_code)}">${icon("trash")}</button></td>
    </tr>`).join("")}</tbody></table>`;
}

async function renderReports() {
  const filters = state.reportFilters;
  const summary = await api(`/reports/summary?date_from=${encodeURIComponent(filters.date_from)}&date_to=${encodeURIComponent(filters.date_to)}`);
  $("#page-content").innerHTML = `
    <div class="page-stack">
      <div class="grid grid-4">
        <article class="stat-card"><span class="stat-icon">${icon("box")}</span><div><span class="stat-value">${fmtNum(summary.products_count, 0)}</span><span class="stat-label">الأصناف</span><div class="stat-hint">${fmtNum(summary.total_stock)} وحدة</div></div></article>
        <article class="stat-card"><span class="stat-icon warn">${icon("warning")}</span><div><span class="stat-value">${fmtNum(summary.low_stock_count, 0)}</span><span class="stat-label">مخزون منخفض</span></div></article>
        <article class="stat-card"><span class="stat-icon info">${icon("arrow")}</span><div><span class="stat-value">${fmtNum(summary.withdrawals_qty)}</span><span class="stat-label">إجمالي المصروف</span><div class="stat-hint">${fmtNum(summary.withdrawals_count, 0)} عملية</div></div></article>
        <article class="stat-card"><span class="stat-icon">${icon("authority")}</span><div><span class="stat-value">${fmtNum(summary.authority_forms_count)}</span><span class="stat-label">رصيد الاستمارات</span></div></article>
      </div>
      <section class="card">
        <form id="report-filter-form" class="toolbar">
          ${field("من تاريخ", "date_from", filters.date_from, { type: "date" })}
          ${field("إلى تاريخ", "date_to", filters.date_to, { type: "date" })}
          ${field("القسم", "category", filters.category, { selectOptions: `<option value="">كل الأقسام</option>${(state.meta?.categories || []).map((category) => `<option value="${esc(category)}" ${category === filters.category ? "selected" : ""}>${esc(category)}</option>`).join("")}` })}
          ${field("بحث", "search", filters.search, { placeholder: "اسم أو كود..." })}
          <div class="actions-row" style="align-self:end"><button class="btn btn-primary btn-sm" type="submit">${icon("search")} تطبيق</button><button class="btn btn-secondary btn-sm" type="button" data-action="clear-report-filters">مسح</button></div>
        </form>
        <div class="section-head" style="margin-top:18px">
          <div class="tabs">
            <button class="tab-button ${state.reportKind === "movements" ? "active" : ""}" type="button" data-action="report-tab" data-kind="movements">حركة المخزن</button>
            <button class="tab-button ${state.reportKind === "withdrawals" ? "active" : ""}" type="button" data-action="report-tab" data-kind="withdrawals">السحوبات</button>
            <button class="tab-button ${state.reportKind === "low" ? "active" : ""}" type="button" data-action="report-tab" data-kind="low">الأصناف المنخفضة</button>
          </div>
          <a id="export-link" class="btn btn-secondary btn-sm" href="#">${icon("download")} تصدير CSV</a>
        </div>
        <div id="report-table" class="table-wrap">${loadingHTML("جارٍ تحميل التقرير...")}</div>
      </section>
    </div>`;
  $("#report-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    state.reportFilters = {
      date_from: form.elements.date_from.value,
      date_to: form.elements.date_to.value,
      category: form.elements.category.value,
      search: form.elements.search.value.trim(),
    };
    await renderRoute();
  });
  await loadReportTable();
}

async function loadReportTable() {
  const filters = state.reportFilters;
  const params = new URLSearchParams({
    date_from: filters.date_from,
    date_to: filters.date_to,
    category: filters.category,
    search: filters.search,
  });
  const exportLink = $("#export-link");
  if (exportLink) exportLink.href = `/api/reports/export.csv?kind=${encodeURIComponent(state.reportKind)}&${params.toString()}`;
  const container = $("#report-table");
  if (!container) return;
  try {
    if (state.reportKind === "low") {
      const data = await api("/reports/low-stock");
      container.innerHTML = lowStockTable(data.items || []);
    } else if (state.reportKind === "withdrawals") {
      const data = await api(`/reports/withdrawals?${params.toString()}`);
      container.innerHTML = withdrawalsReportTable(data.items || []);
    } else {
      const data = await api(`/reports/movements?${params.toString()}`);
      container.innerHTML = movementsTable(data.items || []);
    }
  } catch (err) {
    container.innerHTML = `<div class="table-empty"><strong>تعذر تحميل التقرير</strong>${esc(err.message)}</div>`;
  }
}

function withdrawalsReportTable(items) {
  if (!items.length) return `<div class="table-empty"><strong>لا توجد سحوبات</strong>لا توجد نتائج مطابقة للفلاتر.</div>`;
  return `<table><thead><tr><th>التاريخ</th><th>الصنف</th><th>القسم</th><th class="num">الكمية</th><th>الساحب</th><th>المسؤول</th><th>ملاحظات</th></tr></thead>
    <tbody>${items.map((item) => `<tr><td class="small">${esc(fmtDate(item.withdraw_date))}</td><td><div class="cell-main"><strong>${esc(item.product_name)}</strong><small>${esc(item.product_code)}</small></div></td><td>${categoryBadge(item.category)}</td><td class="num">${fmtNum(item.qty)}</td><td class="small">${esc(item.withdrawn_by || "—")}</td><td class="small">${esc(item.supervisor_name || "—")}</td><td class="small">${esc(item.notes || "—")}</td></tr>`).join("")}</tbody></table>`;
}

function lowStockTable(items) {
  if (!items.length) return `<div class="table-empty"><strong>لا توجد أصناف منخفضة</strong>كل الأصناف ضمن الحدود الآمنة.</div>`;
  return `<table><thead><tr><th>الصنف</th><th>القسم</th><th class="num">الرصيد</th><th class="num">الحد الأدنى</th><th>الوحدة</th><th>الموقع</th></tr></thead>
    <tbody>${items.map((item) => `<tr><td><div class="cell-main"><strong>${esc(item.product_name)}</strong><small>${esc(item.product_code)}</small></div></td><td>${categoryBadge(item.category)}</td><td class="num"><strong>${fmtNum(item.current_stock)}</strong></td><td class="num">${fmtNum(item.min_stock)}</td><td class="small">${esc(item.unit || "—")}</td><td class="small">${esc(item.storage_location || "—")}</td></tr>`).join("")}</tbody></table>`;
}

async function renderUsers() {
  const data = await api("/users");
  const users = data.items || [];
  $("#page-content").innerHTML = `
    <div class="page-stack">
      <div class="page-actions"><button class="btn btn-primary" type="button" data-action="add-user">${icon("plus")} إضافة مستخدم</button></div>
      <section class="card card-flush">
        <div class="card-header"><div><h2>حسابات النظام</h2><p class="small muted">${fmtNum(users.length, 0)} مستخدم</p></div></div>
        <div class="table-wrap"><table><thead><tr><th>المستخدم</th><th>الدور</th><th>تاريخ الإنشاء</th><th>إجراءات</th></tr></thead>
          <tbody>${users.map((user) => `<tr>
            <td><div class="cell-main"><strong>${esc(user.username)}</strong><small>${user.username === state.user.username ? "الحساب الحالي" : "حساب نظام"}</small></div></td>
            <td>${badge(user.role === "admin" ? "مدير" : "مستخدم", user.role === "admin" ? "badge-teal" : "badge")}</td>
            <td class="small">${esc(fmtDate(user.created_at))}</td>
            <td class="actions">
              <button class="btn btn-secondary btn-sm" type="button" data-action="user-reset" data-username="${esc(user.username)}">كلمة المرور</button>
              <button class="btn btn-secondary btn-sm" type="button" data-action="user-role" data-username="${esc(user.username)}" data-role="${user.role === "admin" ? "user" : "admin"}">${user.role === "admin" ? "تحويل لمستخدم" : "ترقية لمدير"}</button>
              ${user.username !== state.user.username ? `<button class="btn btn-danger btn-icon" type="button" title="حذف" data-action="user-delete" data-username="${esc(user.username)}">${icon("trash")}</button>` : ""}
            </td>
          </tr>`).join("")}</tbody></table></div>
      </section>
    </div>`;
}

function openAddUserModal() {
  const body = `<div class="stack">
    ${field("اسم المستخدم", "username", "", { required: true })}
    <div class="field-row">
      ${field("كلمة المرور", "password", "", { type: "password", required: true })}
      ${field("الدور", "role", "user", { selectOptions: `<option value="user">مستخدم</option><option value="admin">مدير</option>` })}
    </div>
  </div>`;
  openModal({
    title: "إضافة مستخدم",
    body,
    submitText: "إضافة الحساب",
    onSubmit: async (formData) => {
      await api("/users", {
        method: "POST",
        body: { username: formData.get("username"), password: formData.get("password"), role: formData.get("role") },
      });
      toast("تمت إضافة المستخدم.");
      await renderRoute();
    },
  });
}

function openResetPasswordModal(username) {
  const body = field("كلمة المرور الجديدة", "new_password", "", { type: "password", required: true });
  openModal({
    title: `إعادة تعيين كلمة مرور ${username}`,
    body,
    submitText: "تحديث كلمة المرور",
    onSubmit: async (formData) => {
      await api(`/users/${encodeURIComponent(username)}/password`, { method: "POST", body: { new_password: formData.get("new_password") } });
      toast("تم تحديث كلمة المرور.");
    },
  });
}

function openEditProductByCode(code) {
  const product = state.categoryItems.find((item) => item.product_code === code) || productByCode(code);
  if (product) openProductModal(product, product.category);
}

async function handleContentClick(event) {
  const nav = event.target.closest("[data-nav]");
  if (nav) {
    event.preventDefault();
    navigate(nav.dataset.nav);
    document.body.classList.remove("sidebar-open");
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  if (action === "refresh-page") return renderRoute();
  if (action === "add-product") return openProductModal(null, state.categoryConfig?.addCategory || state.categoryConfig?.category || "عام");
  if (action === "edit-product") return openEditProductByCode(button.dataset.code);
  if (action === "delete-product") return deleteProduct(button.dataset.code);
  if (action === "withdraw-product") return navigate("withdraw", { code: button.dataset.code });
  if (action === "delete-withdrawal") {
    const id = button.dataset.id;
    return confirmModal({
      title: "إلغاء عملية السحب",
      message: "سيتم إرجاع الكمية إلى رصيد الصنف وتسجيل حركة إرجاع. هل تريد المتابعة؟",
      confirmText: "إلغاء السحب",
      onConfirm: async () => { await api(`/withdrawals/${encodeURIComponent(id)}`, { method: "DELETE" }); toast("تم إلغاء عملية السحب وإرجاع الكمية."); await renderRoute(); },
    });
  }
  if (action === "add-order") return openCreateOrderModal();
  if (action === "open-order") { state.selectedOrderNo = button.dataset.order; return loadOrderDetail(button.dataset.order); }
  if (action === "complete-order") {
    return confirmModal({
      title: "إتمام الطلبية", message: `سيتم تحويل الطلبية ${button.dataset.order} إلى مكتملة.`, confirmText: "إتمام", danger: false,
      onConfirm: async () => { await api(`/orders/${encodeURIComponent(button.dataset.order)}/complete`, { method: "POST" }); toast("تم إتمام الطلبية."); await renderRoute(); },
    });
  }
  if (action === "reopen-order") {
    return confirmModal({
      title: "إعادة فتح الطلبية", message: `سيتم إعادة فتح الطلبية ${button.dataset.order}.`, confirmText: "إعادة فتح", danger: false,
      onConfirm: async () => { await api(`/orders/${encodeURIComponent(button.dataset.order)}/reopen`, { method: "POST" }); toast("تم إعادة فتح الطلبية."); await renderRoute(); },
    });
  }
  if (action === "delete-order") {
    return confirmModal({
      title: "حذف الطلبية", message: "سيتم حذف الطلبية وبنودها وإرجاع الكميات المسحوبة إلى المخزون. لا يمكن التراجع.", confirmText: "حذف الطلبية",
      onConfirm: async () => { await api(`/orders/${encodeURIComponent(button.dataset.order)}`, { method: "DELETE" }); toast("تم حذف الطلبية وإرجاع الكميات."); await renderRoute(); },
    });
  }
  if (action === "remove-order-item") {
    return confirmModal({
      title: "حذف البند", message: "سيتم حذف هذا البند من الطلبية.", confirmText: "حذف البند",
      onConfirm: async () => { await api(`/orders/${encodeURIComponent(button.dataset.order)}/items/${encodeURIComponent(button.dataset.item)}`, { method: "DELETE" }); toast("تم حذف البند."); await renderRoute(); },
    });
  }
  if (action === "withdraw-order-item" && state.currentOrder) {
    const item = state.currentOrder.items.find((entry) => entry.item_id === button.dataset.item);
    if (item) return openOrderWithdrawModal(state.currentOrder, item);
    return;
  }
  if (action === "authority-tab") {
    state.authorityTab = button.dataset.tab;
    $$(".tab-button[data-action='authority-tab']").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === state.authorityTab));
    return renderAuthorityPanel();
  }
  if (action === "delete-decommissioned") {
    const code = button.dataset.code;
    return confirmModal({
      title: "حذف الجهاز المكهّن", message: `سيتم حذف الجهاز ${code} من المخزن نهائياً.`, confirmText: "حذف نهائي",
      onConfirm: async () => { await api(`/products/${encodeURIComponent(code)}?force=true`, { method: "DELETE" }); toast("تم حذف الجهاز."); await renderRoute(); },
    });
  }
  if (action === "report-tab") {
    state.reportKind = button.dataset.kind;
    $$(".tab-button[data-action='report-tab']").forEach((tab) => tab.classList.toggle("active", tab.dataset.kind === state.reportKind));
    return loadReportTable();
  }
  if (action === "clear-report-filters") {
    state.reportFilters = { date_from: "", date_to: "", category: "", search: "" };
    return renderRoute();
  }
  if (action === "add-user") return openAddUserModal();
  if (action === "user-reset") return openResetPasswordModal(button.dataset.username);
  if (action === "user-delete") {
    return confirmModal({
      title: "حذف المستخدم", message: `سيتم حذف حساب ${button.dataset.username}.`, confirmText: "حذف الحساب",
      onConfirm: async () => { await api(`/users/${encodeURIComponent(button.dataset.username)}`, { method: "DELETE" }); toast("تم حذف المستخدم."); await renderRoute(); },
    });
  }
  if (action === "user-role") {
    const role = button.dataset.role;
    return confirmModal({
      title: "تغيير صلاحية المستخدم", message: `سيتم تعيين دور «${role === "admin" ? "مدير" : "مستخدم"}» للحساب ${button.dataset.username}.`, confirmText: "تغيير الدور", danger: false,
      onConfirm: async () => { await api(`/users/${encodeURIComponent(button.dataset.username)}/role`, { method: "PUT", body: { role } }); toast("تم تغيير الدور."); await renderRoute(); },
    });
  }
}

function bindGlobal() {
  $("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const error = $("#login-error");
    const button = $("#login-submit");
    error.hidden = true;
    button.disabled = true;
    button.textContent = "جارٍ تسجيل الدخول...";
    try {
      state.user = await api("/auth/login", {
        method: "POST",
        body: { username: $("#login-username").value.trim(), password: $("#login-password").value },
      });
      await enterApp();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    } finally {
      button.disabled = false;
      button.textContent = "دخول النظام";
    }
  });
  $("#logout-button").addEventListener("click", async () => {
    try { await api("/auth/logout", { method: "POST" }); } catch { /* ignore */ }
    showLogin();
    toast("تم تسجيل الخروج.");
  });
  $("#menu-toggle").addEventListener("click", () => document.body.classList.toggle("sidebar-open"));
  $("#sidebar-backdrop").addEventListener("click", () => document.body.classList.remove("sidebar-open"));
  $("#nav").addEventListener("click", handleNavigation);
  $("#page-content").addEventListener("click", handleContentClick);
  window.addEventListener("hashchange", () => {
    document.body.classList.remove("sidebar-open");
    renderRoute();
  });
}

function updateDateBadge() {
  try {
    $("#date-badge").textContent = new Intl.DateTimeFormat("ar-EG", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date());
  } catch {
    $("#date-badge").textContent = new Date().toLocaleDateString();
  }
}

async function init() {
  bindGlobal();
  updateDateBadge();
  try {
    state.user = await api("/auth/me");
    await enterApp();
  } catch {
    showLogin();
  }
}

document.addEventListener("DOMContentLoaded", init);
