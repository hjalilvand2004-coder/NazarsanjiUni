/* ==================================================
   Mini App Frontend v2.0.0
   ترم بهمن ۱۴۰۴
   ================================================== */

const API = {
    auth: "/api/auth",
    contact: "/api/contact",
    completeRegistration: "/api/complete-registration",
    courses: "/api/courses",
    submit: "/api/submit",
    dashboard: "/api/dashboard",
    profile: "/api/profile",
    cancel: "/api/cancel",
    notifications: "/api/notifications",
    adminStats: "/api/admin/stats",
    adminCourses: "/api/admin/courses",
    adminAddCourse: "/api/admin/courses/add",
    adminUpdateCourse: "/api/admin/courses/update",
    adminDeleteCourse: "/api/admin/courses/delete",
    adminUsers: "/api/admin/users",
    adminReportExcel: "/api/admin/report-excel",
};

const state = {
    init_data: "",
    user: null,
    isAdmin: false,
    isRegistered: false,
    hasSubmitted: false,
    selectedCourses: [],
    availableCourses: [],
    maxCourses: 6,
    exemptIds: [],
    exemptKeywords: ["کارآموزی", "پروژه"],
    currentFilter: "all",
    searchTerm: "",
    activePage: "dashboard",
    chart: null,
    semester: "",
    deadline: "",
};

// ==================================================
// Init
// ==================================================
document.addEventListener("DOMContentLoaded", async () => {
    initTheme();
    initNav();
    initNotifPanel();

    const baleApp = window.Bale && window.Bale.WebApp;

    try {
        if (!baleApp) {
            throw new Error("SDK بله بارگذاری نشده است.");
        }

        // اگر SDK قبلاً داده‌ها را خوانده، دوباره init نکن.
        if (!baleApp.initData && typeof baleApp.init === "function") {
            baleApp.init();
        }

        state.init_data = baleApp.initData || "";

        if (!state.init_data) {
            // حالت تست خارج از بله
            showToast("اطلاعات احراز هویت بله دریافت نشد؛ مینی‌اپ را ببندید و دوباره از ربات باز کنید.", "warning");
            showAuthPage();
            return;
        }

        await checkAuth();
    } catch (e) {
        console.error(e);
        showAuthPage();
    }
});

// ==================================================
// Theme
// ==================================================
function initTheme() {
    const saved = localStorage.getItem("theme") || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    document.getElementById("btn-theme").addEventListener("click", () => {
        const cur = document.documentElement.getAttribute("data-theme");
        const next = cur === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("theme", next);
    });
}

// ==================================================
// Navigation
// ==================================================
function initNav() {
    document.querySelectorAll(".nav-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const page = btn.dataset.page;
            navigateTo(page);
        });
    });
}

function navigateTo(page) {
    state.activePage = page;
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    const btn = document.querySelector(`.nav-btn[data-page="${page}"]`);
    if (btn) btn.classList.add("active");

    document.querySelectorAll(".page").forEach(p => p.hidden = true);

    const map = {
        dashboard: "page-dashboard",
        courses: "page-courses",
        profile: "page-profile",
        admin: "page-admin",
    };

    const target = document.getElementById(map[page]);
    if (target) target.hidden = false;

    if (page === "dashboard") loadDashboard();
    else if (page === "courses") loadCoursesPage();
    else if (page === "profile") loadProfile();
    else if (page === "admin") loadAdmin();
}

// ==================================================
// Toast
// ==================================================
function showToast(message, type = "info") {
    const t = document.getElementById("toast");
    t.textContent = message;
    t.className = "toast show " + type;
    setTimeout(() => t.classList.remove("show"), 3000);
}

// ==================================================
// API Helper
// ==================================================
async function api(url, body = {}) {
    const res = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-Auth-Data": state.init_data || "",
        },
        body: JSON.stringify({ initData: state.init_data, ...body }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
        throw new Error(data.message || "خطای نامشخص");
    }
    return data;
}

async function apiGet(url) {
    const res = await fetch(url);
    return await res.json();
}

// ==================================================
// Auth Flow
// ==================================================
async function checkAuth() {
    try {
        const data = await api(API.auth);
        state.user = data.user;
        state.isAdmin = data.is_admin;
        state.isRegistered = data.registered;
        state.hasSubmitted = data.has_submitted;
        state.semester = data.semester;
        state.deadline = data.deadline;

        updateHeaderUser();

        document.querySelector(".admin-only").hidden = !state.isAdmin;

        if (!data.account_exists) {
            showAuthPage();
        } else if (!state.isRegistered) {
            showRegisterPage();
        } else {
            navigateTo("dashboard");
        }
    } catch (e) {
        console.error(e);
        showAuthPage();
    }
}

function showAuthPage() {
    document.querySelectorAll(".page").forEach(p => p.hidden = true);
    document.getElementById("page-auth").hidden = false;

    const el = document.getElementById("page-auth");
    el.innerHTML = `
        <div class="card welcome-card glass">
            <span class="emoji">🎓</span>
            <h2>خوش آمدید</h2>
            <p>سامانه نظرسنجی دروس ترم ${state.semester || "بهمن ۱۴۰۴"}<br>برای ادامه لطفاً احراز هویت کنید.</p>
            <div class="deadline-pill">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                مهلت: ${state.deadline || "۲۵ دی ۱۴۰۴"}
            </div>
            <button class="btn btn-primary" id="btn-auth-contact">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z"/></svg>
                تأیید شماره تماس
            </button>
        </div>
    `;

    document.getElementById("btn-auth-contact").addEventListener("click", requestContact);
}

function requestContact() {
    const app = window.Bale && window.Bale.WebApp;

    if (!app || typeof app.requestContact !== "function") {
        showToast("مینی‌اپ را از داخل بله و دکمه ربات باز کنید.", "error");
        return;
    }

    try {
        const result = app.requestContact(async (sent, phoneNumber) => {
            if (!sent) {
                showToast("ارسال شماره تماس تأیید نشد.", "error");
                return;
            }

            if (!phoneNumber) {
                showToast("شماره تماس از بله دریافت نشد.", "error");
                return;
            }

            try {
                await api(API.contact, { phone: String(phoneNumber) });
                await checkAuth();
            } catch (e) {
                showToast(e.message, "error");
            }
        });

        if (result === false) {
            showToast("درخواست تماس اجرا نشد؛ مینی‌اپ را ببندید و دوباره باز کنید.", "error");
        }
    } catch (e) {
        showToast(e.message || "درخواست تماس ناموفق بود.", "error");
    }
}

function manualPhoneInput() {
    const el = document.getElementById("page-auth");
    el.innerHTML = `
        <div class="card welcome-card glass">
            <span class="emoji">📱</span>
            <h2>ورود با شماره</h2>
            <p>شماره تماس خود را وارد کنید</p>
            <div class="input-group">
                <input class="input" id="phone-input" placeholder="09xxxxxxxxx" type="tel" maxlength="11">
            </div>
            <button class="btn btn-primary" id="btn-phone-submit">ادامه</button>
        </div>
    `;
    document.getElementById("btn-phone-submit").addEventListener("click", async () => {
        const phone = document.getElementById("phone-input").value.trim();
        if (!/^09\d{9}$/.test(phone)) {
            showToast("شماره معتبر نیست", "error");
            return;
        }
        try {
            await api(API.contact, { phone });
            await checkAuth();
        } catch (e) {
            showToast(e.message, "error");
        }
    });
}

function showRegisterPage() {
    document.querySelectorAll(".page").forEach(p => p.hidden = true);
    document.getElementById("page-register").hidden = false;

    const el = document.getElementById("page-register");
    el.innerHTML = `
        <div class="card glass">
            <h2 class="text-gradient" style="margin-bottom:16px;">تکمیل ثبت‌نام</h2>
            <div class="input-group">
                <label>نام و نام خانوادگی</label>
                <input class="input" id="reg-name" placeholder="مثال: علی رضایی">
            </div>
            <div class="input-group">
                <label>شماره دانشجویی</label>
                <input class="input" id="reg-sn" placeholder="9 رقمی یا 14 رقمی" type="tel">
            </div>
            <div class="input-group">
                <label>نوع کارشناسی</label>
                <select class="select" id="reg-type">
                    <option value="">انتخاب کنید...</option>
                    <option value="پیوسته">پیوسته</option>
                    <option value="ناپیوسته">ناپیوسته</option>
                </select>
            </div>
            <button class="btn btn-primary" id="btn-reg-submit">ثبت‌نام</button>
            <p class="text-muted text-center" style="font-size:12px;margin-top:12px;">
                با ثبت‌نام، قوانین سامانه را می‌پذیرید.
            </p>
        </div>
    `;
    document.getElementById("btn-reg-submit").addEventListener("click", submitRegistration);
}

async function submitRegistration() {
    const name = document.getElementById("reg-name").value.trim();
    const sn = document.getElementById("reg-sn").value.trim();
    const type = document.getElementById("reg-type").value;

    if (!name) return showToast("نام را وارد کنید", "error");
    if (!sn) return showToast("شماره دانشجویی را وارد کنید", "error");
    if (!type) return showToast("نوع کارشناسی را انتخاب کنید", "error");

    try {
        await api(API.completeRegistration, {
            name, student_number: sn, student_type: type
        });
        showToast("ثبت‌نام با موفقیت انجام شد ✓", "success");
        await checkAuth();
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================================================
// Header User
// ==================================================
function updateHeaderUser() {
    if (!state.user) return;
    const el = document.getElementById("header-user");
    const initial = state.user.name ? state.user.name.charAt(0) : "؟";
    el.innerHTML = `
        <span class="chip">
            <span class="chip-avatar">${state.user.avatar ? `<img src="${state.user.avatar}" style="width:100%;height:100%;border-radius:50%">` : initial}</span>
            ${state.user.name || "دانشجو"} ${state.isAdmin ? "• ادمین" : ""}
        </span>
    `;
}

// ==================================================
// Dashboard
// ==================================================
async function loadDashboard() {
    const el = document.getElementById("page-dashboard");
    el.innerHTML = `<div class="spinner"></div>`;

    try {
        const data = await api(API.dashboard);
        const s = data.summary;
        const pct = data.progress_pct;

        const coursesHtml = data.my_courses.length === 0
            ? `<div class="empty-state"><span class="emoji">📚</span><p>هنوز درسی انتخاب نکرده‌اید</p></div>`
            : data.my_courses.map(c => `
                <div class="course-item">
                    <div class="course-check" style="background:linear-gradient(135deg,var(--accent),var(--accent-2));border-color:transparent;color:white;">✓</div>
                    <div class="course-info">
                        <div class="course-title">${escapeHtml(c.title)}</div>
                        <div class="course-meta">
                            ${c.section_label ? `<span class="section-tag">${c.section_label}</span>` : ""}
                            ${c.credits ? `<span>🕒 ${c.credits} واحد</span>` : ""}
                        </div>
                    </div>
                    ${!state.hasSubmitted || state.isAdmin ? `
                        <button class="icon-btn btn-remove" data-id="${c.id}" title="حذف">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                        </button>
                    ` : ""}
                </div>
            `).join("");

        el.innerHTML = `
            <div class="card glass" style="background:linear-gradient(135deg,rgba(167,139,250,0.2),rgba(244,114,182,0.15));">
                <div style="display:flex;justify-content:space-between;align-items:flex-end;">
                    <div>
                        <div class="card-title">پیشرفت نظرسنجی شما</div>
                        <div class="card-value">${s.my_requests} / ${s.max_requests}</div>
                        <div class="text-muted" style="font-size:12px;margin-top:4px;">درس انتخاب شده</div>
                    </div>
                    <div style="text-align:left;">
                        <div class="text-muted" style="font-size:12px;">باقی‌مانده</div>
                        <div class="text-gradient" style="font-size:24px;font-weight:800;">${s.remaining}</div>
                    </div>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width:${pct}%"></div>
                </div>
                <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:11px;color:var(--text-3);">
                    <span>۰</span><span>${s.max_requests}</span>
                </div>
            </div>

            <div class="stats-grid">
                <div class="card glass">
                    <div class="card-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
                    </div>
                    <div class="card-title">کاربران</div>
                    <div class="card-value">${s.total_users.toLocaleString("fa-IR")}</div>
                </div>
                <div class="card glass">
                    <div class="card-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>
                    </div>
                    <div class="card-title">پیشنهادات</div>
                    <div class="card-value">${s.total_requests.toLocaleString("fa-IR")}</div>
                </div>
            </div>

            ${!state.hasSubmitted ? `
                <button class="btn btn-primary" id="btn-go-courses" style="margin-bottom:16px;">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
                    انتخاب دروس
                </button>
            ` : `
                <div class="card glass" style="background:linear-gradient(135deg,rgba(52,211,153,0.18),rgba(56,189,248,0.12));border-color:rgba(52,211,153,0.4);">
                    <div style="display:flex;align-items:center;gap:12px;">
                        <div style="font-size:32px;">✅</div>
                        <div>
                            <div style="font-weight:700;color:var(--success);">ثبت نهایی شد</div>
                            <div class="text-muted" style="font-size:12px;">پیشنهاد شما برای ترم ${data.semester} ثبت شد</div>
                        </div>
                    </div>
                </div>
            `}

            <div class="section-title">درس‌های انتخابی من</div>
            <div class="course-list">${coursesHtml}</div>
        `;

        // اتصال دکمه‌ها
        const goBtn = document.getElementById("btn-go-courses");
        if (goBtn) goBtn.addEventListener("click", () => navigateTo("courses"));

        document.querySelectorAll(".btn-remove").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const id = parseInt(btn.dataset.id);
                if (!confirm("این درس از فهرست شما حذف شود؟")) return;
                try {
                    await api(API.cancel, { course_id: id });
                    showToast("حذف شد", "success");
                    await loadDashboard();
                    state.hasSubmitted = false;
                } catch (err) {
                    showToast(err.message, "error");
                }
            });
        });

    } catch (e) {
        el.innerHTML = `<div class="card glass"><div class="empty-state"><span class="emoji">⚠️</span><p>${escapeHtml(e.message)}</p></div></div>`;
    }
}

// ==================================================
// Courses Page
// ==================================================
async function loadCoursesPage() {
    const el = document.getElementById("page-courses");
    el.innerHTML = `<div class="spinner"></div>`;

    try {
        const data = await api(API.courses);
        state.availableCourses = data.courses;
        state.selectedCourses = data.selected || [];
        state.maxCourses = data.max || 6;
        state.exemptIds = data.exempt_ids || [];
        state.exemptKeywords = data.exempt_keywords || ["کارآموزی", "پروژه"];

        renderCoursesPage();
    } catch (e) {
        el.innerHTML = `<div class="card glass"><div class="empty-state"><span class="emoji">⚠️</span><p>${escapeHtml(e.message)}</p></div></div>`;
    }
}

function renderCoursesPage() {
    const el = document.getElementById("page-courses");

    const sections = ["all", "basic", "core", "specialized", "specialized_ai", "specialized_sw", "electives"];
    const sectionLabels = {
        all: "همه", basic: "پایه", core: "اصلی",
        specialized: "تخصصی", specialized_ai: "هوش",
        specialized_sw: "نرم‌افزار", electives: "اختیاری"
    };

    let filtered = state.availableCourses;
    if (state.currentFilter !== "all") {
        filtered = filtered.filter(c => c.section === state.currentFilter);
    }
    if (state.searchTerm) {
        const q = state.searchTerm.toLowerCase();
        filtered = filtered.filter(c => c.title.toLowerCase().includes(q));
    }

    el.innerHTML = `
        <div class="search-bar card glass" style="padding:10px 14px;">
            <div class="input-group" style="margin:0;">
                <input class="input" id="course-search" placeholder="🔍 جستجوی درس..." value="${escapeHtml(state.searchTerm)}">
            </div>
        </div>
        <div class="chip-row">
            ${sections.map(s => `
                <button class="filter-chip ${state.currentFilter === s ? "active" : ""}" data-section="${s}">
                    ${sectionLabels[s]}
                </button>
            `).join("")}
        </div>
        <div class="course-list" id="course-list">
            ${filtered.length === 0
                ? `<div class="empty-state"><span class="emoji">📚</span><p>درسی یافت نشد</p></div>`
                : filtered.map(c => `
                    <div class="course-item ${state.selectedCourses.includes(c.id) ? "selected" : ""} ${isExemptCourse(c.id) ? "exempt" : ""}" data-id="${c.id}">
                        <div class="course-check"></div>
                        <div class="course-info">
                            <div class="course-title">${escapeHtml(c.title)}${isExemptCourse(c.id) ? ' <span style="color:#10b981;font-size:10px;background:rgba(16,185,129,0.15);padding:2px 6px;border-radius:6px;margin-right:6px;">بدون محدودیت</span>' : ''}</div>
                            <div class="course-meta">
                                <span class="section-tag">${c.section_label || c.section}</span>
                                ${c.credits ? `<span>🕒 ${c.credits} واحد</span>` : ""}
                                ${c.prerequisite && c.prerequisite !== "—" ? `<span>📋 پیش‌نیاز: ${escapeHtml(c.prerequisite)}</span>` : ""}
                            </div>
                        </div>
                    </div>
                `).join("")}
        </div>

        <div class="selected-counter">
            <div class="counter-text">
                انتخاب شده: <strong>${state.selectedCourses.length}</strong> / ${state.maxCourses}
                ${getExemptSelectedCount() > 0 ? `<span style="color:#10b981;font-size:11px;display:block;margin-top:2px;">(${getExemptSelectedCount()} کارآموزی/پروژه بدون محدودیت)</span>` : ""}
            </div>
            <button class="btn btn-primary" id="btn-submit-courses" style="width:auto;padding:10px 20px;">
                ثبت نهایی
            </button>
        </div>
    `;

    // اتصال رویدادها
    document.getElementById("course-search").addEventListener("input", (e) => {
        state.searchTerm = e.target.value;
        renderCoursesPage();
        document.getElementById("course-search").focus();
    });

    document.querySelectorAll(".filter-chip").forEach(c => {
        c.addEventListener("click", () => {
            state.currentFilter = c.dataset.section;
            renderCoursesPage();
        });
    });

    document.querySelectorAll(".course-item").forEach(item => {
        item.addEventListener("click", () => {
            const id = parseInt(item.dataset.id);
            toggleCourse(id);
        });
    });

    document.getElementById("btn-submit-courses").addEventListener("click", submitCourses);
}

function toggleCourse(id) {
    const idx = state.selectedCourses.indexOf(id);
    if (idx >= 0) {
        state.selectedCourses.splice(idx, 1);
    } else {
        // ===== [v3.6.5] استثنای کارآموزی/پروژه از محدودیت ۶ درس =====
        const isExempt = isExemptCourse(id);
        if (!isExempt) {
            const nonExemptCount = state.selectedCourses.filter(cid => !isExemptCourse(cid)).length;
            if (nonExemptCount >= state.maxCourses) {
                showToast(`حداکثر ${state.maxCourses} درس قابل انتخاب است. کارآموزی و پروژه بدون محدودیت است.`, "warning");
                return;
            }
        }
        state.selectedCourses.push(id);
    }
    renderCoursesPage();
}

// ===== [v3.6.5] توابع کمکی برای تشخیص درس‌های مستثنا =====
function isExemptCourse(id) {
    // بررسی با exemptIds از سرور
    if (state.exemptIds && state.exemptIds.includes(id)) return true;
    // بررسی با عنوان درس
    const course = state.availableCourses.find(c => c.id === id);
    if (!course) return false;
    const title = course.title || course.course_title || "";
    return state.exemptKeywords.some(kw => title.includes(kw));
}

function getExemptSelectedCount() {
    return state.selectedCourses.filter(cid => isExemptCourse(cid)).length;
}

function getNonExemptSelectedCount() {
    return state.selectedCourses.filter(cid => !isExemptCourse(cid)).length;
}

async function submitCourses() {
    if (state.selectedCourses.length === 0) {
        showToast("حداقل یک درس انتخاب کنید", "warning");
        return;
    }

    if (!(await confirmCourseSubmission(state.selectedCourses.length))) return;

    try {
        const data = await api(API.submit, { courseIds: state.selectedCourses });
        showToast(`${data.count} درس با موفقیت ثبت شد ✓`, "success");
        state.hasSubmitted = true;
        setTimeout(() => navigateTo("dashboard"), 1500);
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================================================
// Profile
// ==================================================
async function loadProfile() {
    const el = document.getElementById("page-profile");
    el.innerHTML = `<div class="spinner"></div>`;

    try {
        const data = await api(API.profile);
        const p = data.profile;
        const initial = (p.name || "؟").charAt(0);
        const roleLabel = p.role === "admin" ? "مدیر سامانه" : "دانشجو";

        el.innerHTML = `
            <div class="card glass profile-header">
                <div class="avatar-circle">
                    ${p.avatar ? `<img src="${p.avatar}" alt="avatar">` : escapeHtml(initial)}
                </div>
                <div class="profile-name">${escapeHtml(p.name)}</div>
                <div class="profile-role">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"/></svg>
                    ${roleLabel}
                </div>
            </div>

            <div class="card glass">
                <div class="info-row">
                    <span class="info-label">شماره دانشجویی</span>
                    <span class="info-value">${escapeHtml(p.student_number || "—")}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">نوع کارشناسی</span>
                    <span class="info-value">${escapeHtml(p.student_type || "—")}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">شماره تماس</span>
                    <span class="info-value">${escapeHtml(p.phone || "—")}</span>
                </div>
                ${p.bale_username ? `
                    <div class="info-row">
                        <span class="info-label">کاربری بله</span>
                        <span class="info-value">@${escapeHtml(p.bale_username)}</span>
                    </div>
                ` : ""}
                <div class="info-row">
                    <span class="info-label">تاریخ عضویت</span>
                    <span class="info-value">${formatDate(p.created_at)}</span>
                </div>
                ${p.last_seen ? `
                    <div class="info-row">
                        <span class="info-label">آخرین بازدید</span>
                        <span class="info-value">${formatDate(p.last_seen)}</span>
                    </div>
                ` : ""}
            </div>

            <div class="card glass">
                <div class="card-title">ترم فعال</div>
                <div class="info-value text-gradient" style="font-size:18px;">${escapeHtml(state.semester || "بهمن ۱۴۰۴")}</div>
                <div class="text-muted" style="font-size:12px;margin-top:4px;">مهلت نظرسنجی: ${escapeHtml(state.deadline || "")}</div>
            </div>
        `;
    } catch (e) {
        el.innerHTML = `<div class="card glass"><div class="empty-state"><span class="emoji">⚠️</span><p>${escapeHtml(e.message)}</p></div></div>`;
    }
}

// ==================================================
// Admin Panel
// ==================================================
let adminTab = "stats";

async function loadAdmin() {
    const el = document.getElementById("page-admin");
    el.innerHTML = `
        <div class="admin-tabs">
            <button class="admin-tab ${adminTab === "stats" ? "active" : ""}" data-tab="stats">آمار</button>
            <button class="admin-tab ${adminTab === "courses" ? "active" : ""}" data-tab="courses">دروس</button>
            <button class="admin-tab ${adminTab === "users" ? "active" : ""}" data-tab="users">کاربران</button>
            <button class="admin-tab ${adminTab === "report" ? "active" : ""}" data-tab="report">گزارش</button>
        </div>
        <div class="admin-panel" id="admin-content">
            <div class="spinner"></div>
        </div>
    `;

    document.querySelectorAll(".admin-tab").forEach(t => {
        t.addEventListener("click", () => {
            adminTab = t.dataset.tab;
            loadAdmin();
        });
    });

    if (adminTab === "stats") await loadAdminStats();
    else if (adminTab === "courses") await loadAdminCourses();
    else if (adminTab === "users") await loadAdminUsers();
    else if (adminTab === "report") loadAdminReport();
}

async function loadAdminStats() {
    const el = document.getElementById("admin-content");
    try {
        const data = await api(API.adminStats);
        const s = data.stats;

        el.innerHTML = `
            <div class="stats-grid">
                <div class="card glass">
                    <div class="card-title">کاربران</div>
                    <div class="card-value">${s.total_users.toLocaleString("fa-IR")}</div>
                </div>
                <div class="card glass">
                    <div class="card-title">پیشنهادات</div>
                    <div class="card-value">${s.total_requests.toLocaleString("fa-IR")}</div>
                </div>
                <div class="card glass">
                    <div class="card-title">شرکت‌کنندگان</div>
                    <div class="card-value">${s.participants.toLocaleString("fa-IR")}</div>
                </div>
                <div class="card glass">
                    <div class="card-title">دروس فعال</div>
                    <div class="card-value">${s.total_courses.toLocaleString("fa-IR")}</div>
                </div>
            </div>

            <div class="section-title">دروس پرتقاضا</div>
            <div class="card glass">
                <div class="chart-wrap"><canvas id="top-chart"></canvas></div>
            </div>

            ${data.participation.length > 0 ? `
                <div class="section-title">مشارکت بر اساس ورودی</div>
                <div class="card glass">
                    <div class="chart-wrap"><canvas id="part-chart"></canvas></div>
                </div>
            ` : ""}
        `;

        // نمودار دروس پرتقاضا
        const ctx1 = document.getElementById("top-chart").getContext("2d");
        if (state.chart) state.chart.destroy();
        state.chart = new Chart(ctx1, {
            type: "bar",
            data: {
                labels: data.top_courses.slice(0, 10).map(c => c.title),
                datasets: [{
                    label: "تعداد پیشنهاد",
                    data: data.top_courses.slice(0, 10).map(c => c.count),
                    backgroundColor: (ctx) => {
                        const grad = ctx.chart.ctx.createLinearGradient(0, 0, 0, 200);
                        grad.addColorStop(0, "rgba(167,139,250,0.9)");
                        grad.addColorStop(1, "rgba(244,114,182,0.6)");
                        return grad;
                    },
                    borderRadius: 8,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: "#cbd5e1", font: { size: 10 } }, grid: { display: false } },
                    y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.05)" } }
                }
            }
        });

        // نمودار مشارکت
        const partCtx = document.getElementById("part-chart");
        if (partCtx) {
            const partData = data.participation.filter(p => p.year !== 100);
            new Chart(partCtx.getContext("2d"), {
                type: "doughnut",
                data: {
                    labels: partData.map(p => `${p.year_group || p.year} - ${p.student_type}`),
                    datasets: [{
                        data: partData.map(p => p.count),
                        backgroundColor: ["#a78bfa", "#f472b6", "#38bdf8", "#34d399", "#fbbf24"],
                        borderWidth: 0,
                    }]
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { color: "#cbd5e1", font: { size: 11 } } } } }
            });
        }

    } catch (e) {
        el.innerHTML = `<div class="card glass"><div class="empty-state"><span class="emoji">⚠️</span><p>${escapeHtml(e.message)}</p></div></div>`;
    }
}

async function loadAdminCourses() {
    const el = document.getElementById("admin-content");
    try {
        const data = await api(API.adminCourses);
        el.innerHTML = `
            <button class="btn btn-primary" id="btn-add-course" style="margin-bottom:16px;">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
                افزودن درس جدید
            </button>
            <div class="course-list">
                ${data.courses.map(c => `
                    <div class="course-item">
                        <div class="course-info">
                            <div class="course-title">${escapeHtml(c.title)}</div>
                            <div class="course-meta">
                                <span class="section-tag">${c.section_label || c.section}</span>
                                <span>سال ${c.year}</span>
                                ${c.credits ? `<span>🕒 ${c.credits}</span>` : ""}
                            </div>
                        </div>
                        <button class="icon-btn btn-del-course" data-id="${c.id}" title="حذف">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                        </button>
                    </div>
                `).join("")}
            </div>
        `;

        document.getElementById("btn-add-course").addEventListener("click", showAddCourseForm);
        document.querySelectorAll(".btn-del-course").forEach(b => {
            b.addEventListener("click", async () => {
                if (!confirm("حذف شود؟")) return;
                try {
                    await api(API.adminDeleteCourse, { id: parseInt(b.dataset.id) });
                    showToast("حذف شد", "success");
                    loadAdminCourses();
                } catch (e) { showToast(e.message, "error"); }
            });
        });
    } catch (e) {
        el.innerHTML = `<div class="card glass"><div class="empty-state"><span class="emoji">⚠️</span><p>${escapeHtml(e.message)}</p></div></div>`;
    }
}

function showAddCourseForm() {
    const el = document.getElementById("admin-content");
    el.innerHTML = `
        <div class="card glass">
            <h2 class="text-gradient" style="margin-bottom:16px;">افزودن درس</h2>
            <div class="input-group">
                <label>عنوان درس</label>
                <input class="input" id="ac-title">
            </div>
            <div class="input-group">
                <label>بخش</label>
                <select class="select" id="ac-section">
                    <option value="basic">پایه</option>
                    <option value="core">اصلی</option>
                    <option value="specialized">تخصصی</option>
                    <option value="specialized_ai">تخصصی هوش</option>
                    <option value="specialized_sw">تخصصی نرم‌افزار</option>
                    <option value="electives">اختیاری</option>
                </select>
            </div>
            <div class="stats-grid" style="grid-template-columns:1fr 1fr;">
                <div class="input-group">
                    <label>سال ورودی</label>
                    <select class="select" id="ac-year">
                        <option value="1403">1403</option>
                        <option value="1394">1394</option>
                    </select>
                </div>
                <div class="input-group">
                    <label>نوع</label>
                    <select class="select" id="ac-type">
                        <option value="پیوسته">پیوسته</option>
                        <option value="ناپیوسته">ناپیوسته</option>
                    </select>
                </div>
            </div>
            <div class="stats-grid" style="grid-template-columns:1fr 1fr;">
                <div class="input-group">
                    <label>شماره ردیف</label>
                    <input class="input" id="ac-row" type="number">
                </div>
                <div class="input-group">
                    <label>تعداد واحد</label>
                    <input class="input" id="ac-credits" placeholder="3">
                </div>
            </div>
            <div class="input-group">
                <label>پیش‌نیاز</label>
                <input class="input" id="ac-prereq" placeholder="—">
            </div>
            <button class="btn btn-primary" id="btn-save-course">ذخیره</button>
            <button class="btn btn-ghost" id="btn-cancel-add" style="margin-top:8px;">انصراف</button>
        </div>
    `;
    document.getElementById("btn-save-course").addEventListener("click", async () => {
        try {
            await api(API.adminAddCourse, {
                course_title: document.getElementById("ac-title").value,
                section: document.getElementById("ac-section").value,
                year: document.getElementById("ac-year").value,
                type_coures: document.getElementById("ac-type").value,
                row_number: document.getElementById("ac-row").value,
                credits: document.getElementById("ac-credits").value,
                prerequisite: document.getElementById("ac-prereq").value,
            });
            showToast("درس اضافه شد ✓", "success");
            loadAdminCourses();
        } catch (e) { showToast(e.message, "error"); }
    });
    document.getElementById("btn-cancel-add").addEventListener("click", loadAdminCourses);
}

async function loadAdminUsers() {
    const el = document.getElementById("admin-content");
    try {
        const data = await api(API.adminUsers);
        el.innerHTML = `
            <div class="card glass">
                ${data.users.map(u => `
                    <div class="user-row">
                        <div class="user-info-block">
                            <div class="user-name">${escapeHtml(u.name)}</div>
                            <div class="user-meta">
                                <span>شماره: ${escapeHtml(u.student_number)}</span>
                                <span>${escapeHtml(u.student_type || "—")}</span>
                                <span>📞 ${escapeHtml(u.phone)}</span>
                            </div>
                        </div>
                        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px;">
                            <span class="role-badge ${u.role}">${u.role === "admin" ? "ادمین" : "دانشجو"}</span>
                            <span class="text-muted" style="font-size:11px;">${u.requests_count} پیشنهاد</span>
                        </div>
                    </div>
                `).join("")}
            </div>
        `;
    } catch (e) {
        el.innerHTML = `<div class="card glass"><div class="empty-state"><span class="emoji">⚠️</span><p>${escapeHtml(e.message)}</p></div></div>`;
    }
}

function loadAdminReport() {
    const el = document.getElementById("admin-content");
    el.innerHTML = `
        <div class="card glass text-center">
            <span class="emoji" style="font-size:48px;display:block;margin-bottom:12px;">📊</span>
            <h3 class="text-gradient" style="font-size:18px;margin-bottom:8px;">گزارش کامل اکسل</h3>
            <p class="text-muted" style="font-size:13px;margin-bottom:16px;">
                شامل داده‌های خام، خلاصه و نمودار ۲۰ درس پرتقاضا
            </p>
            <button class="btn btn-primary" id="btn-download-excel">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                دانلود فایل اکسل
            </button>
        </div>
    `;
    document.getElementById("btn-download-excel").addEventListener("click", downloadExcel);
}

async function downloadExcel() {
    try {
        showToast("در حال آماده‌سازی...", "info");
        const res = await fetch(API.adminReportExcel, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Auth-Data": state.init_data || "",
            },
            body: JSON.stringify({ initData: state.init_data }),
        });
        if (!res.ok) throw new Error("دانلود ناموفق بود");
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `report_behman_${Date.now()}.xlsx`;
        a.click();
        URL.revokeObjectURL(url);
        showToast("دانلود شد ✓", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ==================================================
// Notifications Panel
// ==================================================
function initNotifPanel() {
    document.getElementById("btn-notif").addEventListener("click", toggleNotifPanel);
    document.getElementById("btn-close-notif").addEventListener("click", toggleNotifPanel);
}

async function toggleNotifPanel() {
    const panel = document.getElementById("notif-panel");
    if (!panel.hidden) {
        panel.hidden = true;
        return;
    }
    panel.hidden = false;
    const list = document.getElementById("notif-list");
    list.innerHTML = `<div class="spinner"></div>`;

    try {
        const data = await api(API.notifications);
        if (data.notifications.length === 0) {
            list.innerHTML = `<div class="empty-state"><span class="emoji">🔔</span><p>اعلانی وجود ندارد</p></div>`;
            return;
        }
        list.innerHTML = data.notifications.map(n => `
            <div class="notif-item ${n.level}">
                <h4>${escapeHtml(n.title)}</h4>
                <p>${escapeHtml(n.body || "")}</p>
                <time>${formatDate(n.created_at)}</time>
            </div>
        `).join("");
    } catch (e) {
        list.innerHTML = `<div class="empty-state"><p>${escapeHtml(e.message)}</p></div>`;
    }
}

// ==================================================
// Helpers
// ==================================================
function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatDate(s) {
    if (!s) return "—";
    try {
        const d = new Date(s + (s.includes("Z") ? "" : "Z"));
        return new Intl.DateTimeFormat("fa-IR", {
            year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
        }).format(d);
    } catch { return s; }
}


function confirmCourseSubmission(count) {
    return new Promise((resolve) => {
        const overlay = document.createElement("div");
        overlay.style.cssText =
            "position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.7);" +
            "display:flex;align-items:center;justify-content:center;padding:20px;";

        const box = document.createElement("div");
        box.dir = "rtl";
        box.style.cssText =
            "background:#182235;color:#fff;padding:24px;border-radius:16px;" +
            "width:100%;max-width:380px;text-align:center;font-family:inherit;";

        const message = document.createElement("p");
        const nonExempt = getNonExemptSelectedCount();
        const exempt = getExemptSelectedCount();
        message.innerHTML =
            `<b>${count}</b> درس انتخاب شده است` +
            (exempt > 0 ? ` (<b>${nonExempt}</b> عادی + <b>${exempt}</b> کارآموزی/پروژه)` : "") +
            `. آیا ثبت نهایی انجام شود؟`;
        message.style.lineHeight = "1.9";
        message.style.cssText = "line-height:1.9;margin:0 0 20px;";

        const yes = document.createElement("button");
        yes.type = "button";
        yes.textContent = "تأیید و ثبت نهایی";
        yes.style.cssText =
            "background:#2563eb;color:white;border:0;border-radius:8px;" +
            "padding:12px;margin:5px;cursor:pointer;font:inherit;";

        const no = document.createElement("button");
        no.type = "button";
        no.textContent = "انصراف";
        no.style.cssText =
            "background:#475569;color:white;border:0;border-radius:8px;" +
            "padding:12px;margin:5px;cursor:pointer;font:inherit;";

        const finish = (accepted) => {
            overlay.remove();
            resolve(accepted);
        };

        yes.addEventListener("click", () => finish(true), { once: true });
        no.addEventListener("click", () => finish(false), { once: true });
        overlay.addEventListener("click", (event) => {
            if (event.target === overlay) finish(false);
        });

        box.append(message, yes, no);
        overlay.appendChild(box);
        document.body.appendChild(overlay);
        no.focus();
    });
}