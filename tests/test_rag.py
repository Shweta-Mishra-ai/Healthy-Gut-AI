from app.rag.retriever import Retriever, build_rag_context
from app.rag.knowledge_base import KNOWLEDGE_BASE


def test_corpus_loaded():
    r = Retriever(KNOWLEDGE_BASE)
    assert r.size() == len(KNOWLEDGE_BASE)
    assert r.size() >= 20


def test_relevant_query_ranks_correct_topic_first():
    r = Retriever(KNOWLEDGE_BASE)
    results = r.retrieve("gluten damage small intestine autoimmune", top_k=3)
    assert results[0]["id"] == "celiac"


def test_different_queries_return_different_top_result():
    r = Retriever(KNOWLEDGE_BASE)
    ibs_result = r.retrieve("IBS bloating FODMAP diet symptoms", top_k=1)[0]
    reflux_result = r.retrieve("acid reflux heartburn esophagus PPI", top_k=1)[0]
    assert ibs_result["id"] != reflux_result["id"]


def test_empty_query_returns_fallback():
    r = Retriever(KNOWLEDGE_BASE)
    results = r.retrieve("", top_k=3)
    assert len(results) == 1
    assert results[0]["relevance_score"] == 0.0


def test_nonsense_query_returns_fallback_not_empty():
    r = Retriever(KNOWLEDGE_BASE)
    results = r.retrieve("zzz qqq unrelated nonsense xyz123", top_k=3)
    assert len(results) >= 1


def test_build_rag_context_returns_text_and_chunks():
    context_text, chunks = build_rag_context("IBS diet plan", "IBS symptoms")
    assert isinstance(context_text, str)
    assert len(context_text) > 0
    assert len(chunks) >= 1
    assert all("relevance_score" in c for c in chunks)
