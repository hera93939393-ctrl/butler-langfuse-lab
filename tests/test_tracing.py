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
    pipeline.run("2025년 점검 실적 찾아서 넣어줘", ["가상_2025_사업성과", "가상_2024_사업성과"], "민수", FakeLLM(), load_settings())

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
