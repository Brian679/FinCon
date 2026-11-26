"""JWT checks for the apps: a token issued before the user's password was changed, the
account was deactivated or the role changed is refused (lost or stolen phones)."""
from datetime import datetime, timezone as dt_tz

from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

MESSAGE = "You were signed out (password changed or account updated). Please log in again."


def _issued_too_early(user, token):
    if user is None or not user.tokens_valid_after:
        return False
    iat = token.get("iat")
    return iat is None or datetime.fromtimestamp(int(iat), tz=dt_tz.utc) < user.tokens_valid_after.replace(microsecond=0)


class CouncilRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        from accounts.models import User

        token = RefreshToken(attrs["refresh"])
        user = User.objects.filter(pk=token.get("user_id")).first()
        if user is None or not user.is_active or _issued_too_early(user, token):
            raise InvalidToken(MESSAGE)
        return super().validate(attrs)


class CouncilRefreshView(TokenRefreshView):
    serializer_class = CouncilRefreshSerializer
