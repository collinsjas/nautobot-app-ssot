"""Migration to add the dns_view field to SSOTInfobloxUDDIConfig."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_ssot", "0020_merge_20261015_1200"),
    ]

    operations = [
        migrations.AddField(
            model_name="ssotinfobloxuddiconfig",
            name="dns_view",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
