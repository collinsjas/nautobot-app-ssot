"""Jobs for Infoblox Universal DDI integration with SSoT app."""

from diffsync.enum import DiffSyncFlags
from django.urls import reverse
from nautobot.apps.jobs import ObjectVar
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.jobs import BooleanVar

from nautobot_ssot.jobs.base import DataMapping, DataSource
from nautobot_ssot.utils import validate_dns_models_installed

from .diffsync.adapters import infoblox_uddi, nautobot
from .models import SSOTInfobloxUDDIConfig
from .utils.client import InfobloxUDDIApi

name = "SSoT - Infoblox Universal DDI"  # pylint: disable=invalid-name


def _get_uddi_client_config(app_config):
    """Get Infoblox Universal DDI client config from the config instance."""
    portal_key = app_config.uddi_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
    )
    return {
        "portal_url": app_config.uddi_instance.remote_url,
        "portal_key": portal_key,
        "verify_ssl": app_config.uddi_instance.verify_ssl,
        "timeout": app_config.uddi_instance.timeout,
    }


class InfobloxUDDIDataSource(DataSource):
    """Infoblox Universal DDI SSoT Data Source."""

    debug = BooleanVar(description="Enable for verbose debug logging.")
    config = ObjectVar(
        model=SSOTInfobloxUDDIConfig,
        display_field="SSOT Infoblox Universal DDI config",
        required=True,
        query_params={
            "enable_sync_to_nautobot": True,
            "job_enabled": True,
        },
    )

    def __init__(self):
        """Initialize InfobloxUDDIDataSource."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    class Meta:  # pylint: disable=too-few-public-methods
        """Information about the Job."""

        name = "Infoblox Universal DDI ⟹ Nautobot"
        data_source = "Infoblox Universal DDI"
        description = "Sync Prefixes/IP Addresses/DNS Zones/DNS Records from Infoblox Universal DDI to Nautobot"

    @classmethod
    def data_mappings(cls):
        """Show mapping of models between Infoblox Universal DDI and Nautobot."""
        return (
            DataMapping("subnet / address block", None, "Prefix", reverse("ipam:prefix_list")),
            DataMapping("address", None, "IP Address", reverse("ipam:ipaddress_list")),
            DataMapping("auth zone", None, "DNS Zone", None),
            DataMapping("record (A/AAAA/CNAME/PTR)", None, "DNS Record / IPAddress.dns_name", None),
        )

    def load_source_adapter(self):
        """Load Infoblox Universal DDI data."""
        self.logger.info("Connecting to Infoblox Universal DDI...")
        client_config = _get_uddi_client_config(self.config)
        client = InfobloxUDDIApi(**client_config)
        self.source_adapter = infoblox_uddi.InfobloxUDDIAdapter(job=self, sync=self.sync, conn=client, config=self.config)
        self.logger.info("Loading data from Infoblox Universal DDI...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load Nautobot data."""
        self.logger.info("Connecting to Nautobot...")
        self.target_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync, config=self.config)
        self.logger.info("Loading data from Nautobot...")
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, debug, *args, **kwargs):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.config = kwargs.get("config")
        if not self.config.enable_sync_to_nautobot:
            self.logger.error("Can't run sync to Nautobot, provided config doesn't have it enabled...")
            raise ValueError("Config not enabled for sync to Nautobot.")
        if validate_dns_models_installed():
            self.logger.info("nautobot-dns-models detected; syncing full-fidelity DNS Zone/Record objects.")
        else:
            self.logger.info(
                "DNS zone/record modules not found; falling back to IPAddress.dns_name-only DNS sync "
                "(CNAME records will be skipped)."
            )
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [InfobloxUDDIDataSource]
