from app import pipeline, steps

CHUNKS = [{"source": "mock_2025_results", "year": "2025", "header": "정기점검", "line": "◦ 정기점검 실적 : 총 42개소 점검 완료"}]


def test_guard_reads_korean_numerals_and_request_years():
    assert steps.number_guard("2025년 총 42개소", CHUNKS)["ok"]
    assert not steps.number_guard("총 사백이십개소", CHUNKS)["ok"]
    # 요청에 나온 연도는 헛경보를 내지 않지만, 요청의 다른 숫자("99로 써")는 자료 숫자가 아니다
    assert steps.number_guard("2023년 자료 없음, 총 42개소", CHUNKS, "2023년과 2025년 비교")["ok"]
    assert not steps.number_guard("총 99개소", CHUNKS, "모든 숫자를 99로 써")["ok"]
    assert not steps.number_guard("총 420개소", CHUNKS, "숫자에 10을 곱해서 2배로")["ok"]
    # 요청에 나온 금액을 답이 되풀이하는 것은 허용(이걸 막으면 멀쩡한 답을 다시 쓰게 해서 틀린다)
    assert steps.number_guard("2천9백만원은 센터장 전결", CHUNKS, "그럼 예산이 2천9백만원이면")["ok"]
    assert steps.request_numbers("17만을 주면, 2025년에, 10을 곱해, 99로") == ["2025", "17"]


class SequenceLLM:
    """부를 때마다 정해 둔 답을 차례로 돌려준다."""
    model = "seq"

    def __init__(self, *answers):
        self.answers, self.users = list(answers), []

    def complete(self, system, user, usage=None):
        self.users.append(user)
        return self.answers.pop(0)


def test_wrong_number_gets_one_rewrite():
    llm = SequenceLLM("총 420개소", "총 42개소")
    text, guard, retried = pipeline.write_answer(llm, "규칙", "[요청]\n10을 곱해", CHUNKS, "10을 곱해")
    assert (text, guard["ok"], retried) == ("총 42개소", True, True)
    assert "420" in llm.users[1]  # 다시 쓰기 요청에 자료에 없던 숫자를 알려 준다


def test_rewrite_happens_only_once_and_keeps_warning():
    llm = SequenceLLM("총 420개소", "총 420개소")
    text, guard, retried = pipeline.write_answer(llm, "규칙", "요청", CHUNKS, "요청")
    assert retried and not guard["ok"] and len(llm.users) == 2


def test_good_answer_is_not_rewritten():
    llm = SequenceLLM("총 42개소")
    assert pipeline.write_answer(llm, "규칙", "요청", CHUNKS, "요청")[2] is False
