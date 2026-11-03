"""data/eval/ 의 데이터셋을 Langfuse 에 올린다(langfuse 5.0.4 의 create_dataset, create_dataset_item).

    find_sources.jsonl → butler-find   (input: 요청·고른 자료,   expected_output: 기대 결과)
    write.jsonl        → butler-write  (input: 요청·모드·고정한 자료 줄, expected_output: 통과 조건)

항목 id 는 "<데이터셋>-<항목 id>" 로 정해 두어서, 다시 실행하면 새로 만들지 않고 그 항목을 고친다(upsert).
키는 .env 에서 읽고 출력하지 않는다. 끝나면 데이터셋별 항목 수만 출력한다.

    .venv\\Scripts\\python scripts/upload_datasets.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import evals, tracing  # noqa: E402
from app.config import load_settings  # noqa: E402

DATASETS = {
    "butler-find": ("find_sources.jsonl", "자료 찾기(read-request, find-sources) 평가. 코드 채점, 모델 호출 없음"),
    "butler-write": ("write.jsonl", "고정한 자료로 글쓰기(write)만 평가. 코드 채점 + LLM 심사"),
}

load_settings()
langfuse = tracing.client()
if langfuse is None:
    sys.exit("LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY 가 없습니다.")

for name, (file, description) in DATASETS.items():
    langfuse.create_dataset(name=name, description=description, metadata={"today": "2026-11-03"})
    for item in evals.load(file):
        expected = item["expected"] if "criterion" in item["expected"] else {"criterion": item.get("criterion"), **item["expected"]}
        langfuse.create_dataset_item(
            dataset_name=name, id=f"{name}-{item['id']}", input=item["input"], expected_output=expected,
            metadata={"id": item["id"], "category": item["category"], "kind": item["kind"], "grader": item.get("grader", "code")})
langfuse.flush()

for name in DATASETS:
    print(f"{name}: {len(langfuse.get_dataset(name).items)}개")
