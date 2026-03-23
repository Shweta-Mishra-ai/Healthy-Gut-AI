import os
import json
from openai import AsyncOpenAI
from app.services.rag_service import retrieve_context

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", "mock-key"))

async def generate_article(topic: str, primary_keyword: str, geo_target: str, article_type: str) -> dict:
    rag_context = retrieve_context(topic)
    
    # Read prompts. Since this runs from root usually, we refer to 'prompts/' directory
    try:
        with open("prompts/prompt1_medical_seo_article.txt", "r", encoding="utf-8") as f:
            prompt1_template = f.read()
        with open("prompts/prompt2_geo_ai_optimization.txt", "r", encoding="utf-8") as f:
            prompt2_template = f.read()
    except FileNotFoundError:
        prompt1_template = "Topic: {{topic}} Keyword: {{primary_keyword}} Type: {{article_type}}"
        prompt2_template = "Optimize article: {{article_markdown}} target {{geo_target}}"
        
    prompt1 = prompt1_template.replace("{{topic}}", topic)
    prompt1 = prompt1.replace("{{primary_keyword}}", primary_keyword)
    prompt1 = prompt1.replace("{{article_type}}", article_type)
    
    # Inject RAG context into Prompt 1
    prompt1 += f"\n\nMEDICAL CONTEXT TO USE (RAG Knowledge Base):\n{rag_context}"
    
    if client.api_key == "mock-key":
        # Return mock response if no key is provided
        return {
            "optimized_article_markdown": f"# {topic.title()} Guide\n\nThis is a mock generated article for **{geo_target}** concerning **{topic}**.\n\n### Key Information\n{rag_context}\n\n### Diet Recommendations\n- Eat more fiber.\n- Stay hydrated.\n\nEnjoy a healthier gut!",
            "meta_description": f"Learn all about {topic} in {geo_target} with {primary_keyword}.",
            "url_slug": f"{topic.lower().replace(' ', '-')}-guide",
            "faqs": [
                {"question": f"What is {topic}?", "answer": f"It is a condition that affects your gut. {rag_context}"},
                {"question": f"Is there a clinic for {topic} in {geo_target}?", "answer": f"There are many specialists in {geo_target}."}
            ],
            "schema_json_ld": {"@context": "https://schema.org", "@type": "Article"},
            "cta_soft": "Learn more about healthy eating on our blog.",
            "cta_direct": "Sign up for Healthy Gut AI today!"
        }

    try:
        # Step 1: Draft Article
        response1 = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a senior medical writer and SEO specialist for Healthy Gut AI."},
                {"role": "user", "content": prompt1}
            ]
        )
        draft_article = response1.choices[0].message.content
        
        # Step 2: Optimization
        prompt2 = prompt2_template.replace("{{article_markdown}}", draft_article)
        prompt2 = prompt2.replace("{{primary_keyword}}", primary_keyword)
        prompt2 = prompt2.replace("{{geo_target}}", geo_target)
        
        response2 = await client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an SEO specialist optimizing markdown content. Return JSON strictly formatted as expected."},
                {"role": "user", "content": prompt2}
            ]
        )
        
        return json.loads(response2.choices[0].message.content)
    except Exception as e:
        return {"error": f"LLM Failure: {str(e)}"}
