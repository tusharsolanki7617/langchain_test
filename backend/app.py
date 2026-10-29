import os
import re
from functools import wraps
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from flask import (
    Flask, flash, jsonify, redirect,
    render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

from database import db

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "milestone2-super-secret-key-2026")
ADMIN_SECRET_KEY = os.getenv("ADMIN_INVITE_CODE", "ADMIN2026")

# ═══════════════════════════════════════════════════════════════
# PERFORMANCE OPTIMIZATIONS
# ═══════════════════════════════════════════════════════════════

# Enable static file caching
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year for static files

# Add cache headers for static resources
@app.after_request
def add_header(response):
    # Cache static files aggressively
    if request.path.startswith('/static/'):
        response.cache_control.max_age = 31536000
        response.cache_control.public = True
    # Don't cache dynamic content
    else:
        response.cache_control.no_cache = True
        response.cache_control.no_store = True
        response.cache_control.must_revalidate = True
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


# ═══════════════════════════════════════════════════════════════
# DECORATORS
# ═══════════════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            user_role = session.get("role")
            if user_role not in allowed_roles:
                flash(f"Access denied — this section is for {', '.join(allowed_roles)}s only.", "error")
                return redirect(url_for(f"dashboard_{user_role}"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ═══════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def home():
    if "user_id" in session:
        role = session.get("role", "student")
        # Verify user still exists in database
        user = db.find_user_by_id(session["user_id"])
        if not user:
            session.clear()
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for("login"))
        return redirect(url_for(f"dashboard_{role}"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for(f"dashboard_{session.get('role', 'student')}"))

    selected_role = request.args.get("role", "student").lower()
    if selected_role not in ("student", "teacher", "admin"):
        selected_role = "student"

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role     = request.form.get("role", "student").lower()

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template("login.html", selected_role=role, email=email)

        user = db.find_user_by_email(email)

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html", selected_role=role, email=email)

        # Approval gate for non-admins
        if user["role"] != "admin":
            if user.get("status") == "pending":
                flash("Your account is awaiting admin approval. You'll be notified once approved.", "warning")
                return render_template("login.html", selected_role=role, email=email)
            if user.get("status") == "rejected":
                reason = user.get("reject_reason") or "No reason provided."
                flash(f"Your account was rejected: {reason}", "error")
                return render_template("login.html", selected_role=role, email=email)

        if not user.get("active", 1):
            flash("Your account has been deactivated. Contact an administrator.", "error")
            return render_template("login.html", selected_role=role, email=email)

        if user["role"] != role:
            flash(f"This account is registered as {user['role'].capitalize()}, not {role.capitalize()}.", "info")

        session.clear()
        session["user_id"]    = user["id"]
        session["first_name"] = user["first_name"]
        session["last_name"]  = user["last_name"]
        session["full_name"]  = f"{user['first_name']} {user['last_name']}"
        session["email"]      = user["email"]
        session["role"]       = user["role"]

        db.update_last_login(user["id"])
        db.log_activity(user["id"], user["email"], user["role"], "LOGIN",
                        f"Signed in as {user['role']}")

        flash(f"Welcome back, {user['first_name']}! You are signed in as {user['role'].capitalize()}.", "success")
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for(f"dashboard_{user['role']}"))

    return render_template("login.html", selected_role=selected_role, email="")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for(f"dashboard_{session.get('role', 'student')}"))

    selected_role = request.args.get("role", "student").lower()
    if selected_role not in ("student", "teacher", "admin"):
        selected_role = "student"

    if request.method == "POST":
        first_name       = request.form.get("first_name", "").strip()
        last_name        = request.form.get("last_name", "").strip()
        email            = request.form.get("email", "").strip().lower()
        password         = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role             = request.form.get("role", "student").lower()
        # Student-specific
        institute        = request.form.get("institute", "").strip()
        roll_number      = request.form.get("roll_number", "").strip()
        class_year       = request.form.get("class_year", "").strip()
        # Teacher-specific
        department       = request.form.get("department", "").strip()
        # Admin
        admin_code       = request.form.get("admin_code", "").strip()

        form_data = dict(first_name=first_name, last_name=last_name,
                         email=email, institute=institute,
                         roll_number=roll_number, class_year=class_year,
                         department=department)

        def err(msg):
            flash(msg, "error")
            return render_template("signup.html", selected_role=role, **form_data)

        if not first_name or not last_name:
            return err("Please enter your first and last name.")
        if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return err("Please enter a valid email address.")
        if len(password) < 6:
            return err("Password must be at least 6 characters.")
        if password != confirm_password:
            return err("Passwords do not match.")
        if role not in ("student", "teacher", "admin"):
            return err("Invalid role selected.")
        if role == "admin" and admin_code != ADMIN_SECRET_KEY:
            return err("Invalid Admin Security Code.")
        if db.find_user_by_email(email):
            return err("An account with this email already exists.")

        try:
            user_id, status = db.create_user(
                first_name, last_name, email, password, role,
                institute=institute, roll_number=roll_number,
                class_year=class_year, department=department
            )
            db.log_activity(user_id, email, role, "SIGNUP",
                            f"Registered new {role} account")

            if role == "admin":
                flash("Admin account created! You can now sign in.", "success")
                return redirect(url_for("login", role="admin"))
            else:
                # Show pending page
                return render_template("pending.html",
                                       first_name=first_name, email=email, role=role)
        except Exception as e:
            return err(f"Registration error: {e}")

    return render_template("signup.html", selected_role=selected_role)


@app.route("/logout")
def logout():
    user_id = session.get("user_id")
    email   = session.get("email")
    role    = session.get("role")
    if user_id:
        db.log_activity(user_id, email, role, "LOGOUT", "Signed out of session")
    session.clear()
    flash("You've been signed out. See you soon!", "info")
    return redirect(url_for("login"))


# ═══════════════════════════════════════════════════════════════
# DASHBOARDS
# ═══════════════════════════════════════════════════════════════

@app.route("/dashboard/student")
@login_required
@role_required("student")
def dashboard_student():
    user = db.find_user_by_id(session["user_id"])
    if not user:
        session.clear()
        flash("User account not found. Please log in again.", "error")
        return redirect(url_for("login"))
    return render_template("dashboard_student.html", user=user)


@app.route("/dashboard/teacher")
@login_required
@role_required("teacher")
def dashboard_teacher():
    user = db.find_user_by_id(session["user_id"])
    if not user:
        session.clear()
        flash("User account not found. Please log in again.", "error")
        return redirect(url_for("login"))
    return render_template("dashboard_teacher.html", user=user)


@app.route("/dashboard/admin")
@login_required
@role_required("admin")
def dashboard_admin():
    user = db.find_user_by_id(session["user_id"])
    if not user:
        session.clear()
        flash("User account not found. Please log in again.", "error")
        return redirect(url_for("login"))
    status_filter = request.args.get("status", "")
    role_filter   = request.args.get("role_filter", "")
    search        = request.args.get("search", "")
    users         = db.get_all_users(status_filter=status_filter or None,
                                     role_filter=role_filter or None,
                                     search=search or None)
    counts        = db.get_role_counts()
    recent_logs   = db.get_recent_logs(limit=15)
    recent_signups= db.get_recent_signups(limit=8)
    pending_count = counts.get("pending", 0)

    return render_template(
        "dashboard_admin.html",
        user=user, users=users, counts=counts,
        recent_logs=recent_logs, recent_signups=recent_signups,
        pending_count=pending_count,
        status_filter=status_filter, role_filter=role_filter, search=search
    )


# ═══════════════════════════════════════════════════════════════
# ADMIN AJAX APIs
# ═══════════════════════════════════════════════════════════════

@app.route("/api/admin/approve/<int:user_id>", methods=["POST"])
@login_required
@role_required("admin")
def approve_user(user_id):
    db.approve_user(user_id)
    target = db.find_user_by_id(user_id)
    if target:
        db.log_activity(session["user_id"], session["email"], "admin",
                        "USER_APPROVED", f"Approved {target['email']}")
    return jsonify({"success": True, "status": "approved"})


@app.route("/api/admin/reject/<int:user_id>", methods=["POST"])
@login_required
@role_required("admin")
def reject_user(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"success": False, "error": "Cannot reject your own account."}), 400
    data   = request.get_json(silent=True) or {}
    reason = data.get("reason", "").strip()
    db.reject_user(user_id, reason)
    target = db.find_user_by_id(user_id)
    if target:
        db.log_activity(session["user_id"], session["email"], "admin",
                        "USER_REJECTED", f"Rejected {target['email']}: {reason}")
    return jsonify({"success": True, "status": "rejected"})


@app.route("/api/admin/toggle-active/<int:user_id>", methods=["POST"])
@login_required
@role_required("admin")
def toggle_active(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"success": False, "error": "Cannot deactivate your own account."}), 400
    new_val = db.toggle_active(user_id)
    if new_val is None:
        return jsonify({"success": False, "error": "User not found."}), 404
    label = "active" if new_val else "inactive"
    db.log_activity(session["user_id"], session["email"], "admin",
                    "TOGGLE_ACTIVE", f"Set user #{user_id} active={new_val}")
    return jsonify({"success": True, "active": new_val, "label": label})


@app.route("/api/check-email")
def check_email():
    email = request.args.get("email", "").strip().lower()
    if not email:
        return jsonify({"available": True})
    user = db.find_user_by_email(email)
    return jsonify({"available": user is None})


# ═══════════════════════════════════════════════════════════════
# SERVER
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Initialize database tables (no demo data)
    db.init_db(seed_demo_data=False)
    port = int(os.getenv("PORT", "5002"))
    print(f"Milestone 2 server starting on http://127.0.0.1:{port}")
    print("Note: All accounts must be created through registration. No demo data loaded.")
    app.run(debug=True, port=port)
