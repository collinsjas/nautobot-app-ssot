"""Tests that Nautobot-side DNS models resolve zones per DNS View."""

import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest import mock

from diffsync import Adapter
from django.apps import apps
from django.test import TestCase
from nautobot.extras.models import CustomField, Status
from nautobot.ipam.models import IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.infoblox_uddi.constant import DNS_OWNER_FIELD
from nautobot_ssot.integrations.infoblox_uddi.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.infoblox_uddi.diffsync.models import nautobot as nb_models


class DnsAdapter(Adapter):
    """Minimal real diffsync adapter; the models require an `Adapter` instance."""

    dnszone = nb_models.DnsZone
    dnsarecord = nb_models.DnsARecord
    dnscnamerecord = nb_models.DnsCnameRecord
    top_level = ["dnszone", "dnsarecord", "dnscnamerecord"]


def _fake_dns_models():
    """Build a stand-in for `nautobot_dns_models.models` whose managers are mocks."""
    module = ModuleType("nautobot_dns_models.models")
    for name in ("DNSZone", "ARecord", "AAAARecord", "CNAMERecord", "PTRRecord", "DNSView"):
        setattr(module, name, mock.Mock(name=name))
    package = ModuleType("nautobot_dns_models")
    package.models = module
    return package, module


class DnsViewLookupTestCase(unittest.TestCase):
    """Zones and records must be looked up by (name, view), never by name alone."""

    def setUp(self):
        """Install the fake dns-models package and a fake adapter."""
        package, self.models = _fake_dns_models()
        patcher = mock.patch.dict(
            sys.modules, {"nautobot_dns_models": package, "nautobot_dns_models.models": self.models}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(nb_models, "validate_dns_models_installed", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.adapter = DnsAdapter()
        self.adapter.sync_tag = mock.Mock()
        self.adapter.job = mock.Mock()
        self.adapter.namespace_id = "ns"
        self.adapter.config = SimpleNamespace(safe_delete_mode=False, pk="config-a")
        self.adapter.dns_owner_filter = {f"_custom_field_data__{DNS_OWNER_FIELD}": "config-a"}
        self.adapter.dns_record_owner_filter = {f"zone___custom_field_data__{DNS_OWNER_FIELD}": "config-a"}

    def test_zone_is_created_in_its_own_view(self):
        """The same zone name in another view must not match an existing zone."""
        external = object()
        self.models.DNSView.objects.get_or_create.return_value = (external, True)
        self.models.DNSZone.objects.get_or_create.return_value = (
            mock.Mock(_custom_field_data={DNS_OWNER_FIELD: "config-a"}), True
        )

        nb_models.DnsZone.create(self.adapter, {"name": "schneider.com.", "view": "external"}, {"ttl": 600})

        self.models.DNSView.objects.get_or_create.assert_called_once_with(name="external")
        self.models.DNSZone.objects.get_or_create.assert_called_once_with(
            defaults={"ttl": 600, "_custom_field_data": {DNS_OWNER_FIELD: "config-a"}},
            name="schneider.com.",
            dns_view=external,
        )

    def test_a_record_uses_the_zone_of_its_view(self):
        """A record in the external view must attach to the external zone, not the default one."""
        external_zone = object()
        self.models.DNSZone.objects.filter.return_value.first.return_value = external_zone
        self.models.ARecord.objects.get_or_create.return_value = (mock.Mock(), True)
        ip_address = object()
        with mock.patch("nautobot.ipam.models.IPAddress") as orm_ip:
            orm_ip.objects.filter.return_value.first.return_value = ip_address
            nb_models.DnsARecord.create(
                self.adapter,
                {"name": "host1", "zone": "schneider.com.", "view": "external", "address": "10.0.0.5"},
                {"ttl": 300},
            )

        self.models.DNSZone.objects.filter.assert_called_once_with(
            name="schneider.com.", dns_view__name="external", **self.adapter.dns_owner_filter
        )
        self.models.ARecord.objects.get_or_create.assert_called_once_with(
            name="host1", zone=external_zone, ip_address=ip_address, defaults={"_ttl": 300}
        )

    def test_record_is_skipped_when_its_view_has_no_zone(self):
        """A missing zone in the record's view must not fall back to a same-named zone in another view."""
        self.models.DNSZone.objects.filter.return_value.first.return_value = None
        with mock.patch("nautobot.ipam.models.IPAddress"):
            nb_models.DnsCnameRecord.create(
                self.adapter,
                {"name": "www", "zone": "schneider.com.", "view": "external", "alias": "host1.schneider.com."},
                {"ttl": None},
            )

        self.models.CNAMERecord.objects.get_or_create.assert_not_called()

    def test_record_delete_is_scoped_to_its_view(self):
        """Deleting a record must only look in the zone of its own view."""
        record = nb_models.DnsARecord(name="host1", zone="schneider.com.", view="external", address="10.0.0.5")
        record.adapter = self.adapter
        with mock.patch.object(nb_models, "_safe_delete_or_hard_delete") as safe_delete:
            record.delete()

        self.models.ARecord.objects.filter.assert_called_once_with(
            name="host1",
            zone__name="schneider.com.",
            zone__dns_view__name="external",
            ip_address__host="10.0.0.5",
            **self.adapter.dns_record_owner_filter,
        )
        safe_delete.assert_called_once()

    def test_existing_zone_owned_by_another_configuration_is_skipped(self):
        """A matching zone identity does not allow a sync to take over another owner's zone."""
        zone = mock.Mock(_custom_field_data={DNS_OWNER_FIELD: "config-b"})
        self.models.DNSView.objects.get_or_create.return_value = (object(), False)
        self.models.DNSZone.objects.get_or_create.return_value = (zone, False)

        result = nb_models.DnsZone.create(
            self.adapter, {"name": "schneider.com.", "view": "external"}, {"ttl": 600}
        )

        self.assertIsNone(result)
        zone.tags.add.assert_not_called()
        self.adapter.job.logger.warning.assert_called_once()


@unittest.skipUnless(apps.is_installed("nautobot_dns_models"), "DNS Models app is optional")
class DnsOwnershipDatabaseTestCase(TestCase):
    """Verify zone ownership and inherited record ownership using the actual DNS models."""

    def test_target_only_loads_dns_objects_owned_by_its_configuration(self):
        """Matching tags alone do not put another configuration's objects in scope."""
        from nautobot_dns_models.models import (  # pylint: disable=import-outside-toplevel
            CNAMERecord,
            DNSView,
            DNSZone,
            PTRRecord,
        )

        config = SimpleNamespace(pk="config-a", default_namespace_id=None, dns_record_types=["CNAME"])
        adapter = NautobotAdapter(config=config)
        field = CustomField.objects.get(key=DNS_OWNER_FIELD)
        self.assertTrue(field.content_types.filter(model="dnszone").exists())
        view = DNSView.objects.create(name="ownership-test")
        for name, owner in (("owned.example", "config-a"), ("foreign.example", "config-b"), ("legacy.example", None)):
            zone = DNSZone.objects.create(
                name=name, dns_view=view, _custom_field_data={DNS_OWNER_FIELD: owner} if owner else {}
            )
            zone.tags.add(adapter.sync_tag)
            record = CNAMERecord.objects.create(name="www", alias="host.example", zone=zone)
            record.tags.add(adapter.sync_tag)

        owned_zone = DNSZone.objects.get(name="owned.example")
        ptr = PTRRecord.objects.create(name="1", ptrdname="host.example", zone=owned_zone)
        ptr.tags.add(adapter.sync_tag)

        adapter.load_dns_zones()
        adapter.load_dns_records()

        self.assertEqual([zone.name for zone in adapter.get_all("dnszone")], ["owned.example"])
        self.assertEqual([record.zone for record in adapter.get_all("dnscnamerecord")], ["owned.example"])
        self.assertEqual(list(adapter.get_all("dnsptrrecord")), [])

        config.dns_record_types = ["PTR"]
        adapter = NautobotAdapter(config=config)
        adapter.load_dns_records()
        self.assertEqual([record.zone for record in adapter.get_all("dnsptrrecord")], ["owned.example"])
        self.assertEqual(list(adapter.get_all("dnscnamerecord")), [])

    def test_dns_record_updates_persist_and_clear_ttl_overrides(self):
        """Update all supported record types and keep inherited TTLs stable on reload."""
        from nautobot_dns_models.models import (  # pylint: disable=import-outside-toplevel
            AAAARecord,
            ARecord,
            CNAMERecord,
            DNSView,
            DNSZone,
            PTRRecord,
        )

        namespace = Namespace.objects.create(name="DNS TTL test")
        status = Status.objects.get(name="Active")
        ipv4_prefix = Prefix.objects.create(prefix="192.0.2.0/24", namespace=namespace, status=status)
        ipv6_prefix = Prefix.objects.create(prefix="2001:db8::/64", namespace=namespace, status=status)
        ipv4 = IPAddress.objects.create(address="192.0.2.5/24", parent=ipv4_prefix, status=status)
        ipv6 = IPAddress.objects.create(address="2001:db8::5/64", parent=ipv6_prefix, status=status)
        config = SimpleNamespace(
            pk="config-a", default_namespace_id=namespace.pk, dns_record_types=["A", "AAAA", "CNAME", "PTR"]
        )
        adapter = NautobotAdapter(config=config)
        view = DNSView.objects.create(name="TTL test view")
        zone = DNSZone.objects.create(
            name="ttl.example", dns_view=view, ttl=600, _custom_field_data={DNS_OWNER_FIELD: "config-a"}
        )
        records = {
            "dnsarecord": ARecord.objects.create(name="ipv4", zone=zone, ip_address=ipv4, _ttl=300),
            "dnsaaaarecord": AAAARecord.objects.create(name="ipv6", zone=zone, ip_address=ipv6, _ttl=300),
            "dnscnamerecord": CNAMERecord.objects.create(name="alias", zone=zone, alias="ipv4.ttl.example", _ttl=300),
            "dnsptrrecord": PTRRecord.objects.create(name="5", zone=zone, ptrdname="ipv4.ttl.example", _ttl=300),
        }
        for record in records.values():
            record.tags.add(adapter.sync_tag)
        adapter.load_dns_records()

        for model_name, record in records.items():
            with self.subTest(model_name=model_name):
                (loaded_record,) = adapter.get_all(model_name)
                loaded_record.update({"ttl": 600})
                record.refresh_from_db()
                self.assertEqual(record._ttl, 600)
                loaded_record.update({"ttl": None})
                record.refresh_from_db()
                self.assertIsNone(record._ttl)
                self.assertEqual(record.ttl, 600)

        reloaded = NautobotAdapter(config=config)
        reloaded.load_dns_records()
        for model_name in records:
            (loaded_record,) = reloaded.get_all(model_name)
            self.assertIsNone(loaded_record.ttl)
