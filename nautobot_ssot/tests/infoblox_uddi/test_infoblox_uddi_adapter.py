"""Infoblox Universal DDI source adapter tests."""

import unittest
from types import SimpleNamespace
from unittest import mock

from nautobot_ssot.integrations.infoblox_uddi.diffsync.adapters.infoblox_uddi import InfobloxUDDIAdapter


def _fake_config(**overrides):
    defaults = {
        "uddi_ip_space": "default",
        "default_namespace": SimpleNamespace(name="Global"),
        "import_prefixes": True,
        "import_ip_addresses": True,
        "import_dns_zones": True,
        "import_dns_records": True,
        "dns_record_types": ["A", "AAAA", "CNAME", "PTR"],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class InfobloxUDDIAdapterTestCase(unittest.TestCase):
    """Tests for the InfobloxUDDIAdapter source adapter."""

    def setUp(self):
        """Set up a fake BloxOne client connection."""
        self.conn = mock.Mock()
        self.conn.get_ip_space.return_value = SimpleNamespace(id="ip_space/1", name="default")
        self.conn.list_address_blocks.return_value = [
            SimpleNamespace(address="10.0.0.0", cidr=8, comment="Container"),
        ]
        self.conn.list_subnets.return_value = [
            SimpleNamespace(address="10.0.0.0", cidr=24, comment="Network"),
        ]
        self.conn.list_addresses.return_value = [
            SimpleNamespace(address="10.0.0.5", comment="Server 1"),
        ]
        self.conn.list_dns_zones.return_value = [
            SimpleNamespace(id="zone/1", fqdn="example.com.", ttl=3600),
        ]

        def fake_list_dns_records(zone_id, record_type=None):  # pylint: disable=unused-argument
            if record_type == "A":
                return [SimpleNamespace(name_in_zone="host1", ttl=300, rdata={"address": "10.0.0.5"})]
            if record_type == "CNAME":
                return [SimpleNamespace(name_in_zone="alias1", ttl=300, rdata={"cname": "host1.example.com."})]
            return []

        self.conn.list_dns_records.side_effect = fake_list_dns_records
        self.job = mock.Mock()
        self.config = _fake_config()
        self.adapter = InfobloxUDDIAdapter(job=self.job, sync=None, conn=self.conn, config=self.config)

    def test_load_prefixes(self):
        """Validate container and network Prefixes are both loaded with combined CIDR notation."""
        self.adapter.load_prefixes()
        prefixes = {str(p.network) for p in self.adapter.get_all("prefix")}
        self.assertEqual(prefixes, {"10.0.0.0/8", "10.0.0.0/24"})

    def test_load_ip_addresses_resolves_prefix_length(self):
        """Validate IP Addresses resolve their prefix_length from the containing loaded Subnet."""
        self.adapter.load_prefixes()
        self.adapter.load_ip_addresses()
        ipaddr = list(self.adapter.get_all("ipaddress"))[0]
        self.assertEqual(ipaddr.address, "10.0.0.5")
        self.assertEqual(ipaddr.prefix_length, 24)

    def test_load_ip_addresses_defaults_to_host_mask_without_subnet(self):
        """Validate IP Addresses default to a host mask when no containing Subnet was loaded."""
        self.adapter.load_ip_addresses()
        ipaddr = list(self.adapter.get_all("ipaddress"))[0]
        self.assertEqual(ipaddr.prefix_length, 32)

    def test_load_dns_zones(self):
        """Validate DNS Zones are loaded."""
        self.adapter.load_dns_zones()
        zones = list(self.adapter.get_all("dnszone"))
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0].name, "example.com.")
        self.assertEqual(zones[0].ttl, 3600)

    def test_load_dns_records(self):
        """Validate A and CNAME DNS Records are loaded with the right fields."""
        self.adapter.load_dns_records()
        a_records = list(self.adapter.get_all("dnsarecord"))
        cname_records = list(self.adapter.get_all("dnscnamerecord"))
        self.assertEqual(len(a_records), 1)
        self.assertEqual(a_records[0].address, "10.0.0.5")
        self.assertEqual(len(cname_records), 1)
        self.assertEqual(cname_records[0].alias, "host1.example.com.")

    def test_load_full(self):
        """Validate `load()` respects the config import toggles."""
        self.adapter.load()
        self.assertTrue(list(self.adapter.get_all("prefix")))
        self.assertTrue(list(self.adapter.get_all("ipaddress")))
        self.assertTrue(list(self.adapter.get_all("dnszone")))
        self.assertTrue(list(self.adapter.get_all("dnsarecord")))

    def test_load_skips_disabled_sections(self):
        """Validate `load()` skips DNS loading when import flags are disabled."""
        config = _fake_config(import_dns_zones=False, import_dns_records=False)
        adapter = InfobloxUDDIAdapter(job=self.job, sync=None, conn=self.conn, config=config)
        adapter.load()
        self.assertFalse(list(adapter.get_all("dnszone")))
        self.assertFalse(list(adapter.get_all("dnsarecord")))
