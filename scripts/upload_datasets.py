"""data/eval/ 의 데이터셋을 Langfuse 에 올린다(langfuse 5.0.4 의 create_dataset, create_dataset_item).

    find_sources.jsonl          → butler-find          (input: 요청·고른 자료, expected_output: 기대 결과)
    write.jsonl 중 mode=write   → butler-write-reply   (프롬프트 butler-write 로 실험)
    write.jsonl 중 mode=question→ butler-answer-reply  (프롬프트 butler-answer 로 실험)

Langfuse 화면의 실험은 프롬프트 하나에 데이터셋 하나를 걸어서, 지시문이 다른 두 모드를 데이터셋으로 나눴다.
글쓰기 항목 input 에는 프롬프트 변수와 같은 이름의 request, sources(서비스와 같은 모양의 자료 줄)를 넣는다.
항목 id 는 "<데이터셋>-<항목 id>" 로 정해 두어서, 다시 실행하면 새로 만들지 않고 그 항목을 고친다(upsert).
키는 .env 에서 읽고 출력하지 않는다. 끝나면 데이터셋별 항목 수만 출력한다.

    .venv\\Scripts\\python scripts/upload_datasets.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import evals, pipeline, tracing  # noqa: E402
from app.config import load_settings  # noqa: E402

DESCRIPTIONS = {
    "butler-find": "자료 찾기(read-request, find-sources) 평가. 코드 채점, 모델 호출 없음",
    "butler-write-reply": "쓰기 요청: 자료를 고정하고 프롬프트 butler-write 로 답만 만든다. 코드 채점 + LLM 심사",
    "butler-answer-reply": "물음: 자료를 고정하고 프롬프트 butler-answer 로 답만 만든다. 코드 채점 + LLM 심사",
}
TODAY = "2026-11-03(화)"  # 프롬프트 변수 {{today}}. 작년·올해 판정 기준일(데이터셋 metadata today 와 같음)
OLD = "butler-write"  # 두 모드를 한데 담았던 첫 데이터셋. 항목은 보관(ARCHIVED)으로 돌린다


def rows():
    for item in evals.load("find_sources.jsonl"):
        yield "butler-find", item, item["input"], {"criterion": item["criterion"], **item["expected"]}
    for item in evals.load("write.jsonl"):
        name = "butler-answer-reply" if item["input"]["mode"] == "question" else "butler-write-reply"
        inp = {"request": item["input"]["request"], "sources": pipeline.list_sources(item["input"]["chunks"]),
               "today": TODAY, **item["input"]}
        yield name, item, inp, item["expected"]


load_settings()
langfuse = tracing.client()
if langfuse is None:
    sys.exit("LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY 가 없습니다.")

for name, description in DESCRIPTIONS.items():
    langfuse.create_dataset(name=name, description=description, metadata={"today": "2026-11-03"})
for name, item, inp, expected in rows():
    langfuse.create_dataset_item(
        dataset_name=name, id=f"{name}-{item['id']}", input=inp, expected_output=expected,
        metadata={"id": item["id"], "category": item["category"], "kind": item["kind"], "grader": item.get("grader", "code")})
for old in langfuse.get_dataset(OLD).items if OLD else []:
    if old.status != "ARCHIVED":
        langfuse.create_dataset_item(dataset_name=OLD, id=old.id, input=old.input, expected_output=old.expected_output,
                                     metadata=old.metadata, status="ARCHIVED")
langfuse.flush()

for name in DESCRIPTIONS:
    print(f"{name}: {len(langfuse.get_dataset(name).items)}개")
