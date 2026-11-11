from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("payments", api.CustomerPaymentViewSet, basename="customer-payment")
router.register("", api.CustomerViewSet, basename="customer")
urlpatterns = router.urls
