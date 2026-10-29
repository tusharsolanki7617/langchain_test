import argparse
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover - optional dependency
    ChatGoogleGenerativeAI = None


VALID_DIFFICULTIES = {"easy", "medium", "hard"}


def get_llm():
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        if OpenAI is None:
            raise RuntimeError(
                "OpenAI Python SDK is missing. Falling back to local MCQ generation."
            )
        return OpenAI(api_key=openai_key)

    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if google_key:
        if ChatGoogleGenerativeAI is None:
            raise RuntimeError(
                "Google GenAI package is missing. Falling back to local MCQ generation."
            )
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.7,
            api_key=google_key,
        )

    raise RuntimeError(
        "No OPENAI_API_KEY or GOOGLE_API_KEY is set. Running local MCQ generator instead."
    )


def build_prompt(topic: str, difficulty: str, count: int) -> str:
    return f"""
Generate exactly {count} multiple-choice questions on the topic: {topic}.
Difficulty level: {difficulty}.

Return valid JSON only.
The JSON must be a list of {count} objects.
Each object must have exactly these keys:
- question
- options
- correct_answer
- explanation

Rules:
- Each question must have exactly 4 options.
- The correct_answer must exactly match one of the options.
- Keep the content relevant to the given topic and difficulty level.
- Do not include markdown fences or any extra text outside the JSON.
- Use plain strings for all values.

Example format:
[
  {{
    "question": "Sample question?",
    "options": ["A", "B", "C", "D"],
    "correct_answer": "B",
    "explanation": "Short explanation why B is correct."
  }}
]
"""


def extract_json_from_response(response_text: str):
    cleaned = response_text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.IGNORECASE)

    match = re.search(r"\[[\s\S]*\]", cleaned)
    if match:
        cleaned = match.group(0)

    return json.loads(cleaned)


def build_local_mcqs(topic: str, difficulty: str, count: int):
    topic_name = (topic or "the selected topic").strip()
    templates = [
        {
            "question": f"What is the main purpose of {topic_name}?",
            "options": [
                f"To understand the core ideas behind {topic_name}",
                f"To avoid learning {topic_name}",
                f"To replace the need for practice in {topic_name}",
                f"To make {topic_name} impossible to use",
            ],
            "correct_answer": f"To understand the core ideas behind {topic_name}",
            "explanation": f"The main purpose of learning {topic_name} is to understand its core concepts and apply them correctly.",
        },
        {
            "question": f"Which statement best describes {topic_name}?",
            "options": [
                f"It is a practical subject that helps solve real problems",
                f"It has no useful applications",
                f"It is only useful for memorization",
                f"It can be ignored in everyday work",
            ],
            "correct_answer": f"It is a practical subject that helps solve real problems",
            "explanation": f"{topic_name} is usually valuable because it supports solving practical problems and building useful skills.",
        },
        {
            "question": f"What is the best way to improve your understanding of {topic_name}?",
            "options": [
                "Study the concepts and practice regularly",
                "Avoid examples and exercises",
                "Only memorize one answer",
                "Ignore feedback and results",
            ],
            "correct_answer": "Study the concepts and practice regularly",
            "explanation": "Consistent study and practice are the most effective ways to learn any topic deeply and retain it.",
        },
        {
            "question": f"Which option is the most accurate about {topic_name}?",
            "options": [
                "It requires understanding, practice, and application",
                "It is only based on guessing",
                "It does not improve with repetition",
                "It can be mastered without learning the basics",
            ],
            "correct_answer": "It requires understanding, practice, and application",
            "explanation": "Strong learning in any topic comes from understanding the fundamentals and practicing their use.",
        },
    ]

    if difficulty == "hard":
        templates[0]["question"] = f"Which answer best explains the value of mastering {topic_name}?"
        templates[0]["options"] = [
            f"It builds the conceptual foundation needed for deeper problem-solving in {topic_name}",
            f"It removes the need for reasoning in {topic_name}",
            f"It makes every problem trivial without effort",
            f"It prevents the need to practice",
        ]
        templates[0]["correct_answer"] = f"It builds the conceptual foundation needed for deeper problem-solving in {topic_name}"
        templates[0]["explanation"] = f"Mastery of {topic_name} grows from building a strong conceptual foundation and then applying it to increasingly complex problems."

    elif difficulty == "easy":
        templates[0]["options"] = [
            f"To learn the basics of {topic_name}",
            f"To stop using {topic_name}",
            f"To make {topic_name} harder",
            f"To ignore examples",
        ]
        templates[0]["correct_answer"] = f"To learn the basics of {topic_name}"
        templates[0]["explanation"] = f"The goal of learning {topic_name} at an easy level is to understand its basic ideas clearly."

    questions = []
    for index in range(count):
        template = templates[index % len(templates)]
        question = {
            "question": template["question"],
            "options": list(template["options"]),
            "correct_answer": template["correct_answer"],
            "explanation": template["explanation"],
        }
        questions.append(question)
    return questions


def generate_mcqs(topic: str, difficulty: str, count: int):
    if count <= 0:
        raise ValueError("Number of questions must be greater than zero.")

    difficulty = difficulty.lower()
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError("Difficulty must be one of: easy, medium, hard")

    try:
        llm = get_llm()

        if isinstance(llm, OpenAI):
            response = llm.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.7,
                messages=[
                    {"role": "system", "content": "You generate valid JSON only."},
                    {"role": "user", "content": build_prompt(topic, difficulty, count)},
                ],
                response_format={"type": "json_object"},
            )
            response_text = response.choices[0].message.content
        else:
            response = llm.invoke(build_prompt(topic, difficulty, count))
            response_text = response.content if hasattr(response, "content") else str(response)

        questions = extract_json_from_response(response_text)
        if isinstance(questions, list):
            return questions[:count]
    except Exception as exc:
        print(f"\nAPI generation failed: {exc}\nFalling back to local MCQ generation.\n")

    return build_local_mcqs(topic, difficulty, count)


def print_mcqs(questions):
    for index, question in enumerate(questions, start=1):
        print(f"\n{index}. {question['question']}")
        for option_letter, option_text in zip(["A", "B", "C", "D"], question["options"]):
            print(f"   {option_letter}. {option_text}")
        print(f"   Correct Answer: {question['correct_answer']}")
        print(f"   Explanation: {question['explanation']}")


def normalize_text(value):
    text = (value or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_qa_answer_correct(user_answer, correct_answer, acceptable_answers=None):
    if user_answer is None:
        return False
    user_norm = normalize_text(user_answer)
    if not user_norm:
        return False
    expected_answers = [correct_answer] + (acceptable_answers or [])
    for expected in expected_answers:
        exp_norm = normalize_text(expected)
        if not exp_norm:
            continue
        if user_norm == exp_norm or exp_norm in user_norm or user_norm in exp_norm:
            return True
        user_tokens = set(user_norm.split())
        expected_tokens = set(exp_norm.split())
        overlap = user_tokens & expected_tokens
        if overlap and len(overlap) / max(len(user_tokens), len(expected_tokens)) >= 0.35:
            return True
    return False


def run_quiz(questions):
    letters = ["A", "B", "C", "D"]
    score = 0
    total = len(questions)
    results = []

    print("\n--- Complete your assessment below ---")
    for idx, q in enumerate(questions, start=1):
        q_type = q.get("type", "mcq")
        print(f"\nQ{idx} ({q_type.upper()}). {q['question']}")

        if q_type == "qa":
            user_text = input("Type your answer: ").strip()
            is_correct = is_qa_answer_correct(user_text, q["correct_answer"], q.get("acceptable_answers", []))
            if is_correct:
                score += 1
            results.append({
                "idx": idx,
                "q": q,
                "user_text": user_text,
                "correct_text": q["correct_answer"],
                "is_correct": is_correct,
                "type": "qa"
            })
            continue

        for letter, opt in zip(letters, q["options"]):
            print(f"   {letter}. {opt}")

        user_ans = ""
        while user_ans not in letters:
            user_ans = input("Your answer (A/B/C/D): ").strip().upper()

        chosen_text = q["options"][letters.index(user_ans)]
        correct_text = q["correct_answer"]
        is_correct = (chosen_text == correct_text or user_ans == correct_text)
        if is_correct:
            score += 1

        results.append({
            "idx": idx,
            "q": q,
            "user_letter": user_ans,
            "user_text": chosen_text,
            "correct_text": correct_text,
            "is_correct": is_correct,
            "type": "mcq"
        })

    print(f"\n==============================")
    print(f"       EVALUATION SCREEN      ")
    print(f"==============================")
    print(f"Final Score: {score} / {total} ({round((score/total)*100)}%)")
    print("------------------------------")
    for r in results:
        status = "✅ Correct" if r["is_correct"] else "❌ Wrong"
        print(f"\nQ{r['idx']}: {status}")
        if r["type"] == "mcq":
            print(f"  Your answer: {r['user_letter']}. {r['user_text']}")
        else:
            print(f"  Your answer: {r['user_text']}")
        print(f"  Correct answer: {r['correct_text']}")
        print(f"  Explanation: {r['q']['explanation']}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate multiple-choice and conceptual Q&A questions for a selected topic and difficulty."
    )
    parser.add_argument("--topic", type=str, help="Topic for the assessment")
    parser.add_argument(
        "--difficulty",
        type=str,
        default="medium",
        choices=["easy", "medium", "hard"],
        help="Difficulty level",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of questions to generate",
    )
    parser.add_argument(
        "--type",
        type=str,
        default="mixed",
        choices=["mcq", "qa", "mixed"],
        help="Question format: mcq, qa, or mixed",
    )
    parser.add_argument(
        "--quiz",
        "--test",
        action="store_true",
        dest="test_mode",
        help="Take interactive test and view evaluation screen with right/wrong answers",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    topic = args.topic.strip() if args.topic else input("Enter topic: ").strip()
    if not topic:
        raise ValueError("Topic cannot be empty.")

    if args.type == "mcq":
        questions = generate_mcqs(topic, args.difficulty, args.count)
    else:
        from task4 import generate_mixed_questions, generate_qa_questions
        if args.type == "qa":
            questions = generate_qa_questions(topic, args.difficulty, args.count)
        else:
            questions = generate_mixed_questions(topic, args.difficulty, args.count)

    print(f"\n===== ASSESSMENT ({args.type.upper()}): {topic.upper()} ({args.difficulty.upper()}) =====")

    if args.test_mode:
        run_quiz(questions)
    else:
        for idx, q in enumerate(questions, start=1):
            print(f"\n{idx}. {q['question']}")
            if q.get("type") == "qa":
                print(f"   Expected Answer: {q['correct_answer']}")
            else:
                for l, opt in zip(["A", "B", "C", "D"], q.get("options", [])):
                    print(f"   {l}. {opt}")
                print(f"   Correct Answer: {q['correct_answer']}")
            print(f"   Explanation: {q['explanation']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
