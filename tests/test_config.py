import os
import importlib
import app.config


def test_settings_load_env(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "custom-model")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30.5")

    importlib.reload(app.config)
    settings = app.config.Settings()
    try:
        assert settings.GROQ_MODEL == "custom-model"
        assert settings.LLM_TIMEOUT_SECONDS == 30.5
    finally:
        monkeypatch.undo()
        importlib.reload(app.config)

