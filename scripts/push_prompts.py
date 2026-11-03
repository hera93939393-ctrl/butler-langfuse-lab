"""서비스의 쓰기 지시문(app/pipeline.py)을 Langfuse 프롬프트로 올린다(langfuse 5.0.4 의 create_prompt).

    butler-write   WRITE_RULES  (쓰기 요청, 개조식)
    butler-answer  ANSWER_RULES (물음, 짧은 답)

Chat 형식: System = 규칙 문장 그대로, User = "[요청]\\n{{request}}\\n\\n[자료]\\n{{sources}}".
변수 이름은 데이터셋 항목 input 의 키와 같다. 내용이 Langfuse 의 최신 버전과 같으면 새 버전을 만들지 않는다.

    .venv\\Scripts\\python scripts/push_prompts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import pipeline, tracing  # noqa: E402
from app.config import load_settings  # noqa: E402

PROMPTS = {"butler-write": pipeline.WRITE_RULES, "butler-answer": pipeline.ANSWER_RULES}
USER = pipeline.USER_TEMPLATE.replace("{request}", "{{request}}").replace("{sources}", "{{sources}}")

load_settings()
langfuse = tracing.client()
if langfuse is None:
    sys.exit("LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY 가 없습니다.")

for name, rules in PROMPTS.items():
    messages = [{"role": "system", "content": rules}, {"role": "user", "content": USER}]
    try:
        current = langfuse.get_prompt(name, type="chat", cache_ttl_seconds=0)
        # 받아 온 메시지에는 type 키가 더 붙어 있어서 role, content 만 비교한다
        if [{"role": m["role"], "content": m["content"]} for m in current.prompt] == messages:
            print(f"{name}: 바뀐 것 없음 (버전 {current.version})")
            continue
    except Exception:
        pass  # 아직 없는 프롬프트
    made = langfuse.create_prompt(name=name, type="chat", prompt=messages, labels=["production"],
                                  commit_message="서비스 app/pipeline.py 의 지시문 그대로")
    print(f"{name}: 버전 {made.version} 만듦, 변수 {made.variables}")
