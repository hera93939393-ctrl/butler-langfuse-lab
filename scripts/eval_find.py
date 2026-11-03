"""자료 찾기 평가: data/eval/find_sources.jsonl 을 지금 코드로 돌려 맞힌 수를 센다. 모델을 부르지 않는다.

    .venv\\Scripts\\python scripts/eval_find.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import evals, steps  # noqa: E402

items = evals.load("find_sources.jsonl")
results = []
for item in items:
    req = steps.read_request(item["input"]["request"])
    chunks = steps.find_sources(req, item["input"]["sources"])
    ok, reasons = evals.grade_find(req, chunks, item["expected"])
    results.append((item, ok, reasons))

print(f"맞힘 {sum(ok for _, ok, _ in results)}/{len(results)}")
for item, ok, reasons in results:
    if not ok:
        print(f"  ✗ {item['id']} [{item['kind']}·{item['category']}] {item['input']['request']} — {'; '.join(reasons)}")
