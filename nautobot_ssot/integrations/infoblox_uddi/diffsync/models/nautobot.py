"""Nautobot-side DiffSync model definitions for Infoblox Universal DDI integration.

These subclasses add ORM persistence on top of the shared `diffsync/models/base.py`
definitions, including safe-delete (status+tag instead of hard delete, IP Fabric style)
and the DNS fallback behavior documented in the design doc: when `nautobot-dns-models`
is not installed, A/AAAA records fall back to setting `IPAddress.dns_name`, PTR records
are a no-op, and CNAME records are skipped with a warning log.
"""

from django.core.exceptions import ObjectDoesNotExist
from nautobot.extras.models import Status, Tag

from nautobot_ssot.utils import validate_dns_models_installed

from . import base

SAFE_DELETE_STATUS = "Deprecated"
SAFE_DELETE_TAG = "SSoT Safe Delete"


def _safe_delete_or_hard_delete(instance, safe_delete_mode):
    """Either mark `instance` deprecated+tagged, or hard-delete it, based on `safe_delete_mode`."""
    if not safe_delete_mode:
        instance.delete()
        return
    try:
        instance.status = Status.objects.get(name=SAFE_DELETE_STATUS)
    except ObjectDoesNotExist:
        pass
    instance.validated_save()
    tag, _ = Tag.objects.get_or_create(name=SAFE_DELETE_TAG, defaults={"name": SAFE_DELETE_TAG})
    instance.tags.add(tag)


def _get_or_create_dns_view(view_name):
    """Resolve a DNSView by name, creating it if needed. Returns None if `view_name` is blank."""
    if not view_name:
        return None
    from nautobot_dns_models.models import DNSView  # pylint: disable=import-outside-toplevel

    view, _ = DNSView.objects.get_or_create(name=view_name)
    return view


class Prefix(base.Prefix):
    """Nautobot ORM-backed Prefix model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a Prefix in Nautobot."""
        from nautobot.ipam.models import Namespace  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import Prefix as OrmPrefix

        namespace = Namespace.objects.get(name=ids["namespace"])
        status = Status.objects.get(name=attrs.get("status", "Active"))
        prefix = OrmPrefix(
            prefix=ids["network"],
            namespace=namespace,
            type=attrs.get("prefix_type", "network"),
            description=attrs.get("description") or "",
            status=status,
        )
        prefix.validated_save()
        prefix.tags.add(adapter.sync_tag)
        return super().create(adapter, ids, attrs)

    def update(self, attrs):
        """Update a Prefix in Nautobot."""
        from nautobot.ipam.models import Namespace  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import Prefix as OrmPrefix

        namespace = Namespace.objects.get(name=self.namespace)
        prefix = OrmPrefix.objects.get(prefix=self.network, namespace=namespace)
        if "prefix_type" in attrs:
            prefix.type = attrs["prefix_type"]
        if "description" in attrs:
            prefix.description = attrs["description"] or ""
        if "status" in attrs:
            prefix.status = Status.objects.get(name=attrs["status"])
        prefix.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete (or safe-delete) a Prefix from Nautobot."""
        from nautobot.ipam.models import Namespace  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import Prefix as OrmPrefix

        namespace = Namespace.objects.get(name=self.namespace)
        prefix = OrmPrefix.objects.get(prefix=self.network, namespace=namespace)
        _safe_delete_or_hard_delete(prefix, self.adapter.config.safe_delete_mode)
        return super().delete()


class IPAddress(base.IPAddress):
    """Nautobot ORM-backed IPAddress model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create an IPAddress in Nautobot."""
        from nautobot.ipam.models import IPAddress as OrmIPAddress  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import Namespace  # pylint: disable=import-outside-toplevel

        status = Status.objects.get(name=attrs.get("status", "Active"))
        # IPAddress has no `namespace_id` field; `namespace` is a constructor-only kwarg
        # that auto-resolves `parent` (the containing Prefix) during clean().
        namespace = Namespace.objects.get(pk=adapter.namespace_id)
        ipaddr = OrmIPAddress(
            address=f"{ids['address']}/{ids['prefix_length']}",
            namespace=namespace,
            description=attrs.get("description") or "",
            dns_name=attrs.get("dns_name") or "",
            status=status,
        )
        ipaddr.validated_save()
        ipaddr.tags.add(adapter.sync_tag)
        return super().create(adapter, ids, attrs)

    def update(self, attrs):
        """Update an IPAddress in Nautobot."""
        from nautobot.ipam.models import IPAddress as OrmIPAddress  # pylint: disable=import-outside-toplevel

        ipaddr = OrmIPAddress.objects.get(
            address=f"{self.address}/{self.prefix_length}", parent__namespace_id=self.adapter.namespace_id
        )
        if "description" in attrs:
            ipaddr.description = attrs["description"] or ""
        if "dns_name" in attrs:
            ipaddr.dns_name = attrs["dns_name"] or ""
        if "status" in attrs:
            ipaddr.status = Status.objects.get(name=attrs["status"])
        ipaddr.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete (or safe-delete) an IPAddress from Nautobot."""
        from nautobot.ipam.models import IPAddress as OrmIPAddress  # pylint: disable=import-outside-toplevel

        ipaddr = OrmIPAddress.objects.get(
            address=f"{self.address}/{self.prefix_length}", parent__namespace_id=self.adapter.namespace_id
        )
        _safe_delete_or_hard_delete(ipaddr, self.adapter.config.safe_delete_mode)
        return super().delete()


class IPAddressRange(base.IPAddressRange):
    """Nautobot ORM-backed IPAddressRange model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create an IPAddressRange in Nautobot."""
        from nautobot.ipam.models import IPAddressRange as OrmIPAddressRange  # pylint: disable=import-outside-toplevel
        from nautobot.ipam.models import Namespace  # pylint: disable=import-outside-toplevel

        status = Status.objects.get(name=attrs.get("status", "Active"))
        namespace = Namespace.objects.get(pk=adapter.namespace_id)
        ip_range = OrmIPAddressRange(
            start_address=ids["start_address"],
            end_address=attrs["end_address"],
            namespace=namespace,
            name=attrs.get("name") or "",
            description=attrs.get("description") or "",
            status=status,
        )
        ip_range.validated_save()
        ip_range.tags.add(adapter.sync_tag)
        return super().create(adapter, ids, attrs)

    def update(self, attrs):
        """Update an IPAddressRange in Nautobot."""
        from nautobot.ipam.models import IPAddressRange as OrmIPAddressRange  # pylint: disable=import-outside-toplevel

        ip_range = OrmIPAddressRange.objects.get(
            start_address=self.start_address, parent__namespace_id=self.adapter.namespace_id
        )
        if "end_address" in attrs:
            ip_range.end_address = attrs["end_address"]
        if "name" in attrs:
            ip_range.name = attrs["name"] or ""
        if "description" in attrs:
            ip_range.description = attrs["description"] or ""
        if "status" in attrs:
            ip_range.status = Status.objects.get(name=attrs["status"])
        ip_range.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete (or safe-delete) an IPAddressRange from Nautobot."""
        from nautobot.ipam.models import IPAddressRange as OrmIPAddressRange  # pylint: disable=import-outside-toplevel

        ip_range = OrmIPAddressRange.objects.get(
            start_address=self.start_address, parent__namespace_id=self.adapter.namespace_id
        )
        _safe_delete_or_hard_delete(ip_range, self.adapter.config.safe_delete_mode)
        return super().delete()


class DnsZone(base.DnsZone):
    """Nautobot ORM-backed DNS Zone model.

    No-op when `nautobot-dns-models` is not installed, since Nautobot core has no
    object representing a bare DNS zone.
    """

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a DNSZone in Nautobot, if `nautobot-dns-models` is installed."""
        if validate_dns_models_installed():
            from nautobot_dns_models.models import DNSZone as OrmDNSZone  # pylint: disable=import-outside-toplevel

            # `ttl` is NOT NULL on DNSZone; omit it from defaults (letting the model's own
            # default apply) rather than forcing an explicit None when the source has no TTL.
            defaults = {}
            if attrs.get("ttl") is not None:
                defaults["ttl"] = attrs["ttl"]
            # dns_view is part of the real (name, dns_view) uniqueness - included in the lookup,
            # not just defaults, so distinct per-view zones are matched/created correctly.
            lookup = {"name": ids["name"]}
            dns_view = _get_or_create_dns_view(attrs.get("view"))
            if dns_view is not None:
                lookup["dns_view"] = dns_view
            try:
                zone, _ = OrmDNSZone.objects.get_or_create(defaults=defaults, **lookup)
                zone.tags.add(adapter.sync_tag)
            except Exception as error:  # pylint: disable=broad-except
                # Guard against unexpected AuthZone name collisions within the same DNS View
                # rather than letting an unhandled IntegrityError abort the whole sync.
                adapter.job.logger.error("Failed to create DNS Zone %s: %s. Skipping.", ids["name"], error)
        else:
            adapter.job.logger.debug(
                "nautobot-dns-models not installed; skipping DNS Zone %s (no-op in fallback mode).", ids["name"]
            )
        return super().create(adapter, ids, attrs)

    def update(self, attrs):
        """Update a DNSZone in Nautobot, if `nautobot-dns-models` is installed."""
        if validate_dns_models_installed():
            from nautobot_dns_models.models import DNSZone as OrmDNSZone  # pylint: disable=import-outside-toplevel

            zone = OrmDNSZone.objects.filter(name=self.name).first()
            if zone:
                update_fields = []
                if attrs.get("ttl") is not None and zone.ttl != attrs["ttl"]:
                    zone.ttl = attrs["ttl"]
                    update_fields.append("ttl")
                if attrs.get("view") and zone.dns_view.name != attrs["view"]:
                    zone.dns_view = _get_or_create_dns_view(attrs["view"])
                    update_fields.append("dns_view")
                if update_fields:
                    # Bypass full_clean(): pre-existing zones may carry legacy required-field
                    # gaps (soa_mname/soa_rname/filename) or wire-format-invalid (trailing-dot)
                    # names that predate validation on this path - not in scope for this sync.
                    zone.save(update_fields=update_fields)
        return super().update(attrs)

    def delete(self):
        """Delete (or safe-delete) a DNSZone from Nautobot, if `nautobot-dns-models` is installed."""
        if validate_dns_models_installed():
            from nautobot_dns_models.models import DNSZone as OrmDNSZone  # pylint: disable=import-outside-toplevel

            zone = OrmDNSZone.objects.filter(name=self.name).first()
            if zone:
                _safe_delete_or_hard_delete(zone, self.adapter.config.safe_delete_mode)
        return super().delete()


class DnsARecord(base.DnsARecord):
    """Nautobot ORM-backed DNS A record model.

    Falls back to setting `IPAddress.dns_name` when `nautobot-dns-models` is not installed.
    """

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create an ARecord in Nautobot, or fall back to `IPAddress.dns_name`."""
        if validate_dns_models_installed():
            from nautobot.ipam.models import IPAddress as OrmIPAddress  # pylint: disable=import-outside-toplevel
            from nautobot_dns_models.models import ARecord, DNSZone  # pylint: disable=import-outside-toplevel

            zone = DNSZone.objects.filter(name=ids["zone"]).first()
            ip_address = OrmIPAddress.objects.filter(
                host=ids["address"], parent__namespace_id=adapter.namespace_id
            ).first()
            if zone and ip_address:
                defaults = {}
                if attrs.get("ttl") is not None:
                    defaults["_ttl"] = attrs["ttl"]
                try:
                    record, _ = ARecord.objects.get_or_create(
                        name=ids["name"], zone=zone, ip_address=ip_address, defaults=defaults
                    )
                    record.tags.add(adapter.sync_tag)
                except Exception as error:  # pylint: disable=broad-except
                    adapter.job.logger.error("Failed to create DNS A record %s: %s. Skipping.", ids["name"], error)
        else:
            from nautobot.ipam.models import IPAddress as OrmIPAddress  # pylint: disable=import-outside-toplevel

            OrmIPAddress.objects.filter(host=ids["address"], parent__namespace_id=adapter.namespace_id).update(
                dns_name=ids["name"]
            )
        return super().create(adapter, ids, attrs)

    def delete(self):
        """Delete an ARecord, or no-op the `dns_name` fallback (handled by safe-delete of the IPAddress itself)."""
        if validate_dns_models_installed():
            from nautobot_dns_models.models import ARecord  # pylint: disable=import-outside-toplevel

            record = ARecord.objects.filter(name=self.name, zone__name=self.zone, ip_address__host=self.address).first()
            if record:
                _safe_delete_or_hard_delete(record, self.adapter.config.safe_delete_mode)
        return super().delete()


class DnsAaaaRecord(base.DnsAaaaRecord):
    """Nautobot ORM-backed DNS AAAA record model.

    Falls back to setting `IPAddress.dns_name` when `nautobot-dns-models` is not installed.
    """

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create an AAAARecord in Nautobot, or fall back to `IPAddress.dns_name`."""
        if validate_dns_models_installed():
            from nautobot.ipam.models import IPAddress as OrmIPAddress  # pylint: disable=import-outside-toplevel
            from nautobot_dns_models.models import AAAARecord, DNSZone  # pylint: disable=import-outside-toplevel

            zone = DNSZone.objects.filter(name=ids["zone"]).first()
            ip_address = OrmIPAddress.objects.filter(
                host=ids["address"], parent__namespace_id=adapter.namespace_id
            ).first()
            if zone and ip_address:
                defaults = {}
                if attrs.get("ttl") is not None:
                    defaults["_ttl"] = attrs["ttl"]
                try:
                    record, _ = AAAARecord.objects.get_or_create(
                        name=ids["name"], zone=zone, ip_address=ip_address, defaults=defaults
                    )
                    record.tags.add(adapter.sync_tag)
                except Exception as error:  # pylint: disable=broad-except
                    adapter.job.logger.error("Failed to create DNS AAAA record %s: %s. Skipping.", ids["name"], error)
        else:
            from nautobot.ipam.models import IPAddress as OrmIPAddress  # pylint: disable=import-outside-toplevel

            OrmIPAddress.objects.filter(host=ids["address"], parent__namespace_id=adapter.namespace_id).update(
                dns_name=ids["name"]
            )
        return super().create(adapter, ids, attrs)

    def delete(self):
        """Delete an AAAARecord, or no-op the `dns_name` fallback."""
        if validate_dns_models_installed():
            from nautobot_dns_models.models import AAAARecord  # pylint: disable=import-outside-toplevel

            record = AAAARecord.objects.filter(
                name=self.name, zone__name=self.zone, ip_address__host=self.address
            ).first()
            if record:
                _safe_delete_or_hard_delete(record, self.adapter.config.safe_delete_mode)
        return super().delete()


class DnsCnameRecord(base.DnsCnameRecord):
    """Nautobot ORM-backed DNS CNAME record model.

    Not representable without `nautobot-dns-models` - skipped with a warning log in fallback mode.
    """

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a CNAMERecord in Nautobot, or skip with a warning if unsupported."""
        if validate_dns_models_installed():
            from nautobot_dns_models.models import CNAMERecord, DNSZone  # pylint: disable=import-outside-toplevel

            zone = DNSZone.objects.filter(name=ids["zone"]).first()
            if zone:
                defaults = {}
                if attrs.get("ttl") is not None:
                    defaults["_ttl"] = attrs["ttl"]
                try:
                    record, _ = CNAMERecord.objects.get_or_create(
                        name=ids["name"], alias=ids["alias"], zone=zone, defaults=defaults
                    )
                    record.tags.add(adapter.sync_tag)
                except Exception as error:  # pylint: disable=broad-except
                    adapter.job.logger.error("Failed to create DNS CNAME record %s: %s. Skipping.", ids["name"], error)
        else:
            adapter.job.logger.warning(
                "nautobot-dns-models not installed; skipping CNAME record %s -> %s (not representable "
                "via IPAddress.dns_name).",
                ids["name"],
                ids["alias"],
            )
        return super().create(adapter, ids, attrs)

    def delete(self):
        """Delete a CNAMERecord, if `nautobot-dns-models` is installed."""
        if validate_dns_models_installed():
            from nautobot_dns_models.models import CNAMERecord  # pylint: disable=import-outside-toplevel

            record = CNAMERecord.objects.filter(name=self.name, alias=self.alias, zone__name=self.zone).first()
            if record:
                _safe_delete_or_hard_delete(record, self.adapter.config.safe_delete_mode)
        return super().delete()


class DnsPtrRecord(base.DnsPtrRecord):
    """Nautobot ORM-backed DNS PTR record model.

    No-op fallback (the forward name already satisfies `dns_name`) when `nautobot-dns-models` is not installed.
    """

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create a PTRRecord in Nautobot, if `nautobot-dns-models` is installed."""
        if validate_dns_models_installed():
            from nautobot_dns_models.models import DNSZone, PTRRecord  # pylint: disable=import-outside-toplevel

            zone = DNSZone.objects.filter(name=ids["zone"]).first()
            if zone:
                defaults = {}
                if attrs.get("ttl") is not None:
                    defaults["_ttl"] = attrs["ttl"]
                try:
                    record, _ = PTRRecord.objects.get_or_create(
                        name=ids["name"], ptrdname=ids["ptrdname"], zone=zone, defaults=defaults
                    )
                    record.tags.add(adapter.sync_tag)
                except Exception as error:  # pylint: disable=broad-except
                    adapter.job.logger.error("Failed to create DNS PTR record %s: %s. Skipping.", ids["name"], error)
        else:
            adapter.job.logger.debug(
                "nautobot-dns-models not installed; skipping PTR record %s (no-op in fallback mode).", ids["name"]
            )
        return super().create(adapter, ids, attrs)

    def delete(self):
        """Delete a PTRRecord, if `nautobot-dns-models` is installed."""
        if validate_dns_models_installed():
            from nautobot_dns_models.models import PTRRecord  # pylint: disable=import-outside-toplevel

            record = PTRRecord.objects.filter(name=self.name, ptrdname=self.ptrdname, zone__name=self.zone).first()
            if record:
                _safe_delete_or_hard_delete(record, self.adapter.config.safe_delete_mode)
        return super().delete()
