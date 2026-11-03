"""Langfuse 데이터셋으로 실험을 돌린다(langfuse 5.0.4 의 run_experiment). 화면의 Run experiment 와 같은 일을 코드로 한다.

항목마다 Langfuse 프롬프트(지정한 버전)에 input 의 request, sources 를 넣어 답을 만들고,
코드로 볼 수 있는 항목(grader=code)은 점수 code-check 를 붙인다.
LLM 심사 butler-reply-judge 는 Langfuse 의 규칙(butler-reply-experiments)이 실험 항목마다 따로 붙인다.

    .venv\\Scripts\\python scripts/experiment.py <데이터셋> <프롬프트> <버전> <실험 이름>
    예) scripts/experiment.py butler-write-reply butler-write 1 write-v1-2
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langfuse.experiment import Evaluation  # noqa: E402

from app import evals, tracing  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.llm import make_llm  # noqa: E402

TEMPERATURE = 0.2  # 서비스(app/llm.py)와 같은 값

if len(sys.argv) != 5:
    sys.exit(__doc__)
dataset_name, prompt_name, version, run_name = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]

settings = load_settings()
llm = make_llm(settings)
langfuse = tracing.client()
if langfuse is None:
    sys.exit("LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY 가 없습니다.")
prompt = langfuse.get_prompt(prompt_name, version=version, type="chat", cache_ttl_seconds=0)
items = {i["id"]: i for i in evals.load("write.jsonl")}


def task(*, item, **kwargs):
    messages = prompt.compile(request=item.input["request"], sources=item.input["sources"])
    system = next(m["content"] for m in messages if m["role"] == "system")
    user = next(m["content"] for m in messages if m["role"] == "user")
    step = langfuse.start_observation(name="write", as_type="generation", model=llm.model, prompt=prompt,
                                      model_parameters={"temperature": TEMPERATURE}, input=messages)
    usage, text = {}, None
    try:
        text = llm.complete(system, user, usage=usage)
    finally:
        step.update(output=text, usage_details=tracing.usage_details(usage)).end()
    return text


def code_check(*, input, output, expected_output, metadata, **kwargs):
    item = items.get((metadata or {}).get("id"))
    if not item or item.get("grader") != "code":
        return []
    ok, reasons = evals.grade_write(output or "", item)
    return Evaluation(name="code-check", value=ok, data_type="BOOLEAN", comment="; ".join(reasons) or "통과")


result = langfuse.run_experiment(name=run_name, run_name=run_name, data=langfuse.get_dataset(dataset_name).items,
                                 task=task, evaluators=[code_check], max_concurrency=4,
                                 metadata={"prompt": f"{prompt_name} v{version}", "model": llm.model})
langfuse.flush()
checked = [e for r in result.item_results for e in r.evaluations if e.name == "code-check"]
print(f"{run_name}: 항목 {len(result.item_results)}개, code-check 통과 {sum(bool(e.value) for e in checked)}/{len(checked)}")
