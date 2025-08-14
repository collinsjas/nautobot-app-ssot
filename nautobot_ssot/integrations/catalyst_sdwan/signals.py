"""Signals for Catalyst SD-WAN SSoT integration."""

import logging

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

from nautobot_ssot.integrations.catalyst_sdwan.constant import PLUGIN_CFG

logger = logging.getLogger("nautobot.ssot.catalyst_sdwan")


def register_signals(sender):
    """Register signals for Catalyst SD-WAN integration."""
    nautobot_database_ready.connect(catalyst_sdwan_create_tag, sender=sender)
    nautobot_database_ready.connect(catalyst_sdwan_create_manufacturer, sender=sender)
    nautobot_database_ready.connect(catalyst_sdwan_device_custom_fields, sender=sender)
    nautobot_database_ready.connect(catalyst_sdwan_interface_custom_fields, sender=sender)


def _ensure_tag(apps, name, color):
    """Ensure tag exists and is properly configured."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Tag = apps.get_model("extras", "Tag")
    tag, created = Tag.objects.get_or_create(name=name)
    if tag.color != color:
        tag.color = color
        tag.save()
    # Add tag to all content types
    for content_type in ContentType.objects.all():
        if content_type not in tag.content_types.all():
            tag.content_types.add(content_type)
    return tag


def catalyst_sdwan_create_tag(apps, **kwargs):
    """Create Catalyst SD-WAN tag."""
    logger.info("Creating tags for Catalyst SD-WAN")
    _ensure_tag(
        apps=apps,
        name=PLUGIN_CFG.get("catalyst_sdwan_tag", "catalyst_sdwan"),
        color="2196f3"  # Blue color for SD-WAN
    )


def catalyst_sdwan_create_manufacturer(apps, **kwargs):
    """Create Cisco manufacturer if it doesn't exist."""
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    manufacturer_name = PLUGIN_CFG.get("catalyst_sdwan_manufacturer_name", "Cisco")
    logger.info(f"Creating manufacturer: {manufacturer_name}")
    Manufacturer.objects.get_or_create(
        name=manufacturer_name,
        defaults={"description": "Cisco Systems"}
    )


def catalyst_sdwan_device_custom_fields(apps, **kwargs):
    """Create custom fields for Catalyst SD-WAN devices."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Device = apps.get_model("dcim", "Device")
    CustomField = apps.get_model("extras", "CustomField")
    
    logger.info("Creating Device custom fields for Catalyst SD-WAN")
    
    device_custom_fields = [
        {
            "key": "catalyst_sdwan_system_ip",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Catalyst SD-WAN System IP",
            "description": "SD-WAN system IP address",
        },
        {
            "key": "catalyst_sdwan_site_id",
            "type": CustomFieldTypeChoices.TYPE_INTEGER,
            "label": "Catalyst SD-WAN Site ID",
            "description": "SD-WAN site identifier",
        },
        {
            "key": "catalyst_sdwan_personality",
            "type": CustomFieldTypeChoices.TYPE_SELECT,
            "label": "Catalyst SD-WAN Personality",
            "description": "SD-WAN device personality",
            "choices": ["vmanage", "vbond", "vsmart", "vedge", "cedge"],
        },
        {
            "key": "catalyst_sdwan_reachability",
            "type": CustomFieldTypeChoices.TYPE_SELECT,
            "label": "Catalyst SD-WAN Reachability",
            "description": "Device reachability status",
            "choices": ["reachable", "unreachable", "unknown"],
        },
        {
            "key": "catalyst_sdwan_device_model",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Catalyst SD-WAN Device Model",
            "description": "Specific device model from vManage",
        },
        {
            "key": "catalyst_sdwan_version",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Catalyst SD-WAN Software Version",
            "description": "Device software version",
        },
        {
            "key": "catalyst_sdwan_uuid",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Catalyst SD-WAN UUID",
            "description": "Unique device identifier from vManage",
        },
    ]
    
    for cf_dict in device_custom_fields:
        field, created = CustomField.objects.get_or_create(
            key=cf_dict["key"],
            defaults=cf_dict
        )
        field.content_types.set([ContentType.objects.get_for_model(Device)])


def catalyst_sdwan_interface_custom_fields(apps, **kwargs):
    """Create custom fields for Catalyst SD-WAN interfaces."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Interface = apps.get_model("dcim", "Interface")
    CustomField = apps.get_model("extras", "CustomField")
    
    logger.info("Creating Interface custom fields for Catalyst SD-WAN")
    
    interface_custom_fields = [
        {
            "key": "catalyst_sdwan_vpn_id",
            "type": CustomFieldTypeChoices.TYPE_INTEGER,
            "label": "Catalyst SD-WAN VPN ID",
            "description": "VPN segment assignment",
        },
        {
            "key": "catalyst_sdwan_admin_status",
            "type": CustomFieldTypeChoices.TYPE_SELECT,
            "label": "Catalyst SD-WAN Admin Status",
            "description": "Administrative status",
            "choices": ["up", "down", "unknown"],
        },
        {
            "key": "catalyst_sdwan_oper_status",
            "type": CustomFieldTypeChoices.TYPE_SELECT,
            "label": "Catalyst SD-WAN Operational Status",
            "description": "Operational status",
            "choices": ["up", "down", "unknown"],
        },
    ]
    
    for cf_dict in interface_custom_fields:
        field, created = CustomField.objects.get_or_create(
            key=cf_dict["key"],
            defaults=cf_dict
        )
        field.content_types.set([ContentType.objects.get_for_model(Interface)])
