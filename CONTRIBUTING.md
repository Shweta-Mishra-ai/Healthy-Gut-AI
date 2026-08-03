# Contributing to Healthy Gut AI

Thanks for considering a contribution to **Healthy Gut AI**. We welcome small, focused pull requests that maintain high code quality, test coverage, and performance.

## Ground Rules

1. **Every behavioral change requires automated test coverage.** New endpoints, validation rules, or export logic must include unit/integration tests in `tests/`.
2. **Never break the LLM fallback chain.** Ensure failure modes (Groq → OpenRouter → OpenAI → Mock) resolve cleanly without 500 errors.
3. **Protect credentials and sensitive keys.** Never commit API keys or secret tokens to the repository.
4. **Ensure clean test suite execution.** All 150 tests must pass before opening a pull request.

## Local Setup

```bash
git clone https://github.com/Shweta-Mishra-ai/Healthy-Gut-AI.git
cd Healthy-Gut-AI/hga
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m pytest
```

## Running Tests

Run the full test suite using Pytest:

```bash
python -m pytest
```

## Code Quality Standards

- Maintain explicit type hints on public methods.
- Use `logger.warning`/`logger.error` for diagnostic logging instead of `print()`.
- Validate input using Pydantic schemas in `app/schemas.py`.
- Preserve UI glassmorphism aesthetics and theme persistence across frontend modifications.
