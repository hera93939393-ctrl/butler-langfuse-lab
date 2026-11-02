"""요청 하나(한 턴)를 처리한다. 트레이스 write-turn 하나 아래에 단계를 하나씩 남긴다.

read-request(span) → find-sources(span) → write(generation) → number-guard(span)
"""
from app import steps, tracing

WRITE_RULES = """너는 공공기관 문서를 쓰는 'AI 한글집사'다. [자료]에 있는 사실과 숫자만 써서 개조식으로 답한다.
- 큰 항목은 □, 작은 항목은 앞에 한 칸 띄우고 ◦ 로 쓴다.
- 문장은 명사형으로 끝낸다(예: 완료, 실시, 증가). '~습니다'로 끝내지 않는다.
- 수치는 '총 N명', '총 N건', '총 N개소'처럼 쓴다.
- 자료에 없는 숫자를 만들지 않는다. 비율이나 차이를 새로 계산하지 않는다.
- 요청한 연도와 다른 해의 자료는 쓰지 않는다. 비교를 요청했을 때만 함께 쓴다.
- 자료에서 찾지 못하면 '□ 자료에서 찾지 못함' 한 줄만 쓴다."""

ANSWER_RULES = """너는 공공기관 문서를 돕는 'AI 한글집사'다. [자료]에 있는 사실과 숫자만으로 짧게 답한다.
자료에 없으면 '자료에서 찾지 못했습니다.'라고만 답한다. 숫자를 새로 계산하지 않는다."""


def run(request_text, source_names, nickname, llm, settings):
    turn = tracing.start_trace("write-turn", attrs=tracing.turn_attrs(nickname, settings, {"sources": ",".join(source_names)}),
                               input={"request": request_text, "sources": source_names})
    try:
        # ① 요청 읽기
        req = steps.read_request(request_text)
        turn.start_observation(name="read-request", input=request_text, output=req).end()

        # ② 자료 찾기
        chunks = steps.find_sources(req, source_names)
        turn.start_observation(name="find-sources", input={"words": req["words"], "years": req["years"], "sources": source_names},
                               output=chunks,
                               metadata={"picked": len(chunks), "years_in_picked": sorted({c["year"] for c in chunks if c["year"]})}).end()

        # ③ 쓰기
        rules = ANSWER_RULES if req["mode"] == "question" else WRITE_RULES
        listed = "\n".join(f"- [{steps.label(c['source'])} · {c['header']}] {c['line']}" for c in chunks) or "(찾은 자료 없음)"
        user = f"[요청]\n{request_text}\n\n[자료]\n{listed}"
        step = turn.start_observation(name="write", as_type="generation", model=llm.model,
                                      input=[{"role": "system", "content": rules}, {"role": "user", "content": user}])
        usage, text = {}, None
        try:
            text = llm.complete(rules, user, usage=usage)
        finally:  # 모델 호출이 실패해도 단계는 닫아서 보낸다
            step.update(output=text, usage_details=tracing.usage_details(usage)).end()

        # ④ 수치 가드
        guard = steps.number_guard(text, chunks)
        turn.start_observation(name="number-guard", input=text, output=guard,
                               level=None if guard["ok"] else "WARNING").end()

        turn.update(output=text, metadata={"mode": req["mode"], "guard_ok": guard["ok"], "unknown_numbers": len(guard["unknown"])})
        return {"text": text, "mode": req["mode"], "guard": guard, "chunks": chunks, "trace_id": turn.trace_id}
    finally:
        turn.end()
