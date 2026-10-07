"""Infoblox Universal DDI config model tests."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration, Secret, SecretsGroup, SecretsGroupAssociation, Status
from nautobot.ipam.models import Namespace

from nautobot_ssot.integrations.infoblox_uddi.models import SSOTInfobloxUDDIConfig


class SSOTInfobloxUDDIConfigTestCase(TestCase):
    """Tests for the SSOTInfobloxUDDIConfig model."""

    def setUp(self):
        """Setup testing."""
        self.secrets_group, _ = SecretsGroup.objects.get_or_create(name="InfobloxUDDISSOTUnitTest")
        token_secret, _ = Secret.objects.get_or_create(
            name="Infoblox UDDI Token - InfobloxUDDISSOTUnitTest",
            defaults={"provider": "text-file", "parameters": {"path": "/dev/null"}},
        )
        SecretsGroupAssociation.objects.get_or_create(
            secrets_group=self.secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
            defaults={"secret": token_secret},
        )
        self.uddi_instance, _ = ExternalIntegration.objects.get_or_create(
            name="InfobloxUDDIInstanceUnitTest",
            defaults={
                "remote_url": "https://csp.infoblox.com",
                "secrets_group": self.secrets_group,
                "verify_ssl": True,
                "timeout": 30,
            },
        )
        self.status = Status.objects.get(name="Active")
        self.namespace, _ = Namespace.objects.get_or_create(name="InfobloxUDDIUnitTestNamespace")

    def _build_config(self, **overrides):
        defaults = {
            "name": "InfobloxUDDIConfigUnitTest",
            "default_status": self.status,
            "uddi_instance": self.uddi_instance,
            "uddi_ip_space": "default",
            "default_namespace": self.namespace,
        }
        defaults.update(overrides)
        return SSOTInfobloxUDDIConfig(**defaults)

    def test_create_valid_config(self):
        """Validate a fully valid config passes `clean()`."""
        config = self._build_config()
        config.clean()
        config.save()
        self.assertEqual(config.dns_record_types, ["A", "AAAA", "CNAME", "PTR"])
        self.assertTrue(config.safe_delete_mode)

    def test_clean_invalid_dns_record_type(self):
        """Validate an invalid DNS record type raises ValidationError."""
        config = self._build_config(dns_record_types=["A", "MX"])
        with self.assertRaises(ValidationError):
            config.clean()

    def test_clean_dns_record_types_not_list(self):
        """Validate a non-list dns_record_types raises ValidationError."""
        config = self._build_config(dns_record_types="A")
        with self.assertRaises(ValidationError):
            config.clean()

    def test_clean_uddi_instance_missing_secrets_group(self):
        """Validate a uddi_instance without a secrets group raises ValidationError."""
        instance, _ = ExternalIntegration.objects.get_or_create(
            name="InfobloxUDDIInstanceNoSecretsUnitTest",
            defaults={"remote_url": "https://csp.infoblox.com"},
        )
        config = self._build_config(name="NoSecretsConfig", uddi_instance=instance)
        with self.assertRaises(ValidationError):
            config.clean()

    def test_clean_uddi_instance_missing_token_secret(self):
        """Validate a uddi_instance whose secrets group lacks a Token/HTTP secret raises ValidationError."""
        secrets_group, _ = SecretsGroup.objects.get_or_create(name="InfobloxUDDINoTokenUnitTest")
        instance, _ = ExternalIntegration.objects.get_or_create(
            name="InfobloxUDDIInstanceNoTokenUnitTest",
            defaults={"remote_url": "https://csp.infoblox.com", "secrets_group": secrets_group},
        )
        config = self._build_config(name="NoTokenConfig", uddi_instance=instance)
        with self.assertRaises(ValidationError):
            config.clean()

    def test_str(self):
        """Validate `__str__` returns the config name."""
        config = self._build_config(name="StrTestConfig")
        self.assertEqual(str(config), "StrTestConfig")
