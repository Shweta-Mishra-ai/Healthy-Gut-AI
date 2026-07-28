import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.config import settings

_UNSAFE_CHARS = re.compile(r'[<>{}$`]')
_WHITESPACE = re.compile(r'\s+')


def clean_text_field(value: str, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    v = _WHITESPACE.sub(" ", value).strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace-only")
    if len(v) > settings.MAX_FIELD_LENGTH:
        raise ValueError(f"{field_name} exceeds {settings.MAX_FIELD_LENGTH} characters")
    if _UNSAFE_CHARS.search(v):
        raise ValueError(f"{field_name} contains disallowed characters (< > {{ }} $ `)")
    return v


class ArticleType(str, Enum):
    pillar = "pillar"
    supporting = "supporting"


class Language(str, Enum):
    en = "en"
    hi = "hi"


class Tone(str, Enum):
    educational = "educational"
    authoritative = "authoritative"
    patient_friendly = "patient_friendly"
    academic = "academic"
    seo_blog = "seo_blog"


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=200)
    primary_keyword: str = Field(..., min_length=2, max_length=100)
    geo_target: str = Field(..., min_length=2, max_length=100)
    article_type: ArticleType = ArticleType.supporting
    language: Language = Language.en
    tone: Tone = Tone.educational

    @field_validator("topic")
    @classmethod
    def v_topic(cls, v):
        return clean_text_field(v, "topic")

    @field_validator("primary_keyword")
    @classmethod
    def v_keyword(cls, v):
        return clean_text_field(v, "primary_keyword")

    @field_validator("geo_target")
    @classmethod
    def v_geo(cls, v):
        return clean_text_field(v, "geo_target")


class BatchGenerateRequest(BaseModel):
    items: List[GenerateRequest]

    @field_validator("items")
    @classmethod
    def v_items(cls, v):
        if not v:
            raise ValueError("items cannot be empty")
        if len(v) > settings.MAX_BATCH_SIZE:
            raise ValueError(f"batch size exceeds max of {settings.MAX_BATCH_SIZE}")
        return v


class ReviewActionRequest(BaseModel):
    note: str = Field("", max_length=500)
    reviewer_name: str = Field("", max_length=100)
    reviewer_credential: str = Field("", max_length=100)

    @field_validator("note", "reviewer_name", "reviewer_credential")
    @classmethod
    def v_clean_text(cls, v):
        v = (v or "").strip()
        if v and _UNSAFE_CHARS.search(v):
            raise ValueError("contains disallowed characters (< > { } $ `)")
        return v


class FAQ(BaseModel):
    question: str
    answer: str


class ArticleResult(BaseModel):
    optimized_article_markdown: str
    meta_description: str = ""
    meta_description_variants: List[str] = []
    url_slug: str = ""
    faqs: List[FAQ] = []
    schema_json_ld: dict = {}
    cta_soft: str = ""
    cta_direct: str = ""
    provider_used: str = "mock"
    metrics: Optional[dict] = None
    error: Optional[str] = None
