"""Jobs for Infoblox Universal DDI integration with SSoT app."""

from diffsync.enum import DiffSyncFlags
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.urls import reverse
from nautobot.apps.jobs import Job, ObjectVar
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.jobs import BooleanVar
from nautobot.extras.models import Tag
from nautobot.ipam.models import IPAddress, IPAddressRange, Prefix

from nautobot_ssot.jobs.base import DataMapping, DataSource
from nautobot_ssot.utils import validate_dns_models_installed

from .diffsync.adapters import infoblox_uddi, nautobot
from .diffsync.adapters.nautobot import SYNC_TAG_NAME
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


def _dns_record_identity(record, model_name, source):
    """Return a DNS record identity tuple for the source or Nautobot representation."""
    zone = record.zone if source else record.zone.name
    if model_name in ("dnsarecord", "dnsaaaarecord"):
        address = record.address if source else str(record.ip_address.host)
        return record.name, zone, address
    if model_name == "dnscnamerecord":
        return record.name, zone, record.alias
    return record.name, zone, record.ptrdname


def _dns_view_name(zone):
    """Return a DNS Zone's view name, or an empty string when it has no view."""
    return zone.dns_view.name if zone.dns_view else ""


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
        description = "Sync Prefixes/IP Addresses/IP Ranges/DNS Zones/DNS Records from Infoblox Universal DDI to Nautobot"

    @classmethod
    def data_mappings(cls):
        """Show mapping of models between Infoblox Universal DDI and Nautobot."""
        return (
            DataMapping("subnet / address block", None, "Prefix", reverse("ipam:prefix_list")),
            DataMapping("address", None, "IP Address", reverse("ipam:ipaddress_list")),
            DataMapping("range", None, "IP Address Range", reverse("ipam:ipaddressrange_list")),
            DataMapping("auth zone", None, "DNS Zone", None),
            DataMapping("record (A/AAAA/CNAME/PTR)", None, "DNS Record / IPAddress.dns_name", None),
        )

    def load_source_adapter(self):
        """Load Infoblox Universal DDI data."""
        self.logger.info("Connecting to Infoblox Universal DDI...")
        if self.debug:
            self.logger.debug("Debug Test")
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


class InfobloxUDDIBrownfieldAdoption(Job):
    """Tag existing Nautobot records that match the configured Infoblox data."""

    config = ObjectVar(
        model=SSOTInfobloxUDDIConfig,
        display_field="SSOT Infoblox Universal DDI config",
        required=True,
        query_params={"enable_sync_to_nautobot": True, "job_enabled": True},
    )
    apply_tags = BooleanVar(
        label="Apply tags",
        description="When disabled, only report matching untagged Nautobot objects. Enable to apply the sync tag.",
        default=False,
    )

    class Meta:  # pylint: disable=too-few-public-methods
        """Job metadata."""

        name = "Infoblox Universal DDI Brownfield Adoption"
        description = (
            "Preview or tag existing Nautobot objects that match data currently present in the configured "
            "Infoblox Universal DDI IP Space and DNS View."
        )

    def run(self, *args, **kwargs):
        """Find matching Nautobot objects and optionally apply the Infoblox SSoT tag."""
        config = kwargs.get("config")
        if not config:
            raise ValueError("An Infoblox Universal DDI configuration is required.")
        if not config.enable_sync_to_nautobot:
            raise ValueError("The selected configuration does not have sync to Nautobot enabled.")

        self.config = config
        apply_tags = kwargs.get("apply_tags", False)
        client = InfobloxUDDIApi(**_get_uddi_client_config(config))
        source_adapter = infoblox_uddi.InfobloxUDDIAdapter(job=self, sync=None, conn=client, config=config)
        self.logger.info("Loading current data from Infoblox Universal DDI for adoption matching...")
        source_adapter.load()

        tag = Tag.objects.filter(name=SYNC_TAG_NAME).first()
        matching = []

        if config.import_prefixes:
            source_keys = {(item.network, item.namespace) for item in source_adapter.get_all("prefix")}
            matching.extend(
                self._get_untagged_matches(
                    Prefix.objects.filter(namespace_id=config.default_namespace_id).select_related("namespace"),
                    tag,
                    source_keys,
                    lambda obj: (str(obj.prefix), obj.namespace.name),
                )
            )

        if config.import_ip_addresses:
            source_keys = {
                (item.address, item.prefix_length, item.namespace) for item in source_adapter.get_all("ipaddress")
            }
            matching.extend(
                self._get_untagged_matches(
                    IPAddress.objects.filter(parent__namespace_id=config.default_namespace_id).select_related(
                        "parent__namespace"
                    ),
                    tag,
                    source_keys,
                    lambda obj: (str(obj.host), obj.mask_length, obj.parent.namespace.name),
                )
            )

        if config.import_ip_ranges:
            source_keys = {(item.start_address, item.namespace) for item in source_adapter.get_all("ipaddressrange")}
            matching.extend(
                self._get_untagged_matches(
                    IPAddressRange.objects.filter(parent__namespace_id=config.default_namespace_id).select_related(
                        "parent__namespace"
                    ),
                    tag,
                    source_keys,
                    lambda obj: (str(obj.start_address), obj.parent.namespace.name),
                )
            )

        if (config.import_dns_zones or config.import_dns_records) and validate_dns_models_installed():
            matching.extend(self._get_dns_matches(source_adapter, tag, config))

        self.logger.info(
            "Found %d untagged Nautobot objects matching Infoblox Universal DDI.",
            len(matching),
        )
        for obj in matching:
            self.logger.info("Matching object: %s (%s)", obj, obj._meta.label)

        if not apply_tags:
            self.logger.info("Preview only; no tags were applied. Enable 'Apply tags' to adopt these objects.")
            return
        if not matching:
            self.logger.info("No matching untagged objects found; no tags were applied.")
            return

        with transaction.atomic():
            if tag is None:
                tag, _ = Tag.objects.get_or_create(
                    name=SYNC_TAG_NAME,
                    defaults={
                        "name": SYNC_TAG_NAME,
                        "description": "Objects managed by Infoblox Universal DDI SSoT.",
                    },
                )
            content_types = {ContentType.objects.get_for_model(obj, for_concrete_model=False) for obj in matching}
            tag.content_types.add(*content_types)
            for obj in matching:
                obj.tags.add(tag)
        self.logger.info("Applied the Infoblox SSoT tag to %d matching Nautobot objects.", len(matching))

    def _get_untagged_matches(self, queryset, tag, source_keys, key_function):
        """Return untagged objects in `queryset` whose identity exists in the source key set."""
        if tag is not None:
            queryset = queryset.exclude(tags=tag)
        return [
            obj
            for obj in queryset.iterator()
            if key_function(obj) in source_keys
        ]

    def _get_dns_matches(self, source_adapter, tag, config):
        """Find matching DNS objects without adopting same-named zones in a different DNS View."""
        from nautobot_dns_models.models import (  # pylint: disable=import-outside-toplevel
            AAAARecord,
            ARecord,
            CNAMERecord,
            DNSZone,
            PTRRecord,
        )

        source_zones = list(source_adapter.get_all("dnszone"))
        zones_by_name = {}
        for zone in source_zones:
            zones_by_name.setdefault(zone.name, set()).add(zone.view)

        matches = []
        if config.import_dns_zones:
            matches.extend(
                self._get_untagged_matches(
                    DNSZone.objects.select_related("dns_view").filter(name__in={zone.name for zone in source_zones}),
                    tag,
                    {(zone.name, zone.view) for zone in source_zones if zone.view},
                    lambda obj: (obj.name, _dns_view_name(obj)),
                )
            )

        if config.dns_view and not source_zones:
            zones_by_name = {
                record.zone: {config.dns_view}
                for name in (
                    "dnsarecord",
                    "dnsaaaarecord",
                    "dnscnamerecord",
                    "dnsptrrecord",
                )
                for record in source_adapter.get_all(name)
            }

        record_models = (
            ("dnsarecord", ARecord),
            ("dnsaaaarecord", AAAARecord),
            ("dnscnamerecord", CNAMERecord),
            ("dnsptrrecord", PTRRecord),
        )
        ambiguous_records = False
        for model_name, orm_model in record_models:
            source_records = list(source_adapter.get_all(model_name))
            source_keys = set()
            for record in source_records:
                views = zones_by_name.get(record.zone, set())
                if len(views) == 1:
                    view = next(iter(views))
                    if view:
                        source_keys.add((*_dns_record_identity(record, model_name, source=True), view))
                    else:
                        ambiguous_records = True
                else:
                    ambiguous_records = True

            related_fields = ("zone", "zone__dns_view")
            if model_name in ("dnsarecord", "dnsaaaarecord"):
                related_fields += ("ip_address",)
            matches.extend(
                self._get_untagged_matches(
                    orm_model.objects.select_related(*related_fields).filter(
                        name__in={record.name for record in source_records},
                        zone__name__in={record.zone for record in source_records},
                    ),
                    tag,
                    source_keys,
                    lambda obj: (*_dns_record_identity(obj, model_name, source=False), _dns_view_name(obj.zone)),
                )
            )
        if ambiguous_records:
            self.logger.warning(
                "Some DNS records were excluded from adoption because their DNS View could not be determined "
                "unambiguously."
            )
        return matches


jobs = [InfobloxUDDIDataSource, InfobloxUDDIBrownfieldAdoption]
