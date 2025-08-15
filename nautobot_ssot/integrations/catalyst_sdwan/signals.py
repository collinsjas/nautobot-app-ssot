"""Signals for Catalyst SD-WAN SSoT integration.

This module automatically creates all required Nautobot objects for the
Catalyst SD-WAN integration when the application starts up:

- Tags: Main SD-WAN tag plus categorization tags
- Manufacturer: Cisco manufacturer entry  
- Device Roles: vmanage, vbond, vsmart, edge roles
- Location Types: SD-WAN specific site/hub/region types
- Custom Fields: All required custom fields for devices, interfaces, and locations

All objects are created using get_or_create to avoid conflicts and are
automatically tagged for easy identification.
"""

import logging

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

from nautobot_ssot.integrations.catalyst_sdwan.constant import PLUGIN_CFG

logger = logging.getLogger("nautobot.ssot.catalyst_sdwan")


def register_signals(sender):
    """Register signals for Catalyst SD-WAN integration."""
    nautobot_database_ready.connect(catalyst_sdwan_create_tag, sender=sender)
    nautobot_database_ready.connect(catalyst_sdwan_create_manufacturer, sender=sender)
    nautobot_database_ready.connect(catalyst_sdwan_create_roles, sender=sender)
    nautobot_database_ready.connect(catalyst_sdwan_create_location_types, sender=sender)
    nautobot_database_ready.connect(catalyst_sdwan_location_custom_fields, sender=sender)
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
    """Create Catalyst SD-WAN tags."""
    logger.info("Creating tags for Catalyst SD-WAN")
    
    # Main SD-WAN tag
    main_tag_name = PLUGIN_CFG.get("tag", "catalyst_sdwan")
    logger.info(f"Creating main tag: {main_tag_name}")
    _ensure_tag(
        apps=apps,
        name=main_tag_name,
        color="2196f3"  # Blue color for SD-WAN
    )
    
    # Additional useful SD-WAN tags
    additional_tags = [
        {
            "name": "sdwan-controller",
            "color": "3f51b5",  # Indigo - for controller devices
        },
        {
            "name": "sdwan-edge", 
            "color": "f44336",  # Red - for edge devices
        },
        {
            "name": "sdwan-transport",
            "color": "ff9800",  # Orange - for transport interfaces/VPNs
        },
        {
            "name": "sdwan-service",
            "color": "4caf50",  # Green - for service VPNs/interfaces
        },
        {
            "name": "sdwan-management",
            "color": "9c27b0",  # Purple - for management VPNs/interfaces
        },
    ]
    
    for tag_data in additional_tags:
        logger.info(f"Creating additional tag: {tag_data['name']}")
        _ensure_tag(
            apps=apps,
            name=tag_data["name"],
            color=tag_data["color"]
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


def catalyst_sdwan_create_roles(apps, **kwargs):
    """Create SD-WAN device roles."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Device = apps.get_model("dcim", "Device")
    Role = apps.get_model("extras", "Role")
    Tag = apps.get_model("extras", "Tag")
    
    logger.info("Creating Device Roles for Catalyst SD-WAN")
    
    # Get the main SD-WAN tag to apply to roles
    tag_name = PLUGIN_CFG.get("tag", "catalyst_sdwan")
    try:
        main_tag = Tag.objects.get(name=tag_name)
    except Tag.DoesNotExist:
        logger.warning(f"Main tag '{tag_name}' not found, roles will be created without tags")
        main_tag = None
    
    # SD-WAN specific device roles
    sdwan_roles = [
        {
            "name": "vmanage",
            "description": "Cisco SD-WAN vManage Controller - Management and orchestration platform",
            "color": "1565c0",  # Dark blue
        },
        {
            "name": "vbond", 
            "description": "Cisco SD-WAN vBond Orchestrator - Initial device connectivity and certificate management",
            "color": "2e7d32",  # Dark green
        },
        {
            "name": "vsmart",
            "description": "Cisco SD-WAN vSmart Controller - Policy engine and route distribution", 
            "color": "f57c00",  # Dark orange
        },
        {
            "name": "edge",
            "description": "Cisco SD-WAN Edge Device - Branch/campus router (vEdge/cEdge)",
            "color": "c62828",  # Dark red
        },
    ]
    
    device_content_type = ContentType.objects.get_for_model(Device)
    
    for role_data in sdwan_roles:
        role, created = Role.objects.get_or_create(
            name=role_data["name"],
            defaults={
                "description": role_data["description"],
                "color": role_data["color"],
            }
        )
        
        # Ensure the role applies to devices
        if device_content_type not in role.content_types.all():
            role.content_types.add(device_content_type)
        
        # Tag the role with SD-WAN tag
        if main_tag and main_tag not in role.tags.all():
            role.tags.add(main_tag)
        
        if created:
            logger.info(f"Created SD-WAN device role: {role_data['name']}")
        else:
            logger.debug(f"SD-WAN device role already exists: {role_data['name']}")


def catalyst_sdwan_create_location_types(apps, **kwargs):
    """Create SD-WAN location types."""
    LocationType = apps.get_model("dcim", "LocationType")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Tag = apps.get_model("extras", "Tag")
    
    logger.info("Creating Location Types for Catalyst SD-WAN")
    
    # Get the main SD-WAN tag to apply to location types
    tag_name = PLUGIN_CFG.get("tag", "catalyst_sdwan")
    try:
        main_tag = Tag.objects.get(name=tag_name)
    except Tag.DoesNotExist:
        logger.warning(f"Main tag '{tag_name}' not found, location types will be created without tags")
        main_tag = None
    
    # SD-WAN specific location types
    sdwan_location_types = [
        {
            "name": "SD-WAN Site",
            "description": "Cisco SD-WAN branch or campus site location",
            "nestable": True,
        },
        {
            "name": "SD-WAN Hub",
            "description": "Cisco SD-WAN hub site or data center location", 
            "nestable": True,
        },
        {
            "name": "SD-WAN Region",
            "description": "Cisco SD-WAN regional grouping for sites",
            "nestable": True,
        },
    ]
    
    for location_type_data in sdwan_location_types:
        location_type, created = LocationType.objects.get_or_create(
            name=location_type_data["name"],
            defaults={
                "description": location_type_data["description"],
                "nestable": location_type_data["nestable"],
            }
        )
        
        # Tag the location type with SD-WAN tag
        if main_tag and main_tag not in location_type.tags.all():
            location_type.tags.add(main_tag)
        
        if created:
            logger.info(f"Created SD-WAN location type: {location_type_data['name']}")
        else:
            logger.debug(f"SD-WAN location type already exists: {location_type_data['name']}")


def catalyst_sdwan_location_custom_fields(apps, **kwargs):
    """Create custom fields for Catalyst SD-WAN locations."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Location = apps.get_model("dcim", "Location")
    CustomField = apps.get_model("extras", "CustomField")
    
    logger.info("Creating Location custom fields for Catalyst SD-WAN")
    
    # Location custom fields
    location_custom_fields = [
        {
            "key": "catalyst_sdwan_site_id",
            "type": CustomFieldTypeChoices.TYPE_INTEGER,
            "label": "Catalyst SD-WAN Site ID",
            "description": "SD-WAN site identifier for this location",
        },
        {
            "key": "catalyst_sdwan_site_name",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Catalyst SD-WAN Site Name",
            "description": "SD-WAN site name from vManage",
        },
    ]
    
    # Create location custom fields
    for cf_dict in location_custom_fields:
        field, created = CustomField.objects.get_or_create(
            key=cf_dict["key"],
            defaults=cf_dict
        )
        field.content_types.set([ContentType.objects.get_for_model(Location)])
        
        if created:
            logger.info(f"Created location custom field: {cf_dict['key']}")


def catalyst_sdwan_device_custom_fields(apps, **kwargs):
    """Create custom fields for Catalyst SD-WAN devices."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Device = apps.get_model("dcim", "Device")
    CustomField = apps.get_model("extras", "CustomField")
    CustomFieldChoice = apps.get_model("extras", "CustomFieldChoice")
    
    logger.info("Creating Device custom fields for Catalyst SD-WAN")
    
    # Text and Integer fields
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
        {
            "key": "catalyst_sdwan_status",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Catalyst SD-WAN Status",
            "description": "Device status from vManage",
        },
    ]
    
    # Create text and integer fields
    for cf_dict in device_custom_fields:
        field, created = CustomField.objects.get_or_create(
            key=cf_dict["key"],
            defaults=cf_dict
        )
        field.content_types.set([ContentType.objects.get_for_model(Device)])
    
    # Create SELECT fields with choices
    select_fields = [
        {
            "field_data": {
                "key": "catalyst_sdwan_personality",
                "type": CustomFieldTypeChoices.TYPE_SELECT,
                "label": "Catalyst SD-WAN Personality",
                "description": "SD-WAN device personality",
            },
            "choices": ["vmanage", "vbond", "vsmart", "vedge", "cedge"]
        },
        {
            "field_data": {
                "key": "catalyst_sdwan_reachability",
                "type": CustomFieldTypeChoices.TYPE_SELECT,
                "label": "Catalyst SD-WAN Reachability",
                "description": "Device reachability status",
            },
            "choices": ["reachable", "unreachable", "unknown", "partial", "maintenance"]
        },
    ]
    
    for select_field in select_fields:
        field, created = CustomField.objects.get_or_create(
            key=select_field["field_data"]["key"],
            defaults=select_field["field_data"]
        )
        field.content_types.set([ContentType.objects.get_for_model(Device)])
        
        # Add choices if field was created or if choices don't exist
        if created or not CustomFieldChoice.objects.filter(custom_field=field).exists():
            for choice_value in select_field["choices"]:
                CustomFieldChoice.objects.get_or_create(
                    custom_field=field,
                    value=choice_value
                )


def catalyst_sdwan_interface_custom_fields(apps, **kwargs):
    """Create custom fields for Catalyst SD-WAN interfaces."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Interface = apps.get_model("dcim", "Interface")
    CustomField = apps.get_model("extras", "CustomField")
    CustomFieldChoice = apps.get_model("extras", "CustomFieldChoice")
    
    logger.info("Creating Interface custom fields for Catalyst SD-WAN")
    
    # Integer field
    integer_fields = [
        {
            "key": "catalyst_sdwan_vpn_id",
            "type": CustomFieldTypeChoices.TYPE_INTEGER,
            "label": "Catalyst SD-WAN VPN ID",
            "description": "VPN segment assignment",
        },
    ]
    
    # Create integer field
    for cf_dict in integer_fields:
        field, created = CustomField.objects.get_or_create(
            key=cf_dict["key"],
            defaults=cf_dict
        )
        field.content_types.set([ContentType.objects.get_for_model(Interface)])
    
    # Create SELECT fields with choices
    select_fields = [
        {
            "field_data": {
                "key": "catalyst_sdwan_admin_status",
                "type": CustomFieldTypeChoices.TYPE_SELECT,
                "label": "Catalyst SD-WAN Admin Status",
                "description": "Administrative status",
            },
            "choices": ["Up", "Down", "up", "down", "unknown"]
        },
        {
            "field_data": {
                "key": "catalyst_sdwan_oper_status",
                "type": CustomFieldTypeChoices.TYPE_SELECT,
                "label": "Catalyst SD-WAN Operational Status",
                "description": "Operational status",
            },
            "choices": ["Up", "Down", "up", "down", "if-state-up", "if-state-down", "unknown"]
        },
    ]
    
    for select_field in select_fields:
        field, created = CustomField.objects.get_or_create(
            key=select_field["field_data"]["key"],
            defaults=select_field["field_data"]
        )
        field.content_types.set([ContentType.objects.get_for_model(Interface)])
        
        # Add choices if field was created or if choices don't exist
        if created or not CustomFieldChoice.objects.filter(custom_field=field).exists():
            for choice_value in select_field["choices"]:
                CustomFieldChoice.objects.get_or_create(
                    custom_field=field,
                    value=choice_value
                )
