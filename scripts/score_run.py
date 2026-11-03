"""Langfuse 화면(Run experiment)에서 돌린 실험의 답을 코드로 채점해 점수 code-check 를 붙인다.

SDK 로 돌린 실험(scripts/experiment.py)은 실행할 때 code-check 를 붙이므로 이 스크립트가 필요 없다.
grader=code 인 항목만 채점한다(숫자, 한글 숫자, 포함 문구). grader=judge 항목은 LLM 심사에 맡긴다.
화면 실험의 이름에는 시각이 붙으므로("write-v1-1 - 2026-11-03T…") 앞부분이 같으면 같은 실험으로 본다.

    .venv\\Scripts\\python scripts/score_run.py write-v1-1 [다른 실험 이름 ...]
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import evals, tracing  # noqa: E402
from app.config import load_settings  # noqa: E402

load_settings()
langfuse = tracing.client()
if langfuse is None or len(sys.argv) < 2:
    sys.exit("사용법: score_run.py <실험 이름> ...  (Langfuse 키 필요)")
items = {i["id"]: i for i in evals.load("write.jsonl")}
since = datetime.now(timezone.utc) - timedelta(days=7)
experiments = langfuse.api.experiments.list(from_start_time=since, limit=100).data

for name in sys.argv[1:]:
    matched = [e for e in experiments if e.name == name or e.name.startswith(f"{name} - ")]
    passed = graded = 0
    for experiment in matched:
        rows = langfuse.api.experiments.list_items(from_start_time=since, experiment_id=experiment.id,
                                                   fields="core,io", limit=100).data
        for row in rows:
            item = items.get(row.experiment_item_id.rsplit("-", 1)[-1])
            if not item or item.get("grader") != "code":
                continue
            ok, reasons = evals.grade_write(row.output or "", item)
            langfuse.create_score(trace_id=row.trace_id, name="code-check", value=1 if ok else 0, data_type="BOOLEAN",
                                  comment="; ".join(reasons) or "통과", environment=row.environment)
            graded += 1
            passed += ok
    print(f"{name}: 실험 {len(matched)}개, code-check 통과 {passed}/{graded}")
langfuse.flush()
