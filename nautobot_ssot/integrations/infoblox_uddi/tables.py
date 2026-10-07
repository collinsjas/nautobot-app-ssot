"""Tables implementation for SSOT Infoblox Universal DDI."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, BooleanColumn, ButtonsColumn

from .models import SSOTInfobloxUDDIConfig


class SSOTInfobloxUDDIConfigTable(BaseTable):
    """Table for SSOTInfobloxUDDIConfig."""

    name = tables.LinkColumn()
    uddi_url = tables.Column(accessor="uddi_instance__remote_url")
    uddi_ip_space = tables.Column()
    default_namespace = tables.Column()
    enable_sync_to_nautobot = BooleanColumn(orderable=False)
    import_prefixes = BooleanColumn(orderable=False)
    import_ip_addresses = BooleanColumn(orderable=False)
    import_dns_zones = BooleanColumn(orderable=False)
    import_dns_records = BooleanColumn(orderable=False)
    safe_delete_mode = BooleanColumn(orderable=False)
    job_enabled = BooleanColumn(orderable=False)
    actions = ButtonsColumn(SSOTInfobloxUDDIConfig, buttons=("changelog", "edit", "delete"))

    class Meta(BaseTable.Meta):
        """Meta attributes."""

        model = SSOTInfobloxUDDIConfig
        fields = (  # pylint: disable=nb-use-fields-all
            "name",
            "uddi_url",
            "uddi_ip_space",
            "default_namespace",
            "enable_sync_to_nautobot",
            "import_prefixes",
            "import_ip_addresses",
            "import_dns_zones",
            "import_dns_records",
            "safe_delete_mode",
            "job_enabled",
        )
