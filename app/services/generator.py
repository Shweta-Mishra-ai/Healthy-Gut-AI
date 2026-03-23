from openai import OpenAI
from app.utils.prompt_loader import load_prompt
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_article(topic, keyword, article_type):
    prompt = load_prompt("prompts/prompt1_medical_seo_article.txt")

    final_prompt = prompt.replace("{{topic}}", topic)\
                         .replace("{{primary_keyword}}", keyword)\
                         .replace("{{article_type}}", article_type)

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": final_prompt}],
        temperature=0.7
    )

    return response.choices[0].message.content
