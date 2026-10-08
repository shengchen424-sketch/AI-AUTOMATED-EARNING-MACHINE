import json
import stat

import pytest

from earnbot.llm import ClaudeCodeJSON, LLMError

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def fake_claude(tmp_path, payload, code=0):
    """A stand-in `claude` binary that records its args/stdin/env and prints `payload`."""
    script = tmp_path / "claude"
    script.write_text(f"""#!/usr/bin/env python3
import json, os, sys
json.dump({{"argv": sys.argv[1:], "stdin": sys.stdin.read(),
           "api_key": os.environ.get("ANTHROPIC_API_KEY")}}, open({str(tmp_path / 'call.json')!r}, "w"))
sys.stdout.write({payload!r})
sys.exit({code})
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_uses_subscription_cli_and_strips_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-be-used")
    out = json.dumps({"type": "result", "subtype": "success", "is_error": False, "structured_output": {"ok": True}})
    llm = ClaudeCodeJSON("claude-opus-5-5", "high", binary=fake_claude(tmp_path, out))
    assert llm.generate_json("SYS", "PROMPT", SCHEMA) == {"ok": True}
    call = json.loads((tmp_path / "call.json").read_text())
    assert call["api_key"] is None
    assert call["stdin"] == "PROMPT"
    argv = call["argv"]
    assert argv[0] == "-p" and json.loads(argv[argv.index("--json-schema") + 1]) == SCHEMA
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
    assert argv[argv.index("--tools") + 1] == ""


@pytest.mark.parametrize("payload,code", [
    (json.dumps({"subtype": "success", "is_error": True, "result": "usage limit reached"}), 1),
    (json.dumps({"subtype": "error_max_turns", "is_error": False}), 0),
    (json.dumps({"subtype": "success", "is_error": False, "result": "no schema"}), 0),
    ("not json", 1),
])
def test_failures_raise_llm_error(tmp_path, payload, code):
    with pytest.raises(LLMError):
        ClaudeCodeJSON("m", "high", binary=fake_claude(tmp_path, payload, code), retry_waits=()).generate_json("s", "p", SCHEMA)


def test_missing_binary(tmp_path):
    with pytest.raises(LLMError, match="not found"):
        ClaudeCodeJSON("m", "high", binary=str(tmp_path / "nope"), retry_waits=()).generate_json("s", "p", SCHEMA)


def test_retries_then_succeeds(tmp_path):
    counter = tmp_path / "n"
    script = tmp_path / "claude"
    ok = json.dumps({"subtype": "success", "is_error": False, "structured_output": {"ok": True}})
    script.write_text(f"""#!/usr/bin/env python3
import pathlib, sys
p = pathlib.Path({str(counter)!r}); n = int(p.read_text()) if p.exists() else 0; p.write_text(str(n + 1))
sys.stdin.read()
print({ok!r} if n >= 1 else "overloaded")
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    llm = ClaudeCodeJSON("m", "high", binary=str(script), retry_waits=(0,))
    assert llm.generate_json("s", "p", SCHEMA) == {"ok": True} and counter.read_text() == "2"
