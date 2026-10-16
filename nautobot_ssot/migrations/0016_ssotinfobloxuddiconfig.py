"""Migration to add the SSOTInfobloxUDDIConfig model."""

import uuid

import django.core.serializers.json
import django.db.models.deletion
import nautobot.core.models.fields
import nautobot.extras.models.mixins
from django.db import migrations, models

import nautobot_ssot.integrations.infoblox_uddi.models


class Migration(migrations.Migration):
    dependencies = [
        # "extras", "0001_initial" was renamed to "0001_initial_part_1" in Nautobot; use the ExternalIntegration migration instead.
        ("extras", "0102_set_null_objectchange_contenttype"),
        # ipam.Namespace doesn't exist until this migration, not "0001_initial".
        ("ipam", "0030_ipam__namespaces"),
        ("nautobot_ssot", "0015_ssotvsphereconfig"),
    ]

    operations = [
        migrations.CreateModel(
            name="SSOTInfobloxUDDIConfig",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "_custom_field_data",
                    models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder),
                ),
                ("name", models.CharField(max_length=255, unique=True)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("job_enabled", models.BooleanField(default=False)),
                ("enable_sync_to_nautobot", models.BooleanField(default=True)),
                ("import_prefixes", models.BooleanField(default=True)),
                ("import_ip_addresses", models.BooleanField(default=True)),
                ("import_dns_zones", models.BooleanField(default=True)),
                ("import_dns_records", models.BooleanField(default=True)),
                ("uddi_ip_space", models.CharField(max_length=255)),
                (
                    "dns_record_types",
                    models.JSONField(
                        default=nautobot_ssot.integrations.infoblox_uddi.models._get_default_dns_record_types,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                ("safe_delete_mode", models.BooleanField(default=True)),
                ("tags", nautobot.core.models.fields.TagsField(through="extras.TaggedItem", to="extras.Tag")),
                (
                    "default_namespace",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="ipam.namespace"),
                ),
                (
                    "default_status",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="extras.status"),
                ),
                (
                    "uddi_instance",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="extras.externalintegration"),
                ),
            ],
            options={
                "verbose_name": "SSOT Infoblox Universal DDI Config",
                "verbose_name_plural": "SSOT Infoblox Universal DDI Configs",
            },
            bases=(
                nautobot.extras.models.mixins.DynamicGroupMixin,
                nautobot.extras.models.mixins.NotesMixin,
                models.Model,
            ),
        ),
    ]
