"""Tests that Nautobot-side DNS models resolve zones per DNS View."""

import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest import mock

from diffsync import Adapter

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
        self.adapter.config = SimpleNamespace(safe_delete_mode=False)

    def test_zone_is_created_in_its_own_view(self):
        """The same zone name in another view must not match an existing zone."""
        external = object()
        self.models.DNSView.objects.get_or_create.return_value = (external, True)
        self.models.DNSZone.objects.get_or_create.return_value = (mock.Mock(), True)

        nb_models.DnsZone.create(self.adapter, {"name": "schneider.com.", "view": "external"}, {"ttl": 600})

        self.models.DNSView.objects.get_or_create.assert_called_once_with(name="external")
        self.models.DNSZone.objects.get_or_create.assert_called_once_with(
            defaults={"ttl": 600}, name="schneider.com.", dns_view=external
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

        self.models.DNSZone.objects.filter.assert_called_once_with(name="schneider.com.", dns_view__name="external")
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
            name="host1", zone__name="schneider.com.", zone__dns_view__name="external", ip_address__host="10.0.0.5"
        )
        safe_delete.assert_called_once()
