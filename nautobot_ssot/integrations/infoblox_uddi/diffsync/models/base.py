"""Shared DiffSync model definitions for the Infoblox Universal DDI integration.

These models represent the BloxOne-side data regardless of sync direction. Since this
integration only ever syncs one-way (Infoblox Universal DDI -> Nautobot), the source
(BloxOne) adapter uses these classes directly - no create/update/delete overrides are
needed on that side. The Nautobot-side adapter uses the subclasses defined in
`diffsync/models/nautobot.py`, which add ORM persistence (including safe-delete and the
DNS fallback behavior).
"""


from diffsync import DiffSyncModel


class Prefix(DiffSyncModel):
    """Prefix synced from a BloxOne AddressBlock or Subnet."""

    _modelname = "prefix"
    _identifiers = ("network", "namespace")
    _attributes = ("prefix_type", "description", "status")

    network: str
    namespace: str
    prefix_type: str = "network"
    description: str | None = None
    status: str = "Active"


class IPAddress(DiffSyncModel):
    """IP Address synced from a BloxOne Address.

    Nautobot's `ipam.IPAddress.address` field requires CIDR notation (e.g. "10.0.0.5/24"), so
    `prefix_length` is tracked as part of the identifier alongside the bare host `address`,
    matching the existing Infoblox WAPI integration's approach.
    """

    _modelname = "ipaddress"
    _identifiers = ("address", "prefix_length", "namespace")
    _attributes = ("status", "description", "dns_name")

    address: str
    prefix_length: int
    namespace: str
    status: str = "Active"
    description: str | None = None
    dns_name: str = ""


class IPAddressRange(DiffSyncModel):
    """DHCP Range synced from a BloxOne Range.

    Matches Nautobot's `ipam.IPAddressRange` uniqueness, which is keyed by the
    (auto-resolved) parent Prefix and `start_address` - `namespace` stands in for the
    parent here, same as on `IPAddress`.
    """

    _modelname = "ipaddressrange"
    _identifiers = ("start_address", "namespace")
    _attributes = ("end_address", "name", "description", "status")

    start_address: str
    end_address: str
    namespace: str
    name: str = ""
    description: str | None = None
    status: str = "Active"


class DnsZone(DiffSyncModel):
    """DNS Zone synced from a BloxOne AuthZone."""

    _modelname = "dnszone"
    _identifiers = ("name",)
    # view is tracked as an attribute, not an identifier, so this stays correct for the common
    # single-view setup (see SSOTInfobloxUDDIConfig.dns_view); if synced unscoped across multiple
    # views with colliding zone names, only one zone per name is represented (same limitation as
    # pre-existing single-key identity), but it is still tied to the correct DNSView.
    _attributes = ("ttl", "view")

    name: str
    ttl: int | None = None
    view: str = ""


class DnsARecord(DiffSyncModel):
    """DNS A record synced from a BloxOne Record (type=A)."""

    _modelname = "dnsarecord"
    _identifiers = ("name", "zone", "address")
    _attributes = ("ttl",)

    name: str
    zone: str
    address: str
    ttl: int | None = None


class DnsAaaaRecord(DiffSyncModel):
    """DNS AAAA record synced from a BloxOne Record (type=AAAA)."""

    _modelname = "dnsaaaarecord"
    _identifiers = ("name", "zone", "address")
    _attributes = ("ttl",)

    name: str
    zone: str
    address: str
    ttl: int | None = None


class DnsCnameRecord(DiffSyncModel):
    """DNS CNAME record synced from a BloxOne Record (type=CNAME)."""

    _modelname = "dnscnamerecord"
    # alias is part of the identifier, matching nautobot-dns-models' unique_together
    # (name, alias, zone) - two records sharing (name, zone) but a different alias are
    # distinct, real records, not duplicates.
    _identifiers = ("name", "zone", "alias")
    _attributes = ("ttl",)

    name: str
    zone: str
    alias: str
    ttl: int | None = None


class DnsPtrRecord(DiffSyncModel):
    """DNS PTR record synced from a BloxOne Record (type=PTR)."""

    _modelname = "dnsptrrecord"
    # ptrdname is part of the identifier, matching nautobot-dns-models' unique_together
    # (name, ptrdname, zone) - two records sharing (name, zone) but a different ptrdname
    # are distinct, real records, not duplicates.
    _identifiers = ("name", "zone", "ptrdname")
    _attributes = ("ttl",)

    name: str
    zone: str
    ptrdname: str
    ttl: int | None = None
