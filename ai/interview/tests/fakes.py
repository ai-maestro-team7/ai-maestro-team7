"""테스트용 가짜 객체. AWS·Bedrock을 부르지 않는다."""


class FakeS3:
    """put_object 호출 인자만 기록한다."""

    def __init__(self):
        self.puts = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        return {}
