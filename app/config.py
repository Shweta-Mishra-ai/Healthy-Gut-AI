import os


class Settings:
    # --- LLM Providers (tried in this order) ---
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # --- Reliability ---
    LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "25"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "1"))
    LLM_RETRY_BACKOFF_BASE: float = float(os.getenv("LLM_RETRY_BACKOFF_BASE", "1.5"))
    # Hard ceiling across ALL providers + retries combined for one generation
    # request. Most reverse proxies (Render's default included) kill a
    # request around 100s with no useful error surfaced to the browser, so
    # this stays comfortably under that regardless of how many providers are
    # configured — once it's spent, mock content is served instead of a
    # silent proxy-level failure.
    LLM_OVERALL_BUDGET_SECONDS: float = float(os.getenv("LLM_OVERALL_BUDGET_SECONDS", "70"))

    # --- Rate limiting (per client IP) ---
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))

    # --- Caching ---
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
    CACHE_MAX_ENTRIES: int = int(os.getenv("CACHE_MAX_ENTRIES", "500"))

    # --- Batch ---
    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "10"))
    BATCH_CONCURRENCY: int = int(os.getenv("BATCH_CONCURRENCY", "3"))

    # --- Input limits ---
    MAX_FIELD_LENGTH: int = 200

    # --- Publishing identity ---
    # Where the finished articles will actually live. Used to build absolute
    # canonical/@id URLs in the structured-data pack; left blank the URLs are
    # emitted as site-relative paths, which stay valid once published.
    PUBLIC_SITE_URL: str = os.getenv("PUBLIC_SITE_URL", "").rstrip("/")

    # --- API auth (optional — if set, /generate*, /export/* require X-API-Key header) ---
    API_KEY: str = os.getenv("API_KEY", "")

    # --- Persistent storage (SQLite) ---
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "gutfolio.db")

    # --- WordPress publishing (optional) ---
    WORDPRESS_URL: str = os.getenv("WORDPRESS_URL", "").rstrip("/")
    WORDPRESS_USERNAME: str = os.getenv("WORDPRESS_USERNAME", "")
    WORDPRESS_APP_PASSWORD: str = os.getenv("WORDPRESS_APP_PASSWORD", "")
    WORDPRESS_TIMEOUT_SECONDS: float = float(os.getenv("WORDPRESS_TIMEOUT_SECONDS", "15"))


settings = Settings()
