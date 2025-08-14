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
