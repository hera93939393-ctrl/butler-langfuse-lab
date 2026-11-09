"""4차: 조건 물음(숫자가 든 물음)이면 기준 줄(이내·이하·초과·최대…)을 먼저 — 동점 줄에 밀려 5줄 밖으로 잘리던 것.
배포 뒤 새 대화 "안전교실에 22명 받아도 되나요?"가 v0·v1·v3 모두 "찾지 못했습니다"."""
from app import steps

ALL = ["mock_2024_results", "mock_2025_results", "mock_delegation_rules"]


def lines(text):
    return [c["line"] for c in steps.find_sources(steps.read_request(text), ALL)]


def test_limit_line_kept_for_numeric_question():
    for text in ("안전교실에 22명 받아도 되나요?", "안전교실 한 번에 30명 받아도 돼?", "안전교실 18명이면 받을 수 있어?"):
        assert any("최대 20명" in l for l in lines(text)), (text, lines(text))


def test_no_boost_without_number_or_in_write_mode():
    # 숫자 없는 물음·쓰기 요청은 그대로 — 묻지 않은 기준 줄을 끌어오지 않는다
    assert not any("최대 20명" in l for l in lines("안전교실 참여 인원 정리해줘"))
