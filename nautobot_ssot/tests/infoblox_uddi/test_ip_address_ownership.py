"""Tests for Infoblox Universal DDI taking over existing IP Addresses during a sync."""

from types import SimpleNamespace
from unittest.mock import Mock

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.models import Status, Tag
from nautobot.ipam.models import IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.infoblox_uddi.diffsync.adapters.nautobot import SYNC_TAG_NAME
from nautobot_ssot.integrations.infoblox_uddi.diffsync.models import nautobot as nb_models


class SyncAdapter(Adapter):
    """Minimal real diffsync adapter; the models require an `Adapter` instance."""

    ipaddress = nb_models.IPAddress
    top_level = ["ipaddress"]


class IPAddressTakeoverTestCase(TestCase):
    """Infoblox Universal DDI is the source of truth for IP Addresses it imports."""

    def setUp(self):
        """Create a Global-style namespace with an IPFabric-owned, deprecated /32 host."""
        self.active = Status.objects.get(name="Active")
        self.namespace = Namespace.objects.create(name="InfobloxUDDITakeoverUnitTest")
        Prefix.objects.create(prefix="10.132.1.0/24", namespace=self.namespace, type="network", status=self.active)
        self.sync_tag, _ = Tag.objects.get_or_create(name=SYNC_TAG_NAME)
        self.ipfabric_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from IPFabric")
        self.safe_delete_tag, _ = Tag.objects.get_or_create(name="SSoT Safe Delete")
        for tag in (self.sync_tag, self.ipfabric_tag, self.safe_delete_tag):
            tag.content_types.add(ContentType.objects.get_for_model(IPAddress))

        self.ipfabric_ip = IPAddress.objects.create(
            address="10.132.1.255/32",
            namespace=self.namespace,
            status=Status.objects.get(name="Deprecated"),
            description="Loopback10",
        )
        self.ipfabric_ip.tags.add(self.ipfabric_tag, self.safe_delete_tag)

        self.adapter = SyncAdapter()
        self.adapter.sync_tag = self.sync_tag
        self.adapter.namespace_id = self.namespace.pk
        self.adapter.job = Mock()
        self.adapter.config = SimpleNamespace(safe_delete_mode=True)

    def _ids(self, prefix_length):
        return {"address": "10.132.1.255", "prefix_length": prefix_length, "namespace": self.namespace.name}

    def test_create_takes_over_an_existing_host_with_a_different_mask(self):
        """Creating a colliding address should re-mask the existing record instead of failing."""
        nb_models.IPAddress.create(
            self.adapter, self._ids(24), {"status": "Active", "description": "from infoblox", "dns_name": "gw.example"}
        )

        ip_addresses = IPAddress.objects.filter(host="10.132.1.255", parent__namespace=self.namespace)
        self.assertEqual(ip_addresses.count(), 1)
        ip_address = ip_addresses.get()
        self.assertEqual(ip_address.pk, self.ipfabric_ip.pk)
        self.assertEqual(ip_address.mask_length, 24)
        self.assertEqual(ip_address.status.name, "Active")
        self.assertEqual(ip_address.description, "from infoblox")
        self.assertEqual(ip_address.dns_name, "gw.example")
        self.assertEqual(set(ip_address.tags.all()), {self.sync_tag})

    def test_create_still_creates_a_new_address(self):
        """An address that does not exist yet should be created and tagged as before."""
        ids = {"address": "10.132.1.10", "prefix_length": 24, "namespace": self.namespace.name}

        nb_models.IPAddress.create(self.adapter, ids, {"status": "Active"})

        ip_address = IPAddress.objects.get(host="10.132.1.10", parent__namespace=self.namespace)
        self.assertEqual(ip_address.mask_length, 24)
        self.assertEqual(set(ip_address.tags.all()), {self.sync_tag})
        self.assertEqual(IPAddress.objects.filter(parent__namespace=self.namespace).count(), 2)

    def test_delete_of_a_re_masked_address_is_skipped(self):
        """The old /32 delete that follows a take-over must not fail or deprecate the re-masked record."""
        nb_models.IPAddress.create(self.adapter, self._ids(24), {"status": "Active"})
        old_model = nb_models.IPAddress(adapter=self.adapter, **self._ids(32))

        old_model.delete()

        ip_address = IPAddress.objects.get(host="10.132.1.255", parent__namespace=self.namespace)
        self.assertEqual(ip_address.status.name, "Active")
        self.assertEqual(set(ip_address.tags.all()), {self.sync_tag})
        self.adapter.job.logger.warning.assert_called_once()
