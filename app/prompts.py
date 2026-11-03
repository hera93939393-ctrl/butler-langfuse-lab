"""쓰기 지시문을 Langfuse 프롬프트 관리에서 가져온다(langfuse 5.0.4 의 get_prompt).

    모드 write    → 프롬프트 butler-write   (코드의 기본: pipeline.WRITE_RULES)
    모드 question → 프롬프트 butler-answer  (코드의 기본: pipeline.ANSWER_RULES)

라벨은 ENV 가 production 이면 production, 그 밖(lab, local)에는 staging.
Langfuse 키가 없거나 닿지 못하면 코드에 남겨 둔 지금 문장(fallback)으로 답한다.
SDK 가 가져온 프롬프트를 cache_ttl_seconds 동안 기억해 두므로 요청마다 Langfuse 를 부르지 않는다.
"""
from app import tracing

NAMES = {"write": "butler-write", "question": "butler-answer"}
CACHE_SECONDS = 60


def label_for(env):
    return "production" if env == "production" else "staging"


def fallback_messages(rules, user_template):
    user = user_template.replace("{request}", "{{request}}").replace("{sources}", "{{sources}}")
    return [{"role": "system", "content": rules}, {"role": "user", "content": user}]


def get(mode, label, rules, user_template):
    """Langfuse 프롬프트(ChatPromptClient)를 돌려준다. 키가 없으면 None. 못 가져오면 is_fallback=True 인 것."""
    langfuse = tracing.client()
    if langfuse is None:
        return None
    return langfuse.get_prompt(NAMES[mode], label=label, type="chat", cache_ttl_seconds=CACHE_SECONDS,
                               fallback=fallback_messages(rules, user_template), max_retries=1,
                               fetch_timeout_seconds=3)
