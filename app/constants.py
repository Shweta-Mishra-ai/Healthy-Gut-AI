import os

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

OUT_OF_SCOPE_MESSAGE = (
    "Gutfolio specializes in gut/digestive health topics (IBS, IBD, GERD, "
    "Celiac, SIBO, microbiome, diet, and related conditions). This topic looks "
    "outside that scope, so we're not generating it rather than producing an "
    "unfocused, low-trust article. Try a gut-health-related angle instead."
)
