import json

import httpx
import pytest

import main
from app.config import Settings
from app.llm import AnthropicClient, LLMError, OpenAICompatibleClient, extract_json
from app.tracing import Tracer


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_anthropic_client_parses_text_blocks():
    def handler(req):
        body = json.loads(req.content)
        assert req.headers["x-api-key"] == "sk-test" and body["system"] == "sys"
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"a": 1}'}]})
    c = AnthropicClient("sk-test", "m", client=_client(handler))
    assert extract_json(c.complete("sys", "hi")) == {"a": 1}


def test_openai_client_parses_choices_and_maps_errors():
    ok = OpenAICompatibleClient("k", "m", client=_client(lambda r: httpx.Response(
        200, json={"choices": [{"message": {"content": "hello"}}]})))
    assert ok.complete("s", "p") == "hello"
    bad = OpenAICompatibleClient("k", "m", client=_client(lambda r: httpx.Response(401)))
    with pytest.raises(LLMError, match="401"):
        bad.complete("s", "p")


def test_extract_json_rejects_non_json():
    with pytest.raises(LLMError):
        extract_json("I cannot help with that")


def test_settings_degrade_to_no_llm_without_key(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    s = Settings.from_env(load_env_file=False)
    assert s.llm_provider == "none" and s.llm_api_key is None


def test_tracer_redacts_secrets(tmp_path):
    t = Tracer(quiet=True, secrets=["sk-very-secret-key"], jsonl_path=tmp_path / "t.jsonl")
    t.log("TOOL", "calling with sk-very-secret-key")
    t.close()
    assert "sk-very-secret-key" not in t.lines[0]
    assert "sk-very-secret-key" not in (tmp_path / "t.jsonl").read_text()


def test_cli_offline_run_with_injected_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RETRY_BACKOFF_S", "0")
    transcript = tmp_path / "t.txt"
    code = main.main(["--offline", "--output-dir", str(tmp_path), "--transcript", str(transcript),
                      "--inject-failure", "web_search:malformed",
                      "Analyze the competitive landscape of Voltaic Semiconductors"])
    assert code == 0
    text = transcript.read_text(encoding="utf-8")
    assert "AGENT EXECUTION PLAN" in text and "[RECOVERY]" in text and 'missing "results"' in text
    run_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert {f.name for f in run_dirs[0].iterdir()} == {"report.json", "report.md", "trace.jsonl"}


def test_cli_rejects_bad_injection_spec(capsys):
    assert main.main(["--offline", "--inject-failure", "nope", "Analyze Voltaic"]) == 2
