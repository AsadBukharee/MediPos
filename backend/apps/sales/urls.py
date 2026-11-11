from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("returns", api.SaleReturnViewSet, basename="sale-return")
router.register("shifts", api.ShiftViewSet, basename="shift")
router.register("", api.SaleViewSet, basename="sale")
urlpatterns = router.urls
