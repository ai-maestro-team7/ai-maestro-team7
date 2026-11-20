"""모든 A 모델의 바탕. Python 속성은 snake_case, JSON 키는 카멜 표기다 (D-02)."""
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class MentoringModel(BaseModel):
    """저장·응답용 모델. 저장된 항목에 필드가 더 있어도 읽을 수 있게 모르는 키는 무시한다."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    def to_api(self) -> dict:
        """API 응답·DB 저장용 dict. 카멜 표기, None은 뺀다."""
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")


class RequestModel(BaseModel):
    """요청 본문. 카멜 키만 받는다. userId 같은 정의되지 않은 키는 무시한다 (Requirement 2 기준 1)."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=False, extra="ignore")
