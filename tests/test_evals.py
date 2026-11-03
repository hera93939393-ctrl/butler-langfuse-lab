from app import evals, steps


def item(answer_checks, chunks, request="요청"):
    return {"input": {"request": request, "mode": "write", "chunks": chunks}, "expected": answer_checks}


CHUNK = [{"source": "mock_2025_results", "year": "2025", "header": "정기점검", "line": "◦ 정기점검 실적 : 총 42개소 점검 완료"}]


def test_korean_numerals_are_caught():
    assert evals.korean_numerals("총 사백이십개소, 총 천 명, 어린이 40명") == ["사백이십", "천"]
    ok, reasons = evals.grade_write("총 사백이십개소 점검", item({"no_korean_numerals": True}, CHUNK))
    assert not ok and "사백이십" in reasons[0]


def test_numbers_must_come_from_sources_or_request():
    checks = {"numbers_from_sources": True}
    assert evals.grade_write("2025년 총 42개소", item(checks, CHUNK))[0]
    ok, reasons = evals.grade_write("총 420개소", item(checks, CHUNK))
    assert not ok and "420" in reasons[0]
    # 요청에 나온 숫자(연도)는 헛경보 내지 않는다
    assert evals.grade_write("2023년 자료 없음, 2025년 42개소", item(checks, CHUNK, "2023년과 2025년 비교"))[0]


def test_grade_find_checks_years_mode_and_headers():
    req = steps.read_request("2024년과 2025년 사업성과 비교해줘")
    chunks = [{"year": "2024", "header": "정기점검", "line": "◦ a"}]
    ok, reasons = evals.grade_find(req, chunks, {"years": ["2024", "2025"], "mode": "question", "only_headers": ["예산 집행"]})
    assert not ok and len(reasons) == 3


def test_dataset_files_are_valid():
    for name in ("find_sources.jsonl", "write.jsonl"):
        rows = evals.load(name)
        assert len({r["id"] for r in rows}) == len(rows)
        assert {r["kind"] for r in rows} == {"failure", "normal"}
    assert len(evals.load("write.jsonl")) >= 10
