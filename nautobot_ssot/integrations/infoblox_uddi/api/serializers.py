"""API serializers for nautobot_ssot infoblox_uddi."""

from nautobot.apps.api import NautobotModelSerializer

from nautobot_ssot.integrations.infoblox_uddi.models import SSOTInfobloxUDDIConfig


class SSOTInfobloxUDDIConfigSerializer(NautobotModelSerializer):  # pylint: disable=too-many-ancestors
    """REST API serializer for SSOTInfobloxUDDIConfig records."""

    class Meta:
        """Meta attributes."""

        model = SSOTInfobloxUDDIConfig
        fields = "__all__"
