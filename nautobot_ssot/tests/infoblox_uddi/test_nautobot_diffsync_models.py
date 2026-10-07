"""Infoblox Universal DDI Nautobot-side DiffSync model tests."""

from types import SimpleNamespace
from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.models import Status, Tag
from nautobot.ipam.models import IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.infoblox_uddi.diffsync.models import nautobot as nb_models


def _fake_adapter(namespace_id, safe_delete_mode=True):
    sync_tag, _ = Tag.objects.get_or_create(
        name="SSoT Synced from Infoblox Universal DDI", defaults={"name": "SSoT Synced from Infoblox Universal DDI"}
    )
    sync_tag.content_types.add(ContentType.objects.get_for_model(Prefix), ContentType.objects.get_for_model(IPAddress))
    return SimpleNamespace(
        namespace_id=namespace_id,
        sync_tag=sync_tag,
        config=SimpleNamespace(safe_delete_mode=safe_delete_mode),
        job=mock.Mock(),
    )


class PrefixModelTestCase(TestCase):
    """Tests for the Nautobot-backed Prefix DiffSync model."""

    def setUp(self):
        """Set up test data."""
        self.namespace, _ = Namespace.objects.get_or_create(name="InfobloxUDDIModelUnitTest")
        self.status = Status.objects.get(name="Active")
        deprecated_status, _ = Status.objects.get_or_create(name="Deprecated")
        deprecated_status.content_types.add(ContentType.objects.get_for_model(Prefix))
        self.adapter = _fake_adapter(self.namespace.id)

    def test_create(self):
        """Validate Prefix.create() creates a tagged ORM Prefix."""
        nb_models.Prefix.create(
            self.adapter,
            {"network": "192.0.2.0/24", "namespace": self.namespace.name},
            {"prefix_type": "network", "description": "test", "status": "Active"},
        )
        prefix = Prefix.objects.get(prefix="192.0.2.0/24", namespace=self.namespace)
        self.assertEqual(prefix.description, "test")
        self.assertIn(self.adapter.sync_tag, prefix.tags.all())

    def test_delete_safe_mode(self):
        """Validate delete() marks the Prefix Deprecated + tagged instead of hard-deleting it, by default."""
        prefix = Prefix.objects.create(
            prefix="198.51.100.0/24", namespace=self.namespace, type="network", status=self.status
        )
        model = nb_models.Prefix(network="198.51.100.0/24", namespace=self.namespace.name)
        model.adapter = self.adapter
        model.delete()
        prefix.refresh_from_db()
        self.assertEqual(prefix.status.name, "Deprecated")
        self.assertTrue(prefix.tags.filter(name="SSoT Safe Delete").exists())

    def test_delete_hard_mode(self):
        """Validate delete() hard-deletes the Prefix when safe_delete_mode is False."""
        Prefix.objects.create(prefix="203.0.113.0/24", namespace=self.namespace, type="network", status=self.status)
        model = nb_models.Prefix(network="203.0.113.0/24", namespace=self.namespace.name)
        model.adapter = _fake_adapter(self.namespace.id, safe_delete_mode=False)
        model.delete()
        self.assertFalse(Prefix.objects.filter(prefix="203.0.113.0/24", namespace=self.namespace).exists())


class IPAddressModelTestCase(TestCase):
    """Tests for the Nautobot-backed IPAddress DiffSync model."""

    def setUp(self):
        """Set up test data."""
        self.namespace, _ = Namespace.objects.get_or_create(name="InfobloxUDDIIPModelUnitTest")
        self.status = Status.objects.get(name="Active")
        deprecated_status, _ = Status.objects.get_or_create(name="Deprecated")
        deprecated_status.content_types.add(ContentType.objects.get_for_model(IPAddress))
        self.adapter = _fake_adapter(self.namespace.id)

    def test_create(self):
        """Validate IPAddress.create() builds the full CIDR address from host + prefix_length."""
        nb_models.IPAddress.create(
            self.adapter,
            {"address": "192.0.2.5", "prefix_length": 24, "namespace": self.namespace.name},
            {"status": "Active", "description": "test", "dns_name": "host.example.com"},
        )
        ipaddr = IPAddress.objects.get(host="192.0.2.5", parent__namespace=self.namespace)
        self.assertEqual(str(ipaddr.mask_length), "24")
        self.assertEqual(ipaddr.dns_name, "host.example.com")
        self.assertIn(self.adapter.sync_tag, ipaddr.tags.all())


class DnsARecordFallbackTestCase(TestCase):
    """Tests for the DNS A record fallback behavior when `nautobot-dns-models` is not installed."""

    def setUp(self):
        """Set up test data."""
        self.namespace, _ = Namespace.objects.get_or_create(name="InfobloxUDDIDnsFallbackUnitTest")
        self.status = Status.objects.get(name="Active")
        self.ipaddr = IPAddress.objects.create(
            address="192.0.2.10/24", namespace=self.namespace, status=self.status
        )
        self.adapter = _fake_adapter(self.namespace.id)

    @mock.patch("nautobot_ssot.integrations.infoblox_uddi.diffsync.models.nautobot.validate_dns_models_installed")
    def test_a_record_create_sets_dns_name(self, mock_validate):
        """Validate A record creation falls back to setting IPAddress.dns_name."""
        mock_validate.return_value = False
        nb_models.DnsARecord.create(
            self.adapter,
            {"name": "host10", "zone": "example.com.", "address": "192.0.2.10"},
            {"ttl": 300},
        )
        self.ipaddr.refresh_from_db()
        self.assertEqual(self.ipaddr.dns_name, "host10")


class DnsCnameRecordFallbackTestCase(TestCase):
    """Tests for the DNS CNAME record fallback behavior when `nautobot-dns-models` is not installed."""

    def setUp(self):
        """Set up test data."""
        self.namespace, _ = Namespace.objects.get_or_create(name="InfobloxUDDICnameFallbackUnitTest")
        self.adapter = _fake_adapter(self.namespace.id)

    @mock.patch("nautobot_ssot.integrations.infoblox_uddi.diffsync.models.nautobot.validate_dns_models_installed")
    def test_cname_record_create_logs_warning_and_skips(self, mock_validate):
        """Validate CNAME record creation is skipped with a warning log in fallback mode."""
        mock_validate.return_value = False
        nb_models.DnsCnameRecord.create(
            self.adapter,
            {"name": "alias1", "zone": "example.com."},
            {"alias": "host1.example.com.", "ttl": 300},
        )
        self.adapter.job.logger.warning.assert_called_once()
