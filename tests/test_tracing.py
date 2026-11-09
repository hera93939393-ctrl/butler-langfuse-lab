"""계측 구조 표대로 단계 이름과 속성이 남는지. 진짜 Langfuse 대신 받아 적는 기록기를 끼운다."""
from contextlib import contextmanager

from app import pipeline, tracing
from app.config import load_settings
from app.llm import FakeLLM


class Recorder:
    current_attrs = None

    def __init__(self, **fields):
        self.fields, self.children, self.ended, self.attrs = fields, [], False, Recorder.current_attrs
        self.trace_id = "t-1"

    def start_observation(self, **fields):
        self.children.append(Recorder(**fields))
        return self.children[-1]

    def update(self, **fields):
        self.fields.update(fields)
        return self

    def end(self, **fields):
        self.ended = True
        return self


def test_write_turn_steps_and_attributes(monkeypatch):
    traces = []

    @contextmanager
    def propagate(attrs):
        Recorder.current_attrs = attrs
        try:
            yield
        finally:
            Recorder.current_attrs = None

    def start_trace(name, attrs=None, **fields):
        with propagate(attrs):
            traces.append(Recorder(name=name, **fields))
        return tracing.Observation(traces[-1], attrs)

    monkeypatch.setattr(tracing, "_propagate", propagate)
    monkeypatch.setattr(tracing, "start_trace", start_trace)
    pipeline.run("2025년 점검 실적 찾아서 넣어줘", ["mock_2025_results", "mock_2024_results"], "민수", FakeLLM(), load_settings())

    turn = traces[-1]
    assert turn.fields["name"] == "write-turn" and turn.ended
    assert [c.fields["name"] for c in turn.children] == ["read-request", "find-sources", "write", "number-guard"]
    assert all(c.ended for c in turn.children)
    write_step = turn.children[2]
    assert write_step.fields["as_type"] == "generation" and write_step.fields["model"] == "fake"
    assert turn.attrs["user_id"] == "민수" and turn.attrs["session_id"].startswith("민수-")
    assert turn.attrs["environment"] == "test"
    assert all(c.attrs["user_id"] == "민수" for c in turn.children)


def test_mask_hides_phone_and_email():
    masked = tracing.mask(data={"x": "연락 010-1234-5678, a.b@example.com"})["x"]
    assert "[전화번호]" in masked and "[이메일]" in masked


def test_write_and_feedback_flush_traces(monkeypatch):
    """2026-11-09 운영: 답 10개 중 트레이스 5개가 Langfuse 에 안 들어옴(반응 점수는 들어옴).
    Cloud Run 은 요청 밖에서 CPU 를 거의 멈춰 모아 둔 기록이 인스턴스에 남는다 → 요청 끝에 바로 보낸다."""
    from fastapi.testclient import TestClient
    from app import main

    flushed = []
    monkeypatch.setattr(tracing, "flush", lambda: flushed.append(1))
    c = TestClient(main.app)
    h = {"x-team-password": "test-pw", "x-nickname": "%EB%AF%BC%EC%88%98"}
    monkeypatch.setattr(main.settings, "team_password", h["x-team-password"])
    r = c.post("/api/write", json={"request": "2025년 점검 실적 찾아서 넣어줘", "sources": ["mock_2025_results"]}, headers=h)
    assert r.status_code == 200 and flushed == [1], (r.status_code, r.text[:200], flushed)
    c.post("/api/feedback", json={"result_id": r.json()["id"], "value": "up"}, headers=h)
    assert flushed == [1, 1]


def test_flush_without_langfuse_is_noop(monkeypatch):
    monkeypatch.setattr(tracing, "_client", None)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    tracing.flush()   # 키가 없으면 아무 일도 안 하고 예외도 없다
