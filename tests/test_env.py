from pathlib import Path

from nbim_digest.env import get_anthropic_api_key, get_env_secret, load_app_env


def test_load_app_env_overrides_stale_process_value(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=sk-ant-api03-new\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-old")

    load_app_env(tmp_path)

    assert get_env_secret("ANTHROPIC_API_KEY") == "sk-ant-api03-new"


def test_get_anthropic_api_key_rejects_malformed_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k-ant-api03-missing-leading-s")

    assert get_anthropic_api_key() is None


def test_get_anthropic_api_key_accepts_expected_prefix(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", " sk-ant-api03-valid-looking ")

    assert get_anthropic_api_key() == "sk-ant-api03-valid-looking"
