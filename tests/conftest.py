import os

for var in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "API_KEY"):
    os.environ.pop(var, None)
