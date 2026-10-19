"""Migration to add the import_ip_ranges field to SSOTInfobloxUDDIConfig."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_ssot", "0021_ssotinfobloxuddiconfig_dns_view"),
    ]

    operations = [
        migrations.AddField(
            model_name="ssotinfobloxuddiconfig",
            name="import_ip_ranges",
            field=models.BooleanField(default=True),
        ),
    ]
