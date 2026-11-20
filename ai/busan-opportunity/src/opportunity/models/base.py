"""모든 B 모델의 바탕. Python 속성은 snake_case, JSON 키는 카멜 표기다 (D-02)."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class OppModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    def to_api(self) -> dict:
        """API 응답·DB 저장용 dict. 카멜 표기, None은 뺀다."""
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")
