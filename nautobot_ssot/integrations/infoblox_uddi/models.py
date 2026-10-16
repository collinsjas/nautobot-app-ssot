"""Models implementation for SSOT Infoblox Universal DDI (BloxOne)."""

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

try:
    from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
except ImportError:
    CHARFIELD_MAX_LENGTH = 255

from nautobot.core.models.generics import PrimaryModel
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import SecretsGroupAssociation

from nautobot_ssot.integrations.infoblox_uddi.choices import DnsRecordTypeChoices
from nautobot_ssot.integrations.infoblox_uddi.constant import DEFAULT_DNS_RECORD_TYPES


def _get_default_dns_record_types():
    """Provides default value for SSOTInfobloxUDDIConfig dns_record_types field."""
    return list(DEFAULT_DNS_RECORD_TYPES)


class SSOTInfobloxUDDIConfig(PrimaryModel):  # pylint: disable=too-many-ancestors
    """SSOT Infoblox Universal DDI (BloxOne) Configuration model."""

    name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, unique=True)
    is_saved_view_model = False
    description = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    default_status = models.ForeignKey(
        to="extras.Status",
        on_delete=models.PROTECT,
        verbose_name="Default Object Status",
        help_text="Default Object Status",
    )
    uddi_instance = models.ForeignKey(
        to="extras.ExternalIntegration",
        on_delete=models.PROTECT,
        verbose_name="Universal DDI Instance Config",
        help_text="Infoblox Universal DDI (BloxOne CSP) Instance",
    )
    job_enabled = models.BooleanField(
        default=False,
        verbose_name="Enabled for Sync Job",
        help_text="Enable use of this configuration in the sync jobs.",
    )
    enable_sync_to_nautobot = models.BooleanField(
        default=True,
        verbose_name="Sync to Nautobot",
        help_text="Enable syncing of data from Infoblox Universal DDI to Nautobot.",
    )
    import_prefixes = models.BooleanField(default=True, verbose_name="Import Prefixes")
    import_ip_addresses = models.BooleanField(default=True, verbose_name="Import IP Addresses")
    import_dns_zones = models.BooleanField(default=True, verbose_name="Import DNS Zones")
    import_dns_records = models.BooleanField(default=True, verbose_name="Import DNS Records")
    uddi_ip_space = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        verbose_name="Universal DDI IP Space",
        help_text="Name of the single BloxOne IP Space to sync from (Phase 1 supports one IP Space).",
    )
    default_namespace = models.ForeignKey(
        to="ipam.Namespace",
        on_delete=models.PROTECT,
        verbose_name="Default Namespace",
        help_text="Nautobot Namespace that the configured IP Space is mapped to.",
    )
    dns_record_types = models.JSONField(
        default=_get_default_dns_record_types,
        encoder=DjangoJSONEncoder,
        verbose_name="DNS Record Types",
        help_text="Which DNS record types (A/AAAA/CNAME/PTR) to sync.",
    )
    dns_view = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH,
        blank=True,
        verbose_name="DNS View",
        help_text="Name of the single BloxOne DNS View to sync zones/records from. If left blank, zones/records "
        "from all DNS Views are loaded, and same-named zones in different views will collide (only the "
        "first-seen one is synced).",
    )
    safe_delete_mode = models.BooleanField(
        default=True,
        verbose_name="Safe Delete Mode",
        help_text="When enabled, objects no longer present in Infoblox Universal DDI are marked with a "
        "deprecated status and tagged instead of being hard-deleted from Nautobot.",
    )

    class Meta:
        """Meta class for SSOTInfobloxUDDIConfig."""

        verbose_name = "SSOT Infoblox Universal DDI Config"
        verbose_name_plural = "SSOT Infoblox Universal DDI Configs"

    def __str__(self):
        """String representation of singleton instance."""
        return self.name

    def _clean_uddi_instance(self):
        """Performs validation of the uddi_instance field."""
        if not self.uddi_instance.secrets_group:
            raise ValidationError({"uddi_instance": "Universal DDI instance must have Secrets groups assigned."})
        try:
            self.uddi_instance.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
            )
        except SecretsGroupAssociation.DoesNotExist:
            raise ValidationError(  # pylint: disable=raise-missing-from
                {
                    "uddi_instance": "Secrets group for the Universal DDI instance must have a secret with type "
                    "Token and access type HTTP(S)."
                }
            )

    def _clean_dns_record_types(self):
        """Performs validation of the dns_record_types field."""
        if not isinstance(self.dns_record_types, list):
            raise ValidationError({"dns_record_types": "DNS record types must be a list."})
        invalid_types = set(self.dns_record_types) - set(DnsRecordTypeChoices.values())
        if invalid_types:
            raise ValidationError(
                {"dns_record_types": f"Invalid DNS record type(s): {', '.join(sorted(invalid_types))}."}
            )

    def clean(self):
        """Clean method for SSOTInfobloxUDDIConfig."""
        super().clean()
        self._clean_uddi_instance()
        self._clean_dns_record_types()
