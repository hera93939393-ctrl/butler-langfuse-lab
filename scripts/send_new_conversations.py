"""배포 뒤 확인용 새 대화 보내기(2026-11-09). 데이터셋(replay_1109.jsonl)에 없는 말을 여러 사용자 유형으로 만들어
배포된 서비스(태그 주소)에 그대로 보낸다. 같은 대화를 버전마다 보내고, 트레이스를 version 으로 나눠 비교한다(compare_versions.py).

    .venv\\Scripts\\python scripts/send_new_conversations.py https://v0-before---butler-lab-....run.app v0

- 팀 비밀번호는 .env 의 TEAM_PASSWORD 를 읽어 머리글로만 보낸다(화면·파일에 남기지 않음)
- 별명: new-<버전>-<사용자유형> — 트레이스 user 로 남는다
- 실제 개인정보는 쓰지 않는다. 자료는 목업뿐
- 답 원문은 저장하지 않는다(대화 내용 파일을 남기지 않음). 판정은 compare_versions.py 가 트레이스에서 한다
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALL = ["mock_2024_results", "mock_2025_results", "mock_delegation_rules"]
TWO = ["mock_2024_results", "mock_2025_results"]

# (사용자 유형, 요청, 고른 자료, 현상 분류) — 분류: find(①) / years(③) / rule(②) / normal
# 통과 조건은 EXPECT(요청 → 조건). 판정은 compare_versions.py 가 트레이스의 답으로 한다
CONVERSATIONS = [
    ("꼼꼼한담당자", "2024년하고 2025년 성과를 항목별로 견줘서 정리해줘", TWO, "find"),
    ("꼼꼼한담당자", "올해 2025년이랑 작년 2024년 비상벨이랑 보행로 실적 같이 정리해줘", ALL, "years"),
    ("꼼꼼한담당자", "점검하고 나서 보고는 며칠 안에 누구한테 해야 되는지 알려줘", ALL, "find"),
    ("꼼꼼한담당자", "강사비를 한 시간에 16만원 드리면 규정 위반이야?", ALL, "rule"),
    ("급한팀장", "24년 25년 점검 실적 비교 빨리", TWO, "years"),
    ("급한팀장", "예산 천만원짜리 집행하면 결재 누구", ALL, "rule"),
    ("급한팀장", "중대한 지적 나오면 어떻게 해야 돼", ALL, "find"),
    ("급한팀장", "2025 만족도 몇 점", ALL, "normal"),
    ("신입직원", "정기점검 결과는 어디에 보고해야 하나요?", ALL, "find"),
    ("신입직원", "2024년도와 2025년도 안전교실 운영 횟수를 비교해 주세요", TWO, "years"),
    ("신입직원", "안전교실에 22명 받아도 되나요?", ALL, "rule"),
    ("신입직원", "2025년 불시점검은 몇 번 했나요?", ALL, "normal"),
    ("보고서작성자", "2024·2025 사업성과를 보고서에 넣게 정리해줘", TWO, "years"),
    ("보고서작성자", "두 해 예산 집행률 비교해서 넣어줘 2024 2025", TWO, "years"),
    ("보고서작성자", "센터장한테 올리는 보고 기한 정리해줘", ALL, "find"),
    ("보고서작성자", "2025년 주민참여 안전교실 실적 넣어줘", ALL, "normal"),
    ("엉뚱한질문", "예산이 3천만원 딱이면 시장 결재야?", ALL, "rule"),
    ("엉뚱한질문", "2022년 점검 실적 알려줘", ALL, "normal"),
    ("엉뚱한질문", "보행로는 해마다 몇 곳씩 고쳤어?", TWO, "years"),
    ("엉뚱한질문", "팀장 전결은 얼마까지야?", ALL, "normal"),
]

EXPECT = {
    "2024년하고 2025년 성과를 항목별로 견줘서 정리해줘": {"must_include": ["38", "42"], "must_not_include": ["찾지 못"]},
    "올해 2025년이랑 작년 2024년 비상벨이랑 보행로 실적 같이 정리해줘": {"must_include": ["22", "30"], "must_not_include": ["찾지 못"], "years_labeled": ["2024", "2025"]},
    "점검하고 나서 보고는 며칠 안에 누구한테 해야 되는지 알려줘": {"must_include": ["7일", "센터장"], "must_not_include": ["찾지 못"]},
    "강사비를 한 시간에 16만원 드리면 규정 위반이야?": {"must_any": ["초과", "넘", "위반", "안 됩", "불가"], "must_not_include": ["찾지 못"]},
    "24년 25년 점검 실적 비교 빨리": {"must_include": ["38", "42"], "must_not_include": ["찾지 못"], "years_labeled": ["2024", "2025"]},
    "예산 천만원짜리 집행하면 결재 누구": {"must_any": ["센터장"], "must_not_include": ["찾지 못"]},
    "중대한 지적 나오면 어떻게 해야 돼": {"must_include": ["즉시"], "must_not_include": ["찾지 못"]},
    "2025 만족도 몇 점": {"must_include": ["4.6"], "must_not_include": ["찾지 못"]},
    "정기점검 결과는 어디에 보고해야 하나요?": {"must_include": ["센터장"], "must_not_include": ["찾지 못"]},
    "2024년도와 2025년도 안전교실 운영 횟수를 비교해 주세요": {"must_include": ["7", "8"], "must_not_include": ["찾지 못"], "years_labeled": ["2024", "2025"]},
    "안전교실에 22명 받아도 되나요?": {"must_any": ["초과", "넘", "안 됩", "불가", "20명"], "must_not_include": ["찾지 못"]},
    "2025년 불시점검은 몇 번 했나요?": {"must_include": ["6"], "must_not_include": ["찾지 못"]},
    "2024·2025 사업성과를 보고서에 넣게 정리해줘": {"must_include": ["38", "42"], "must_not_include": ["찾지 못"], "years_labeled": ["2024", "2025"]},
    "두 해 예산 집행률 비교해서 넣어줘 2024 2025": {"must_include": ["88", "91"], "must_not_include": ["찾지 못"], "years_labeled": ["2024", "2025"]},
    "센터장한테 올리는 보고 기한 정리해줘": {"must_include": ["7일"], "must_not_include": ["찾지 못"]},
    "2025년 주민참여 안전교실 실적 넣어줘": {"must_include": ["100"], "must_not_include": ["찾지 못"]},
    "예산이 3천만원 딱이면 시장 결재야?": {"must_any": ["센터장"], "must_not_include": ["찾지 못"]},
    "2022년 점검 실적 알려줘": {"must_include": ["찾지 못"]},
    "보행로는 해마다 몇 곳씩 고쳤어?": {"must_include": ["9", "12"], "must_not_include": ["21", "찾지 못"], "years_labeled": ["2024", "2025"]},
    "팀장 전결은 얼마까지야?": {"must_include": ["5백만"], "must_not_include": ["찾지 못"]},
}
assert set(EXPECT) == {c[1] for c in CONVERSATIONS}


def team_password():
    pw = os.environ.get("TEAM_PASSWORD", "").strip()
    if not pw and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("TEAM_PASSWORD="):
                pw = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not pw:
        sys.exit("TEAM_PASSWORD 가 없어요(.env)")
    return pw


def send(base, version, pw, who, text, sources, prefix="new"):
    req = urllib.request.Request(
        base.rstrip("/") + "/api/write", method="POST",
        data=json.dumps({"request": text, "sources": sources}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Team-Password": urllib.parse.quote(pw),
                 "X-Nickname": urllib.parse.quote(f"{prefix}-{version}-{who}")})
    t = time.monotonic()
    with urllib.request.urlopen(req, timeout=90) as r:
        r.read()
        return r.status, time.monotonic() - t


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    base, version = sys.argv[1], sys.argv[2]
    gap = float(sys.argv[3]) if len(sys.argv) == 4 else 1.0   # 2026-11-09: 1초 간격이면 트레이스가 약 11초에 하나만 남아 12초로
    pw = team_password()
    ok = 0
    for who, text, sources, kind in CONVERSATIONS:
        try:
            status, sec = send(base, version, pw, who, text, sources, "new" if gap <= 1 else "slow")
            ok += status == 200
            print(f"{status} {sec:4.1f}s [{kind}] {who}: {text}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"실패 [{kind}] {who}: {text} — {type(e).__name__}: {str(e)[:80]}", flush=True)
        time.sleep(gap)
    print(f"끝: {ok}/{len(CONVERSATIONS)}")


if __name__ == "__main__":
    main()
