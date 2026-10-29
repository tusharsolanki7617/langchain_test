import os
import json
import re
import io
import base64
from pathlib import Path
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, render_template, request, flash, session, redirect, url_for, jsonify
from werkzeug.security import check_password_hash
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from database import db

# Load the existing .env file
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "merged-app-secret-key-2026")
ADMIN_SECRET_KEY = os.getenv("ADMIN_INVITE_CODE", "ADMIN2026")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload

TOPICS = [
    "SQL", "Python", "Java", "Data Structures",
    "DBMS", "HTML/CSS", "JavaScript", "Other"
]

# ═══════════════════════════════════════════════════════════════
# AI PROMPTS FOR TEST GENERATION
# ═══════════════════════════════════════════════════════════════

MCQ_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
        You are an educational MCQ generator.

        Return only valid JSON without Markdown fences.
        Generate accurate questions with four options.

        Every question must have:
        - A question
        - Four options: A, B, C, D
        - One correct answer: A, B, C, or D
        - A short explanation

        Do not repeat questions.
        Follow the requested difficulty level.

        Return data in this JSON format:
        {{ 
            "questions": [
                {{
                    "question": "Example question?",
                    "options": {{
                        "A": "Option one",
                        "B": "Option two",
                        "C": "Option three",
                        "D": "Option four"
                    }},
                    "correct_answer": "A",
                    "explanation": "Explanation of the correct answer."
                }}
            ]
        }}
        """
    ),
    (
        "human",
        "Generate exactly {count} MCQs about {topic}. "
        "Difficulty: {difficulty}. "
        "Return exactly the requested number of questions."
    )
])

QA_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
        You are an educational assessment generator.
        Return only valid JSON without Markdown fences.
        Generate high quality, clear short-answer/conceptual questions (Q&A) on the requested topic.

        Every question must have:
        - "question": string (clear question asking for explanation, concept, or practical use)
        - "correct_answer": string (ideal concise accurate answer, 1-2 sentences)
        - "acceptable_answers": list of 3-5 strings (alternative phrasings, key phrases, or core keywords)
        - "explanation": string (clear explanation of why this is correct and context)

        Do not repeat questions.
        Follow the requested difficulty level.

        Return data in this JSON format:
        {{ 
            "questions": [
                {{
                    "question": "Example conceptual question?",
                    "correct_answer": "Concise expected answer.",
                    "acceptable_answers": ["key phrase 1", "key phrase 2"],
                    "explanation": "Detailed explanation."
                }}
            ]
        }}
        """
    ),
    (
        "human",
        "Generate exactly {count} short-answer Q&A questions about {topic}. "
        "Difficulty: {difficulty}. "
        "Return exactly the requested number of questions."
    )
])


# ═══════════════════════════════════════════════════════════════
# PERFORMANCE OPTIMIZATIONS
# ═══════════════════════════════════════════════════════════════

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year for static files

@app.after_request
def add_header(response):
    if request.path.startswith('/static/'):
        response.cache_control.max_age = 31536000
        response.cache_control.public = True
    else:
        response.cache_control.no_cache = True
        response.cache_control.no_store = True
        response.cache_control.must_revalidate = True
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def normalize_text(value):
    """Normalize text by lowercasing and stripping punctuation."""
    text = (value or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def evaluate_qa_response(user_answer, correct_answer, acceptable_answers=None):
    """Evaluate open-ended Q&A responses using keyword & token overlap analysis."""
    if not user_answer or not str(user_answer).strip():
        return {
            "is_correct": False,
            "status": "unanswered",
            "score": 0.0,
            "feedback": "No answer provided."
        }

    user_norm = normalize_text(user_answer)
    expected_list = [correct_answer] + (acceptable_answers or [])

    # Exact or substring match
    for exp in expected_list:
        exp_norm = normalize_text(exp)
        if not exp_norm:
            continue
        if user_norm == exp_norm:
            return {
                "is_correct": True,
                "status": "correct",
                "score": 1.0,
                "feedback": "Outstanding! Complete and accurate match."
            }
        if exp_norm in user_norm or user_norm in exp_norm:
            if len(user_norm) >= 4 and len(exp_norm) >= 4:
                return {
                    "is_correct": True,
                    "status": "correct",
                    "score": 1.0,
                    "feedback": "Correct! Key concepts identified."
                }

    # Token overlap analysis
    user_tokens = set(user_norm.split())
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "to", "in", "of", "and", "or", "for", "with", "it", "that", "this", "by", "on"}
    user_keywords = user_tokens - stopwords

    best_overlap_ratio = 0.0
    for exp in expected_list:
        exp_tokens = (set(normalize_text(exp).split())) - stopwords
        if not exp_tokens or not user_keywords:
            continue
        overlap = user_keywords & exp_tokens
        ratio = len(overlap) / max(len(user_keywords), len(exp_tokens))
        if ratio > best_overlap_ratio:
            best_overlap_ratio = ratio

    if best_overlap_ratio >= 0.35:
        return {
            "is_correct": True,
            "status": "correct",
            "score": 1.0,
            "feedback": f"Correct! Good conceptual match ({round(best_overlap_ratio * 100)}% keyword alignment)."
        }
    elif best_overlap_ratio >= 0.20:
        return {
            "is_correct": False,
            "status": "partial",
            "score": 0.5,
            "feedback": f"Partially correct ({round(best_overlap_ratio * 100)}% keyword alignment). Missing key details."
        }
    else:
        return {
            "is_correct": False,
            "status": "wrong",
            "score": 0.0,
            "feedback": "Incorrect. Review the model answer and explanation below."
        }


def extract_text_from_image(image_bytes, filename=""):
    """
    Extract text from an image using AI Vision (gpt-4o-mini) with fallback to local pytesseract.
    """
    if not image_bytes:
        return "", "None"

    # 1. Try OpenAI Multimodal Vision (fast and accurate for handwriting and complex formatting)
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and OpenAI is not None:
        try:
            client = OpenAI(api_key=openai_key)
            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            mime = "image/png"
            if filename.lower().endswith((".jpg", ".jpeg")):
                mime = "image/jpeg"
            elif filename.lower().endswith(".webp"):
                mime = "image/webp"

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert OCR system. Extract all text, questions, handwriting, or technical content from the provided image accurately. Return only the extracted text without conversational markdown or filler."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract all text from this image:"},
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64_img}"}}
                        ]
                    }
                ],
                max_tokens=1500,
                temperature=0.0
            )
            extracted = response.choices[0].message.content.strip()
            if extracted:
                return extracted, "AI Vision (GPT-4o-mini)"
        except Exception as ai_err:
            app.logger.warning("AI vision OCR failed: %s, falling back to local Tesseract", ai_err)

    # 2. Fallback to local Pytesseract
    if Image is not None and pytesseract is not None:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(img).strip()
            if text:
                return text, "Tesseract OCR"
        except Exception as tess_err:
            app.logger.warning("Local Tesseract OCR failed: %s", tess_err)

    return "", "None"


def create_model(provider):
    """Choose the AI provider selected by the user."""
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is missing in .env")

        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=key,
            temperature=0.3
        )

    if provider == "gemini":
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            raise ValueError("GOOGLE_API_KEY is missing in .env")
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            google_api_key=key,
            temperature=0.3
        )

    raise ValueError("Select OpenAI or Gemini.")


def parse_response(text):
    """Convert the AI response into a Python dictionary."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("The AI did not return valid JSON.")

    return json.loads(text[start:end + 1])


def validate_questions(data, count):
    """Check the number of questions and their required fields for MCQs."""
    questions = data.get("questions")

    if not isinstance(questions, list) or len(questions) != count:
        raise ValueError(
            f"The AI must return exactly {count} questions. Please try again."
        )

    for number, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise ValueError(f"Question {number} has an invalid format.")

        if not question.get("question"):
            raise ValueError(f"Question {number} is missing its text.")

        options = question.get("options", {})
        if not isinstance(options, dict) or any(
            letter not in options for letter in "ABCD"
        ):
            raise ValueError(f"Question {number} needs options A, B, C and D.")

        answer = question.get("correct_answer")
        if answer not in ("A", "B", "C", "D"):
            raise ValueError(f"Question {number} has an invalid answer.")

        question["explanation"] = question.get("explanation", "")
        question["type"] = "mcq"

    return questions


def validate_qa_questions(data, count):
    """Validate open-ended Q&A questions."""
    questions = data.get("questions")

    if not isinstance(questions, list) or len(questions) != count:
        raise ValueError(
            f"The AI must return exactly {count} Q&A questions. Please try again."
        )

    for number, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise ValueError(f"Question {number} has an invalid format.")

        if not question.get("question"):
            raise ValueError(f"Question {number} is missing its text.")

        if not question.get("correct_answer"):
            raise ValueError(f"Question {number} is missing its expected answer.")

        acceptable = question.get("acceptable_answers", [])
        if not isinstance(acceptable, list):
            acceptable = [str(acceptable)] if acceptable else []
        question["acceptable_answers"] = acceptable

        question["explanation"] = question.get("explanation", "")
        question["type"] = "qa"

    return questions


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
# TEST GENERATION & EVALUATION (ExamAI)
# ═══════════════════════════════════════════════════════════════

@app.route("/tests", methods=["GET", "POST"])
@login_required
def tests():
    """Test generation page - available to authenticated users."""
    selected_topic = "SQL"
    difficulty = "Medium"
    count = 5
    custom_topic = ""
    provider = "openai"
    question_type = "mixed"

    if request.method == "POST":
        action = request.form.get("action", "generate")

        if action == "new_test":
            session.pop("test_data", None)
            session.pop("evaluation", None)
            return redirect(url_for("tests"))

        if action == "retake":
            session.pop("evaluation", None)
            flash("Test reset! You can retake the questions now.", "info")
            return redirect(url_for("tests"))

        if action == "submit_test":
            test_data = session.get("test_data")
            # Fallback to hidden payload if session was lost
            if not test_data:
                raw_payload = request.form.get("questions_payload")
                if raw_payload:
                    try:
                        test_data = json.loads(raw_payload)
                    except Exception:
                        test_data = None

            if not test_data or not test_data.get("questions"):
                flash("No active test found to evaluate. Please generate a new test.", "error")
                return redirect(url_for("tests"))

            questions = test_data["questions"]
            score = 0.0
            correct_count = 0
            partial_count = 0
            wrong_count = 0
            evaluated_questions = []

            for idx, q in enumerate(questions):
                q_type = q.get("type", "mcq")

                if q_type == "qa":
                    user_text = request.form.get(f"q_{idx}", "").strip()
                    ocr_note = None

                    # Check if an answer photo/image was uploaded for this question
                    uploaded_img = request.files.get(f"q_img_{idx}")
                    if uploaded_img and uploaded_img.filename:
                        try:
                            extracted_ocr, ocr_method = extract_text_from_image(uploaded_img.read(), uploaded_img.filename)
                            if extracted_ocr:
                                user_text = extracted_ocr
                                ocr_note = f"Extracted via {ocr_method} from uploaded image: {uploaded_img.filename}"
                        except Exception as ocr_err:
                            app.logger.warning("OCR failed for question %s: %s", idx, ocr_err)

                    qa_res = evaluate_qa_response(
                        user_text,
                        q.get("correct_answer", ""),
                        q.get("acceptable_answers", [])
                    )
                    score += qa_res["score"]
                    if qa_res["status"] == "correct":
                        correct_count += 1
                    elif qa_res["status"] == "partial":
                        partial_count += 1
                    else:
                        wrong_count += 1

                    evaluated_questions.append({
                        "type": "qa",
                        "question": q["question"],
                        "correct_answer": q.get("correct_answer", ""),
                        "acceptable_answers": q.get("acceptable_answers", []),
                        "explanation": q.get("explanation", ""),
                        "user_answer": user_text,
                        "ocr_note": ocr_note,
                        "is_correct": qa_res["is_correct"],
                        "qa_eval": qa_res,
                        "points_earned": qa_res["score"]
                    })

                else:
                    # MCQ
                    user_choice = request.form.get(f"q_{idx}")
                    correct_choice = q.get("correct_answer")
                    is_correct = (user_choice == correct_choice)

                    if is_correct:
                        score += 1.0
                        correct_count += 1
                    else:
                        wrong_count += 1

                    evaluated_questions.append({
                        "type": "mcq",
                        "question": q["question"],
                        "options": q.get("options", {}),
                        "correct_answer": correct_choice,
                        "explanation": q.get("explanation", ""),
                        "user_choice": user_choice,
                        "is_correct": is_correct,
                        "points_earned": 1.0 if is_correct else 0.0
                    })

            total = len(evaluated_questions)
            percentage = round((score / total) * 100) if total > 0 else 0

            if percentage == 100:
                remark = "Outstanding! Perfect score!"
                badge_type = "excellent"
            elif percentage >= 70:
                remark = "Great job! You passed with high proficiency."
                badge_type = "good"
            elif percentage >= 50:
                remark = "Fair effort! Review the explanations to strengthen your understanding."
                badge_type = "average"
            else:
                remark = "Needs practice. Go through the explanations below and try again!"
                badge_type = "poor"

            # Display score formatted nicely (integer if whole, float if partial)
            display_score = int(score) if score.is_integer() else round(score, 1)

            evaluation = {
                "topic": test_data.get("topic", "Selected Topic"),
                "difficulty": test_data.get("difficulty", "Medium"),
                "question_type": test_data.get("question_type", "mixed"),
                "score": display_score,
                "total": total,
                "percentage": percentage,
                "correct_count": correct_count,
                "partial_count": partial_count,
                "wrong_count": wrong_count,
                "remark": remark,
                "badge_type": badge_type,
                "questions": evaluated_questions
            }

            session["evaluation"] = evaluation
            flash(f"Test evaluated! You scored {display_score}/{total} ({percentage}%).", "success")
            return redirect(url_for("tests"))

        # Default action: "generate"
        selected_topic = request.form.get("topic", "SQL")
        difficulty = request.form.get("difficulty", "Medium")
        custom_topic = request.form.get("custom_topic", "").strip()
        provider = request.form.get("provider", "openai")
        question_type = request.form.get("question_type", "mixed")

        try:
            count = int(request.form.get("count", "5"))

            if selected_topic not in TOPICS:
                raise ValueError("Please select a valid topic.")

            if difficulty not in ("Easy", "Medium", "Hard"):
                raise ValueError("Please select a valid difficulty.")

            if provider not in ("openai", "gemini"):
                raise ValueError("Please select a valid AI provider.")

            if question_type not in ("mcq", "qa", "mixed"):
                question_type = "mixed"

            if not 1 <= count <= 30:
                raise ValueError("Choose between 1 and 30 questions.")

            topic = (
                custom_topic if selected_topic == "Other"
                else selected_topic
            )

            # Check for source image upload for OCR
            source_img = request.files.get("source_image")
            ocr_source_note = None
            if source_img and source_img.filename:
                ocr_text, ocr_method = extract_text_from_image(source_img.read(), source_img.filename)
                if ocr_text:
                    ocr_source_note = f"Generated from uploaded image '{source_img.filename}' ({ocr_method})"
                    topic = f"Document content extracted from {source_img.filename}:\n\n{ocr_text}"
                    flash(f"OCR Success: Extracted {len(ocr_text.split())} words from {source_img.filename} using {ocr_method}.", "info")
                else:
                    flash(f"Notice: No readable text found in {source_img.filename}. Proceeding with topic '{topic}'.", "info")

            if not topic:
                raise ValueError("Please enter a topic or upload an image to extract text from.")

            # Generate questions using the chosen LangChain model
            model = create_model(provider)

            if question_type == "mcq":
                chain = MCQ_PROMPT | model
                response = chain.invoke({
                    "topic": topic,
                    "difficulty": difficulty,
                    "count": count
                })
                data = parse_response(str(response.content))
                questions = validate_questions(data, count)

            elif question_type == "qa":
                chain = QA_PROMPT | model
                response = chain.invoke({
                    "topic": topic,
                    "difficulty": difficulty,
                    "count": count
                })
                data = parse_response(str(response.content))
                questions = validate_qa_questions(data, count)

            else:  # "mixed" mode
                mcq_count = max(1, count // 2)
                qa_count = max(1, count - mcq_count)

                chain_mcq = MCQ_PROMPT | model
                res_mcq = chain_mcq.invoke({
                    "topic": topic,
                    "difficulty": difficulty,
                    "count": mcq_count
                })
                mcqs = validate_questions(parse_response(str(res_mcq.content)), mcq_count)

                chain_qa = QA_PROMPT | model
                res_qa = chain_qa.invoke({
                    "topic": topic,
                    "difficulty": difficulty,
                    "count": qa_count
                })
                qas = validate_qa_questions(parse_response(str(res_qa.content)), qa_count)

                questions = []
                m_i, q_i = 0, 0
                for _ in range(count):
                    if m_i < len(mcqs) and (m_i + q_i) % 2 == 0:
                        questions.append(mcqs[m_i])
                        m_i += 1
                    elif q_i < len(qas):
                        questions.append(qas[q_i])
                        q_i += 1
                    elif m_i < len(mcqs):
                        questions.append(mcqs[m_i])
                        m_i += 1
                    else:
                        break

            # Save the successfully generated questions to MySQL if available
            try:
                user_id = session.get("user_id")
                db.save_questions(user_id, topic, difficulty, provider, questions)
            except Exception as db_err:
                app.logger.warning("Could not save to MySQL: %s", db_err)

            display_topic = ocr_source_note if ocr_source_note else (custom_topic if selected_topic == "Other" else selected_topic)

            # Store the test in session and reset previous evaluation
            session["test_data"] = {
                "topic": display_topic,
                "difficulty": difficulty,
                "count": len(questions),
                "provider": provider,
                "question_type": question_type,
                "questions": questions,
                "ocr_note": ocr_source_note
            }
            session.pop("evaluation", None)

            # Log test generation activity
            db.log_activity(
                session["user_id"],
                session["email"],
                session["role"],
                "TEST_GENERATED",
                f"{len(questions)} {difficulty} {question_type.upper()} questions on {display_topic}"
            )

            flash(
                f"{len(questions)} {difficulty} {question_type.upper()} questions generated! Complete your test below.",
                "success"
            )
            return redirect(url_for("tests"))

        except Exception as error:
            app.logger.exception("Question generation failed")
            flash(f"Could not generate questions: {error}", "error")

    # GET request handling
    test_data = session.get("test_data")
    evaluation = session.get("evaluation")

    if test_data:
        selected_topic = test_data.get("topic", selected_topic)
        difficulty = test_data.get("difficulty", difficulty)
        count = test_data.get("count", count)
        provider = test_data.get("provider", provider)
        question_type = test_data.get("question_type", question_type)

    return render_template(
        "tests.html",
        topics=TOPICS,
        test_data=test_data,
        evaluation=evaluation,
        selected_topic=selected_topic,
        difficulty=difficulty,
        count=count,
        custom_topic=custom_topic,
        provider=provider,
        question_type=question_type
    )


@app.route("/api/ocr", methods=["POST"])
@login_required
def api_ocr():
    """Extract text from an uploaded image using OCR (AI Vision + Tesseract)."""
    if "image" not in request.files:
        return jsonify({"success": False, "error": "No image file provided."}), 400
    file = request.files["image"]
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file selected."}), 400

    try:
        text, method = extract_text_from_image(file.read(), file.filename)
        if not text:
            return jsonify({
                "success": False,
                "error": "No readable text detected in this image. Please ensure the image has clear text."
            }), 400

        return jsonify({
            "success": True,
            "text": text,
            "method": method,
            "filename": file.filename,
            "words": len(text.split())
        })
    except Exception as exc:
        app.logger.exception("OCR extraction endpoint failed")
        return jsonify({"success": False, "error": str(exc)}), 500


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
    # Initialize database tables (no demo data by default)
    db.init_db(seed_demo_data=False)
    port = int(os.getenv("PORT", "5003"))
    print(f"\n{'='*60}")
    print(f"🚀 ExamAI Unified Platform Starting")
    print(f"{'='*60}")
    print(f"Server: http://127.0.0.1:{port}")
    print(f"Features: Authentication + Role-based Access + AI Test Generation")
    print(f"{'='*60}\n")
    app.run(debug=True, port=port)
