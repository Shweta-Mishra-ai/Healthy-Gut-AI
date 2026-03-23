from openai import OpenAI
from app.utils.prompt_loader import load_prompt
import os
import json

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def optimize_article(article, keyword, geo):
    prompt = load_prompt("prompts/prompt2_geo_ai_optimization.txt")

    final_prompt = prompt.replace("{{article_markdown}}", article)\
                         .replace("{{primary_keyword}}", keyword)\
                         .replace("{{geo_target}}", geo)

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": final_prompt}],
        temperature=0.5
    )

    content = response.choices[0].message.content

    return json.loads(content)
