"""Langfuse 계측. 친구 에이전트 수업(2026-11-02)에서 만든 방식을 그대로 가져왔다.

- LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY 가 둘 다 있을 때만 보낸다. 없으면 빈 기록기(OFF)라 앱은 그대로 돈다.
- 단계는 직접 만들고 직접 닫는다(start_observation → end). 자동으로 '지금 단계'를 찾지 않는다.
- 속성(사용자, 세션, 환경, 버전)은 단계를 만드는 그 순간에만 propagate_attributes 로 감싼다.
- 이 저장소는 목업 자료만 쓰므로 원문을 남긴다. 그래도 전화번호, 이메일, 카드 번호 모양은 가린다.
SDK 근거: https://langfuse.com/docs/observability/sdk/python/instrumentation , langfuse==5.0.4
"""
import json
import os
import re
from contextlib import nullcontext
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "[이메일]"),
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[카드번호]"),
    (re.compile(r"\b01[016789][ -]?\d{3,4}[ -]?\d{4}\b"), "[전화번호]"),
]


def mask(*, data, **kwargs):
    if isinstance(data, str):
        for pattern, label in PATTERNS:
            data = pattern.sub(label, data)
        return data
    if isinstance(data, dict):
        return {k: mask(data=v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [mask(data=v) for v in data]
    return data


class _Off:
    trace_id = None

    def start_observation(self, **kwargs):
        return self

    def update(self, **kwargs):
        return self

    def end(self, **kwargs):
        return self


OFF = _Off()
_client = None


def flush():
    """모아 둔 기록을 지금 보낸다(2026-11-09 운영: 답 10개 중 트레이스 5개가 안 들어옴 — Cloud Run 은 요청 밖에서
    CPU 를 거의 멈춰 SDK 의 묶음 전송이 인스턴스에 남는다). 키가 없으면 아무 일도 안 한다. 실패해도 답은 막지 않는다."""
    c = client()
    if c is None:
        return
    try:
        c.flush()
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"severity": "WARNING", "message": "Langfuse 기록 보내기 실패", "error": type(error).__name__},
                         ensure_ascii=False), flush=True)


def client():
    global _client
    if _client is None:
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
        if not (public_key and secret_key):
            return None
        from langfuse import Langfuse

        _client = Langfuse(public_key=public_key, secret_key=secret_key,
                           base_url=os.environ.get("LANGFUSE_BASE_URL") or None, mask=mask)
    return _client


def _propagate(attrs):
    if not attrs:
        return nullcontext()
    from langfuse import propagate_attributes

    return propagate_attributes(**attrs)


class Observation:
    """Langfuse 단계 하나와, 그 아래 단계에 붙일 속성을 같이 들고 다닌다."""

    def __init__(self, observation, attrs):
        self._observation = observation
        self.attrs = attrs

    @property
    def trace_id(self):
        return getattr(self._observation, "trace_id", None)

    def start_observation(self, **fields):
        with _propagate(self.attrs):
            return Observation(self._observation.start_observation(**fields), self.attrs)

    def update(self, **fields):
        self._observation.update(**fields)
        return self

    def end(self, **fields):
        self._observation.end(**fields)
        return self


def turn_attrs(nickname, settings, metadata=None):
    """사용자는 팀원 별명, 세션은 '별명 + 한국 날짜'(하루치 시험을 한 세션으로)."""
    return {
        "user_id": nickname,
        "session_id": f"{nickname}-{datetime.now(KST):%Y-%m-%d}",
        "environment": settings.env,
        "version": settings.revision,
        "metadata": {"commit": settings.commit, **(metadata or {})},
    }


def start_trace(name, attrs=None, **fields):
    langfuse = client()
    if langfuse is None:
        return OFF
    with _propagate(attrs):
        return Observation(langfuse.start_observation(name=name, as_type="span", **fields), attrs)


def score(trace_id, name, value, environment, comment=None):
    """반응을 BOOLEAN 점수로. 키나 트레이스 ID가 없으면 건너뛰고 False."""
    langfuse = client()
    if langfuse is None or not trace_id:
        return False
    # 점수 사유(신고 사유)도 보내기 전에 전화번호·이메일·카드 번호 모양을 가린다(SDK 마스킹은 입력·출력에만 걸린다)
    langfuse.create_score(trace_id=trace_id, name=name, value=value, data_type="BOOLEAN",
                          comment=mask(data=comment) if comment else None, environment=environment)
    return True


def usage_details(usage):
    if usage and usage.get("input") is not None:
        return {"input": usage["input"], "output": usage.get("output") or 0}
    return None
