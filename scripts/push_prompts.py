"""쓰기 지시문을 Langfuse 프롬프트로 올린다(langfuse 5.0.4 의 create_prompt).

    butler-write   쓰기 요청, 개조식   (코드: app/pipeline.py 의 WRITE_RULES)
    butler-answer  물음, 짧은 답       (코드: ANSWER_RULES)

Chat 형식: System = 규칙 문장, User = 사용자 메시지 틀. 변수 이름은 데이터셋 항목 input 의 키와 같다.
내용이 Langfuse 의 최신 버전과 같으면 새 버전을 만들지 않는다.

    .venv\\Scripts\\python scripts/push_prompts.py
        서비스 코드의 지금 문장(라벨 production, staging)
    .venv\\Scripts\\python scripts/push_prompts.py --file data/prompts/butler-write.v2.txt "메모"
        파일의 규칙을 새 버전으로(라벨 없이, latest 만). User 틀에 [오늘] {{today}} 를 더한다.
        파일 이름의 앞부분(butler-write)이 프롬프트 이름이다.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import pipeline, tracing  # noqa: E402
from app.config import load_settings  # noqa: E402

CODE_USER = pipeline.USER_TEMPLATE.replace("{request}", "{{request}}").replace("{sources}", "{{sources}}")
DATED_USER = "[오늘] {{today}}\n" + CODE_USER

parser = argparse.ArgumentParser()
parser.add_argument("--file", help="새 버전으로 올릴 규칙 파일(data/prompts/<이름>.vN.txt)")
parser.add_argument("message", nargs="?", default="서비스 app/pipeline.py 의 지시문 그대로")
args = parser.parse_args()

if args.file:
    path = Path(args.file)
    plan = {path.name.split(".")[0]: (path.read_text(encoding="utf-8").strip(), DATED_USER, [])}
else:
    plan = {name: (rules, CODE_USER, ["production", "staging"])
            for name, rules in {"butler-write": pipeline.WRITE_RULES, "butler-answer": pipeline.ANSWER_RULES}.items()}

load_settings()
langfuse = tracing.client()
if langfuse is None:
    sys.exit("LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY 가 없습니다.")

for name, (rules, user, labels) in plan.items():
    messages = [{"role": "system", "content": rules}, {"role": "user", "content": user}]
    try:
        current = langfuse.get_prompt(name, label="latest", type="chat", cache_ttl_seconds=0)
        # 받아 온 메시지에는 type 키가 더 붙어 있어서 role, content 만 비교한다
        if [{"role": m["role"], "content": m["content"]} for m in current.prompt] == messages:
            print(f"{name}: 바뀐 것 없음 (버전 {current.version})")
            continue
    except Exception:
        pass  # 아직 없는 프롬프트
    made = langfuse.create_prompt(name=name, type="chat", prompt=messages, labels=labels, commit_message=args.message)
    print(f"{name}: 버전 {made.version} 만듦, 라벨 {made.labels}, 변수 {made.variables}")
