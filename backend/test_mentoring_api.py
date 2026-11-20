"""공통 Lambda 입구에서 A의 REST·작업 핸들러까지 연결을 검증한다."""

import json
import sys
from types import ModuleType
from unittest import TestCase
from unittest.mock import Mock, patch

from mentoring.config import MissingEnvError, get_config
from mentoring.deps import Deps
from mentoring.models import CareerProfile
from mentoring.store.memory import MemoryUserRepo

import mentoring_api
from app import lambda_handler
from common import hash_user_id


def profile_request(user_id=None):
    path = "/api/v1/mentoring/profiles/me"
    context = {"stage": "$default", "http": {"method": "GET", "path": path}}
    if user_id is not None:
        context["authorizer"] = {"jwt": {"claims": {"sub": user_id}}}
    return {
        "version": "2.0",
        "rawPath": path,
        "rawQueryString": "userId=other-user",
        "requestContext": context,
    }


class MentoringApiTest(TestCase):
    def setUp(self):
        self.addCleanup(mentoring_api.deps.cache_clear)

    def test_unavailable_aws_factory_keeps_rest_disabled_and_fails_async(self):
        with patch.dict(sys.modules, {"mentoring.store.factory": None}):
            response = lambda_handler(profile_request("jwt-user"), None)
            self.assertEqual(response["statusCode"], 501)
            self.assertEqual(json.loads(response["body"])["error"]["code"], "NOT_IMPLEMENTED")
            with self.assertRaises(RuntimeError):
                lambda_handler({"mentoringTask": {}}, None)

    def test_missing_aws_environment_keeps_rest_disabled(self):
        factory_module = ModuleType("mentoring.store.factory")
        factory_module.build_aws_deps = Mock(side_effect=MissingEnvError("TABLE_REFERENCE"))
        with patch.dict(sys.modules, {"mentoring.store.factory": factory_module}):
            self.assertEqual(lambda_handler(profile_request("jwt-user"), None)["statusCode"], 501)

    def test_rest_uses_jwt_user_and_task_reuses_the_same_dependencies(self):
        users = MemoryUserRepo()
        users.put_profile_version(CareerProfile(
            profile_id="jwt-profile", profile_version=1, owner_user_id="jwt-user",
            created_by="EXTRACTION", created_at="2026-11-20T10:00:00+09:00",
        ), expected_version=None)
        factory_module = ModuleType("mentoring.store.factory")
        factory = Mock(return_value=Deps(
            config=get_config(), users=users, objects=Mock(), llm=Mock(), tasks=Mock(), text=Mock(),
            hash_user_id=Mock(side_effect=AssertionError("백엔드 공통 해시를 써야 한다")),
        ))
        factory_module.build_aws_deps = factory
        with patch.dict(sys.modules, {"mentoring.store.factory": factory_module}):
            self.assertEqual(lambda_handler(profile_request(), None)["statusCode"], 401)
            factory.assert_not_called()
            response = lambda_handler(profile_request("jwt-user"), None)
            self.assertEqual(response["statusCode"], 200)
            self.assertEqual(json.loads(response["body"])["profileId"], "jwt-profile")
            self.assertEqual(lambda_handler({"mentoringTask": {
                "taskId": "missing-task", "taskType": "PROFILE_EXTRACT", "userId": "jwt-user",
                "resourceId": "doc-1", "resourceVersion": 1,
            }}, None), {"taskId": "missing-task", "status": "SKIPPED", "reason": "TASK_NOT_FOUND"})
            factory.assert_called_once_with()
            self.assertIs(mentoring_api.deps(factory).hash_user_id, hash_user_id)
