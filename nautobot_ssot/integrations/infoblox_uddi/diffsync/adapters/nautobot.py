"""DiffSync adapter for loading data from Nautobot for the Infoblox Universal DDI integration."""

from diffsync import DiffSync
from diffsync.exceptions import ObjectAlreadyExists
from nautobot.extras.models import Tag
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import IPAddressRange as OrmIPAddressRange
from nautobot.ipam.models import Prefix as OrmPrefix

from nautobot_ssot.utils import validate_dns_models_installed

from ...models import SSOTInfobloxUDDIConfig
from ..models import nautobot as nb_models

SYNC_TAG_NAME = "SSoT Synced from Infoblox Universal DDI"


class NautobotAdapter(DiffSync):
    """DiffSync adapter for loading data from Nautobot."""

    prefix = nb_models.Prefix
    ipaddress = nb_models.IPAddress
    ipaddressrange = nb_models.IPAddressRange
    dnszone = nb_models.DnsZone
    dnsarecord = nb_models.DnsARecord
    dnsaaaarecord = nb_models.DnsAaaaRecord
    dnscnamerecord = nb_models.DnsCnameRecord
    dnsptrrecord = nb_models.DnsPtrRecord

    top_level = [
        "prefix",
        "ipaddress",
        "ipaddressrange",
        "dnszone",
        "dnsarecord",
        "dnsaaaarecord",
        "dnscnamerecord",
        "dnsptrrecord",
    ]

    def __init__(self, *args, job=None, sync=None, config: SSOTInfobloxUDDIConfig = None, **kwargs):
        """Initialize NautobotAdapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.config = config
        self.namespace_id = config.default_namespace_id if config else None
        self.sync_tag, _ = Tag.objects.get_or_create(name=SYNC_TAG_NAME, defaults={"name": SYNC_TAG_NAME})

    def load_prefixes(self):
        """Load Prefixes from Nautobot."""
        for prefix in OrmPrefix.objects.filter(namespace_id=self.namespace_id, tags=self.sync_tag):
            new_prefix = self.prefix(
                network=str(prefix.prefix),
                namespace=prefix.namespace.name,
                prefix_type=prefix.type,
                description=prefix.description,
                status=prefix.status.name,
            )
            try:
                self.add(new_prefix)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate prefix found: {new_prefix}.")

    def load_ip_addresses(self):
        """Load IP Addresses from Nautobot."""
        for ipaddr in OrmIPAddress.objects.filter(parent__namespace_id=self.namespace_id, tags=self.sync_tag):
            new_ipaddress = self.ipaddress(
                address=str(ipaddr.host),
                prefix_length=ipaddr.mask_length,
                namespace=ipaddr.parent.namespace.name,
                status=ipaddr.status.name,
                description=ipaddr.description,
                dns_name=ipaddr.dns_name,
            )
            try:
                self.add(new_ipaddress)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate IP Address found: {new_ipaddress}.")

    def load_ip_ranges(self):
        """Load IP Address Ranges from Nautobot."""
        for ip_range in OrmIPAddressRange.objects.filter(parent__namespace_id=self.namespace_id, tags=self.sync_tag):
            new_range = self.ipaddressrange(
                start_address=str(ip_range.start_address),
                end_address=str(ip_range.end_address),
                namespace=ip_range.parent.namespace.name,
                name=ip_range.name,
                description=ip_range.description,
            )
            try:
                self.add(new_range)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate IP Address Range found: {new_range}.")

    def load_dns_zones(self):
        """Load DNS Zones from Nautobot, if `nautobot-dns-models` is installed."""
        if not validate_dns_models_installed():
            return
        from nautobot_dns_models.models import DNSZone  # pylint: disable=import-outside-toplevel

        for zone in DNSZone.objects.filter(tags=self.sync_tag):
            new_zone = self.dnszone(name=zone.name, ttl=zone.ttl, view=zone.dns_view.name)
            try:
                self.add(new_zone)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate DNS Zone found: {new_zone}.")

    def load_dns_records(self):
        """Load DNS Records from Nautobot, if `nautobot-dns-models` is installed."""
        if not validate_dns_models_installed():
            return
        from nautobot_dns_models.models import (  # pylint: disable=import-outside-toplevel
            AAAARecord,
            ARecord,
            CNAMERecord,
            PTRRecord,
        )

        for record in ARecord.objects.filter(tags=self.sync_tag):
            new_record = self.dnsarecord(
                name=record.name, zone=record.zone.name, address=str(record.ip_address.host), ttl=record.ttl
            )
            try:
                self.add(new_record)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate DNS A record found: {new_record}.")
        for record in AAAARecord.objects.filter(tags=self.sync_tag):
            new_record = self.dnsaaaarecord(
                name=record.name, zone=record.zone.name, address=str(record.ip_address.host), ttl=record.ttl
            )
            try:
                self.add(new_record)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate DNS AAAA record found: {new_record}.")
        for record in CNAMERecord.objects.filter(tags=self.sync_tag):
            new_record = self.dnscnamerecord(
                name=record.name, zone=record.zone.name, alias=record.alias, ttl=record.ttl
            )
            try:
                self.add(new_record)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate DNS CNAME record found: {new_record}.")
        for record in PTRRecord.objects.filter(tags=self.sync_tag):
            new_record = self.dnsptrrecord(
                name=record.name, zone=record.zone.name, ptrdname=record.ptrdname, ttl=record.ttl
            )
            try:
                self.add(new_record)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate DNS PTR record found: {new_record}.")

    def load(self):
        """Load data from Nautobot."""
        self.load_prefixes()
        self.load_ip_addresses()
        if self.config.import_ip_ranges:
            self.load_ip_ranges()
        if self.config.import_dns_zones:
            self.load_dns_zones()
        if self.config.import_dns_records:
            self.load_dns_records()
