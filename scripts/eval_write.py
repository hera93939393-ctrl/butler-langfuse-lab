"""글쓰기 평가: data/eval/write.jsonl 의 고정한 자료로 답만 만들게 해 채점한다. 실제 LLM 을 항목 수만큼 부른다.

코드로 볼 수 있는 항목(grader=code)은 맞힌 수를 세고, LLM 심사 항목(grader=judge)은 답을 보여 주기만 한다.
실행마다 답이 달라지므로 두 번 돌려 비교한다.

    .venv\\Scripts\\python scripts/eval_write.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import evals, pipeline  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.llm import make_llm  # noqa: E402

settings = load_settings()
llm = make_llm(settings)
items = evals.load("write.jsonl")
coded, judged = [], []
for item in items:
    rules, user = pipeline.compose(item["input"]["request"], item["input"]["chunks"], item["input"]["mode"])
    answer = llm.complete(rules, user)
    if item["grader"] == "code":
        coded.append((item, *evals.grade_write(answer, item), answer))
    else:
        judged.append((item, answer))

print(f"모델 {llm.model} · 코드 채점 맞힘 {sum(ok for _, ok, _, _ in coded)}/{len(coded)}")
for item, ok, reasons, answer in coded:
    if not ok:
        print(f"  ✗ {item['id']} [{item['kind']}·{item['category']}] {'; '.join(reasons)}")
        print(f"      답: {answer.replace(chr(10), ' / ')[:160]}")
print(f"LLM 심사 대상 {len(judged)}개 (섹션 3 뒷부분에서 Langfuse 심사로 판정)")
for item, answer in judged:
    print(f"  ? {item['id']} [{item['category']}] {answer.replace(chr(10), ' / ')[:160]}")
