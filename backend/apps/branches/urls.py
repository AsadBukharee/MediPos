from django.urls import path
from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("", api.BranchViewSet, basename="branch")

urlpatterns = [path("profile/", api.BusinessProfileView.as_view(), name="business-profile")] + router.urls
