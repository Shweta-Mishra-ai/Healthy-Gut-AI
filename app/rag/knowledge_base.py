"""Curated gut-health knowledge base for retrieval-augmented generation.

Each entry is an independently-retrievable chunk: general medical/nutrition
knowledge written for this project, not copied from any single source.
This is a starting corpus (24 topics) meant to be extended — see
docs for how to add entries without touching retriever logic.
"""

KNOWLEDGE_BASE = [
    {
        "id": "ibs",
        "topic": "IBS",
        "title": "Irritable Bowel Syndrome (IBS)",
        "content": "IBS is a functional gastrointestinal disorder diagnosed by symptom pattern rather than "
                   "structural damage: recurring abdominal pain linked to bowel movements, with altered stool "
                   "frequency or form (diarrhea-predominant, constipation-predominant, or mixed). The low-FODMAP "
                   "diet, developed at Monash University, is the leading first-line dietary intervention, "
                   "temporarily restricting fermentable carbohydrates before a structured reintroduction phase. "
                   "Stress and the gut-brain axis strongly influence symptom severity in IBS.",
    },
    {
        "id": "ibd_crohns",
        "topic": "IBD",
        "title": "Crohn's Disease",
        "content": "Crohn's disease is a chronic inflammatory bowel disease that can affect any part of the "
                   "gastrointestinal tract from mouth to anus, most commonly the terminal ileum, and causes "
                   "transmural (full-thickness) inflammation that can lead to strictures and fistulas. Unlike IBS, "
                   "it involves measurable tissue damage and requires medical management with anti-inflammatory, "
                   "immunosuppressive, or biologic therapies rather than diet alone.",
    },
    {
        "id": "ibd_uc",
        "topic": "IBD",
        "title": "Ulcerative Colitis",
        "content": "Ulcerative colitis is an inflammatory bowel disease limited to the colon and rectum, causing "
                   "continuous mucosal inflammation and ulceration starting from the rectum and extending "
                   "proximally. Common symptoms include bloody diarrhea, urgency, and abdominal cramping. "
                   "Treatment ranges from 5-ASA compounds for mild cases to biologics or surgery (colectomy) "
                   "for severe or refractory disease.",
    },
    {
        "id": "gerd",
        "topic": "GERD",
        "title": "Acid Reflux / GERD",
        "content": "Gastroesophageal reflux disease occurs when stomach acid regularly flows back into the "
                   "esophagus, most often due to a weakened lower esophageal sphincter. Common triggers include "
                   "fatty or spicy foods, caffeine, alcohol, large meals, and lying down soon after eating. "
                   "Management includes elevating the head of the bed, weight management, meal timing, and "
                   "medications such as PPIs or H2 blockers for persistent cases.",
    },
    {
        "id": "celiac",
        "topic": "Celiac",
        "title": "Celiac Disease",
        "content": "Celiac disease is an autoimmune condition in which ingesting gluten triggers an immune "
                   "response that damages the villi of the small intestine, impairing nutrient absorption. "
                   "It is distinct from non-celiac gluten sensitivity, which lacks the same autoimmune markers "
                   "and intestinal damage. Diagnosis typically involves serology (tTG-IgA) followed by endoscopic "
                   "biopsy; the only treatment is a strict, lifelong gluten-free diet.",
    },
    {
        "id": "sibo",
        "topic": "SIBO",
        "title": "Small Intestinal Bacterial Overgrowth (SIBO)",
        "content": "SIBO occurs when bacteria that normally reside in the colon proliferate excessively in the "
                   "small intestine, causing bloating, gas, and malabsorption. It is commonly diagnosed via "
                   "hydrogen/methane breath testing and is frequently found alongside IBS, since overlapping "
                   "symptoms make differentiation important. Treatment often combines targeted antibiotics "
                   "(such as rifaximin) with dietary approaches like low-FODMAP.",
    },
    {
        "id": "microbiome",
        "topic": "gut microbiome",
        "title": "The Gut Microbiome",
        "content": "The gut microbiome is the community of trillions of bacteria, archaea, fungi, and viruses "
                   "residing primarily in the large intestine. It plays roles in digesting fiber into "
                   "short-chain fatty acids, training and modulating the immune system, synthesizing certain "
                   "vitamins (like vitamin K and some B vitamins), and communicating with the brain via the "
                   "gut-brain axis. Diversity and balance of microbial species are generally associated with "
                   "better metabolic and immune health.",
    },
    {
        "id": "gut_brain_axis",
        "topic": "gut-brain axis",
        "title": "The Gut-Brain Axis",
        "content": "The gut-brain axis is the bidirectional communication network linking the enteric nervous "
                   "system in the gut to the central nervous system, involving the vagus nerve, immune "
                   "signaling, and microbial metabolites like short-chain fatty acids and neurotransmitter "
                   "precursors. This axis helps explain why psychological stress can worsen GI symptoms, and why "
                   "GI distress can, in turn, affect mood and cognition.",
    },
    {
        "id": "probiotics",
        "topic": "probiotics",
        "title": "Probiotics",
        "content": "Probiotics are live microorganisms that, when consumed in adequate amounts, can confer a "
                   "health benefit, most commonly strains of Lactobacillus and Bifidobacterium. Evidence "
                   "supports specific strains for specific conditions (e.g., certain strains for "
                   "antibiotic-associated diarrhea), but benefits are strain-specific rather than universal — "
                   "a generic 'probiotic' claim without a named strain and dose is not clinically meaningful.",
    },
    {
        "id": "prebiotics",
        "topic": "prebiotics",
        "title": "Prebiotics",
        "content": "Prebiotics are non-digestible fibers and compounds, such as inulin and fructooligosaccharides "
                   "(FOS), that selectively feed beneficial gut bacteria. Common food sources include onions, "
                   "garlic, leeks, asparagus, and bananas. Increasing prebiotic intake too quickly can cause "
                   "bloating and gas, especially in people with IBS or SIBO, so gradual introduction is "
                   "generally recommended.",
    },
    {
        "id": "fodmap",
        "topic": "FODMAP",
        "title": "The Low-FODMAP Diet",
        "content": "FODMAP stands for Fermentable Oligosaccharides, Disaccharides, Monosaccharides, and Polyols — "
                   "short-chain carbohydrates that are poorly absorbed in the small intestine and rapidly "
                   "fermented by gut bacteria, drawing water into the bowel and producing gas. The diet has "
                   "three phases: strict elimination (2-6 weeks), structured reintroduction to identify specific "
                   "triggers, and long-term personalization — it is not meant to be followed strictly forever.",
    },
    {
        "id": "leaky_gut",
        "topic": "leaky gut",
        "title": "Intestinal Permeability ('Leaky Gut')",
        "content": "Intestinal permeability refers to the tightness of junctions between intestinal epithelial "
                   "cells that normally control what passes from the gut into the bloodstream. Increased "
                   "permeability is a recognized feature of conditions like celiac disease and IBD, though "
                   "'leaky gut syndrome' as a standalone diagnosis for vague symptoms is not a formally "
                   "recognized medical diagnosis and claims about it should be presented cautiously.",
    },
    {
        "id": "gastritis",
        "topic": "gastritis",
        "title": "Gastritis",
        "content": "Gastritis is inflammation of the stomach lining, commonly caused by Helicobacter pylori "
                   "infection, chronic NSAID use, or excessive alcohol consumption. Symptoms include upper "
                   "abdominal pain, nausea, and bloating. Diagnosis often involves endoscopy with biopsy, and "
                   "treatment depends on cause — H. pylori requires antibiotic eradication therapy, while "
                   "NSAID-induced gastritis resolves with discontinuation and acid-suppressing medication.",
    },
    {
        "id": "diverticulitis",
        "topic": "diverticulitis",
        "title": "Diverticulitis",
        "content": "Diverticulitis occurs when small pouches (diverticula) that form in the colon wall, "
                   "usually with age and low dietary fiber intake, become inflamed or infected. Acute episodes "
                   "present with left lower abdominal pain, fever, and altered bowel habits, often requiring "
                   "antibiotics or, in severe/recurrent cases, surgery. Between episodes, a high-fiber diet is "
                   "generally recommended to reduce recurrence risk.",
    },
    {
        "id": "constipation",
        "topic": "constipation",
        "title": "Chronic Constipation",
        "content": "Chronic constipation is defined by infrequent bowel movements, straining, or a sense of "
                   "incomplete evacuation persisting over time. Common contributors include low fiber and fluid "
                   "intake, sedentary lifestyle, certain medications (opioids, some antidepressants), and "
                   "hypothyroidism. First-line management includes increasing soluble fiber gradually, adequate "
                   "hydration, and physical activity before considering laxatives.",
    },
    {
        "id": "fiber",
        "topic": "fiber",
        "title": "Dietary Fiber and Gut Health",
        "content": "Dietary fiber is categorized as soluble (dissolves in water, forming a gel — found in oats, "
                   "beans, and psyllium) or insoluble (adds bulk to stool — found in whole grains and "
                   "vegetable skins). Soluble fiber is fermented by gut bacteria into short-chain fatty acids "
                   "like butyrate, which nourish colon cells and have anti-inflammatory effects. Most adults "
                   "fall short of recommended daily fiber intake (roughly 25-38g depending on age and sex).",
    },
    {
        "id": "fermented_foods",
        "topic": "fermented foods",
        "title": "Fermented Foods",
        "content": "Fermented foods such as yogurt, kefir, sauerkraut, kimchi, and miso contain live microbial "
                   "cultures produced through controlled fermentation. Regular consumption has been associated "
                   "with increased microbiome diversity and reduced inflammatory markers in some studies, "
                   "though effects vary by product and strain. Pasteurized versions of fermented foods (e.g., "
                   "some shelf-stable sauerkraut) may no longer contain live cultures.",
    },
    {
        "id": "lactose_intolerance",
        "topic": "lactose intolerance",
        "title": "Lactose Intolerance",
        "content": "Lactose intolerance results from insufficient lactase enzyme production, leading to "
                   "undigested lactose fermenting in the colon and causing bloating, gas, and diarrhea after "
                   "consuming dairy. It is distinct from a milk allergy, which involves the immune system. "
                   "Severity varies by individual lactase levels, and many people with lactose intolerance can "
                   "tolerate small amounts or fermented dairy (like hard cheese or yogurt) better than milk.",
    },
    {
        "id": "food_intolerance_vs_allergy",
        "topic": "food intolerance",
        "title": "Food Intolerance vs. Food Allergy",
        "content": "Food intolerances (e.g., to lactose or certain FODMAPs) involve the digestive system and "
                   "typically cause delayed, dose-dependent GI symptoms without involving the immune system. "
                   "Food allergies involve an IgE-mediated immune response, can be triggered by trace amounts, "
                   "and can escalate to anaphylaxis — a medical emergency. Confusing the two can lead to unsafe "
                   "assumptions about the seriousness of accidental exposure.",
    },
    {
        "id": "bloating",
        "topic": "bloating",
        "title": "Bloating",
        "content": "Bloating is the subjective sensation of abdominal fullness or pressure, which may or may "
                   "not be accompanied by visible distension. Common causes include excess gas production from "
                   "fermentable carbohydrates, swallowed air, slowed gut motility, SIBO, or underlying "
                   "conditions like IBS. Persistent bloating accompanied by weight loss, blood in stool, or "
                   "night symptoms warrants medical evaluation rather than dietary self-management alone.",
    },
    {
        "id": "elimination_diet",
        "topic": "elimination diet",
        "title": "Elimination Diets",
        "content": "An elimination diet systematically removes suspected trigger foods for a defined period, "
                   "then reintroduces them one at a time to identify individual triggers. It differs from "
                   "indefinite restrictive dieting, which can lead to nutritional gaps and, in some cases, "
                   "disordered eating patterns if not time-bound and professionally guided. Working with a "
                   "registered dietitian is recommended for elimination diets lasting more than a few weeks.",
    },
    {
        "id": "gut_microbiome_diet",
        "topic": "diet diversity",
        "title": "Plant Diversity and Microbiome Health",
        "content": "Research, including the American Gut Project, has associated eating a wide variety of "
                   "different plant species (rather than a large quantity of a few plants) with greater gut "
                   "microbial diversity. A commonly cited target is 30+ different plant foods per week, "
                   "including vegetables, fruits, whole grains, legumes, nuts, and seeds, as each species tends "
                   "to feed different bacterial populations.",
    },
    {
        "id": "hydration_gut",
        "topic": "hydration",
        "title": "Hydration and Digestion",
        "content": "Adequate fluid intake helps soluble fiber form the gel-like consistency that eases stool "
                   "passage, and supports overall motility. Insufficient hydration is a common, easily "
                   "correctable contributor to constipation, particularly when fiber intake is increased "
                   "without a corresponding increase in fluids, which can paradoxically worsen bloating and "
                   "constipation.",
    },
    {
        "id": "when_to_see_doctor",
        "topic": "warning signs",
        "title": "Gut Symptom Red Flags",
        "content": "Certain gastrointestinal symptoms warrant prompt medical evaluation rather than home "
                   "management: unintentional weight loss, blood in stool or black tarry stools, persistent "
                   "vomiting, difficulty swallowing, symptoms waking someone from sleep, iron-deficiency anemia, "
                   "or a family history of colorectal cancer or IBD combined with new symptoms after age 50. "
                   "These are commonly referred to as 'alarm features' in gastroenterology.",
    },
]
