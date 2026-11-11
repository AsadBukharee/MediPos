from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import exceptions, permissions, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.audit.services import log_action
from apps.branches.models import Branch
from apps.common.api import AuditedMixin, PermMixin
from apps.common.schema import documented

from . import permissions as perms

User = get_user_model()


class BranchBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "code", "kind"]


class MeSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="effective_role")
    permissions = serializers.SerializerMethodField()
    branches = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone", "role",
                  "max_discount_percent", "permissions", "branches"]

    def get_permissions(self, obj) -> list[str]:
        return sorted(obj.permission_codes)

    def get_branches(self, obj) -> list[dict]:
        return BranchBriefSerializer(obj.accessible_branches(), many=True).data


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = MeSerializer(self.user).data
        log_action(user=self.user, action="login", request=self.context.get("request"))
        return data


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    throttle_scope = "auth"


class LogoutView(APIView):
    @documented("Sign out: blacklist the refresh token", body=True, empty=True)
    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            pass  # already expired or blacklisted: the session is over either way
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    @documented("The signed-in user, with permissions and branches")
    def get(self, request):
        return Response(MeSerializer(request.user).data)


class ChangePasswordView(APIView):
    throttle_scope = "auth"

    @documented("Change your own password (current_password, new_password)", body=True, empty=True)
    def post(self, request):
        current = request.data.get("current_password", "")
        new = request.data.get("new_password", "")
        if not request.user.check_password(current):
            raise exceptions.ValidationError({"current_password": "Wrong password."})
        password_validation.validate_password(new, request.user)
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        log_action(user=request.user, action="password_change", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    @documented("Email a password reset link (email)", body=True)
    def post(self, request):
        email = str(request.data.get("email", "")).strip()
        user = User.objects.filter(email__iexact=email, is_active=True).first() if email else None
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            send_mail("Reset your MediPos password", f"Open this link to choose a new password:\n{link}",
                      settings.DEFAULT_FROM_EMAIL, [user.email])
        # Always the same answer, so the endpoint cannot be used to discover accounts.
        return Response({"detail": "If the email exists, a reset link has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    @documented("Set a new password from a reset link (uid, token, new_password)", body=True, empty=True)
    def post(self, request):
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(request.data.get("uid", ""))))
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            user = None
        if user is None or not default_token_generator.check_token(user, request.data.get("token", "")):
            raise exceptions.ValidationError({"token": "The reset link is invalid or has expired."})
        new = request.data.get("new_password", "")
        password_validation.validate_password(new, user)
        user.set_password(new)
        user.save(update_fields=["password"])
        log_action(user=user, action="password_reset", request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    branches = serializers.PrimaryKeyRelatedField(many=True, queryset=Branch.objects.all(), required=False)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone", "role", "branches",
                  "max_discount_percent", "is_active", "password", "last_login"]
        read_only_fields = ["last_login"]

    def validate(self, attrs):
        actor = self.context["request"].user
        if not actor.is_owner:
            if attrs.get("role") == perms.OWNER:
                raise serializers.ValidationError({"role": "Only an owner can create another owner."})
            allowed = set(actor.accessible_branches().values_list("pk", flat=True))
            if any(b.pk not in allowed for b in attrs.get("branches", [])):
                raise serializers.ValidationError({"branches": "You can only assign your own branches."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "This field is required."})
        branches = validated_data.pop("branches", [])
        user = User(**validated_data)
        password_validation.validate_password(password, user)
        user.set_password(password)
        user.save()
        user.branches.set(branches)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            password_validation.validate_password(password, instance)
            instance.set_password(password)
        return super().update(instance, validated_data)


class UserViewSet(AuditedMixin, PermMixin, viewsets.ModelViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.none()  # for schema generation; see get_queryset
    read_perm = write_perm = "users.manage"
    search_fields = ["username", "first_name", "last_name", "email"]
    filterset_fields = ["role", "is_active"]
    http_method_names = ["get", "post", "patch", "head", "options"]  # users are deactivated, never deleted

    def get_queryset(self):
        actor = self.request.user
        qs = User.objects.prefetch_related("branches").order_by("username")
        if not actor.is_owner:
            qs = qs.filter(branches__in=actor.accessible_branches()).exclude(role=perms.OWNER).distinct()
        return qs


class RoleListView(APIView):
    @documented("Roles and the permissions each one grants")
    def get(self, request):
        return Response([
            {"role": role, "label": label, "permissions": sorted(perms.ROLE_PERMISSIONS[role])}
            for role, label in perms.ROLE_CHOICES
        ])
