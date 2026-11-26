"""DRF authentication class for the apps (kept separate from api.auth to avoid a settings import cycle)."""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


def _issued_too_early(user, token):
    from api.auth import _issued_too_early as check

    return check(user, token)


MESSAGE = "You were signed out (password changed or account updated). Please log in again."


class CouncilJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not user.is_active:
            raise AuthenticationFailed("This account has been deactivated.", code="user_inactive")
        if _issued_too_early(user, validated_token):
            raise AuthenticationFailed(MESSAGE, code="token_revoked")
        return user


