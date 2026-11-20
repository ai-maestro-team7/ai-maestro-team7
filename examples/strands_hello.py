"""Strands Agents + Bedrock 최소 예제 (팀 공용).

실행:  aws login 후
  uv run --python 3.13 --with strands-agents --with "botocore[crt]" examples/strands_hello.py

`botocore[crt]`가 없으면 aws login 자격 증명을 못 읽는다 (MissingDependencyException).
"""

from strands import Agent, tool
from strands.models import BedrockModel

# 확인된 모델 ID (2026-11-20, ap-northeast-2)
HAIKU = "global.anthropic.claude-haiku-5-5"    # 빠르고 저렴: 라우팅, 짧은 답변
SONNET = "global.anthropic.claude-sonnet-5-5"  # 정확도: 분석, 첨삭

model = BedrockModel(model_id=HAIKU, region_name="ap-northeast-2", max_tokens=512)


@tool
def busan_youth_age_check(birth_year: int) -> str:
    """부산 청년정책 나이 기준(만 18~39세)에 해당하는지 확인한다.

    Args:
        birth_year: 출생 연도
    """
    age = 2026 - birth_year
    return f"만 {age}세 → {'대상' if 18 <= age <= 39 else '대상 아님'}"


agent = Agent(
    model=model,
    tools=[busan_youth_age_check],
    system_prompt="너는 부산 청년 취업 멘토다. 계산은 반드시 도구로 하고, 한국어로 짧게 답한다.",
)

if __name__ == "__main__":
    result = agent("2000년생인데 부산 청년정책 나이 기준에 맞아?")
    print("\n---\ntool calls:", list(result.metrics.tool_metrics.keys()))
