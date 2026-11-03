"""Langfuse 데이터셋으로 실험을 돌린다(langfuse 5.0.4 의 run_experiment). 화면의 Run experiment 와 같은 일을 코드로 한다.

항목마다 Langfuse 프롬프트(지정한 버전)에 input 의 request, sources, today 를 넣어 답을 만들고,
코드로 볼 수 있는 항목(grader=code)은 점수 code-check 를 붙인다.
LLM 심사는 Langfuse 규칙(butler-reply-experiments)이 SDK 실험에는 붙지 않아서, 같은 심사 지시문
(docs/judge-prompt.md)과 같은 모델(gpt-4o)로 여기서 판정해 점수 judge-sdk 로 붙인다.

    .venv\\Scripts\\python scripts/experiment.py <데이터셋> <프롬프트> <버전> <실험 이름>
    예) scripts/experiment.py butler-write-reply butler-write 1 write-v1-2
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langfuse.experiment import Evaluation  # noqa: E402

from app import evals, tracing  # noqa: E402
from app.config import ROOT, load_settings  # noqa: E402
from app.llm import OpenAILLM, make_llm  # noqa: E402

TEMPERATURE = 0.2  # 서비스(app/llm.py)와 같은 값
JUDGE_MODEL = "gpt-4o"  # Langfuse 심사 butler-reply-judge 와 같은 모델

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


def judge_blocks():
    """docs/judge-prompt.md 의 ## System, ## User 아래 코드 블록."""
    text = (ROOT / "docs" / "judge-prompt.md").read_text(encoding="utf-8")
    blocks = re.findall(r"## (System|User)\s*```\n(.*?)```", text, re.S)
    return dict(blocks)["System"], dict(blocks)["User"]


JUDGE_SYSTEM, JUDGE_USER = judge_blocks()
JUDGE_SYSTEM += '\n\n답은 JSON 한 줄로만 쓴다: {"reasoning": "판단 이유 한두 문장(한국어)", "pass": true 또는 false}'
judge_llm = OpenAILLM(settings.api_key, JUDGE_MODEL)


def task(*, item, **kwargs):
    messages = prompt.compile(request=item.input["request"], sources=item.input["sources"],
                              today=item.input.get("today", ""))
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


def judge(*, input, output, expected_output, **kwargs):
    user = (JUDGE_USER.replace("{{input}}", json.dumps(input, ensure_ascii=False))
            .replace("{{output}}", output or "").replace("{{ground_truth}}", json.dumps(expected_output, ensure_ascii=False)))
    raw = judge_llm.complete(JUDGE_SYSTEM, user)
    try:
        verdict = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        return Evaluation(name="judge-sdk", value=bool(verdict["pass"]), data_type="BOOLEAN",
                          comment=str(verdict.get("reasoning", "")))
    except (ValueError, KeyError):
        return Evaluation(name="judge-sdk-error", value=raw[:200], data_type="CATEGORICAL")


result = langfuse.run_experiment(name=run_name, run_name=run_name, data=langfuse.get_dataset(dataset_name).items,
                                 task=task, evaluators=[code_check, judge], max_concurrency=4,
                                 metadata={"prompt": f"{prompt_name} v{version}", "model": llm.model})
langfuse.flush()
for name in ("code-check", "judge-sdk"):
    got = [e for r in result.item_results for e in r.evaluations if e.name == name]
    print(f"{run_name}: {name} 통과 {sum(bool(e.value) for e in got)}/{len(got)}")
