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


def extract_site_name_from_site_id(site_id):
    """
    Extract site name from SD-WAN site ID based on naming convention.
    
    Convention: 100### or 10#### where ### or #### is the site name
    Examples:
        100123 -> "123"
        10456 -> "456" 
        100001 -> "001"
    
    Args:
        site_id: SD-WAN site ID (integer or string)
        
    Returns:
        Extracted site name (string) or None if pattern doesn't match
    """
    if site_id is None:
        return None
        
    site_id_str = str(site_id)
    
    # Pattern 1: 100### (6 digits total, remove first 3)
    if site_id_str.startswith("100") and len(site_id_str) == 6:
        return site_id_str[3:]  # Remove "100" prefix
    
    # Pattern 2: 10#### (6 digits total, remove first 2) 
    if site_id_str.startswith("10") and len(site_id_str) == 6:
        return site_id_str[2:]  # Remove "10" prefix
        
    # Pattern 3: 10### (5 digits total, remove first 2)
    if site_id_str.startswith("10") and len(site_id_str) == 5:
        return site_id_str[2:]  # Remove "10" prefix
    
    # If no pattern matches, return the full site ID as string
    return site_id_str


def find_location_by_site_name_pattern(site_id, location_queryset=None):
    """
    Find location by extracting site name from site ID pattern.
    
    Args:
        site_id: SD-WAN site ID
        location_queryset: Optional queryset to search within
        
    Returns:
        Location object or None
    """
    from nautobot.dcim.models import Location
    
    if location_queryset is None:
        location_queryset = Location.objects.all()
    
    # Extract site name from site ID
    site_name = extract_site_name_from_site_id(site_id)
    if not site_name:
        return None
    
    # Try to find location with exact name match
    try:
        location = location_queryset.get(name=site_name)
        return location
    except Location.DoesNotExist:
        pass
    
    # Try with zero-padded versions for common patterns
    for padding in [3, 4, 5]:
        padded_name = site_name.zfill(padding)
        try:
            location = location_queryset.get(name=padded_name)
            return location
        except Location.DoesNotExist:
            continue
    
    return None


def extract_location_name_from_site_id(site_id):
    """
    Extract location name from SD-WAN site ID based on naming convention.
    
    SD-WAN site IDs are 6-digit numbers with multiple patterns:
    - Format: 100### (on-premise sites) → ### is the location name
    - Format: 10#### (on-premise sites) → #### is the location name  
    - Format: 127### (AWS-hosted sites) → ### is the location name
    
    Examples:
    - 100123 → "123"
    - 100001 → "1" 
    - 101234 → "1234"
    - 100050 → "50"
    - 127001 → "1" (AWS)
    - 127021 → "21" (AWS)
    - 127032 → "32" (AWS)
    
    Args:
        site_id: SD-WAN site ID (integer or string)
        
    Returns:
        str: Extracted location name or None if pattern doesn't match
    """
    if not site_id:
        return None
        
    # Convert to string and ensure it's 6 digits
    site_str = str(site_id).zfill(6)
    
    if len(site_str) != 6:
        return None
    
    # Check different patterns
    if site_str.startswith("100"):
        # Format: 100### (3-digit location name)
        location_digits = site_str[3:]
        # Remove leading zeros and return
        return str(int(location_digits))
    elif site_str.startswith("127"):
        # Format: 127### (AWS-hosted, 3-digit location name)
        location_digits = site_str[3:]
        # Remove leading zeros and return
        return str(int(location_digits))
    elif site_str.startswith("10") and not site_str.startswith("100"):
        # Format: 10#### (4-digit location name)
        location_digits = site_str[2:]
        # Remove leading zeros and return
        return str(int(location_digits))
    
    # If pattern doesn't match, return the full site ID as fallback
    return str(site_id)


def find_location_by_extracted_name(site_id, location_queryset=None):
    """
    Find a Nautobot Location by extracting the name from SD-WAN site ID.
    
    Args:
        site_id: SD-WAN site ID 
        location_queryset: Optional queryset to search within
        
    Returns:
        tuple: (Location object or None, extracted_name)
    """
    from nautobot.dcim.models import Location
    
    if location_queryset is None:
        location_queryset = Location.objects.all()
    
    # Extract location name from site ID
    extracted_name = extract_location_name_from_site_id(site_id)
    
    if not extracted_name:
        return None, None
    
    # Try to find location with extracted name
    try:
        location = location_queryset.get(name=extracted_name)
        return location, extracted_name
    except Location.DoesNotExist:
        return None, extracted_name
    except Location.MultipleObjectsReturned:
        # If multiple locations, get the first one
        location = location_queryset.filter(name=extracted_name).first()
        return location, extracted_name


def find_location_by_site_id(site_id, location_queryset=None):
    """
    Find a Nautobot Location by SD-WAN Site ID using multiple strategies.
    
    This function tries multiple approaches:
    1. Look for locations with matching catalyst_sdwan_site_id custom field
    2. Extract location name from site ID based on naming convention (100### or 10####)
    3. Direct name matching as fallback
    
    Args:
        site_id: SD-WAN site ID (integer)
        location_queryset: Optional queryset to search within
        
    Returns:
        Location object or None
    """
    from nautobot.dcim.models import Location
    
    if location_queryset is None:
        location_queryset = Location.objects.all()
    
    # Strategy 1: Look for locations with matching site ID custom field
    matching_locations = location_queryset.filter(
        custom_field_data__catalyst_sdwan_site_id=site_id
    )
    
    if matching_locations.exists():
        return matching_locations.first()
    
    # Strategy 2: Extract location name from site ID pattern
    location, extracted_name = find_location_by_extracted_name(site_id, location_queryset)
    if location:
        return location
    
    return None


def get_default_location_for_site_id(site_id, default_location_name=None):
    """
    Get or suggest a location for a given site ID.
    
    Args:
        site_id: SD-WAN site ID
        default_location_name: Default location name if no mapping found
        
    Returns:
        tuple: (Location object or None, suggested_name)
    """
    from nautobot.dcim.models import Location
    
    # First try to find existing location with this site ID or pattern
    location = find_location_by_site_id(site_id)
    if location:
        return location, location.name
    
    # If not found, suggest a name based on pattern
    extracted_name = extract_site_name_from_site_id(site_id)
    if extracted_name:
        suggested_name = extracted_name
    elif default_location_name:
        suggested_name = default_location_name
    else:
        suggested_name = f"Site-{site_id}"
    
    # Check if a location with suggested name exists
    try:
        location = Location.objects.get(name=suggested_name)
        return location, suggested_name
    except Location.DoesNotExist:
        return None, suggested_name


def map_device_to_location_by_site_id(device_info, default_location_name=None):
    """
    Map a device to a location based on its site ID using naming conventions.
    
    SD-WAN site IDs follow pattern: 100### or 10#### where ### or #### is the location name.
    
    Examples:
    - site-id 100123 → location "123"  
    - site-id 101456 → location "1456"
    - site-id 100001 → location "1"
    
    Args:
        device_info: Device information from vManage containing site-id
        default_location_name: Default location if site mapping not found
        
    Returns:
        tuple: (location_name, site_id, extracted_location_name)
    """
    site_id = device_info.get("site-id")
    
    if site_id:
        # Try to find existing location using multiple strategies
        location = find_location_by_site_id(site_id)
        if location:
            return location.name, site_id, location.name
        
        # Extract location name from site ID pattern
        extracted_name = extract_location_name_from_site_id(site_id)
        if extracted_name:
            return extracted_name, site_id, extracted_name
        
        # Fallback to site ID as location name  
        return f"Site-{site_id}", site_id, str(site_id)
    
    # Fall back to default location
    return default_location_name or "Unknown-Site", None, None
    
    # Fall back to default location
    return default_location_name or "Unknown-Site", None, None


def populate_location_site_id_field(location, site_id, logger=None):
    """
    Populate the catalyst_sdwan_site_id custom field for a location if not already set.
    
    Args:
        location: Nautobot Location object
        site_id: SD-WAN site ID to populate
        logger: Optional logger for info messages
        
    Returns:
        bool: True if field was updated, False if already set or error
    """
    try:
        current_site_id = location.custom_field_data.get("catalyst_sdwan_site_id")
        
        # Only update if field is empty or None
        if current_site_id is None or current_site_id == "":
            location.custom_field_data["catalyst_sdwan_site_id"] = site_id
            location.save()
            
            if logger:
                logger.info(
                    f"Populated catalyst_sdwan_site_id={site_id} for location '{location.name}'"
                )
            return True
        elif current_site_id != site_id:
            if logger:
                logger.warning(
                    f"Location '{location.name}' has catalyst_sdwan_site_id={current_site_id} "
                    f"but device reports site-id={site_id}. Not updating."
                )
        
        return False
        
    except Exception as e:
        if logger:
            logger.error(f"Failed to populate site ID for location '{location.name}': {e}")
        return False
