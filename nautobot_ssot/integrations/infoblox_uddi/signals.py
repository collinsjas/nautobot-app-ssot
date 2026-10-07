"""Signal handlers for Infoblox Universal DDI integration."""

from django.conf import settings
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

from nautobot_ssot.integrations.infoblox_uddi.constant import TAG_COLOR

config = settings.PLUGINS_CONFIG["nautobot_ssot"]


def register_signals(sender):
    """Register signals for Infoblox Universal DDI integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Create Tag and CustomField to note System of Record for SSoT.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    Prefix = apps.get_model("ipam", "Prefix")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Tag = apps.get_model("extras", "Tag")

    tag_sync_from_uddi, _ = Tag.objects.get_or_create(
        name="SSoT Synced from Infoblox Universal DDI",
        defaults={
            "name": "SSoT Synced from Infoblox Universal DDI",
            "description": "Object synced at some point from Infoblox Universal DDI",
            "color": TAG_COLOR,
        },
    )
    for model in [Prefix, IPAddress]:
        tag_sync_from_uddi.content_types.add(ContentType.objects.get_for_model(model))

    safe_delete_tag, _ = Tag.objects.get_or_create(
        name="SSoT Safe Delete",
        defaults={
            "name": "SSoT Safe Delete",
            "description": "Object no longer present in the source of truth system",
            "color": TAG_COLOR,
        },
    )
    for model in [Prefix, IPAddress]:
        safe_delete_tag.content_types.add(ContentType.objects.get_for_model(model))

    custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_DATE,
        key="ssot_synced_to_infoblox_uddi",
        defaults={
            "label": "Last synced from Infoblox Universal DDI on",
        },
    )
    for model in [Prefix, IPAddress]:
        custom_field.content_types.add(ContentType.objects.get_for_model(model))

    # nautobot-dns-models is an optional soft dependency; add the same tags/custom field to its
    # models when installed so DNS objects are consistently marked, but don't fail setup if absent.
    try:
        DNSZone = apps.get_model("nautobot_dns_models", "DNSZone")
        ARecord = apps.get_model("nautobot_dns_models", "ARecord")
        AAAARecord = apps.get_model("nautobot_dns_models", "AAAARecord")
        CNAMERecord = apps.get_model("nautobot_dns_models", "CNAMERecord")
        PTRRecord = apps.get_model("nautobot_dns_models", "PTRRecord")
    except LookupError:
        return

    for model in [DNSZone, ARecord, AAAARecord, CNAMERecord, PTRRecord]:
        tag_sync_from_uddi.content_types.add(ContentType.objects.get_for_model(model))
        safe_delete_tag.content_types.add(ContentType.objects.get_for_model(model))
        custom_field.content_types.add(ContentType.objects.get_for_model(model))
