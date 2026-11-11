"""Migration to remove the dns_view field from SSOTInfobloxUDDIConfig (all DNS Views are always synced)."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_ssot", "0022_ssotinfobloxuddiconfig_import_ip_ranges"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="ssotinfobloxuddiconfig",
            name="dns_view",
        ),
    ]
