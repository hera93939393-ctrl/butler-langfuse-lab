"""새 대화 트레이스를 version(Cloud Run 리비전)으로 나눠 같은 현상 횟수·지연 시간·비용을 비교한다(2026-11-09).

    .venv\\Scripts\\python scripts/compare_versions.py            # 화면에 표
    .venv\\Scripts\\python scripts/compare_versions.py --md docs/version-compare.md

- Langfuse 공개 API v2 observations(트레이스 단위로 묶음)에서 user 가 'new-' 로 시작하는 write-turn 만
- 판정은 send_new_conversations.EXPECT 의 조건으로 코드 채점(replay_logs.grade) — 답 원문은 파일에 남기지 않는다
- 지연: write-turn latency(초), 비용: 그 트레이스의 모든 관찰 totalCost 합(USD)
"""
import argparse
import collections
import json
import os
import statistics
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import replay_logs  # noqa: E402
import send_new_conversations as conv  # noqa: E402

KIND_NAME = {"find": "① 자료 못 고름", "years": "③ 연도 표시", "rule": "② 기준 미적용", "normal": "정상"}


def env():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return os.environ["LANGFUSE_BASE_URL"].rstrip("/"), (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])


def fetch(since):
    base, auth = env()
    rows, cur = [], None
    for _ in range(200):
        p = {"limit": 1000, "fields": "core,basic,io,metadata,usage", "fromStartTime": since}
        if cur:
            p["cursor"] = cur
        r = httpx.get(base + "/api/public/v2/observations", params=p, auth=auth, timeout=60)
        r.raise_for_status()
        j = r.json()
        rows += j.get("data", [])
        cur = (j.get("meta") or {}).get("cursor")
        if not cur:
            break
    return rows


def text_of(x):
    if isinstance(x, dict):
        return x.get("request") or x.get("text") or json.dumps(x, ensure_ascii=False)
    if isinstance(x, str):
        try:
            return text_of(json.loads(x))
        except ValueError:
            return x
    return str(x or "")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-11-09T00:00:00Z")
    ap.add_argument("--md")
    ap.add_argument("--prefix", default="slow-", help="새 대화 별명 앞부분(slow- = 12초 간격으로 보낸 판)")
    a = ap.parse_args()
    obs = fetch(a.since)
    by_trace = collections.defaultdict(list)
    for o in obs:
        by_trace[o["traceId"]].append(o)
    kind_of = {c[1]: c[3] for c in conv.CONVERSATIONS}
    stats = collections.defaultdict(lambda: {"n": 0, "lat": [], "cost": [], "kinds": collections.defaultdict(lambda: [0, 0]),
                                             "fails": []})
    for t, os_ in by_trace.items():
        turn = next((o for o in os_ if o["name"] == "write-turn"), None)
        if not turn or not str(turn.get("userId") or "").startswith(a.prefix):
            continue
        req = text_of(turn.get("input"))
        if req not in kind_of:
            continue
        ver = turn.get("version") or "?"
        s = stats[ver]
        ok, why = replay_logs.grade(text_of(turn.get("output")), conv.EXPECT[req])
        k = kind_of[req]
        s["n"] += 1
        s["kinds"][k][0] += ok
        s["kinds"][k][1] += 1
        if not ok:
            s["fails"].append(f"[{KIND_NAME[k]}] {req} — {'; '.join(why)}")
        if turn.get("latency") is not None:
            s["lat"].append(float(turn["latency"]))
        s["cost"].append(sum(float(o.get("totalCost") or 0) for o in os_))
    lines = ["| 버전(리비전) | 새 대화 | " + " | ".join(f"{v} 실패" for v in KIND_NAME.values()) + " | 지연 중앙값(초) | 지연 최대(초) | 비용 합(USD) |",
             "|---|---|" + "---|" * len(KIND_NAME) + "---|---|---|"]
    for ver in sorted(stats):
        s = stats[ver]
        cells = []
        for k in KIND_NAME:
            p, n = s["kinds"][k]
            cells.append(f"{n - p}/{n}" if n else "-")
        lat = s["lat"]
        lines.append(f"| {ver} | {s['n']} | " + " | ".join(cells) +
                     f" | {statistics.median(lat):.2f} | {max(lat):.2f} | {sum(s['cost']):.5f} |" if lat else " | - | - | - |")
    out = "\n".join(lines)
    detail = []
    for ver in sorted(stats):
        detail.append(f"\n### {ver} 실패 목록")
        detail += [f"- {f}" for f in stats[ver]["fails"]] or ["- 없음"]
    print(out + "\n" + "\n".join(detail))
    if a.md:
        Path(a.md).write_text("# 새 대화 버전별 비교\n\n" + out + "\n" + "\n".join(detail) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
