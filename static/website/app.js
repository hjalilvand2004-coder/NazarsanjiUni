/* ==================================================
   Public Website JS v2.0.0
   ================================================== */

document.addEventListener("DOMContentLoaded", () => {
    createStars();
    animateCounters();
    initScrollReveal();
});

// ==================================================
// Stars Background
// ==================================================
function createStars() {
    const container = document.getElementById("stars");
    if (!container) return;
    const count = 80;
    for (let i = 0; i < count; i++) {
        const s = document.createElement("div");
        s.className = "star";
        s.style.left = Math.random() * 100 + "%";
        s.style.top = Math.random() * 100 + "%";
        s.style.animationDelay = Math.random() * 3 + "s";
        s.style.animationDuration = (2 + Math.random() * 3) + "s";
        const size = 1 + Math.random() * 2;
        s.style.width = size + "px";
        s.style.height = size + "px";
        container.appendChild(s);
    }
}

// ==================================================
// Counter Animation
// ==================================================
function animateCounters() {
    const counters = document.querySelectorAll("[data-counter]");
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const el = entry.target;
                const target = parseInt(el.dataset.counter) || 0;
                const valueEl = el.querySelector(".stat-value");
                if (!valueEl) return;
                animateNumber(valueEl, target);
                observer.unobserve(el);
            }
        });
    }, { threshold: 0.5 });

    counters.forEach(c => observer.observe(c));
}

function animateNumber(el, target) {
    let current = 0;
    const duration = 1500;
    const start = performance.now();
    const easeOutCubic = t => 1 - Math.pow(1 - t, 3);

    function update(now) {
        const elapsed = now - start;
        const t = Math.min(elapsed / duration, 1);
        const eased = easeOutCubic(t);
        current = Math.floor(eased * target);
        el.textContent = toFaDigits(current);
        if (t < 1) requestAnimationFrame(update);
        else el.textContent = toFaDigits(target);
    }
    requestAnimationFrame(update);
}

function toFaDigits(n) {
    return String(n).replace(/[0-9]/g, d => "۰۱۲۳۴۵۶۷۸۹"[d]);
}

// ==================================================
// Scroll Reveal
// ==================================================
function initScrollReveal() {
    const elements = document.querySelectorAll(".feature-card, .stat-card, .top-course-card, .step");
    elements.forEach(el => {
        el.style.opacity = "0";
        el.style.transform = "translateY(20px)";
        el.style.transition = "opacity 0.6s ease, transform 0.6s ease";
    });

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry, i) => {
            if (entry.isIntersecting) {
                setTimeout(() => {
                    entry.target.style.opacity = "1";
                    entry.target.style.transform = "translateY(0)";
                }, i * 60);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    elements.forEach(el => observer.observe(el));
}

// ==================================================
// Live Stats Refresh (Dashboard page)
// ==================================================
let liveChart = null;

async function refreshLiveStats() {
    try {
        const res = await fetch("/api/public/stats");
        const data = await res.json();
        if (!data.ok) return;

        const s = data.stats;
        updateCounter("stat-users", s.total_users);
        updateCounter("stat-requests", s.total_requests);
        updateCounter("stat-participants", s.participants);
        updateCounter("stat-courses", s.total_courses);

        if (typeof Chart !== "undefined") {
            renderCharts(s);
        }
    } catch (e) {
        console.error("Live refresh failed:", e);
    }
}

function updateCounter(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = toFaDigits(val);
}

function renderCharts(s) {
    // Top courses chart
    const ctx = document.getElementById("chart-top");
    if (ctx && s.top_courses && s.top_courses.length) {
        if (window._topChart) window._topChart.destroy();
        window._topChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels: s.top_courses.map(c => c.title),
                datasets: [{
                    label: "تعداد پیشنهاد",
                    data: s.top_courses.map(c => c.cnt),
                    backgroundColor: (ctx) => {
                        const grad = ctx.chart.ctx.createLinearGradient(0, 0, 0, 280);
                        grad.addColorStop(0, "rgba(167,139,250,0.9)");
                        grad.addColorStop(1, "rgba(244,114,182,0.5)");
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
                    x: { ticks: { color: "#cbd5e1", font: { size: 11 } }, grid: { display: false } },
                    y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.05)" } }
                }
            }
        });
    }

    // Sections chart
    const ctx2 = document.getElementById("chart-sections");
    if (ctx2 && s.sections && s.sections.length) {
        if (window._sectChart) window._sectChart.destroy();
        const labels = { basic: "پایه", core: "اصلی", specialized: "تخصصی", specialized_ai: "هوش", specialized_sw: "نرم‌افزار", electives: "اختیاری" };
        window._sectChart = new Chart(ctx2, {
            type: "doughnut",
            data: {
                labels: s.sections.map(s => labels[s.section] || s.section),
                datasets: [{
                    data: s.sections.map(s => s.cnt),
                    backgroundColor: ["#a78bfa", "#f472b6", "#38bdf8", "#34d399", "#fbbf24", "#f87171"],
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "bottom", labels: { color: "#cbd5e1", font: { size: 11 }, padding: 14 } } }
            }
        });
    }

    // Daily trend
    const ctx3 = document.getElementById("chart-daily");
    if (ctx3 && s.daily && s.daily.length) {
        if (window._dailyChart) window._dailyChart.destroy();
        const reversed = [...s.daily].reverse();
        window._dailyChart = new Chart(ctx3, {
            type: "line",
            data: {
                labels: reversed.map(d => d.day),
                datasets: [{
                    label: "پیشنهادهای روزانه",
                    data: reversed.map(d => d.cnt),
                    borderColor: "#a78bfa",
                    backgroundColor: (ctx) => {
                        const grad = ctx.chart.ctx.createLinearGradient(0, 0, 0, 280);
                        grad.addColorStop(0, "rgba(167,139,250,0.4)");
                        grad.addColorStop(1, "rgba(167,139,250,0)");
                        return grad;
                    },
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 4,
                    pointBackgroundColor: "#f472b6",
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: "#94a3b8", font: { size: 10 } }, grid: { display: false } },
                    y: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255,255,255,0.05)" } }
                }
            }
        });
    }
}

// اگر در صفحه داشبورد بودیم، هر ۳۰ ثانیه رفرش
if (window.location.pathname.startsWith("/dashboard")) {
    if (typeof Chart !== "undefined") {
        // اضافه کردن Chart.js
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js";
        script.onload = () => {
            refreshLiveStats();
            setInterval(refreshLiveStats, 30000);
        };
        document.head.appendChild(script);
    }
}
