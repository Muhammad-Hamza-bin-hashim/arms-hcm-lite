from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    refresh["ver"] = user.token_version
    refresh["role"] = user.role
    access = refresh.access_token
    return {"access": str(access), "refresh": str(refresh)}


class VersionedJWTAuthentication(JWTAuthentication):
    """Rejects tokens issued before the user's last logout / password change / deactivation."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)  # also rejects inactive users
        if validated_token.get("ver") != user.token_version:
            raise InvalidToken("Session expired. Please sign in again.")
        if not user.is_active:
            raise AuthenticationFailed("Account is deactivated.", code="user_inactive")
        return user
