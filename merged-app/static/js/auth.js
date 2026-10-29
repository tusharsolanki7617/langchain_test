/* ============================================================
   EduX Platform — auth.js
   Role switching · Demo login · Password utilities · Admin controls
   ============================================================ */

/* ── Role Switcher ────────────────────────────────────────────── */
function switchRole(role) {
  // Update hidden input
  const roleInput = document.getElementById('role-input');
  if (roleInput) roleInput.value = role;

  // Update tab styling
  ['student', 'teacher', 'admin'].forEach(function(r) {
    const tab = document.getElementById('tab-' + r);
    if (tab) {
      tab.classList.toggle('active', r === role);
      tab.setAttribute('aria-selected', r === role ? 'true' : 'false');
    }
  });

  // Update signup-specific dynamic fields
  updateSignupFields(role);

  // Update the "go to signup / login" link role param
  ['go-to-signup', 'back-to-login', 'go-to-login'].forEach(function(id) {
    const link = document.getElementById(id);
    if (link) {
      const url = new URL(link.href, window.location.origin);
      url.searchParams.set('role', role);
      link.href = url.toString();
    }
  });

  // Animate the card on role change
  const card = document.querySelector('.auth-card');
  if (card) {
    card.style.animation = 'none';
    card.offsetHeight; // reflow
    card.style.animation = 'cardIn 0.3s ease';
  }
}

/* ── Dynamic Signup Field Show/Hide ─────────────────────────── */
function updateSignupFields(role) {
  const studentFields = document.getElementById('student-fields');
  const teacherFields = document.getElementById('teacher-fields');
  const adminFields   = document.getElementById('admin-fields');

  // If none exist this isn't the signup page — skip
  if (!studentFields && !teacherFields && !adminFields) return;

  if (studentFields) studentFields.style.display = role === 'student' ? 'block' : 'none';
  if (teacherFields) teacherFields.style.display = role === 'teacher' ? 'block' : 'none';
  if (adminFields)   adminFields.style.display   = role === 'admin'   ? 'block' : 'none';

  // Toggle required on admin code
  const adminCodeInput = document.getElementById('admin_code');
  if (adminCodeInput) adminCodeInput.required = role === 'admin';
}

/* ── 1-Click Demo Login ───────────────────────────────────────── */
function demoLogin(role) {
  const btn = document.getElementById('demo-' + role + '-btn');
  if (btn) {
    btn.disabled = true;
    btn.style.opacity = '0.7';
    btn.innerHTML = '<span class="demo-icon">⏳</span><span class="demo-info"><strong>Signing in…</strong><small>' + role + '@edux.com</small></span>';
  }

  fetch('/api/demo-login/' + role, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(function(res) { return res.json(); })
  .then(function(data) {
    if (data.success && data.redirect) {
      window.location.href = data.redirect;
    } else {
      showToast('Demo login failed: ' + (data.error || 'Unknown error'), 'error');
      if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
    }
  })
  .catch(function(err) {
    showToast('Network error. Please try again.', 'error');
    if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
  });
}

/* ── Password Visibility Toggle ──────────────────────────────── */
function togglePassword(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const isText = input.type === 'text';
  input.type = isText ? 'password' : 'text';
  // Swap icon
  btn.innerHTML = isText
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
}

/* ── Password Strength Meter ─────────────────────────────────── */
function updatePasswordStrength(value) {
  const fill = document.getElementById('strength-fill');
  const label = document.getElementById('strength-label');
  if (!fill || !label) return;

  let score = 0;
  if (value.length >= 6) score++;
  if (value.length >= 10) score++;
  if (/[A-Z]/.test(value)) score++;
  if (/[0-9]/.test(value)) score++;
  if (/[^A-Za-z0-9]/.test(value)) score++;

  const levels = [
    { pct: '8%',  color: '#f87171', text: 'Too short' },
    { pct: '28%', color: '#fb923c', text: 'Weak' },
    { pct: '50%', color: '#fbbf24', text: 'Fair' },
    { pct: '72%', color: '#60a5fa', text: 'Good' },
    { pct: '92%', color: '#34d399', text: 'Strong' },
    { pct: '100%',color: '#34d399', text: 'Very strong ✓' }
  ];

  const level = levels[Math.min(score, 5)];
  fill.style.width = level.pct;
  fill.style.background = level.color;
  label.textContent = level.text;
  label.style.color = level.color;
}

/* ── Password Match Check ────────────────────────────────────── */
function checkPasswordMatch() {
  const pw = document.getElementById('password');
  const cp = document.getElementById('confirm_password');
  const hint = document.getElementById('match-hint');
  if (!pw || !cp || !hint) return;
  if (cp.value.length === 0) { hint.style.display = 'none'; return; }
  const match = pw.value === cp.value;
  hint.style.display = match ? 'none' : 'block';
}

/* ── Email Availability Check ────────────────────────────────── */
let emailDebounce = null;
function checkEmailAvailability(value) {
  const statusEl = document.getElementById('email-status');
  if (!statusEl) return;

  clearTimeout(emailDebounce);
  if (!value || !value.includes('@')) { statusEl.textContent = ''; return; }

  statusEl.textContent = '⏳ Checking…';
  statusEl.style.color = 'var(--text-muted)';

  emailDebounce = setTimeout(function() {
    fetch('/api/check-email?email=' + encodeURIComponent(value))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.available) {
        statusEl.textContent = '✅ Available';
        statusEl.style.color = 'var(--success)';
      } else {
        statusEl.textContent = '❌ Already taken';
        statusEl.style.color = 'var(--error)';
      }
    })
    .catch(function() { statusEl.textContent = ''; });
  }, 500);
}

/* ── Admin: Toggle User Status ───────────────────────────────── */
function toggleUser(userId) {
  const btn = document.getElementById('toggle-' + userId);
  if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; }

  fetch('/api/admin/toggle-user/' + userId, { method: 'POST' })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.success) {
      const statusEl = document.getElementById('status-' + userId);
      const ns = data.new_status;
      if (statusEl) {
        statusEl.textContent = ns.charAt(0).toUpperCase() + ns.slice(1);
        statusEl.className = 'status-pill status-' + ns;
      }
      if (btn) {
        btn.disabled = false;
        btn.style.opacity = '1';
        if (ns === 'active') {
          btn.textContent = '🔒 Deactivate';
          btn.className = 'toggle-btn btn-deactivate';
        } else {
          btn.textContent = '✅ Activate';
          btn.className = 'toggle-btn btn-activate';
        }
      }
      showToast('User status changed to ' + ns, 'success');
    } else {
      showToast(data.error || 'Action failed', 'error');
      if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
    }
  })
  .catch(function() {
    showToast('Network error. Please try again.', 'error');
    if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
  });
}

/* ── Toast Notification ──────────────────────────────────────── */
function showToast(message, type) {
  type = type || 'info';
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };

  const container = document.querySelector('.flash-container') || createFlashContainer();
  const toast = document.createElement('div');
  toast.className = 'flash flash-' + type;
  toast.innerHTML =
    '<span class="flash-icon">' + (icons[type] || 'ℹ️') + '</span>' +
    '<span class="flash-msg">' + message + '</span>' +
    '<button class="flash-close" onclick="this.parentElement.remove()">✕</button>';

  container.appendChild(toast);
  setTimeout(function() {
    toast.style.animation = 'slideOut 0.4s ease forwards';
    setTimeout(function() { toast.remove(); }, 400);
  }, 4000);
}

function createFlashContainer() {
  const div = document.createElement('div');
  div.className = 'flash-container';
  document.body.appendChild(div);
  return div;
}

/* ── Page Initializer ────────────────────────────────────────── */
function initAuthPage(currentRole) {
  // Set initial role state
  switchRole(currentRole || 'student');
}

/* ── Score bar animation on load ─────────────────────────────── */
document.addEventListener('DOMContentLoaded', function() {
  // Animate score bars after paint
  setTimeout(function() {
    document.querySelectorAll('.score-fill').forEach(function(bar) {
      const w = bar.style.width;
      bar.style.width = '0';
      setTimeout(function() { bar.style.width = w; }, 100);
    });
  }, 200);

  // Sidebar active link from hash
  const hash = window.location.hash;
  if (hash) {
    document.querySelectorAll('.nav-link').forEach(function(link) {
      link.classList.toggle('active', link.getAttribute('href') === hash);
    });
  }
});
