import asyncio
import logging

from app.config import settings
from app.language import check_language, strip_foreign_script
from app.mock_content import mock_result
from app.postprocess import (
    ProviderOutputError,
    append_references,
    ensure_disclaimer,
    ensure_meta_variants,
    extract_json,
    validate_provider_result,
)
from app.prompts import LANGUAGE_CORRECTION, build_prompts
from app.rag.retriever import build_rag_context

logger = logging.getLogger("gutfolio.llm")


# One AsyncOpenAI client per (base_url, key) instead of one per request.
# Each client owns an httpx connection pool; building a fresh one on every
# call meant a new TLS handshake per LLM request and a pool that was never
# closed — measurable added latency under batch load, and a slow file-handle
# leak on a long-running instance.
_CLIENTS: dict[tuple, object] = {}


def _get_client(base_url, api_key, timeout=None):
    from openai import AsyncOpenAI

    key = (base_url, api_key, timeout or settings.LLM_TIMEOUT_SECONDS)
    client = _CLIENTS.get(key)
    if client is None:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout or settings.LLM_TIMEOUT_SECONDS)
        _CLIENTS[key] = client
    return client


async def _call_openai_compatible(base_url, api_key, model, prompt, json_mode=False, timeout=None):
    client = _get_client(base_url, api_key, timeout)
    kwargs = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = await client.chat.completions.create(**kwargs)
    if not resp.choices:
        raise ProviderOutputError("provider returned no choices")
    content = resp.choices[0].message.content
    if not content or not content.strip():
        finish = getattr(resp.choices[0], "finish_reason", "unknown")
        raise ProviderOutputError(f"provider returned an empty message (finish_reason={finish})")
    return content


async def _run_pipeline(base_url, api_key, model, provider_name, topic, keyword, geo, article_type, language,
                        tone="educational", feedback=""):
    prompt1, prompt2_template = build_prompts(topic, keyword, geo, article_type, language, tone, feedback)

    last_err = None
    needs_language_correction = False
    for attempt in range(settings.LLM_MAX_RETRIES + 1):
        try:
            draft_prompt = prompt1
            if needs_language_correction:
                draft_prompt += LANGUAGE_CORRECTION.get(language, LANGUAGE_CORRECTION["en"])
            draft = await _call_openai_compatible(base_url, api_key, model, draft_prompt)
            prompt2 = prompt2_template.replace("{DRAFT}", draft)
            try:
                raw_json = await _call_openai_compatible(base_url, api_key, model, prompt2, json_mode=True)
            except ProviderOutputError:
                raise
            except Exception:
                # some free-tier models reject response_format=json_object; retry without it
                raw_json = await _call_openai_compatible(base_url, api_key, model, prompt2, json_mode=False)
            result = extract_json(raw_json)
            # The optimization pass rewrites the whole body, so the script
            # check has to run on what actually comes back from step 2, not
            # on the draft from step 1.
            result = validate_provider_result(result, language)
            result["provider_used"] = provider_name
            return result
        except ProviderOutputError as e:
            last_err = f"{provider_name} returned unusable output: {e}"
            needs_language_correction = "language check failed" in str(e)
        except TimeoutError as e:
            last_err = f"{provider_name} timed out: {e}"
        except Exception as e:
            last_err = f"{provider_name} error: {e}"
        if attempt < settings.LLM_MAX_RETRIES:
            backoff = settings.LLM_RETRY_BACKOFF_BASE ** attempt
            logger.warning("Retrying %s after failure (attempt %d): %s", provider_name, attempt + 1, last_err)
            await asyncio.sleep(backoff)
    raise RuntimeError(last_err or f"{provider_name} failed with no error captured")


async def llm_generate(topic: str, keyword: str, geo: str, article_type: str, language: str = "en",
                       tone: str = "educational", feedback: str = "") -> dict:
    """Tries providers in order: Groq (free) -> OpenRouter (free) -> OpenAI (paid, optional)
    -> Mock template. Each failure is logged and the next provider is tried,
    so a single provider outage never takes the whole app down.

    The whole loop (every provider, every retry) is wrapped in one hard
    overall-time ceiling (settings.LLM_OVERALL_BUDGET_SECONDS). Without this,
    even a *single* configured provider could legitimately run
    LLM_TIMEOUT_SECONDS * (LLM_MAX_RETRIES + 1) seconds — at the old defaults
    (45s x 3) that's 135s for one provider alone, comfortably past the
    request timeout most reverse proxies enforce (Render's default is 100s).
    When that proxy timeout fires, the browser sees a bare connection
    failure with zero explanation — which is very likely what "loading
    sometimes just errors out" was. Falling back to mock content once the
    overall budget is spent guarantees a real (if degraded) response
    instead of a silent proxy kill.
    """
    providers = []
    if settings.GROQ_API_KEY:
        providers.append(("groq", settings.GROQ_BASE_URL, settings.GROQ_API_KEY, settings.GROQ_MODEL))
    if settings.OPENROUTER_API_KEY:
        providers.append((
            "openrouter", settings.OPENROUTER_BASE_URL, settings.OPENROUTER_API_KEY, settings.OPENROUTER_MODEL,
        ))
    if settings.OPENAI_API_KEY:
        providers.append(("openai", None, settings.OPENAI_API_KEY, settings.OPENAI_MODEL))

    async def _try_all_providers():
        result = None
        errors = []
        for name, base_url, api_key, model in providers:
            try:
                result = await asyncio.wait_for(
                    _run_pipeline(
                        base_url, api_key, model, name, topic, keyword, geo, article_type, language, tone, feedback,
                    ),
                    timeout=settings.LLM_TIMEOUT_SECONDS * (settings.LLM_MAX_RETRIES + 1) + 5,
                )
                return result, errors
            except Exception as e:
                logger.error("Provider %s failed entirely: %s", name, e)
                errors.append(f"{name}: {e}")
                continue
        return result, errors

    try:
        result, errors = await asyncio.wait_for(_try_all_providers(), timeout=settings.LLM_OVERALL_BUDGET_SECONDS)
    except TimeoutError:
        budget = settings.LLM_OVERALL_BUDGET_SECONDS
        result, errors = None, [f"overall {budget}s generation budget exceeded across all providers"]

    if result is None:
        if providers:
            logger.error("All LLM providers failed, falling back to mock. Errors: %s", errors)
        result = mock_result(topic, keyword, geo, language)
        if errors:
            result["provider_note"] = "All configured providers failed; served template content. " + " | ".join(errors)

    _, matched_chunks = build_rag_context(topic, keyword)
    result["rag_sources"] = [
        {"title": c["title"], "topic": c["topic"], "relevance_score": c["relevance_score"]}
        for c in matched_chunks
    ]
    if "optimized_article_markdown" in result:
        article = result["optimized_article_markdown"]
        # Last-resort repair on the fallback path. A validated provider
        # response can't reach this branch dirty (validate_provider_result
        # already rejected it), but the retrieved knowledge-base context is
        # interpolated into the template article, so strip anything that
        # slipped in from the corpus rather than shipping mixed scripts.
        leftover = check_language(article, language)
        if not leftover["ok"]:
            logger.warning("Repairing residual script contamination in served article: %s", leftover["reason"])
            article = strip_foreign_script(article)
            result["language_repaired"] = True
        article = ensure_disclaimer(article, language)
        result["optimized_article_markdown"] = append_references(article, matched_chunks, language)
        result["language_check"] = check_language(result["optimized_article_markdown"], language)
    result = ensure_meta_variants(result, language)
    if feedback:
        # The template path cannot act on feedback; say so rather than imply
        # the rejection note shaped this article.
        result["reviewer_feedback"] = {"note": feedback, "applied": result.get("provider_used") != "mock"}
    return result
