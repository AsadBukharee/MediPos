from django.urls import path
from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("users", api.UserViewSet, basename="user")

urlpatterns = [
    path("login/", api.LoginView.as_view(), name="login"),
    path("refresh/", api.RefreshView.as_view(), name="refresh"),
    path("logout/", api.LogoutView.as_view(), name="logout"),
    path("me/", api.MeView.as_view(), name="me"),
    path("roles/", api.RoleListView.as_view(), name="roles"),
    path("password/change/", api.ChangePasswordView.as_view(), name="password-change"),
    path("password/reset/", api.PasswordResetRequestView.as_view(), name="password-reset"),
    path("password/reset/confirm/", api.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
] + router.urls
