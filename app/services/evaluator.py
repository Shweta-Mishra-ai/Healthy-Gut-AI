from openai import OpenAI
import os
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def evaluate(article):
    prompt = f"""
Evaluate this medical article:

Score (0-10):
- Medical accuracy
- SEO quality
- Readability

Return JSON only.
ARTICLE:
{article}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return json.loads(response.choices[0].message.content)
