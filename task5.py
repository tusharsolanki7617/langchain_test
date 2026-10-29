import argparse
import base64
import io
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

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

from task2 import extract_json_from_response, get_llm
from task4 import evaluate_answers, is_qa_answer_correct


def extract_text_from_image(image_path: str):
    """
    Extract text from an image file using AI Vision (gpt-4o-mini) with fallback to pytesseract.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    # 1. Try AI Vision (OpenAI gpt-4o-mini)
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and OpenAI is not None:
        try:
            client = OpenAI(api_key=openai_key)
            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            mime = "image/png"
            if image_path.lower().endswith((".jpg", ".jpeg")):
                mime = "image/jpeg"
            elif image_path.lower().endswith(".webp"):
                mime = "image/webp"

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert OCR system. Extract all text, questions, handwriting, or technical content from the provided image accurately. Return only the extracted text without conversational markdown or commentary."
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
            print(f"AI vision OCR failed: {ai_err}. Attempting local Tesseract OCR fallback...")

    # 2. Fallback to local Pytesseract
    if Image is not None and pytesseract is not None:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(img).strip()
            if text:
                return text, "Tesseract OCR"
        except Exception as tess_err:
            print(f"Local Tesseract OCR failed: {tess_err}")

    raise RuntimeError("Could not extract any text from the provided image.")


def generate_qa_from_extracted_text(text: str, count: int = 3, difficulty: str = "medium"):
    """
    Generate Q&A questions directly from OCR-extracted text using LangChain / OpenAI.
    """
    llm = get_llm()

    prompt = f"""
You are an assessment generator.
Based on the following extracted document text:
\"\"\"
{text}
\"\"\"

Generate exactly {count} short-answer/conceptual Q&A questions directly based on this material.
Difficulty: {difficulty}.

Return valid JSON only as a list of objects with these exact keys:
- "question": string
- "correct_answer": string
- "acceptable_answers": list of 3-5 strings (alternative phrasings, key phrases, or synonyms)
- "explanation": string

Example:
[
  {{
    "question": "What is the key idea described?",
    "correct_answer": "Expected direct answer.",
    "acceptable_answers": ["key concept 1", "key concept 2"],
    "explanation": "Detailed reasoning."
  }}
]
"""

    if isinstance(llm, OpenAI):
        response = llm.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.7,
            messages=[
                {"role": "system", "content": "You generate valid JSON only without markdown fences."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        response_text = response.choices[0].message.content
    else:
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, "content") else str(response)

    data = extract_json_from_response(response_text)
    if isinstance(data, dict):
        for key in ["questions", "items", "data"]:
            if key in data and isinstance(data[key], list):
                data = data[key]
                break

    if not isinstance(data, list):
        data = [data]

    questions = []
    for item in data[:count]:
        questions.append({
            "type": "qa",
            "question": item.get("question", "Conceptual question?"),
            "correct_answer": item.get("correct_answer", ""),
            "acceptable_answers": item.get("acceptable_answers", []),
            "explanation": item.get("explanation", "")
        })

    return questions


def parse_args():
    parser = argparse.ArgumentParser(
        description="Task 5: Perform OCR on an uploaded image, generate Q&A questions, and evaluate responses."
    )
    parser.add_argument("--image", type=str, help="Path to image file to perform OCR on")
    parser.add_argument("--count", type=int, default=3, help="Number of questions to generate")
    parser.add_argument("--difficulty", type=str, default="medium", choices=["easy", "medium", "hard"])
    parser.add_argument("--quiz", action="store_true", help="Interactively take and evaluate the generated test")
    return parser.parse_args()


def main():
    args = parse_args()

    image_path = args.image
    if not image_path:
        image_path = input("Enter path to image for OCR text extraction: ").strip()

    print(f"\n--- Running OCR Text Extraction on: {image_path} ---")
    extracted_text, method = extract_text_from_image(image_path)
    print(f"Extracted using: {method}")
    print("--------------------------------------------------")
    print(extracted_text)
    print("--------------------------------------------------")

    print(f"\nGenerating {args.count} Q&A questions from extracted text...")
    questions = generate_qa_from_extracted_text(extracted_text, count=args.count, difficulty=args.difficulty)

    if args.quiz:
        from task4 import prompt_for_answers, evaluate_answers
        selected = prompt_for_answers(questions)
        evaluate_answers(selected)
    else:
        print("\n===== GENERATED Q&A QUESTIONS (FROM OCR IMAGE) =====")
        for idx, q in enumerate(questions, start=1):
            print(f"\nQ{idx}. {q['question']}")
            print(f"   Expected Answer: {q['correct_answer']}")
            print(f"   Acceptable Concepts: {', '.join(q.get('acceptable_answers', []))}")
            print(f"   Explanation: {q['explanation']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
