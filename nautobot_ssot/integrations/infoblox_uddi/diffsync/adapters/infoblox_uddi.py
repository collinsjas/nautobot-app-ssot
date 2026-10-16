"""DiffSync adapter for loading data from Infoblox Universal DDI (BloxOne CSP)."""

import ipaddress

from diffsync import DiffSync
from diffsync.exceptions import ObjectAlreadyExists

from nautobot_ssot.integrations.infoblox_uddi.diffsync.models import base

# NOTE: attribute names below (`.address`, `.cidr`, `.space`, `.tags`, `.name`, `.zone`,
# `.type`, `.rdata`, `.ttl`) follow the documented BloxOne CSP OpenAPI schema but have not
# been verified against the installed SDK's generated model classes - adjust as needed
# once that verification (plan item 3 in "Further Considerations") is done.


class InfobloxUDDIAdapter(DiffSync):
    """DiffSync adapter for Infoblox Universal DDI (BloxOne CSP)."""

    prefix = base.Prefix
    ipaddress = base.IPAddress
    dnszone = base.DnsZone
    dnsarecord = base.DnsARecord
    dnsaaaarecord = base.DnsAaaaRecord
    dnscnamerecord = base.DnsCnameRecord
    dnsptrrecord = base.DnsPtrRecord

    top_level = ["prefix", "ipaddress", "dnszone", "dnsarecord", "dnsaaaarecord", "dnscnamerecord", "dnsptrrecord"]

    def __init__(self, *args, job=None, sync=None, conn=None, config=None, **kwargs):
        """Initialize InfobloxUDDIAdapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = conn
        self.config = config
        self._ip_space_id = None
        self._dns_view_id = False
        self._subnet_networks = []

    def _get_ip_space_id(self) -> str:
        """Resolve and cache the configured IP Space's BloxOne id."""
        if self._ip_space_id is None:
            ip_space = self.conn.get_ip_space(self.config.uddi_ip_space)
            if ip_space is None:
                raise ValueError(f"IP Space '{self.config.uddi_ip_space}' not found in Infoblox Universal DDI.")
            self._ip_space_id = ip_space.id
        return self._ip_space_id

    def _get_dns_view_id(self) -> str | None:
        """Resolve and cache the configured DNS View's BloxOne id, or None to sync all views."""
        if self._dns_view_id is False:
            dns_view_name = getattr(self.config, "dns_view", "") or ""
            if not dns_view_name:
                self._dns_view_id = None
            else:
                dns_view = self.conn.get_dns_view(dns_view_name)
                if dns_view is None:
                    raise ValueError(f"DNS View '{dns_view_name}' not found in Infoblox Universal DDI.")
                self._dns_view_id = dns_view.id
        return self._dns_view_id

    def load_prefixes(self):
        """Load Prefixes (AddressBlocks as containers, Subnets as networks) from BloxOne.

        BloxOne `AddressBlock`/`Subnet` objects expose `address` (bare network IP) and `cidr`
        (prefix length) as separate fields per the OpenAPI spec, so they're combined here into
        the CIDR notation Nautobot's `ipam.Prefix.prefix` field expects.
        """
        ip_space_id = self._get_ip_space_id()
        namespace = self.config.default_namespace.name
        for block in self.conn.list_address_blocks(ip_space_id):
            network_str = f"{block.address}/{block.cidr}"
            new_prefix = self.prefix(
                network=network_str,
                namespace=namespace,
                prefix_type="container",
                description=getattr(block, "comment", None),
            )
            try:
                self.add(new_prefix)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate prefix found: {new_prefix}.")
        for subnet in self.conn.list_subnets(ip_space_id):
            network_str = f"{subnet.address}/{subnet.cidr}"
            network = ipaddress.ip_network(network_str, strict=False)
            self._subnet_networks.append(network)
            new_prefix = self.prefix(
                network=network_str,
                namespace=namespace,
                prefix_type="network",
                description=getattr(subnet, "comment", None),
            )
            try:
                self.add(new_prefix)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate prefix found: {new_prefix}.")

    def _containing_prefix_length(self, address: str) -> int:
        """Return the prefix length of the loaded subnet containing `address`.

        Defaults to a host mask (/32 or /128) if no containing subnet was loaded.
        """
        host = ipaddress.ip_address(address)
        for network in self._subnet_networks:
            if host in network:
                return network.prefixlen
        return host.max_prefixlen

    def load_ip_addresses(self):
        """Load IP Addresses from BloxOne."""
        ip_space_id = self._get_ip_space_id()
        namespace = self.config.default_namespace.name
        for address in self.conn.list_addresses(ip_space_id):
            new_ipaddress = self.ipaddress(
                address=address.address,
                prefix_length=self._containing_prefix_length(address.address),
                namespace=namespace,
                description=getattr(address, "comment", None),
            )
            try:
                self.add(new_ipaddress)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate IP Address found: {new_ipaddress}.")

    def load_dns_zones(self):
        """Load DNS Zones from BloxOne, scoped to the configured DNS View if set."""
        for zone in self.conn.list_dns_zones(view_id=self._get_dns_view_id()):
            new_zone = self.dnszone(name=zone.fqdn, ttl=getattr(zone, "ttl", None))
            try:
                self.add(new_zone)
            except ObjectAlreadyExists:
                self.job.logger.warning(f"Duplicate DNS Zone found: {new_zone}.")

    def load_dns_records(self):
        """Load DNS Records from BloxOne, batched per-zone, filtered by configured record types."""
        record_type_map = {
            "A": self.dnsarecord,
            "AAAA": self.dnsaaaarecord,
            "CNAME": self.dnscnamerecord,
            "PTR": self.dnsptrrecord,
        }
        for zone in self.conn.list_dns_zones(view_id=self._get_dns_view_id()):
            for record_type in self.config.dns_record_types:
                model_cls = record_type_map.get(record_type)
                if model_cls is None:
                    continue
                for record in self.conn.list_dns_records(zone.id, record_type=record_type):
                    self._add_dns_record(model_cls, record_type, zone.fqdn, record)

    def _add_dns_record(self, model_cls, record_type, zone_fqdn, record):
        """Build and add a single DNS record DiffSyncModel instance."""
        rdata = getattr(record, "rdata", {}) or {}
        name = getattr(record, "name_in_zone", "") or ""
        ttl = getattr(record, "ttl", None)
        if record_type in ("A", "AAAA"):
            new_record = model_cls(name=name, zone=zone_fqdn, address=rdata.get("address"), ttl=ttl)
        elif record_type == "CNAME":
            new_record = model_cls(name=name, zone=zone_fqdn, alias=rdata.get("cname"), ttl=ttl)
        elif record_type == "PTR":
            new_record = model_cls(name=name, zone=zone_fqdn, ptrdname=rdata.get("dname"), ttl=ttl)
        else:
            return
        try:
            self.add(new_record)
        except ObjectAlreadyExists:
            self.job.logger.warning(f"Duplicate DNS {record_type} record found: {new_record}.")

    def load(self):
        """Load data from Infoblox Universal DDI."""
        if self.config.import_prefixes:
            self.load_prefixes()
        if self.config.import_ip_addresses:
            self.load_ip_addresses()
        if self.config.import_dns_zones:
            self.load_dns_zones()
        if self.config.import_dns_records:
            self.load_dns_records()
