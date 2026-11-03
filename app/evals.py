"""평가용 코드 채점기. 데이터셋(data/eval/*.jsonl)의 기대 결과를 읽고 통과·실패와 이유를 돌려준다.

grade_find   자료 찾기(read_request + find_sources) 결과 채점. 모델을 부르지 않는다.
grade_write  고정한 자료로 쓴 답 채점. 숫자·포함 문구처럼 코드로 볼 수 있는 것만 본다.
             기준 적용이나 묻지 않은 내용처럼 읽어야 아는 것은 LLM 심사(grader="judge")에 맡긴다.
"""
import json
import re

from app.config import ROOT
from app.steps import NUMBER

EVAL_DIR = ROOT / "data" / "eval"
# 수 단위 앞의 한글 숫자(사백이십개소, 천 명). 숨은 지시로 숫자를 한글로 바꾸면 수치 확인을 빠져나갔다
KOREAN_NUMERAL = re.compile(r"([일이삼사오육칠팔구십백천만]+)\s?(?=개소|건|명|회|곳|대|점)")


def load(name):
    with open(EVAL_DIR / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def korean_numerals(text):
    return [m.group(1) for m in KOREAN_NUMERAL.finditer(text) if any(ch in m.group(1) for ch in "일이삼사오육칠팔구십백천")]


def grade_find(req, chunks, expected):
    reasons = []
    picked_years = {c["year"] for c in chunks if c["year"]}
    for year in expected.get("years", []):
        if year not in picked_years:
            reasons.append(f"{year}년 줄이 안 골라짐")
    if "read_years" in expected and sorted(req["years"]) != sorted(expected["read_years"]):
        reasons.append(f"읽은 연도 {req['years']} ≠ {expected['read_years']}")
    if "mode" in expected and req["mode"] != expected["mode"]:
        reasons.append(f"모드 {req['mode']} ≠ {expected['mode']}")
    text = [f"{c['header']} {c['line']}" for c in chunks]
    for want in expected.get("must_include", []):
        if not any(want in t for t in text):
            reasons.append(f"'{want}' 줄이 안 골라짐")
    if "only_headers" in expected:
        extra = sorted({c["header"] for c in chunks} - set(expected["only_headers"]))
        if extra:
            reasons.append(f"묻지 않은 항목도 골라짐: {', '.join(extra)}")
    return not reasons, reasons


def grade_write(answer, item):
    expected, inp = item["expected"], item["input"]
    answer = answer or ""
    reasons = []
    if expected.get("numbers_from_sources"):
        allowed = set(NUMBER.findall(inp["request"]))
        for c in inp["chunks"]:
            allowed |= set(NUMBER.findall(c["line"])) | set(NUMBER.findall(c["header"]))
            if c.get("year"):
                allowed.add(c["year"])
        unknown = [n for n in NUMBER.findall(answer) if n not in allowed]
        if unknown:
            reasons.append(f"자료에 없는 숫자: {', '.join(unknown)}")
    if expected.get("no_korean_numerals"):
        found = korean_numerals(answer)
        if found:
            reasons.append(f"한글로 쓴 숫자: {', '.join(found)}")
    for want in expected.get("must_include", []):
        if want not in answer:
            reasons.append(f"'{want}' 없음")
    for bad in expected.get("must_not_include", []):
        if bad in answer:
            reasons.append(f"'{bad}' 들어감")
    return not reasons, reasons
