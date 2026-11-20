"""AWS 호출 없이 기존 설정 보존, 일정 생성·갱신, 실패 전파를 검증한다."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import setup_opp_batch as setup

ARN = "arn:aws:lambda:ap-northeast-2:123456789012:function:team07-api"
ROLE = "arn:aws:iam::123456789012:role/team07-scheduler-role"


class SetupTests(unittest.TestCase):
    def current(self):
        return {
            "FunctionArn": ARN, "RevisionId": "revision", "Timeout": 300,
            "Environment": {"Variables": {
                **{name: "test" for name in (
                    "TABLE_CATALOG", "TABLE_CAREER_MENTOR", "OPP_DATA_BUCKET", "OPP_VECTOR_BUCKET",
                    "OPP_VECTOR_INDEX", "MODEL_ID", "EMBEDDING_MODEL_ID",
                )},
                "SCHEDULER_TARGET_ARN": ARN, "SCHEDULER_ROLE_ARN": ROLE,
                "COGNITO_CLIENT_ID": "keep-login", "TABLE_REFERENCE": "keep-reference", "KB_ID": "keep-kb",
            }},
        }

    def test_configuration_preserves_existing_environment_and_uses_revision(self):
        current = self.current()
        observed = []
        def aws(service, action, *args):
            if action == "update-function-configuration":
                observed.append((args, json.loads(Path(args[3][7:]).read_text())))
            return {}
        with patch.object(setup, "aws", side_effect=aws):
            setup.set_lambda_config(current)
        args, env = observed[0]
        self.assertEqual(env["Variables"], {**current["Environment"]["Variables"], "OPP_SECRET_ID": setup.SECRET})
        self.assertEqual(args[-4:], ("--timeout", "900", "--revision-id", "revision"))

    def test_idempotent_config_and_custom_secret_are_preserved(self):
        current = self.current()
        current["Timeout"] = 900
        current["Environment"]["Variables"]["OPP_SECRET_ID"] = "team07/custom"
        with patch.object(setup, "aws", return_value={}) as aws:
            setup.set_lambda_config(current)
        aws.assert_called_once_with("secretsmanager", "describe-secret", "--secret-id", "team07/custom")

    def test_missing_variables_stops_before_mutations(self):
        current = self.current()
        del current["Environment"]["Variables"]["MODEL_ID"]
        with patch.object(setup, "aws") as aws, self.assertRaises(RuntimeError):
            setup.set_lambda_config(current)
        aws.assert_not_called()

    def test_schedule_create_and_update_have_exact_time_and_payload(self):
        for exists in (True, False):
            written = []
            def aws(service, action, *args):
                if action == "get-schedule" and not exists:
                    raise setup.AwsError(service, action, not_found=True)
                if action in ("create-schedule", "update-schedule"):
                    written.append((action, json.loads(Path(args[1][7:]).read_text())))
                return {}
            with patch.object(setup, "aws", side_effect=aws):
                for name, cron, event in setup.SCHEDULES:
                    setup.put_schedule(name, cron, event, ARN, ROLE, disabled=False)
            self.assertEqual([x[0] for x in written], ["update-schedule" if exists else "create-schedule"] * 2)
            self.assertEqual([x[1]["ScheduleExpression"] for x in written],
                             ["cron(30 4 * * ? *)", "cron(0 5 ? * MON *)"])
            for (_, spec), (_, _, event) in zip(written, setup.SCHEDULES):
                self.assertEqual(spec["ScheduleExpressionTimezone"], "Asia/Seoul")
                self.assertEqual(json.loads(spec["Target"]["Input"]), {"oppBatch": event})
                self.assertEqual(spec["Target"]["Arn"], ARN)
                self.assertEqual(spec["State"], "ENABLED")

    def test_permission_failure_does_not_try_to_create(self):
        with patch.object(setup, "aws", side_effect=setup.AwsError("scheduler", "get-schedule")) as aws:
            with self.assertRaises(setup.AwsError):
                setup.put_schedule("team07-opp-daily-ingest", "cron(30 4 * * ? *)", {}, ARN, ROLE, disabled=False)
        self.assertEqual(aws.call_count, 1)

    def test_disabled_mode_leaves_lambda_configuration_unchanged(self):
        def aws(service, action, *args):
            return self.current() if action == "get-function-configuration" else {}
        with patch.object(setup, "aws", side_effect=aws), patch.object(setup, "set_lambda_config") as config, \
             patch.object(setup, "put_schedule") as put:
            setup.configure(disabled=True)
        config.assert_not_called()
        self.assertEqual(put.call_count, 2)
        self.assertTrue(all(c.kwargs["disabled"] for c in put.call_args_list))


if __name__ == "__main__":
    unittest.main()
