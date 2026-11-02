"""참고 작성의 단계들. 단계마다 고칠 곳이 달라서 Langfuse 에도 따로 남긴다(pipeline.py).

read_request  요청 읽기: 물음인지, 자료를 보고 써 달라는 것인지. 연도와 낱말을 뽑는다(코드 규칙).
find_sources  자료 찾기: 고른 자료의 줄마다 낱말이 얼마나 겹치는지로 점수를 매겨 위에서부터 고른다.
              연도를 묻는데 다른 해 자료가 고른 목록에 있으면, 낱말이 같아 함께 뽑힐 수 있다(의도한 함정).
number_guard  수치 가드: 쓴 글의 숫자가 고른 자료에 있는지 코드로 확인한다.
"""
import re

from app.config import MOCK_DIR

QUESTION_END = re.compile(r"(\?|뭐야|언제야|얼마야|몇\s*개야|있어|했어|인가요|나요|까)\s*$")
STOPWORDS = {"찾아서", "넣어줘", "넣어", "줘", "써줘", "정리해줘", "알려줘", "그리고", "자료", "내용", "관련"}
PARTICLES = re.compile(r"(은|는|이|가|을|를|의|에|에서|으로|로|과|와|도|만)$")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def list_sources():
    """목업 폴더의 .txt 만. 다른 곳의 파일은 읽지 않는다."""
    return sorted(p.stem for p in MOCK_DIR.glob("*.txt"))


def read_source(name):
    if name not in list_sources():
        raise ValueError(f"없는 자료입니다: {name}")
    return (MOCK_DIR / f"{name}.txt").read_text(encoding="utf-8")


def read_request(text):
    words = []
    for w in re.findall(r"[가-힣A-Za-z0-9]+", text):
        w = PARTICLES.sub("", w)
        if len(w) >= 2 and w not in STOPWORDS and not w.isdigit():
            words.append(w)
    return {
        "mode": "question" if QUESTION_END.search(text.strip()) else "write",
        "years": re.findall(r"(20\d{2})년?", text),
        "words": words,
        "decided_by": "rule",
    }


def source_year(text):
    m = re.search(r"(20\d{2})년", text.splitlines()[0] if text else "")
    return m.group(1) if m else None


def find_sources(request, names, limit=5):
    """고른 자료에서 요청과 겹치는 줄을 점수 순으로. 줄마다 바로 위 □ 머리줄을 함께 붙인다."""
    picked = []
    for name in names:
        text = read_source(name)
        year = source_year(text)
        header = ""
        for line in text.splitlines():
            if line.startswith("□"):
                header = line.strip("□ ").strip()
                continue
            if not line.strip().startswith("◦"):
                continue
            body = f"{header} {line}"
            score = sum(1 for w in request["words"] if w in body)
            if request["years"] and year in request["years"]:
                score += 1  # 연도가 맞으면 조금 더 위로(다른 해 자료도 낱말만 같으면 함께 뽑힌다)
            if score > 0:
                picked.append({"source": name, "year": year, "header": header, "line": line.strip(), "score": score})
    picked.sort(key=lambda c: -c["score"])
    return picked[:limit]


def number_guard(text, chunks):
    """글의 숫자가 자료 줄에 있는지. 요청에 나온 연도는 자료 머리말에도 있으니 함께 허용한다."""
    allowed = set()
    for c in chunks:
        allowed |= set(NUMBER.findall(c["line"])) | set(NUMBER.findall(c["header"]))
        if c["year"]:
            allowed.add(c["year"])
    found = NUMBER.findall(text)
    known = [n for n in found if n in allowed]
    unknown = [n for n in found if n not in allowed]
    return {"known": known, "unknown": unknown, "ok": not unknown}
