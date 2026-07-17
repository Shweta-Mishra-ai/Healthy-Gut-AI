# Contributing to Healthy Gut AI

Thanks for considering a contribution. This project favors small, well-tested
pull requests over large speculative ones — that keeps review fast and the
`main` branch always deployable.

## Ground rules

1. **Every behavioral change needs a test.** New endpoint, new validation
   rule, new provider, new metric — if it can break, it should have a test
   that catches the break.
2. **No provider outage should ever 500 the app.** If you touch
   `app/llm_providers.py`, make sure the fallback chain (Groq → OpenRouter →
   OpenAI → Mock) still degrades gracefully on your change.
3. **No secrets in code or commits.** API keys live in `.env` (git-ignored)
   or platform environment variables — never hardcoded, never in a PR diff.
4. **Keep PRs scoped.** One feature or one fix per PR. If a review reveals a
   second issue, open a follow-up PR instead of expanding the current one.

## Local development setup

```bash
git clone https://github.com/Shweta-Mishra-ai/Healthy-Gut-AI.git
cd Healthy-Gut-AI
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # optional — app runs in mock mode without keys
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000` — the UI works immediately in mock mode, no API
key required.

## Running tests

```bash
python -m pytest tests/ -v
```

All 29 existing tests must pass before you open a PR. Add new tests under
`tests/` mirroring the module you changed:

| You changed... | Add/update tests in... |
|---|---|
| `app/metrics.py` | `tests/test_metrics.py` |
| `app/schemas.py` | `tests/test_schemas.py` |
| `app/rag/*` | `tests/test_rag.py` |
| `app/main.py`, new endpoints | `tests/test_api.py` |
| `app/llm_providers.py` | `tests/test_api.py` (mock-mode path) + manual live-key smoke test |

## Code style

- Type hints on new functions where practical.
- Keep provider-specific logic inside `app/llm_providers.py` — routes in
  `app/main.py` should stay provider-agnostic.
- Prefer explicit Pydantic validation over ad-hoc `if` checks in route
  handlers.
- Log at `logger.warning`/`logger.error` for anything that would help debug a
  production incident; avoid `print()`.

## Submitting a pull request

1. Fork the repo and create a branch: `git checkout -b fix/short-description`.
2. Make your change, add tests, run `python -m pytest tests/ -v` locally.
3. Update `README.md` if you added a route, env var, or user-facing feature.
4. Open a PR with:
   - what changed and why (1–2 sentences is fine)
   - how you tested it
   - any known limitations
5. CI (`.github/workflows/ci.yml`) runs the full test suite on Python 3.11
   and 3.12 automatically — it must be green before merge.

## Reporting bugs / requesting features

Open a GitHub issue with:
- **Bug reports:** steps to reproduce, expected vs. actual behavior, and
  whether it happens in mock mode or only with a live provider key.
- **Feature requests:** the user problem it solves, not just the
  implementation idea — that helps us evaluate scope and priority.

## Known gaps that are good first contributions

- Redis-backed cache/rate-limiter (currently in-memory, documented in README)
- Markdown table rendering in DOCX/PDF export (currently skipped)
- API-key auth layer for the public endpoints
- Expanding the RAG knowledge base beyond IBS/IBD/GERD/Celiac

Thanks again for contributing — every fix, however small, is appreciated.
