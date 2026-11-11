/* ==================================================
   دانشجو360 — Mobile App PWA v1.0.0
   ================================================== */

// PWA Registration
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/app/sw.js')
            .then(reg => console.log('✓ SW registered', reg.scope))
            .catch(err => console.log('SW registration failed', err));
    });
}

// PWA Install Prompt
let deferredPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    showInstallBanner();
});

window.addEventListener('appinstalled', () => {
    hideInstallBanner();
    console.log('✓ دانشجو360 نصب شد');
});

function showInstallBanner() {
    const banner = document.getElementById('install-banner');
    if (banner) banner.style.display = 'flex';
}

function hideInstallBanner() {
    const banner = document.getElementById('install-banner');
    if (banner) banner.style.display = 'none';
    deferredPrompt = null;
}

async function installApp() {
    if (!deferredPrompt) {
        showToast('برای نصب، روی دکمه «افزودن به صفحه اصلی» در منوی مرورگر بزنید', 'info');
        return;
    }
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') {
        console.log('✓ User accepted install');
    }
    deferredPrompt = null;
    hideInstallBanner();
}

// Toast
function showToast(message, type = 'info') {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = message;
    t.className = 'toast show ' + type;
    setTimeout(() => t.classList.remove('show'), 3000);
}

// Number formatting — فارسی
function toFa(n) {
    return String(n).replace(/[0-9]/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
}

// Live stats refresh (dashboard page)
let refreshTimer = null;

async function refreshStats() {
    try {
        const res = await fetch('/api/public/stats');
        const data = await res.json();
        if (!data.ok) return;
        const s = data.stats;
        updateElement('stat-users', toFa(s.total_users));
        updateElement('stat-requests', toFa(s.total_requests));
        updateElement('stat-participants', toFa(s.participants));
        updateElement('stat-courses', toFa(s.total_courses));
    } catch (e) {
        console.error('Refresh failed:', e);
    }
}

function updateElement(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

// On DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Auto-refresh stats every 30s on dashboard
    if (window.location.pathname === '/app/dashboard') {
        refreshStats();
        refreshTimer = setInterval(refreshStats, 30000);
    }

    // Bottom nav active state
    const path = window.location.pathname;
    document.querySelectorAll('.nav-btn').forEach(btn => {
        const href = btn.getAttribute('href') || '';
        if (path === href || (href !== '/app' && path.startsWith(href))) {
            btn.classList.add('active');
        } else if (href === '/app' && path === '/app') {
            btn.classList.add('active');
        }
    });

    // Course search
    const searchInput = document.getElementById('course-search');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const q = e.target.value.toLowerCase();
            document.querySelectorAll('.course-item').forEach(item => {
                const name = (item.dataset.name || '').toLowerCase();
                item.style.display = name.includes(q) ? 'flex' : 'none';
            });
        });
    }
});

// Online/offline indicator
window.addEventListener('online', () => {
    showToast('اتصال اینترنت برقرار شد', 'success');
});

window.addEventListener('offline', () => {
    showToast('اینترنت قطع است — حالت آفلاین', 'warning');
});
