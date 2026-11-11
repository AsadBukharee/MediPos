from rest_framework.routers import DefaultRouter

from . import api

router = DefaultRouter()
router.register("requisitions", api.RequisitionViewSet, basename="requisition")
router.register("orders", api.PurchaseOrderViewSet, basename="purchase-order")
router.register("grns", api.GRNViewSet, basename="grn")
router.register("returns", api.PurchaseReturnViewSet, basename="purchase-return")
urlpatterns = router.urls
