"""테스트용 가짜 객체. AWS·Bedrock을 부르지 않는다."""


class FakeS3:
    """put_object 호출 인자만 기록한다."""

    def __init__(self):
        self.puts = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        return {}


class FakeLLM:
    """정해 둔 응답을 차례로 돌려준다. 예외 객체를 넣으면 그 차례에 던진다. 받은 프롬프트를 기록한다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, *, system_prompt, user_prompt):
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if not self.responses:
            raise RuntimeError("FakeLLM: no more responses")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item
