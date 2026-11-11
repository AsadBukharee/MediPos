from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("stock", api.StockViewSet, basename="stock")
router.register("batches", api.BatchViewSet, basename="batch")
router.register("movements", api.StockMovementViewSet, basename="movement")
router.register("adjustments", api.AdjustmentViewSet, basename="adjustment")
urlpatterns = router.urls
