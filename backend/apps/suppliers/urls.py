from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("prices", api.SupplierProductViewSet, basename="supplier-price")
router.register("payments", api.SupplierPaymentViewSet, basename="supplier-payment")
router.register("", api.SupplierViewSet, basename="supplier")
urlpatterns = router.urls
