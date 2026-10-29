import argparse

from task2 import generate_mcqs

OPTIONS = ["A", "B", "C", "D"]


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

    if not topic:
        raise ValueError("Topic cannot be empty.")

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
        print(f"\nQuestion {index}: {question['question']}")
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
        description="Generate an MCQ test, let the user answer it, and evaluate the result."
    )
    parser.add_argument("--topic", type=str, help="Topic for the MCQ test")
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

    questions = generate_mcqs(topic, difficulty, count)
    print(f"\n===== MCQ TEST: {topic.upper()} ({difficulty.upper()}) =====")

    selected_answers = prompt_for_answers(questions)
    evaluate_answers(selected_answers)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
