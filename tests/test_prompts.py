from app import pipeline, prompts


class FakePrompt:
    """Langfuse ChatPromptClient 의 compile 만 흉내 낸다."""
    is_fallback = False

    def __init__(self, system):
        self.system = system

    def compile(self, **values):
        user = "[오늘] {today}\n[요청]\n{request}\n\n[자료]\n{sources}".format(**values)
        return [{"role": "system", "content": self.system}, {"role": "user", "content": user}]


CHUNKS = [{"source": "mock_2025_results", "year": "2025", "header": "정기점검", "line": "◦ 정기점검 실적 : 총 42개소"}]


def test_label_follows_env():
    assert prompts.label_for("production") == "production"
    assert prompts.label_for("lab") == "staging"
    assert prompts.label_for("local") == "staging"


def test_without_langfuse_keys_service_uses_code_rules():
    assert prompts.get("write", "staging", pipeline.WRITE_RULES, pipeline.USER_TEMPLATE) is None
    rules, user = pipeline.compose("2025 점검 실적", CHUNKS, "write")
    assert rules == pipeline.WRITE_RULES and "총 42개소" in user


def test_compose_fills_prompt_variables():
    rules, user = pipeline.compose("2025 점검 실적", CHUNKS, "write", FakePrompt("규칙 v2"), "2026-11-03(화)")
    assert rules == "규칙 v2"
    assert user.startswith("[오늘] 2026-11-03(화)") and "총 42개소" in user


def test_fallback_matches_code_rules():
    messages = prompts.fallback_messages(pipeline.ANSWER_RULES, pipeline.USER_TEMPLATE)
    assert messages[0]["content"] == pipeline.ANSWER_RULES
    assert "{{request}}" in messages[1]["content"] and "{{sources}}" in messages[1]["content"]
