"""글쓰기 평가: data/eval/write.jsonl 의 고정한 자료로 답만 만들게 해 채점한다. 실제 LLM 을 항목 수만큼 부른다.

코드로 볼 수 있는 항목(grader=code)은 맞힌 수를 세고, LLM 심사 항목(grader=judge)은 답을 보여 주기만 한다.
실행마다 답이 달라질 수 있으므로 두 번 돌려 비교한다.

    .venv\\Scripts\\python scripts/eval_write.py                  (코드의 지금 문장)
    .venv\\Scripts\\python scripts/eval_write.py --label staging  (Langfuse 프롬프트의 그 라벨 버전)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import evals, pipeline, prompts  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.llm import make_llm  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--label", help="Langfuse 프롬프트 라벨(production, staging, latest). 없으면 코드의 문장")
parser.add_argument("--today", default="2026-11-03(화)", help="{{today}} 에 넣을 날짜. 데이터셋 기준일과 같아야 한다")
args = parser.parse_args()

settings = load_settings()
llm = make_llm(settings)
items = evals.load("write.jsonl")
coded, judged, versions = [], [], {}
for item in items:
    mode = item["input"]["mode"]
    prompt = None
    if args.label:
        rules = pipeline.ANSWER_RULES if mode == "question" else pipeline.WRITE_RULES
        prompt = prompts.get(mode, args.label, rules, pipeline.USER_TEMPLATE)
        if prompt is None or prompt.is_fallback:
            sys.exit(f"Langfuse 에서 {prompts.NAMES[mode]}({args.label}) 를 가져오지 못했습니다.")
        versions[prompt.name] = prompt.version
    rules, user = pipeline.compose(item["input"]["request"], item["input"]["chunks"], mode, prompt, args.today)
    answer = llm.complete(rules, user)
    if item["grader"] == "code":
        coded.append((item, *evals.grade_write(answer, item), answer))
    else:
        judged.append((item, answer))

where = ", ".join(f"{n} v{v}" for n, v in versions.items()) or "코드의 지금 문장"
print(f"모델 {llm.model} · 지시문 {where} · 코드 채점 맞힘 {sum(ok for _, ok, _, _ in coded)}/{len(coded)}")
for item, ok, reasons, answer in coded:
    if not ok:
        print(f"  ✗ {item['id']} [{item['kind']}·{item['category']}] {'; '.join(reasons)}")
        print(f"      답: {answer.replace(chr(10), ' / ')[:160]}")
print(f"LLM 심사 대상 {len(judged)}개 (Langfuse 실험의 butler-reply-judge 로 판정)")
for item, answer in judged:
    print(f"  ? {item['id']} [{item['category']}] {answer.replace(chr(10), ' / ')[:160]}")
