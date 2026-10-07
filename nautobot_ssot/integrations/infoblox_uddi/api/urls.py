"""Django urlpatterns declaration for nautobot_ssot infoblox_uddi API."""

from rest_framework import routers

from nautobot_ssot.integrations.infoblox_uddi.api.views import SSOTInfobloxUDDIConfigView

router = routers.DefaultRouter()

router.register("config/infoblox-uddi", SSOTInfobloxUDDIConfigView)
app_name = "ssot"  # pylint: disable=invalid-name

urlpatterns = router.urls
