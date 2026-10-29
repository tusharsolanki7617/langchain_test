# LangChain AI Model Explorer

This project demonstrates how to load environment variables and connect to OpenAI and Google Gemini models using LangChain and the official SDKs.

## What it does

The script in `task1.py`:

- loads values from a local `.env` file
- reads `OPENAI_API_KEY` and `GOOGLE_API_KEY` / `GEMINI_API_KEY`
- lists available OpenAI and Gemini models when credentials are configured
- creates LangChain chat clients for OpenAI and Gemini
- sends a simple prompt asking: "What is an array?"
- prints the model responses to the terminal

## Project files

- `task1.py` — main script
- `.env` — environment variables (not committed to source control)

## Setup

1. Create a virtual environment if needed.
2. Install the required packages:

```bash
pip install python-dotenv openai google-genai langchain-openai langchain-google-genai
```

3. Create a `.env` file in the project root with your keys:

```env
OPENAI_API_KEY=your_openai_key_here
GOOGLE_API_KEY=your_google_key_here
```

You may also use `GEMINI_API_KEY` instead of `GOOGLE_API_KEY`.

## Run

```bash
python task1.py
```

## Notes

- The script handles missing dependencies and missing API keys gracefully.
- Model calls are skipped if the required packages or keys are unavailable.
- The OpenAI model is configured as `gpt-3.5-turbo`.
- The Gemini model is configured as `gemini-2.5-flash`.
