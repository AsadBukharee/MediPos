from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("categories", api.CategoryViewSet, basename="category")
router.register("manufacturers", api.ManufacturerViewSet, basename="manufacturer")
router.register("units", api.UnitViewSet, basename="unit")
router.register("barcodes", api.BarcodeViewSet, basename="barcode")
router.register("branch-prices", api.BranchPriceViewSet, basename="branch-price")
router.register("products", api.ProductViewSet, basename="product")
urlpatterns = router.urls
