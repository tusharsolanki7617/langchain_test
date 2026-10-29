import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None

try:
    from google import genai
except Exception:  # pragma: no cover - optional dependency
    genai = None

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - optional dependency
    ChatOpenAI = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover - optional dependency
    ChatGoogleGenerativeAI = None


openai_key = os.getenv("OPENAI_API_KEY")
google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


# =====================================
# 1. LIST CHATGPT / OPENAI MODELS
# =====================================

if openai_key and OpenAI is not None:
    try:
        openai_client = OpenAI(api_key=openai_key)
        print("\n===== CHATGPT / OPENAI MODELS =====")
        for model in openai_client.models.list().data:
            print(model.id)
    except Exception as exc:
        print(f"\nOpenAI model listing failed: {exc}\n")
else:
    print("\nOpenAI API key not configured; skipping OpenAI model listing.")


# =====================================
# 2. LIST GEMINI MODELS
# =====================================

if google_key and genai is not None:
    try:
        gemini_client = genai.Client(api_key=google_key)
        print("\n===== GEMINI MODELS =====")
        for model in gemini_client.models.list():
            print(model.name)
    except Exception as exc:
        print(f"\nGemini model listing failed: {exc}\n")
else:
    print("\nGoogle/Gemini API key not configured; skipping Gemini model listing.")


# =====================================
# 3. CREATE CHATGPT MODEL
# =====================================

chatgpt = None
if openai_key and ChatOpenAI is not None:
    chatgpt = ChatOpenAI(model="gpt-3.5-turbo", api_key=openai_key)


# =====================================
# 4. CREATE GEMINI FLASH MODEL
# =====================================

gemini = None
if google_key and ChatGoogleGenerativeAI is not None:
    gemini = ChatGoogleGenerativeAI(model="gemini-2.5-flash", api_key=google_key)

# =====================================
# 5. COMMON PROMPT
# =====================================

prompt = """
What is an array?
Explain it in simple English and give one example.
"""


# =====================================
# 6. CHATGPT RESPONSE
# =====================================

if chatgpt is not None:
    try:
        chatgpt_response = chatgpt.invoke(prompt)
        print("\n===== CHATGPT RESPONSE =====")
        print(chatgpt_response.content)
    except Exception as exc:
        print(f"\nChatGPT request failed: {exc}\n")
else:
    print("\nChatGPT not available because no valid OpenAI key or LangChain package is configured.")


# =====================================
# 7. GEMINI FLASH RESPONSE
# =====================================

if gemini is not None:
    try:
        gemini_response = gemini.invoke(prompt)
        print("\n===== GEMINI FLASH RESPONSE =====")
        print(gemini_response.content)
    except Exception as exc:
        print(f"\nGemini request failed: {exc}\n")
else:
    print("\nGemini not available because no valid Google key or LangChain package is configured.")