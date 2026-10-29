import argparse
import re

from task2 import generate_mcqs

OPTIONS = ["A", "B", "C", "D"]
VALID_DIFFICULTIES = {"easy", "medium", "hard"}


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

    expected_answers = [correct_answer]
    if acceptable_answers:
        expected_answers.extend(acceptable_answers)

    for expected in expected_answers:
        expected_norm = normalize_text(expected)
        if not expected_norm:
            continue

        if user_norm == expected_norm:
            return True

        if user_norm in expected_norm or expected_norm in user_norm:
            return True

        user_tokens = set(user_norm.split())
        expected_tokens = set(expected_norm.split())
        if not user_tokens or not expected_tokens:
            continue

        overlap = user_tokens & expected_tokens
        if overlap and len(overlap) / max(len(user_tokens), len(expected_tokens)) >= 0.5:
            return True

    return False


def generate_qa_questions(topic, difficulty, count):
    topic_name = (topic or "the selected topic").strip() or "the selected topic"
    difficulty = (difficulty or "medium").lower()
    if difficulty not in VALID_DIFFICULTIES:
        difficulty = "medium"

    base_templates = [
        {
            "question": f"What is the main purpose of learning {topic_name}?",
            "correct_answer": f"To understand the core concepts and practical use of {topic_name}",
            "acceptable_answers": [
                f"understand the basics of {topic_name}",
                f"learn the key ideas of {topic_name}",
                f"understand {topic_name} conceptually",
            ],
            "explanation": f"The main goal of learning {topic_name} is to understand it well enough to apply it in real situations.",
        },
        {
            "question": f"Why is {topic_name} important in practice?",
            "correct_answer": f"It helps solve real problems and build useful skills",
            "acceptable_answers": [
                f"it helps solve practical problems",
                f"it is useful for real world tasks",
                f"it helps improve problem solving skills",
            ],
            "explanation": f"{topic_name} is valuable because it supports useful problem-solving and practical application.",
        },
        {
            "question": f"How can someone improve their understanding of {topic_name}?",
            "correct_answer": "By studying the concepts and practicing regularly",
            "acceptable_answers": [
                "study the concepts and practice",
                "practice regularly and learn the concepts",
                "learn with examples and repetition",
            ],
            "explanation": "Consistent study and repeated practice help build understanding and long-term retention.",
        },
        {
            "question": f"What does mastering {topic_name} usually require?",
            "correct_answer": "Understanding the fundamentals and applying them through practice",
            "acceptable_answers": [
                "understanding fundamentals and practice",
                "learning the basics and applying them",
                "knowledge plus practice",
            ],
            "explanation": "Mastery usually grows from learning the basics well and then applying them in practical tasks.",
        },
    ]

    if difficulty == "easy":
        base_templates[0]["correct_answer"] = f"To learn the basics of {topic_name}"
        base_templates[0]["acceptable_answers"] = [
            f"learn the basics of {topic_name}",
            f"understand the basics of {topic_name}",
            f"learn {topic_name} fundamentals",
        ]
    elif difficulty == "hard":
        base_templates[0]["question"] = f"Which idea best explains the value of mastering {topic_name}?"
        base_templates[0]["correct_answer"] = f"It builds the conceptual foundation needed for deeper problem-solving in {topic_name}"
        base_templates[0]["acceptable_answers"] = [
            f"strong foundation for deeper problem solving in {topic_name}",
            f"builds understanding for advanced work in {topic_name}",
            f"helps solve harder problems in {topic_name}",
        ]

    questions = []
    for index in range(count):
        template = base_templates[index % len(base_templates)]
        questions.append({
            "type": "qa",
            "question": template["question"],
            "correct_answer": template["correct_answer"],
            "acceptable_answers": list(template["acceptable_answers"]),
            "explanation": template["explanation"],
        })

    return questions


def generate_mixed_questions(topic, difficulty, count):
    if count <= 0:
        raise ValueError("Number of questions must be greater than zero.")

    mcq_count = max(1, count // 2)
    qa_count = max(0, count - mcq_count)

    mcq_questions = generate_mcqs(topic, difficulty, mcq_count)
    qa_questions = generate_qa_questions(topic, difficulty, qa_count)

    mixed_questions = []
    mcq_index = 0
    qa_index = 0

    for _ in range(count):
        if mcq_index < len(mcq_questions) and (mcq_index + qa_index) % 2 == 0:
            mixed_questions.append({**mcq_questions[mcq_index], "type": "mcq"})
            mcq_index += 1
        elif qa_index < len(qa_questions):
            mixed_questions.append(qa_questions[qa_index])
            qa_index += 1
        elif mcq_index < len(mcq_questions):
            mixed_questions.append({**mcq_questions[mcq_index], "type": "mcq"})
            mcq_index += 1
        else:
            break

    return mixed_questions


def ask_for_topic_and_count():
    available_topics = ["Python", "C", "C++", "AI", "JavaScript", "SQL", "Data Structures", "Java"]
    print("Select a topic:")
    for index, topic in enumerate(available_topics, start=1):
        print(f"  {index}. {topic}")

    while True:
        raw_choice = input("Enter topic number or type a custom topic: ").strip()
        if raw_choice.isdigit():
            choice = int(raw_choice)
            if 1 <= choice <= len(available_topics):
                topic = available_topics[choice - 1]
                break
        elif raw_choice:
            topic = raw_choice
            break
        print("Invalid selection. Please choose a valid topic number or type a custom topic.")

    difficulty = input("Enter difficulty (easy/medium/hard) [medium]: ").strip().lower() or "medium"
    count = input("How many questions? [3]: ").strip() or "3"

    try:
        count = int(count)
    except ValueError as exc:
        raise ValueError("Question count must be a number.") from exc

    if count <= 0:
        raise ValueError("Question count must be greater than zero.")

    return topic, difficulty, count


def prompt_for_answers(questions):
    selected_answers = []

    for index, question in enumerate(questions, start=1):
        q_type = question.get("type", "mcq")
        print(f"\nQuestion {index}: {question['question']}")

        if q_type == "qa":
            while True:
                answer = input("Type your answer: ").strip()
                if answer:
                    selected_answers.append({
                        "question": question,
                        "selected_answer": answer,
                        "selected_letter": "QA",
                    })
                    break
                print("Please enter an answer before continuing.")
            continue

        for letter, option in zip(OPTIONS, question["options"]):
            print(f"  {letter}. {option}")

        while True:
            answer = input("Select your answer (A/B/C/D): ").strip().upper()
            if answer in OPTIONS:
                selected_answers.append({
                    "question": question,
                    "selected_answer": question["options"][OPTIONS.index(answer)],
                    "selected_letter": answer,
                })
                break
            print("Invalid choice. Please choose A, B, C, or D.")

    return selected_answers


def evaluate_answers(selected_answers):
    score = 0
    total = len(selected_answers)

    print("\n===== RESULT =====")
    for index, item in enumerate(selected_answers, start=1):
        question = item["question"]
        q_type = question.get("type", "mcq")

        if q_type == "qa":
            user_answer = item["selected_answer"]
            correct_answer = question["correct_answer"]
            acceptable_answers = question.get("acceptable_answers", [])
            is_correct = is_qa_answer_correct(user_answer, correct_answer, acceptable_answers)

            if is_correct:
                score += 1
                print(f"\nQ{index}: ✅ Correct")
            else:
                print(f"\nQ{index}: ❌ Wrong")

            print(f"Your answer: {user_answer}")
            print(f"Expected answer: {correct_answer}")
            print(f"Explanation: {question['explanation']}")
            continue

        selected = item["selected_answer"]
        correct = question["correct_answer"]
        is_correct = selected == correct

        if is_correct:
            score += 1
            print(f"\nQ{index}: ✅ Correct")
        else:
            print(f"\nQ{index}: ❌ Wrong")

        print(f"Your answer: {selected}")
        print(f"Correct answer: {correct}")
        print(f"Explanation: {question['explanation']}")

    print(f"\nFinal score: {score}/{total}")
    if score == total:
        print("Excellent! You got all the answers correct.")
    elif score >= total / 2:
        print("Good job! You passed this round.")
    else:
        print("Keep practicing. Review the explanations and try again.")

    return score, total


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a mixed quiz with multiple-choice and short-answer questions."
    )
    parser.add_argument("--topic", type=str, help="Topic for the quiz")
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
        default=3,
        help="Number of questions to generate",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.topic:
        topic = args.topic.strip()
        difficulty = args.difficulty
        count = args.count
    else:
        topic, difficulty, count = ask_for_topic_and_count()

    if not topic:
        raise ValueError("Topic cannot be empty.")

    questions = generate_mixed_questions(topic, difficulty, count)
    print(f"\n===== MIXED QUIZ: {topic.upper()} ({difficulty.upper()}) =====")
    selected_answers = prompt_for_answers(questions)
    evaluate_answers(selected_answers)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
