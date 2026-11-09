"""replay 채점기(코드, 모델 호출 없음) — 특히 ③ 두 해 답의 연도 표시."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("replay_logs", Path(__file__).resolve().parents[1] / "scripts" / "replay_logs.py")
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
Y = ["2024", "2025"]


def test_years_split_by_heading_passes():
    ok = "□ 2024년 보행로 정비\n ◦ 총 9곳 완료\n□ 2025년 보행로 정비\n ◦ 총 12곳 완료"
    assert replay.years_labeled(ok, Y) == []


def test_both_years_on_one_line_passes():
    assert replay.years_labeled("□ 보행로 정비 비교\n ◦ 2024년 : 총 9곳 완료\n ◦ 2025년 : 총 12곳 완료", Y) == []
    assert replay.years_labeled("2024년 9곳, 2025년 12곳입니다.", Y) == []


def test_unlabelled_second_year_fails():
    # 2026-11-09 새 대화(트레이스 108) 그대로: 2024 제목 아래 2025 숫자가 연도 없이
    bad = "□ 2024년 보행로 정비\n ◦ 총 9곳 완료\n ◦ 총 12곳 완료"
    why = replay.years_labeled(bad, Y)
    assert why and "12" in why[0], why


def test_missing_year_fails():
    assert replay.years_labeled("□ 2024년 보행로 정비\n ◦ 총 9곳 완료", Y) == ["2025년 숫자가 답에 없음"]


def test_grade_combines_checks():
    item = {"must_include": ["9"], "must_not_include": ["21"], "years_labeled": Y}
    assert replay.grade("□ 보행로\n ◦ 2024년 : 9곳\n ◦ 2025년 : 12곳", item) == (True, [])
    ok, why = replay.grade("□ 보행로 정비는 총 21곳", item)
    assert not ok and any("21" in w for w in why)
