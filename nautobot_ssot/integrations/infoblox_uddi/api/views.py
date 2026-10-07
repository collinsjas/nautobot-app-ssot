"""API views for nautobot_ssot infoblox_uddi."""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_ssot.integrations.infoblox_uddi.filters import SSOTInfobloxUDDIConfigFilterSet
from nautobot_ssot.integrations.infoblox_uddi.models import SSOTInfobloxUDDIConfig

from .serializers import SSOTInfobloxUDDIConfigSerializer


class SSOTInfobloxUDDIConfigView(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """API CRUD operations set for the SSOTInfobloxUDDIConfig view."""

    queryset = SSOTInfobloxUDDIConfig.objects.all()
    filterset_class = SSOTInfobloxUDDIConfigFilterSet
    serializer_class = SSOTInfobloxUDDIConfigSerializer
