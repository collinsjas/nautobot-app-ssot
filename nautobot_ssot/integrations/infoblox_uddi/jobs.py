"""Jobs for Infoblox Universal DDI integration with SSoT app."""

import traceback

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

from .constant import DNS_OWNER_FIELD
from .diffsync.adapters import infoblox_uddi, nautobot
from .diffsync.adapters.nautobot import SYNC_TAG_NAME
from .diffsync.models.nautobot import claim_ownership, get_conflicting_ownership_tags
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
        try:
            self._load_source_adapter()
        except Exception:
            # The parallel loader only reports the exception message, so log the traceback here.
            self.logger.error("Infoblox Universal DDI load failed:\n%s", traceback.format_exc())
            raise

    def _load_source_adapter(self):
        """Connect to Infoblox Universal DDI and load its data."""
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
        try:
            self._load_target_adapter()
        except Exception:
            self.logger.error("Nautobot load failed:\n%s", traceback.format_exc())
            raise

    def _load_target_adapter(self):
        """Connect to Nautobot and load its data."""
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
        mask_changes = {}
        dns_zones = []
        dns_matches = []

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
            source_masks = {
                (item.address, item.namespace): item.prefix_length for item in source_adapter.get_all("ipaddress")
            }
            ip_matches = self._get_untagged_matches(
                IPAddress.objects.filter(parent__namespace_id=config.default_namespace_id).select_related(
                    "parent__namespace"
                ),
                tag,
                source_masks,
                lambda obj: (str(obj.host), obj.parent.namespace.name),
            )
            for ip_address in ip_matches:
                new_mask = source_masks[(str(ip_address.host), ip_address.parent.namespace.name)]
                if ip_address.mask_length != new_mask:
                    mask_changes[ip_address.pk] = new_mask
                    self.logger.info(
                        "Mask of %s will be changed to /%d to match Infoblox Universal DDI.", ip_address, new_mask
                    )
            matching.extend(ip_matches)

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
            if not config.import_dns_zones:
                source_adapter.load_dns_zones()
            dns_zones, dns_matches = self._get_dns_matches(source_adapter, tag, config)
            matching.extend(dns_matches)
            if config.import_dns_zones:
                matching.extend(dns_zones)
            for zone in dns_zones:
                self.logger.info("Matching DNS zone for ownership: %s (view %s)", zone, _dns_view_name(zone))

        self.logger.info(
            "Found %d Nautobot objects eligible for Infoblox Universal DDI tagging.",
            len(matching),
        )
        for obj in matching:
            self.logger.info("Matching object: %s (%s)", obj, obj._meta.label)
            other_tags = get_conflicting_ownership_tags(obj, tag)
            if other_tags:
                self.logger.info(
                    "Other SSoT tags on %s will be removed: %s", obj, ", ".join(sorted(t.name for t in other_tags))
                )

        if not apply_tags:
            self.logger.info("Preview only; no tags were applied. Enable 'Apply tags' to adopt these objects.")
            return
        if not matching and not dns_zones:
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
            owner = str(config.pk)
            eligible_zone_ids = set()
            for zone in sorted(dns_zones, key=lambda item: item.pk):
                locked_zone = type(zone).objects.select_for_update().get(pk=zone.pk)
                current_owner = locked_zone._custom_field_data.get(DNS_OWNER_FIELD)
                if current_owner and current_owner != owner:
                    self.logger.warning("DNS zone %s is owned by another configuration. Skipping.", locked_zone)
                    continue
                if not current_owner:
                    locked_zone._custom_field_data[DNS_OWNER_FIELD] = owner
                    locked_zone.save(update_fields=["_custom_field_data"])
                eligible_zone_ids.add(zone.pk)
            blocked_dns_objects = {zone for zone in dns_zones if zone.pk not in eligible_zone_ids}
            blocked_dns_objects.update(record for record in dns_matches if record.zone_id not in eligible_zone_ids)
            matching = [obj for obj in matching if obj not in blocked_dns_objects]
            content_types = {ContentType.objects.get_for_model(obj, for_concrete_model=False) for obj in matching}
            tag.content_types.add(*content_types)
            for obj in matching:
                if obj.pk in mask_changes:
                    obj.mask_length = mask_changes[obj.pk]
                    obj.validated_save()
                claim_ownership(obj, tag)
        self.logger.info("Applied the Infoblox SSoT tag to %d matching Nautobot objects.", len(matching))

    def _get_untagged_matches(self, queryset, tag, source_keys, key_function):
        """Return untagged objects in `queryset` whose identity exists in the source key set."""
        if tag is not None:
            queryset = queryset.exclude(tags=tag)
        return [obj for obj in queryset.iterator() if key_function(obj) in source_keys]

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
        source_zone_keys = {(zone.name, zone.view) for zone in source_zones if zone.view}
        owner = str(config.pk)
        zones = []
        for zone in DNSZone.objects.select_related("dns_view").filter(
            name__in={name for name, _ in source_zone_keys}
        ):
            if (zone.name, _dns_view_name(zone)) not in source_zone_keys:
                continue
            if zone._custom_field_data.get(DNS_OWNER_FIELD) not in (None, "", owner):
                self.logger.warning("DNS zone %s is owned by another configuration. Skipping.", zone)
                continue
            zones.append(zone)

        matches = []
        record_models = (
            ("dnsarecord", ARecord),
            ("dnsaaaarecord", AAAARecord),
            ("dnscnamerecord", CNAMERecord),
            ("dnsptrrecord", PTRRecord),
        )
        for model_name, orm_model in record_models:
            source_records = list(source_adapter.get_all(model_name))
            source_keys = {
                (*_dns_record_identity(record, model_name, source=True), record.view)
                for record in source_records
                if record.view
            }

            related_fields = ("zone", "zone__dns_view")
            if model_name in ("dnsarecord", "dnsaaaarecord"):
                related_fields += ("ip_address",)
            matches.extend(
                self._get_untagged_matches(
                    orm_model.objects.select_related(*related_fields).filter(
                        name__in={record.name for record in source_records},
                        zone_id__in={zone.pk for zone in zones},
                    ),
                    tag,
                    source_keys,
                    lambda obj: (*_dns_record_identity(obj, model_name, source=False), _dns_view_name(obj.zone)),
                )
            )
        return zones, matches


jobs = [InfobloxUDDIDataSource, InfobloxUDDIBrownfieldAdoption]
