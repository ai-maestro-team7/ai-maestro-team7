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


class FakeTranscribe:
    """Transcribe 가짜. 시작한 작업과 조회 호출을 기록한다.

    - get_responses: get_transcription_job이 차례로 돌려줄 TranscriptionJob 값(또는 던질 예외). 다 쓰면 아래 규칙
    - 시작한 작업은 pending_polls번 IN_PROGRESS를 준 뒤 COMPLETED와 결과 주소(경로형)를 준다
    - start_error가 있으면 start_transcription_job에서 던진다
    """

    def __init__(self, get_responses=None, start_error=None, pending_polls=0, region="ap-northeast-2"):
        self.get_responses = list(get_responses or [])
        self.start_error = start_error
        self.pending_polls = pending_polls
        self.region = region
        self.starts = []
        self.gets = []
        self._jobs = {}

    def start_transcription_job(self, **kwargs):
        self.starts.append(kwargs)
        if self.start_error is not None:
            raise self.start_error
        self._jobs[kwargs["TranscriptionJobName"]] = {"polls": 0, **kwargs}
        return {"TranscriptionJob": {"TranscriptionJobName": kwargs["TranscriptionJobName"],
                                     "TranscriptionJobStatus": "IN_PROGRESS"}}

    def get_transcription_job(self, *, TranscriptionJobName):
        self.gets.append(TranscriptionJobName)
        if self.get_responses:
            item = self.get_responses.pop(0)
            if isinstance(item, BaseException):
                raise item
            return {"TranscriptionJob": item}
        job = self._jobs.get(TranscriptionJobName)
        if job is None:
            raise client_error("BadRequestException", "GetTranscriptionJob")
        job["polls"] += 1
        if job["polls"] <= self.pending_polls:
            return {"TranscriptionJob": {"TranscriptionJobName": TranscriptionJobName,
                                         "TranscriptionJobStatus": "IN_PROGRESS"}}
        uri = f"https://s3.{self.region}.amazonaws.com/{job['OutputBucketName']}/{job['OutputKey']}"
        return {"TranscriptionJob": {"TranscriptionJobName": TranscriptionJobName,
                                     "TranscriptionJobStatus": "COMPLETED", "Transcript": {"TranscriptFileUri": uri}}}


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


class FakeToolLLM:
    """툴을 쓰는 에이전트 가짜 (피드백 C-2).

    run_with_tools가 불릴 때마다 tool_calls에 적은 순서대로 툴 함수를 직접 부르고(모델이 툴을 고른 것처럼),
    tool_responses의 다음 값을 마지막 답으로 돌려준다. 예외 객체면 그 차례에 던진다.
    complete는 FakeLLM처럼 responses를 차례로 돌려준다 (C-1 등). 둘 다 받은 값을 기록한다.
    """

    def __init__(self, tool_responses, tool_calls=(), responses=()):
        self.tool_responses = list(tool_responses)
        self.tool_calls = list(tool_calls)
        self.responses = list(responses)
        self.runs = []
        self.calls = []

    def complete(self, *, system_prompt, user_prompt):
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if not self.responses:
            raise RuntimeError("FakeToolLLM: no more complete responses")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def run_with_tools(self, *, system_prompt, user_prompt, tools, limits):
        by_name = {t.__name__: t for t in tools}
        results = [(name, kwargs, by_name[name](**kwargs)) for name, kwargs in self.tool_calls]
        self.runs.append({"system": system_prompt, "user": user_prompt, "tools": sorted(by_name),
                          "limits": limits, "results": results})
        if not self.tool_responses:
            raise RuntimeError("FakeToolLLM: no more tool responses")
        item = self.tool_responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


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
