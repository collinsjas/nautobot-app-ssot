"""Infoblox Universal DDI Nautobot adapter tests."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.models import Status, Tag
from nautobot.ipam.models import IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.infoblox_uddi.diffsync.adapters.nautobot import SYNC_TAG_NAME, NautobotAdapter


class NautobotAdapterTestCase(TestCase):
    """Tests for the NautobotAdapter (Infoblox Universal DDI target side)."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up test data."""
        self.namespace, _ = Namespace.objects.get_or_create(name="InfobloxUDDIAdapterUnitTest")
        self.status = Status.objects.get(name="Active")
        self.sync_tag, _ = Tag.objects.get_or_create(name=SYNC_TAG_NAME, defaults={"name": SYNC_TAG_NAME})
        self.sync_tag.content_types.add(
            ContentType.objects.get_for_model(Prefix), ContentType.objects.get_for_model(IPAddress)
        )

        self.prefix = Prefix.objects.create(
            prefix="10.0.0.0/24", namespace=self.namespace, type="network", status=self.status
        )
        self.prefix.tags.add(self.sync_tag)
        self.ipaddr = IPAddress.objects.create(
            address="10.0.0.5/24", namespace=self.namespace, status=self.status, dns_name="host1.example.com"
        )
        self.ipaddr.tags.add(self.sync_tag)

        self.config = type(
            "FakeConfig",
            (),
            {
                "default_namespace_id": self.namespace.id,
                "import_dns_zones": True,
                "import_dns_records": True,
                "safe_delete_mode": True,
            },
        )()
        self.adapter = NautobotAdapter(job=None, sync=None, config=self.config)

    def test_load_prefixes_only_tagged(self):
        """Validate only tagged Prefixes in the configured Namespace are loaded."""
        self.adapter.load_prefixes()
        prefixes = list(self.adapter.get_all("prefix"))
        self.assertEqual(len(prefixes), 1)
        self.assertEqual(prefixes[0].network, "10.0.0.0/24")
        self.assertEqual(prefixes[0].namespace, "InfobloxUDDIAdapterUnitTest")

    def test_load_ip_addresses_only_tagged(self):
        """Validate only tagged IPAddresses in the configured Namespace are loaded."""
        self.adapter.load_ip_addresses()
        ipaddrs = list(self.adapter.get_all("ipaddress"))
        self.assertEqual(len(ipaddrs), 1)
        self.assertEqual(ipaddrs[0].address, "10.0.0.5")
        self.assertEqual(ipaddrs[0].prefix_length, 24)
        self.assertEqual(ipaddrs[0].dns_name, "host1.example.com")

    def test_load_dns_zones_noop_without_dns_models(self):
        """Validate loading DNS Zones is a no-op when `nautobot-dns-models` isn't installed."""
        self.adapter.load_dns_zones()
        self.assertEqual(list(self.adapter.get_all("dnszone")), [])
