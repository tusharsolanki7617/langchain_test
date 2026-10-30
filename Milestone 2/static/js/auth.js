/* ============================================================
   EduX Platform — auth.js
   Role Switching · Live Validation · Demo Sign-In · Password Metrics
   ============================================================ */

/* ── Role Switcher ────────────────────────────────────────────── */
function switchRole(role) {
  role = (role || 'student').toLowerCase();
  if (!['student', 'teacher', 'admin'].includes(role)) {
    role = 'student';
  }

  // 1. Update container theme class for dynamic theme accents
  const container = document.getElementById('auth-container');
  if (container) {
    container.classList.remove('role-theme-student', 'role-theme-teacher', 'role-theme-admin');
    container.classList.add('role-theme-' + role);
  }

  document.body.classList.toggle('examai-teacher-auth', role === 'teacher');
  if (role === 'teacher') {
    document.documentElement.setAttribute('data-theme', 'light');
  }

  // 2. Update hidden role input in form
  const roleInput = document.getElementById('role-input');
  if (roleInput) roleInput.value = role;

  // 3. Update role selector tabs
  ['student', 'teacher', 'admin'].forEach(function(r) {
    const tab = document.getElementById('tab-' + r);
    if (tab) {
      const isActive = r === role;
      tab.classList.toggle('active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    }
  });

  // 4. Update left-side hero block showcase
  ['student', 'teacher', 'admin'].forEach(function(r) {
    const heroBlock = document.getElementById('hero-role-' + r);
    if (heroBlock) {
      heroBlock.style.display = r === role ? 'block' : 'none';
      if (r === role) {
        heroBlock.style.animation = 'none';
        heroBlock.offsetHeight; // trigger reflow
        heroBlock.style.animation = 'fadeIn 0.35s ease';
      }
    }
  });

  const cardTitle = document.getElementById('auth-card-title');
  const cardSub = document.getElementById('auth-card-sub');
  if (cardTitle && cardSub) {
    if (role === 'teacher') {
      cardTitle.textContent = 'Teacher sign in';
      cardSub.textContent = 'Enter your faculty credentials to open the ExamAI teacher portal.';
    } else {
      cardTitle.textContent = 'Welcome back';
      cardSub.textContent = 'Choose your role and enter your institutional credentials to continue';
    }
  }

  // 5. Update header role badge in card
  const headerBadge = document.getElementById('header-role-badge');
  if (headerBadge) {
    const badges = {
      student: '🎓 Student Sign In',
      teacher: 'Teacher portal',
      admin:   '⚙️ Admin Sign In'
    };
    const signupBadges = {
      student: '🎓 Student Registration',
      teacher: '📚 Teacher Registration',
      admin:   '⚙️ Admin Registration'
    };
    const isSignup = document.getElementById('signup-form') !== null;
    headerBadge.textContent = isSignup ? signupBadges[role] : badges[role];
    headerBadge.className = 'role-badge role-badge-current role-' + role;
  }

  // 6. Update action button label
  const btnText = document.getElementById('btn-text');
  if (btnText) {
    btnText.textContent = 'Sign In as ' + role.charAt(0).toUpperCase() + role.slice(1);
  }
  const signupBtnText = document.getElementById('signup-btn-text');
  if (signupBtnText) {
    signupBtnText.textContent = 'Create ' + role.charAt(0).toUpperCase() + role.slice(1) + ' Account';
  }

  // 7. Highlight matching demo pill button if present
  ['student', 'teacher', 'admin'].forEach(function(r) {
    const pill = document.getElementById('demo-' + r + '-btn');
    if (pill) pill.classList.toggle('active-demo', r === role);
  });

  // 8. Update signup-specific dynamic fields
  updateSignupFields(role);

  // 9. Update links to carry the current role query param
  ['go-to-signup', 'back-to-login', 'go-to-login'].forEach(function(id) {
    const link = document.getElementById(id);
    if (link) {
      try {
        const url = new URL(link.href, window.location.origin);
        url.searchParams.set('role', role);
        link.href = url.pathname + url.search;
      } catch (e) {
        // Fallback
      }
    }
  });

  // 10. Update email placeholder / hint
  const emailInput = document.getElementById('email');
  if (emailInput && !emailInput.value) {
    const hints = {
      student: 'e.g. student@university.edu',
      teacher: 'e.g. professor@university.edu',
      admin:   'e.g. admin@university.edu'
    };
    emailInput.placeholder = hints[role] || 'name@university.edu';
  }
}

/* ── Dynamic Signup Field Show/Hide ─────────────────────────── */
function updateSignupFields(role) {
  const studentFields = document.getElementById('student-fields');
  const teacherFields = document.getElementById('teacher-fields');
  const adminFields   = document.getElementById('admin-fields');

  if (studentFields) studentFields.style.display = role === 'student' ? 'block' : 'none';
  if (teacherFields) teacherFields.style.display = role === 'teacher' ? 'block' : 'none';
  if (adminFields)   adminFields.style.display   = role === 'admin'   ? 'block' : 'none';

  // Toggle required on admin code
  const adminCodeInput = document.getElementById('admin_code');
  if (adminCodeInput) adminCodeInput.required = (role === 'admin');

  // Update signup callout text
  const callout = document.getElementById('form-role-callout');
  if (callout) {
    if (role === 'admin') {
      callout.innerHTML = `
        <div class="callout-content callout-admin">
          <span class="callout-icon">⚡</span>
          <span>Admin accounts with valid code are activated instantly.</span>
        </div>`;
    } else {
      const roleCapital = role.charAt(0).toUpperCase() + role.slice(1);
      callout.innerHTML = `
        <div class="callout-content callout-pending">
          <span class="callout-icon">⏳</span>
          <span>${roleCapital} accounts will be placed in the Admin Approval queue before first sign-in.</span>
        </div>`;
    }
  }
}

/* ── 1-Click Demo Login ───────────────────────────────────────── */
function demoLogin(role) {
  const btn = document.getElementById('demo-' + role + '-btn');
  const origContent = btn ? btn.innerHTML : '';

  if (btn) {
    btn.disabled = true;
    btn.classList.add('demo-loading');
    btn.innerHTML = '<span class="demo-pill-icon">⏳</span><span class="demo-pill-text">Signing in…</span>';
  }

  // Switch tab visually right away
  switchRole(role);

  fetch('/api/demo-login/' + encodeURIComponent(role), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  .then(function(res) {
    return res.json().then(data => ({ status: res.status, data: data }));
  })
  .then(function(result) {
    if (result.data.success && result.data.redirect) {
      if (btn) {
        btn.innerHTML = '<span class="demo-pill-icon">✅</span><span class="demo-pill-text">Success!</span>';
      }
      showToast('Signed in successfully as ' + role.toUpperCase() + '!', 'success');
      setTimeout(function() {
        window.location.href = result.data.redirect;
      }, 400);
    } else {
      showToast(result.data.error || 'Demo login failed.', 'error');
      if (btn) {
        btn.disabled = false;
        btn.classList.remove('demo-loading');
        btn.innerHTML = origContent;
      }
    }
  })
  .catch(function(err) {
    showToast('Network error during quick sign-in. Please try again.', 'error');
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('demo-loading');
      btn.innerHTML = origContent;
    }
  });
}

/* ── Password Visibility Toggle ──────────────────────────────── */
function togglePassword(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const isText = input.type === 'text';
  input.type = isText ? 'password' : 'text';

  btn.innerHTML = isText
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
}

/* ── Multi-Segment Password Strength Meter ───────────────────── */
function updatePasswordStrength(val) {
  val = val || '';
  const seg1 = document.getElementById('seg-1');
  const seg2 = document.getElementById('seg-2');
  const seg3 = document.getElementById('seg-3');
  const seg4 = document.getElementById('seg-4');
  const label = document.getElementById('strength-label');
  const chkLen = document.getElementById('chk-len');
  const chkNum = document.getElementById('chk-num');
  const chkSym = document.getElementById('chk-sym');

  const hasLen = val.length >= 6;
  const hasNum = /[0-9]/.test(val);
  const hasSym = /[^A-Za-z0-9]/.test(val) || /[A-Z]/.test(val);

  if (chkLen) chkLen.classList.toggle('chk-passed', hasLen);
  if (chkNum) chkNum.classList.toggle('chk-passed', hasNum);
  if (chkSym) chkSym.classList.toggle('chk-passed', hasSym);

  // Score calculation
  let score = 0;
  if (val.length >= 6) score++;
  if (val.length >= 9) score++;
  if (hasNum) score++;
  if (hasSym) score++;

  const segments = [seg1, seg2, seg3, seg4];
  segments.forEach(function(s) {
    if (s) { s.className = 'strength-bar-segment'; }
  });

  if (!val) {
    if (label) { label.textContent = 'Enter password'; label.style.color = 'var(--text-muted)'; }
    return;
  }

  const levels = [
    { text: 'Too short', color: '#f87171', fill: 1, cls: 'seg-weak' },
    { text: 'Weak',      color: '#fb923c', fill: 2, cls: 'seg-fair' },
    { text: 'Good',      color: '#60a5fa', fill: 3, cls: 'seg-good' },
    { text: 'Strong ✓',  color: '#34d399', fill: 4, cls: 'seg-strong' }
  ];

  const idx = Math.min(Math.max(score - 1, 0), 3);
  const level = levels[idx];

  for (let i = 0; i < level.fill; i++) {
    if (segments[i]) segments[i].classList.add(level.cls);
  }

  if (label) {
    label.textContent = level.text;
    label.style.color = level.color;
  }
}

/* ── Password Match Real-Time Check ──────────────────────────── */
function checkPasswordMatch() {
  const pw = document.getElementById('password');
  const cp = document.getElementById('confirm_password');
  const hint = document.getElementById('match-hint');
  const status = document.getElementById('match-status');

  if (!pw || !cp) return;

  if (!cp.value) {
    if (hint) hint.style.display = 'none';
    if (status) status.innerHTML = '';
    cp.classList.remove('input-match-success', 'input-match-error');
    return;
  }

  const matches = (pw.value === cp.value);
  if (matches) {
    if (hint) hint.style.display = 'none';
    if (status) {
      status.innerHTML = '<span class="status-match-good">✓ Passwords match</span>';
    }
    cp.classList.add('input-match-success');
    cp.classList.remove('input-match-error');
  } else {
    if (hint) hint.style.display = 'block';
    if (status) {
      status.innerHTML = '<span class="status-match-bad">✕ Passwords mismatch</span>';
    }
    cp.classList.add('input-match-error');
    cp.classList.remove('input-match-success');
  }
}

/* ── Live Email Availability Check ───────────────────────────── */
let emailDebounceTimer = null;
function checkEmailAvailability(val) {
  const statusEl = document.getElementById('email-status');
  if (!statusEl) return;

  clearTimeout(emailDebounceTimer);
  val = (val || '').trim();

  if (!val || !val.includes('@') || !val.includes('.')) {
    statusEl.innerHTML = '';
    return;
  }

  statusEl.innerHTML = '<span class="status-checking">⏳ Verifying…</span>';

  emailDebounceTimer = setTimeout(function() {
    fetch('/api/check-email?email=' + encodeURIComponent(val))
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.available) {
          statusEl.innerHTML = '<span class="status-available">✅ Available</span>';
        } else {
          statusEl.innerHTML = '<span class="status-taken">❌ Already registered</span>';
        }
      })
      .catch(function() {
        statusEl.innerHTML = '';
      });
  }, 400);
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
    '<button class="flash-close" onclick="this.parentElement.remove()" aria-label="Dismiss">✕</button>';

  container.appendChild(toast);
  setTimeout(function() {
    toast.style.animation = 'slideOut 0.35s ease forwards';
    setTimeout(function() { toast.remove(); }, 350);
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
  switchRole(currentRole || 'student');

  // Attach submit spinner on forms
  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', function() {
      const btn = document.getElementById('login-submit-btn');
      const spinner = document.getElementById('btn-spinner');
      if (btn) btn.classList.add('btn-submitting');
      if (spinner) spinner.style.display = 'inline-block';
    });
  }

  const signupForm = document.getElementById('signup-form');
  if (signupForm) {
    signupForm.addEventListener('submit', function() {
      const btn = document.getElementById('signup-submit-btn');
      const spinner = document.getElementById('signup-spinner');
      if (btn) btn.classList.add('btn-submitting');
      if (spinner) spinner.style.display = 'inline-block';
    });
  }
}
