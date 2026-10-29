import os
import json
import re
import io
import base64
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, render_template, request, flash, session, redirect, url_for, jsonify
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

# Load the existing .env file from langchain_test.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "task2-development-key")
# 16 MB max upload size
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

TOPICS = [
    "SQL", "Python", "Java", "Data Structures",
    "DBMS", "HTML/CSS", "JavaScript", "Other"
]

# Prompt used by both OpenAI and Gemini through LangChain.

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

# Prompt for Task 4 Q&A questions (open-ended / conceptual)
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


def get_connection():
    """Connect to the MySQL database."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "mcq_generator")
    )


def create_table():
    """Create the question-history table if needed."""
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mcq_sets (
            id INT AUTO_INCREMENT PRIMARY KEY,
            topic VARCHAR(255) NOT NULL,
            difficulty VARCHAR(20) NOT NULL,
            provider VARCHAR(20) NOT NULL,
            questions_json LONGTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    cursor.close()
    connection.close()


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


def save_questions(topic, difficulty, provider, questions):
    """Save generated questions to MySQL."""
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO mcq_sets
                (topic, difficulty, provider, questions_json)
            VALUES (%s, %s, %s, %s)
        """, (
            topic,
            difficulty,
            provider,
            json.dumps(questions, ensure_ascii=False)
        ))
        connection.commit()
    finally:
        cursor.close()
        connection.close()


@app.route("/api/ocr", methods=["POST"])
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


@app.route("/", methods=["GET", "POST"])
def index():
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
            return redirect(url_for("index"))

        if action == "retake":
            session.pop("evaluation", None)
            flash("Test reset! You can retake the questions now.", "info")
            return redirect(url_for("index"))

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
                return redirect(url_for("index"))

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

                    # Check if an answer photo/image was uploaded for this question (Task 5)
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
            return redirect(url_for("index"))

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

            # Check for source image upload for OCR (Task 5)
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

            # Save the successfully generated questions to MySQL if available.
            try:
                save_questions(topic, difficulty, provider, questions)
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

            flash(
                f"{len(questions)} {difficulty} {question_type.upper()} questions generated! Complete your test below.",
                "success"
            )
            return redirect(url_for("index"))

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
        "index.html",
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


if __name__ == "__main__":
    try:
        create_table()
        print("Database connected successfully.")
    except Exception as error:
        print(f"Warning: MySQL database connection failed: {error}")
        print("App will run, but questions will not be saved to DB until MySQL is available.")

    port = int(os.getenv("PORT", "5001"))
    print(f"Starting server on http://127.0.0.1:{port}")
    app.run(debug=True, port=port)
