from rest_framework.routers import DefaultRouter

from .api import AuditLogViewSet

router = DefaultRouter()
router.register("logs", AuditLogViewSet, basename="audit-log")
urlpatterns = router.urls
