"""Utility functions for Catalyst SD-WAN integration."""

import os
import yaml


def load_yamlfile(yaml_file):
    """Load YAML file and return content."""
    try:
        with open(yaml_file, encoding="utf-8") as file:
            return yaml.safe_load(file)
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"Error loading YAML file {yaml_file}: {e}")
        return None


def get_device_type_definition(model_name):
    """Get device type definition from YAML file."""
    devicetype_file_path = os.path.join(os.path.dirname(__file__), "..", "device-types")
    yaml_file = os.path.join(devicetype_file_path, f"{model_name}.yaml")
    
    if os.path.exists(yaml_file):
        return load_yamlfile(yaml_file)
    return None


def normalize_interface_name(interface_name):
    """Normalize interface names to consistent format."""
    # Convert common variations to standard format
    name_mappings = {
        "ge": "GigabitEthernet",
        "gi": "GigabitEthernet", 
        "te": "TenGigabitEthernet",
        "fa": "FastEthernet",
        "eth": "Ethernet",
        "mgmt": "Management",
    }
    
    for short_name, full_name in name_mappings.items():
        if interface_name.lower().startswith(short_name):
            # Extract the number part
            number_part = interface_name[len(short_name):]
            return f"{full_name}{number_part}"
    
    return interface_name


def map_sdwan_personality_to_role(personality):
    """Map SD-WAN personality to device role."""
    role_mapping = {
        "vmanage": "vmanage",
        "vbond": "vbond",
        "vsmart": "vsmart",
        "vedge": "edge",
        "cedge": "edge"
    }
    return role_mapping.get(personality, "edge")


def determine_interface_type(interface_name):
    """Determine interface type based on name."""
    interface_name_lower = interface_name.lower()
    
    type_mappings = [
        (["tengigabitethernet", "te"], "10gbase-t"),
        (["gigabitethernet", "ge", "gi"], "1000base-t"),
        (["fastethernet", "fa"], "100base-tx"),
        (["ethernet", "eth"], "1000base-t"),
        (["management", "mgmt"], "1000base-t"),
        (["serial"], "other"),
        (["loopback"], "virtual"),
        (["tunnel"], "virtual"),
    ]
    
    for name_patterns, interface_type in type_mappings:
        if any(pattern in interface_name_lower for pattern in name_patterns):
            return interface_type
    
    return "other"


def normalize_device_name(vmanage_hostname, existing_device_names=None):
    """
    Normalize device names between vManage and Nautobot.
    
    This function handles cases where device names might differ between
    vManage (host-name) and Nautobot device names.
    
    Args:
        vmanage_hostname: Hostname from vManage
        existing_device_names: List of existing device names in Nautobot
        
    Returns:
        Normalized device name that should match Nautobot
    """
    # Basic normalization - remove common suffixes/prefixes that might differ
    normalized = vmanage_hostname.strip()
    
    # Handle common naming patterns
    # Example: if vManage shows "router.domain.com" but Nautobot has "router"
    if "." in normalized:
        base_name = normalized.split(".")[0]
        # Check if base name exists in Nautobot
        if existing_device_names and base_name in existing_device_names:
            return base_name
    
    # Handle underscore vs dash differences
    # Example: "s356r1__001" vs "s356r1-001"
    if existing_device_names:
        # Try dash version
        dash_version = normalized.replace("__", "-").replace("_", "-")
        if dash_version in existing_device_names:
            return dash_version
            
        # Try underscore version
        underscore_version = normalized.replace("-", "_")
        if underscore_version in existing_device_names:
            return underscore_version
    
    return normalized


def find_matching_device_in_nautobot(vmanage_hostname, existing_devices):
    """
    Find a matching device in Nautobot for a vManage hostname.
    
    This handles cases where device names might not match exactly.
    
    Args:
        vmanage_hostname: Hostname from vManage
        existing_devices: QuerySet or list of Nautobot Device objects
        
    Returns:
        Matching Device object or None
    """
    # Try exact match first
    for device in existing_devices:
        if device.name == vmanage_hostname:
            return device
    
    # Try normalized matches
    normalized_name = normalize_device_name(
        vmanage_hostname, 
        [d.name for d in existing_devices]
    )
    
    for device in existing_devices:
        if device.name == normalized_name:
            return device
    
    # Try partial matches (be careful with this)
    base_vmanage = vmanage_hostname.split(".")[0].lower()
    for device in existing_devices:
        base_device = device.name.split(".")[0].lower()
        if base_vmanage == base_device:
            return device
    
    return None
