"""테스트용 가짜 객체. AWS·Bedrock을 부르지 않는다."""


import io


def client_error(code, operation="Operation"):
    """botocore ClientError. 실제 SDK 예외 모양으로 오류 코드 분기를 시험한다."""
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": code, "Message": "fake"}}, operation)


class FakeS3:
    """put_object 호출 인자를 기록하고, objects에 넣어 둔 내용을 get_object로 돌려준다.

    errors에 {key: 예외}를 넣으면 그 키를 읽을 때 던진다. default_body가 있으면 없는 키에도 그 내용을 준다.
    """

    def __init__(self, objects=None, errors=None, default_body=None):
        self.puts = []
        self.gets = []
        self.objects = dict(objects or {})
        self.errors = dict(errors or {})
        self.default_body = default_body

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        return {}

    def get_object(self, *, Bucket, Key):
        self.gets.append({"Bucket": Bucket, "Key": Key})
        if Key in self.errors:
            raise self.errors[Key]
        body = self.objects.get((Bucket, Key), self.default_body)
        if body is None:
            raise client_error("NoSuchKey", "GetObject")
        return {"Body": io.BytesIO(body if isinstance(body, bytes) else body.encode("utf-8"))}


class FakePolly:
    """synthesize_speech 호출 인자를 기록하고 audio를 돌려준다. error가 있으면 던진다."""

    def __init__(self, audio=b"ID3fake-mp3", error=None):
        self.audio, self.error = audio, error
        self.calls = []

    def synthesize_speech(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"AudioStream": io.BytesIO(self.audio), "ContentType": "audio/mpeg"}


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
