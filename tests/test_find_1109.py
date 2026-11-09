"""2026-11-09 운영 기록 개선: 자료 찾기가 필요한 줄을 못 고르던 두 꼴.
① 두 해 비교인데 한 해 줄로 다 차서 다른 해가 잘림(트레이스 25 신고 "2024·2025 사업성과가 있는데 찾지 못한다고 함")
② 낱말에 어미·조사가 붙어(보고해야, 센터장에게) 자료 낱말과 안 맞아 아무 줄도 못 고름(트레이스 20)
"""
from app import steps

TWO_YEARS = ["mock_2024_results", "mock_2025_results"]
RULES = ["mock_2025_results", "mock_delegation_rules"]


def find(text, names):
    return steps.find_sources(steps.read_request(text), names)


def test_two_year_compare_picks_both_years():
    for text in ("2024년과 2025년 사업성과 비교해줘", "2024년이랑 2025년 성과 정리해서 비교해줘"):
        years = {c["year"] for c in find(text, TWO_YEARS)}
        assert {"2024", "2025"} <= years, (text, years)


def test_two_year_compare_keeps_lines_paired():
    # 같은 항목을 두 해 모두: 2024 정기점검 실적이 있으면 2025 정기점검 실적도
    chunks = find("2024년과 2025년 사업성과 비교해줘", TWO_YEARS)
    lines = {(c["year"], c["line"].split(":")[0]) for c in chunks}
    for year, head in list(lines):
        other = "2025" if year == "2024" else "2024"
        assert (other, head) in lines, (year, head, lines)


def test_word_endings_and_particles_are_stripped():
    assert "보고" in steps.read_request("누구에게 보고해야 하지?")["words"]
    assert "센터장" in steps.read_request("센터장에게 보고하는 건 뭐야?")["words"]
    assert "2024년" in steps.read_request("2024년이랑 2025년 비교")["words"]


def test_report_question_finds_report_rule():
    for text in ("누구에게 보고해야 하지?", "센터장에게 보고하는 건 뭐야?"):
        chunks = find(text, RULES)
        assert any("센터장 보고" in c["line"] for c in chunks), (text, chunks)


def test_single_year_and_question_behaviour_unchanged():
    # 정상 항목(기록에서 잘 되던 꼴) — 고친 뒤에도 그대로
    chunks = find("2025년 점검 실적 찾아서 넣어줘", ["mock_2025_results", "mock_2024_results"])
    assert chunks[0]["year"] == "2025" and len(chunks) <= 5
    assert find("보행로 정비는 몇 곳이야?", ["mock_delegation_rules"]) == []
    assert steps.read_request("외부 강사 수당을 17만을 주게 된다면?")["mode"] == "question"
