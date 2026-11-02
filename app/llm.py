"""모델 호출. usage 에 dict 를 넘기면 쓴 토큰 수를 {"input": n, "output": n} 으로 채운다(Langfuse 비용 계산용).

LLM 객체 하나를 모든 요청이 같이 쓰므로 토큰 수를 객체에 저장하지 않고 부를 때마다 받은 dict 에 채운다.
fake 는 키 없이 화면과 흐름을 확인하거나 테스트할 때 쓰는 가짜 응답이다.
"""
import re


class OpenAILLM:
    def __init__(self, api_key, model):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, timeout=60)
        self.model = model

    def complete(self, system, user, usage=None):
        response = self.client.chat.completions.create(
            model=self.model, temperature=0.2,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        if usage is not None and response.usage:
            usage["input"] = response.usage.prompt_tokens
            usage["output"] = response.usage.completion_tokens
        return response.choices[0].message.content.strip()


class FakeLLM:
    """AI를 부르지 않는다. 받은 자료 줄을 그대로 개조식으로 옮겨 적는다(테스트와 키 없는 화면 확인용)."""

    model = "fake"

    def complete(self, system, user, usage=None):
        lines = re.findall(r"^- \[[^\]]+\] (.+)$", user, re.M)
        if not lines:
            return "□ 자료에서 찾지 못함"
        return "□ 찾은 내용\n" + "\n".join(f" ◦ {line.strip(' ◦')}" for line in lines[:4])


def make_llm(settings):
    if settings.provider == "fake":
        return FakeLLM()
    return OpenAILLM(settings.api_key, settings.model)
