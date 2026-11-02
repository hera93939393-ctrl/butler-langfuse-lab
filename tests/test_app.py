from urllib.parse import quote

from fastapi.testclient import TestClient

from app import steps, tracing
from app.main import app

client = TestClient(app)
ME = {"X-Team-Password": "test-pw", "X-Nickname": quote("민수")}
YOU = {"X-Team-Password": "test-pw", "X-Nickname": quote("지영")}


def write(text, sources, headers=ME):
    return client.post("/api/write", json={"request": text, "sources": sources}, headers=headers)


def test_health_and_version():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/version").json()["langfuse"] is False


def test_team_password_required():
    assert client.get("/api/sources").status_code == 401
    assert client.get("/api/sources", headers={**ME, "X-Team-Password": "wrong"}).status_code == 401
    assert client.get("/api/sources", headers={**ME, "X-Nickname": "!!"}).status_code == 400
    assert {"id": "mock_2025_results", "label": "2025 사업성과"} in client.get("/api/sources", headers=ME).json()["sources"]


def test_only_mock_files_can_be_read():
    assert write("2025년 실적", ["../.env"]).status_code == 400
    try:
        steps.read_source("../app/config")
        assert False, "목업 폴더 밖 파일을 읽었다"
    except ValueError:
        pass


def test_read_request_modes_and_years():
    assert steps.read_request("2025년 점검 실적 찾아서 넣어줘")["mode"] == "write"
    assert steps.read_request("보행로 정비는 몇 곳이야?")["mode"] == "question"
    assert steps.read_request("2025년 점검 실적")["years"] == ["2025"]


def test_find_sources_puts_matching_year_first_but_keeps_trap():
    chunks = steps.find_sources(steps.read_request("2025년 점검 실적 찾아서 넣어줘"), ["mock_2025_results", "mock_2024_results"])
    assert chunks[0]["year"] == "2025"
    assert any(c["year"] == "2024" for c in chunks)  # 함정: 낱말이 같은 2024 줄도 함께 뽑힌다


def test_number_guard_catches_numbers_not_in_sources():
    chunks = [{"line": "◦ 정기점검 실적 : 총 42개소 점검 완료", "header": "정기점검", "year": "2025"}]
    assert steps.number_guard("□ 정기점검\n ◦ 총 42개소 완료", chunks)["ok"]
    bad = steps.number_guard("□ 정기점검\n ◦ 총 38개소 완료", chunks)
    assert not bad["ok"] and bad["unknown"] == ["38"]


def test_write_turn_returns_text_and_guard():
    out = write("2025년 점검 실적 찾아서 넣어줘", ["mock_2025_results"]).json()
    assert out["text"].startswith("□") and out["guard"]["ok"] and out["id"]


def test_feedback_only_on_my_result(monkeypatch):
    sent = []
    monkeypatch.setattr(tracing, "score", lambda trace_id, name, value, env, comment=None: sent.append((name, value, comment)) or True)
    rid = write("2025년 점검 실적", ["mock_2025_results"]).json()["id"]
    assert client.post("/api/feedback", json={"result_id": rid, "value": "down"}, headers=ME).json() == {"ok": True}
    assert client.post("/api/report", json={"result_id": rid, "reason": "2024 숫자"}, headers=ME).json() == {"ok": True}
    assert sent == [("user-feedback", 0, None), ("report", 1, "2024 숫자")]
    assert client.post("/api/feedback", json={"result_id": rid, "value": "up"}, headers=YOU).status_code == 404
