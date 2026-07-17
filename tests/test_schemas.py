import pytest
from pydantic import ValidationError

from app.schemas import BatchGenerateRequest, GenerateRequest


def test_valid_request():
    req = GenerateRequest(topic="IBS diet", primary_keyword="IBS symptoms", geo_target="USA")
    assert req.article_type.value == "supporting"
    assert req.language.value == "en"


def test_empty_topic_rejected():
    with pytest.raises(ValidationError):
        GenerateRequest(topic="   ", primary_keyword="kw", geo_target="USA")


def test_topic_too_short_rejected():
    with pytest.raises(ValidationError):
        GenerateRequest(topic="ab", primary_keyword="kw", geo_target="USA")


def test_unsafe_characters_rejected():
    with pytest.raises(ValidationError):
        GenerateRequest(topic="<script>alert(1)</script>", primary_keyword="kw", geo_target="USA")


def test_invalid_article_type_rejected():
    with pytest.raises(ValidationError):
        GenerateRequest(topic="IBS diet", primary_keyword="kw", geo_target="USA", article_type="invalid")


def test_batch_empty_rejected():
    with pytest.raises(ValidationError):
        BatchGenerateRequest(items=[])


def test_batch_over_limit_rejected():
    item = {"topic": "IBS diet", "primary_keyword": "kw", "geo_target": "USA"}
    with pytest.raises(ValidationError):
        BatchGenerateRequest(items=[item] * 11)


def test_batch_within_limit_ok():
    item = {"topic": "IBS diet", "primary_keyword": "kw", "geo_target": "USA"}
    req = BatchGenerateRequest(items=[item] * 5)
    assert len(req.items) == 5
