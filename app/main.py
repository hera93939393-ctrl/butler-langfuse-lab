"""AI 한글집사 실습 서비스(목업 자료 + Langfuse 관측).

- /                 화면
- /health, /version 서비스 상태와 배포 버전
- /api/sources      목업 자료 목록
- /api/write        요청 하나 처리(참고 작성)
- /api/feedback     좋아요(1)·별로예요(0) → Langfuse 점수 user-feedback
- /api/report       신고 → Langfuse 점수 report, 사유는 comment

팀 비밀번호(TEAM_PASSWORD)를 아는 사람만 쓸 수 있다. 화면이 X-Team-Password, X-Nickname 헤더로 보낸다.
하루 요청 수는 DAILY_LIMIT 까지(인스턴스 하나 기준). 키나 자료 원문은 서버 로그에 남기지 않는다.
"""
import hmac
import json
import re
import sys
import threading
from collections import OrderedDict
from datetime import datetime
from typing import Literal
from urllib.parse import unquote

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app import pipeline, steps, tracing
from app.config import ROOT, load_settings
from app.llm import make_llm

settings = load_settings()
llm = make_llm(settings)
app = FastAPI(title="AI 한글집사 실습")

# 답 ID → (별명, 트레이스 ID). 인스턴스 메모리라 다시 시작하면 지난 답에는 반응을 못 붙인다(실습용).
results = OrderedDict()
results_lock = threading.Lock()
usage_today = {"date": None, "count": 0}


def log(severity, message, **fields):
    print(json.dumps({"severity": severity, "message": message, **fields}, ensure_ascii=False), file=sys.stdout, flush=True)


def get_llm():
    return llm


def member(x_team_password: str = Header(""), x_nickname: str = Header("")):
    """팀 비밀번호와 별명을 확인하고 별명을 돌려준다."""
    if not settings.team_password or not hmac.compare_digest(x_team_password, settings.team_password):
        raise HTTPException(401, "팀 비밀번호가 맞지 않습니다.")
    # 헤더에는 한글을 그대로 못 넣어서 화면이 encodeURIComponent 로 보낸다
    nickname = re.sub(r"[^가-힣A-Za-z0-9_-]", "", unquote(x_nickname))[:20]
    if not nickname:
        raise HTTPException(400, "별명을 적어 주세요.")
    return nickname


def count_request():
    today = datetime.now(tracing.KST).date()
    with results_lock:
        if usage_today["date"] != today:
            usage_today.update(date=today, count=0)
        if usage_today["count"] >= settings.daily_limit:
            raise HTTPException(429, "오늘 쓸 수 있는 횟수를 다 썼습니다. 내일 다시 써 주세요.")
        usage_today["count"] += 1


class WriteRequest(BaseModel):
    request: str = Field(min_length=1, max_length=300)
    sources: list[str] = Field(min_length=1, max_length=5)


class FeedbackRequest(BaseModel):
    result_id: str
    value: Literal["up", "down"]


class ReportRequest(BaseModel):
    result_id: str
    reason: str = Field("", max_length=500)


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"commit": settings.commit, "revision": settings.revision, "env": settings.env, "model": llm.model,
            "langfuse": tracing.client() is not None}


@app.get("/api/sources")
def sources(nickname: str = Depends(member)):
    return {"sources": steps.list_sources()}


@app.post("/api/write")
def write(req: WriteRequest, nickname: str = Depends(member), model=Depends(get_llm)):
    unknown = [s for s in req.sources if s not in steps.list_sources()]
    if unknown:
        raise HTTPException(400, "목업 자료만 고를 수 있습니다.")
    count_request()
    out = pipeline.run(req.request, req.sources, nickname, model, settings)
    result_id = (out["trace_id"] or f"local-{len(results) + 1}")[:40]
    with results_lock:
        results[result_id] = (nickname, out["trace_id"])
        while len(results) > 1000:
            results.popitem(last=False)
    log("INFO", "참고 작성", user=nickname, mode=out["mode"], chunks=len(out["chunks"]), guard_ok=out["guard"]["ok"])
    return {"id": result_id, "text": out["text"], "mode": out["mode"], "guard": out["guard"],
            "sources": [{"source": c["source"], "header": c["header"]} for c in out["chunks"]]}


def my_result(nickname, result_id):
    """내가 받은 답만. 남의 답이면 404."""
    owner = results.get(result_id)
    if not owner or owner[0] != nickname:
        raise HTTPException(404, "답을 찾지 못했습니다.")
    return owner[1]


def send_score(trace_id, name, value, comment=None):
    try:
        return tracing.score(trace_id, name, value, settings.env, comment)
    except Exception as error:
        log("WARNING", "Langfuse 점수 보내기 실패", name=name, error=type(error).__name__)
        return False


@app.post("/api/feedback")
def feedback(req: FeedbackRequest, nickname: str = Depends(member)):
    sent = send_score(my_result(nickname, req.result_id), "user-feedback", 1 if req.value == "up" else 0)
    log("INFO", "답변 반응", user=nickname, value=req.value, scored=sent)
    return {"ok": True}


@app.post("/api/report")
def report(req: ReportRequest, nickname: str = Depends(member)):
    sent = send_score(my_result(nickname, req.result_id), "report", 1, req.reason)
    log("WARNING", "답변 신고", user=nickname, reason_length=len(req.reason), scored=sent)
    return {"ok": True}
