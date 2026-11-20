"""CloudWatch 지표를 EMF(Embedded Metric Format) 로그 한 줄로 남긴다 (Requirement 12 기준 3, 개발계획서1 F-08).
PutMetricData 권한 없이 로그만으로 지표가 생긴다. Lambda 로그 앞머리가 붙지 않게 stdout에 JSON 한 줄을 그대로 쓴다.
값과 차원(feature)만 남기고 원문·사용자 정보는 넣지 않는다.
"""
import json
import sys

METRIC_UNITS = {
    "DocumentParseFailure": "Count",
    "EvidenceValidationFailure": "Count",
    "LLMSchemaFailure": "Count",
    "AnalysisLatency": "Milliseconds",
}


def _stdout(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def emit_metric(deps, name: str, value: float, *, feature: str) -> dict:
    if name not in METRIC_UNITS:
        raise ValueError(f"알 수 없는 지표: {name}")
    record = {
        "_aws": {
            "Timestamp": int(deps.now().timestamp() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": deps.config.metrics.namespace,
                "Dimensions": [["feature"]],
                "Metrics": [{"Name": name, "Unit": METRIC_UNITS[name]}],
            }],
        },
        "feature": feature,
        name: value,
    }
    (deps.metrics_sink or _stdout)(json.dumps(record, ensure_ascii=False))
    return record
