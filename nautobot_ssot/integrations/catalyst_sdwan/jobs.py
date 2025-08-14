"""Jobs for Catalyst SD-WAN SSoT app."""

from django.templatetags.static import static
from django.urls import reverse
from nautobot.dcim.models import Controller, Location
from nautobot.extras.jobs import BooleanVar, Job, ObjectVar

from nautobot_ssot.exceptions import ConfigurationError
from nautobot_ssot.integrations.catalyst_sdwan.diffsync.adapters.catalyst_sdwan import CatalystSdwanAdapter
from nautobot_ssot.integrations.catalyst_sdwan.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.catalyst_sdwan.diffsync.client import CatalystSdwanApi
from nautobot_ssot.jobs.base import DataMapping, DataSource
from nautobot_ssot.utils import get_username_password_https_from_secretsgroup, verify_controller_managed_device_group

name = "Cisco Catalyst SD-WAN SSoT"  # pylint: disable=invalid-name, abstract-method


class CatalystSdwanDataSource(DataSource, Job):  # pylint: disable=abstract-method, too-many-instance-attributes
    """Catalyst SD-WAN SSoT Data Source."""

    vmanage = ObjectVar(
        model=Controller,
        queryset=Controller.objects.all(),
        display_field="name",
        required=True,
        label="vManage Controller",
    )
    device_site = ObjectVar(
        model=Location,
        queryset=Location.objects.all(),
        display_field="name",
        required=False,
        label="Default Device Location",
        description="Default location for devices without site ID mapping.",
    )

    enable_site_mapping = BooleanVar(
        default=True,
        description="Enable automatic site mapping based on SD-WAN site IDs. "
                   "Devices will be placed in locations with matching catalyst_sdwan_site_id custom field."
    )

    debug = BooleanVar(description="Enable for verbose debug logging.")

    class Meta:  # pylint: disable=too-few-public-methods
        """Information about the Job."""

        name = "Cisco Catalyst SD-WAN Data Source"
        data_source = "Catalyst SD-WAN"
        data_source_icon = static("nautobot_ssot_catalyst_sdwan/catalyst_sdwan.png")
        description = "Sync information from Catalyst SD-WAN to Nautobot"

    @classmethod
    def data_mappings(cls):
        """Shows mapping of models between Catalyst SD-WAN and Nautobot."""
        return (
            DataMapping("Global Tenant", None, "Tenant", reverse("tenancy:tenant_list")),
            DataMapping("Device", None, "Device", reverse("dcim:device_list")),
            DataMapping("Device Model", None, "Device Type", reverse("dcim:devicetype_list")),
            DataMapping("Device Interface", None, "Interface", reverse("dcim:interface_list")),
            DataMapping("VPN", None, "VRF", reverse("ipam:vrf_list")),
            DataMapping("Device Template", None, "Config Context", reverse("extras:configcontext_list")),
        )

    def load_source_adapter(self):
        """Method to instantiate and load the Catalyst SD-WAN adapter into `self.source_adapter`."""
        if not self.device_site:
            self.logger.info("Device Location is unspecified so will revert to specified Controller's Location.")
        verify_controller_managed_device_group(controller=self.vmanage)
        if not self.vmanage.external_integration:
            self.logger.error("ExternalIntegration was not found on specified Controller.")
            raise ConfigurationError
        if not self.vmanage.external_integration.secrets_group:
            self.logger.error("SecretsGroup not found on %s", self.vmanage.external_integration)
            raise ConfigurationError
        username, password = get_username_password_https_from_secretsgroup(
            group=self.vmanage.external_integration.secrets_group
        )
        client = CatalystSdwanApi(
            username=username,
            password=password,
            base_uri=self.vmanage.external_integration.remote_url,
            verify=self.vmanage.external_integration.verify_ssl,
            site=self.device_site.name if self.device_site else self.vmanage.location.name,
        )
        self.source_adapter = CatalystSdwanAdapter(
            job=self,
            sync=self.sync,
            client=client,
            tenant_prefix=self.vmanage.external_integration.extra_config.get("tenant_prefix", "Catalyst-SDWAN"),
        )
        self.source_adapter.load()

    def load_target_adapter(self):
        """Method to instantiate and load the Nautobot adapter into `self.target_adapter`."""
        self.target_adapter = NautobotAdapter(
            job=self, 
            sync=self.sync, 
            site_name=self.device_site.name if self.device_site else self.vmanage.location.name
        )
        self.target_adapter.load()

    def run(  # pylint: disable=arguments-differ, too-many-arguments
        self, dryrun, memory_profiling, vmanage, device_site, enable_site_mapping, debug, *args, **kwargs
    ):
        """Perform data synchronization."""
        self.vmanage = vmanage
        self.device_site = device_site
        self.enable_site_mapping = enable_site_mapping
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [CatalystSdwanDataSource]
