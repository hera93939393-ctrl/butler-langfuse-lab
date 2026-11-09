"""운영 기록에서 뽑은 문제·정상 항목을 지금 코드로 처음부터 끝까지(요청 읽기 → 자료 찾기 → 쓰기 → 수치 확인) 다시 돌려 센다.
(2026-11-09 퀘스트 "로그와 피드백으로 에이전트 개선하기")

    .venv\\Scripts\\python scripts/replay_logs.py --label before --repeat 2
    .venv\\Scripts\\python scripts/replay_logs.py --label after  --repeat 2

- 데이터셋: data/eval/replay_1109.jsonl (problem = 기록에서 실패한 꼴, normal = 기록에서 잘 된 꼴)
- 채점은 코드: must_include 전부, must_any 하나 이상, must_not_include 하나도 없음
- 실제 LLM 을 부른다(gpt-4o-mini, 항목 24 × 반복 수 ≈ 50번, 몇 원). 프롬프트는 배포와 같은 라벨(ENV=lab → staging)
- 트레이스 environment 는 'eval-replay' 라 사용자 기록과 섞이지 않는다
- 결과: data/eval/results/replay_<label>.json (답 원문 포함 — .gitignore, 저장소에 올리지 않음)
- 항목에 "years_labeled": ["2024","2025"] 가 있으면 연도 표시도 본다(years_labeled 함수)
"""
import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_NUM = re.compile(r"\d+(?:\.\d+)?")
_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def _year_numbers():
    """목업 연도 자료의 숫자 → 그 숫자가 나오는 해들. 한 해에만 나오는 숫자로 연도 표시를 가린다."""
    out = collections.defaultdict(set)
    for y in ("2024", "2025"):
        for line in (ROOT / "mock_data" / f"mock_{y}_results.txt").read_text(encoding="utf-8").splitlines()[1:]:
            for n in _NUM.findall(line):
                out[n].add(y)
    return out


def years_labeled(answer, years):
    """두 해 답에서 숫자마다 '어느 해 숫자인지' 보이는가 → 걸린 까닭들(빈 목록이면 통과).
    숫자의 해 = 같은 줄에 적힌 연도, 없으면 바로 위 □ 제목줄의 연도. 한 해 자료에만 있는 숫자가
    다른 해 아래 있거나 연도 없이 있으면 실패(2026-11-09 새 대화 4/4: '□ 2024년 …' 아래 2025 줄이 연도 없이 이어짐)."""
    owner = _year_numbers()
    why, head_year, seen = [], None, set()
    for raw in (answer or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        in_line = [y for y in _YEAR.findall(line) if y in years]
        if line.startswith("□"):
            head_year = in_line[0] if len(in_line) == 1 else None
        here = in_line[0] if len(in_line) == 1 else head_year
        for n in _NUM.findall(_YEAR.sub("", line)):
            ys = owner.get(n, set())
            if len(ys) != 1:
                continue           # 두 해 모두 있거나 자료에 없는 숫자는 판정 안 함
            y = next(iter(ys))
            seen.add(y)
            if len(in_line) >= 2:
                continue           # 한 줄에 두 해를 나란히 적은 꼴("2024년 9곳, 2025년 12곳")은 통과
            if here != y:
                why.append(f"{y}년 숫자 {n}이 {'연도 없이' if here is None else here + '년 아래'} 있음")
    for y in years:
        if y not in seen:
            why.append(f"{y}년 숫자가 답에 없음")
    return why[:5]


def grade(answer, item):
    answer = answer or ""
    why = []
    if item.get("years_labeled"):
        why += years_labeled(answer, item["years_labeled"])
    for w in item.get("must_include", []):
        if w not in answer:
            why.append(f"'{w}' 없음")
    if item.get("must_any") and not any(w in answer for w in item["must_any"]):
        why.append(f"{item['must_any']} 중 하나도 없음")
    for b in item.get("must_not_include", []):
        if b in answer:
            why.append(f"'{b}' 들어감")
    return not why, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--only", help="id 들(쉼표)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    os.environ["ENV"] = "eval-replay"   # 프롬프트 라벨은 production 이 아니면 staging — 배포(ENV=lab)와 같다
    from app import config, llm as llm_mod, pipeline, tracing  # noqa: E402
    settings = config.load_settings()
    model = llm_mod.make_llm(settings)
    items = [json.loads(l) for l in open(ROOT / "data/eval/replay_1109.jsonl", encoding="utf-8") if l.strip()]
    if a.only:
        keep = set(a.only.split(","))
        items = [i for i in items if i["id"] in keep]
    rows = []
    for rep in range(a.repeat):
        for it in items:
            r = pipeline.run(it["request"], it["sources"], f"replay-{a.label}", model, settings)
            ok, why = grade(r["text"], it)
            rows.append({"id": it["id"], "kind": it["kind"], "type": it["type"], "rep": rep, "ok": ok, "why": why,
                         "answer": r["text"], "mode": r["mode"], "retried": r.get("retried"), "trace_id": r.get("trace_id")})
            print(f"{'✓' if ok else '✗'} {it['id']} {it['type']:<8} {'; '.join(why)}", flush=True)
    try:
        tracing.client().flush()
    except Exception as e:  # noqa: BLE001
        print("트레이스 flush 실패:", e)
    out = ROOT / "data/eval/results"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"replay_{a.label}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    by = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        by[(r["kind"], r["type"])][0] += r["ok"]
        by[(r["kind"], r["type"])][1] += 1
    print(f"\n== {a.label} (반복 {a.repeat})")
    for (k, t), (p, n) in sorted(by.items()):
        print(f"{k:<8} {t:<12} {p}/{n} 통과")
    for k in ("problem", "normal"):
        p = sum(r["ok"] for r in rows if r["kind"] == k)
        n = sum(1 for r in rows if r["kind"] == k)
        print(f"{k} 전체 {p}/{n}")


if __name__ == "__main__":
    main()
