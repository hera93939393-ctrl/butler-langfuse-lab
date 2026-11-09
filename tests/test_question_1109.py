"""3차 ② 조건 물음: "~이면"·"누가/얼마" 물음이 쓰기로 판정돼 쓰기 지시문이 "□ 자료에서 찾지 못함"을 냄
(트레이스 29 신고 "예산 사이에 있는 금액을 추측해서 답변하지 못해요", 데이터셋 R08·R18 0/6)."""
from app import steps


def test_conditional_and_wh_questions_are_questions():
    for text in ("그럼 예산이 2천9백만원이면", "예산이 4백만원이면 누가 결재해", "외부 강사 수당을 17만을 주게 된다면?",
                 "예산 천만원짜리 집행하면 결재 누구", "팀장 전결은 얼마까지야"):
        assert steps.read_request(text)["mode"] == "question", text


def test_write_requests_stay_write():
    for text in ("2025년 점검 실적 찾아서 넣어줘", "2024년과 2025년 사업성과 비교해줘", "안전교실 참여 인원 정리해줘",
                 "다음 메모를 반영해서 2025 점검 실적을 정리해줘", "2024년이랑 2025년 성과 정리해서 비교해줘"):
        assert steps.read_request(text)["mode"] == "write", text
