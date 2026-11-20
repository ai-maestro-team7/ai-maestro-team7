"""SES 메일 구현. 메일 알림에 동의한 사용자에게만 부르는 쪽(notify)이 책임지고, 여기서는 주소를 찾아 보내기만 한다."""

from collections.abc import Callable

from botocore.exceptions import BotoCoreError, ClientError

from ..models.errors import aws_service_error
from .dynamo import error_code

SERVICE = "ses"


class SesMailer:
    """`resolve_email(user_id)`가 받는 주소를 찾아 준다. 못 찾으면 보내지 않고 False.

    SES 샌드박스는 검증하지 않은 주소로 보내지 못한다(MessageRejected). 그 주소도 False로 돌려준다.
    """

    def __init__(self, client, *, from_address: str, resolve_email: Callable[[str], str | None],
                 configuration_set: str | None = None):
        self.client = client
        self.from_address = from_address
        self.resolve_email = resolve_email
        self.configuration_set = configuration_set

    def send(self, user_id: str, subject: str, body: str) -> bool:
        address = self.resolve_email(user_id)
        if not address:
            return False
        params = {
            "FromEmailAddress": self.from_address,
            "Destination": {"ToAddresses": [address]},
            "Content": {"Simple": {"Subject": {"Data": subject, "Charset": "UTF-8"},
                                   "Body": {"Text": {"Data": body, "Charset": "UTF-8"}}}},
        }
        if self.configuration_set:
            params["ConfigurationSetName"] = self.configuration_set
        try:
            self.client.send_email(**params)
        except ClientError as e:
            if error_code(e) == "MessageRejected":
                return False
            raise aws_service_error(SERVICE) from e
        except BotoCoreError as e:
            raise aws_service_error(SERVICE) from e
        return True


def cognito_email_resolver(client, user_pool_id: str) -> Callable[[str], str | None]:
    """Cognito 사용자 풀에서 userId(sub)의 이메일을 읽는 `resolve_email`. 사용자가 없거나 이메일이 없으면 None."""

    def resolve(user_id: str) -> str | None:
        try:
            user = client.admin_get_user(UserPoolId=user_pool_id, Username=user_id)
        except ClientError as e:
            if error_code(e) == "UserNotFoundException":
                return None
            raise aws_service_error("cognito-idp") from e
        except BotoCoreError as e:
            raise aws_service_error("cognito-idp") from e
        attributes = {a["Name"]: a.get("Value") for a in user.get("UserAttributes", [])}
        return attributes.get("email") or None

    return resolve
