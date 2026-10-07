"""DiffSync model definitions re-export."""

from .base import (
    DnsAaaaRecord,
    DnsARecord,
    DnsCnameRecord,
    DnsPtrRecord,
    DnsZone,
    IPAddress,
    Prefix,
)

__all__ = (
    "Prefix",
    "IPAddress",
    "DnsZone",
    "DnsARecord",
    "DnsAaaaRecord",
    "DnsCnameRecord",
    "DnsPtrRecord",
)
