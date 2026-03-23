# A simple mock knowledge base
KNOWLEDGE_BASE = {
    "gut": "The gut microbiome plays a crucial role in immune function, digestion, and mental health via the gut-brain axis. Fermented foods, high-fiber diets, and polyphenols support a healthy gut. Avoid excessive processed foods, artificial sweeteners, and unnecessary antibiotics. Key conditions include IBS (Irritable Bowel Syndrome) and IBD (Inflammatory Bowel Disease).",
    "ibs": "IBS (Irritable Bowel Syndrome) is a functional gastrointestinal disorder characterized by abdominal pain, bloating, and changes in bowel habits. First-line dietary treatment often involves the Low FODMAP diet to identify trigger foods.",
    "ibd": "IBD (Inflammatory Bowel Disease) includes Crohn's disease and Ulcerative Colitis. Unlike IBS, IBD involves chronic inflammation and structural damage to the digestive tract. Treatment usually involves immunosuppressants or biologics."
}

def retrieve_context(topic: str) -> str:
    topic_lower = topic.lower()
    context_chunks = []
    for key, info in KNOWLEDGE_BASE.items():
        if key in topic_lower:
            context_chunks.append(info)
    
    # If no strict match, fallback to general gut knowledge to ensure groundedness
    if not context_chunks:
        context_chunks.append(KNOWLEDGE_BASE["gut"])

    return " ".join(context_chunks)
