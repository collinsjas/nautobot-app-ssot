# Cisco Catalyst SD-WAN SSoT Integration

This integration provides synchronization capabilities between Cisco Catalyst SD-WAN (vManage) and Nautobot, allowing you to maintain a single source of truth for your SD-WAN infrastructure.

## Features

- **Device Synchronization**: Syncs SD-WAN devices (vManage, vBond, vSmart, Edge devices) from vManage to Nautobot
- **Interface Management**: Synchronizes device interfaces with their operational states and configurations
- **VPN/VRF Mapping**: Maps SD-WAN VPNs to Nautobot VRFs
- **Template Tracking**: Tracks device template assignments (planned feature)
- **DiffSync Technology**: Uses DiffSync for intelligent synchronization that only updates when needed

## Supported Device Types

The integration includes device type definitions for common Catalyst SD-WAN devices:

- **C8000v**: Cisco Catalyst 8000V Edge Software Router
- **C8300 Series**: Cisco Catalyst 8300 Edge Platforms
- **vManage**: Network Management System
- **vBond**: Orchestrator
- **vSmart**: Controller

## Configuration

### Prerequisites

1. **vManage Controller**: Configure a Controller object in Nautobot pointing to your vManage instance
2. **External Integration**: Set up an ExternalIntegration with:
   - Remote URL pointing to your vManage (e.g., `https://vmanage.example.com`)
   - Secrets group containing vManage credentials (see details below)
   - SSL verification settings
3. **Managed Device Group**: Create a ControllerManagedDeviceGroup for SD-WAN devices
4. **Tags**: Ensure required tags exist in Nautobot:
   - `catalyst_sdwan` (default tag for SD-WAN objects)
   - Site-specific tags

### Settings

Add the following configuration to your `nautobot_config.py`:

```python
PLUGINS_CONFIG["nautobot_ssot"] = {
    # ... other SSoT config ...

    # Catalyst SD-WAN specific settings
    "catalyst_sdwan_tag": "catalyst_sdwan",
    "catalyst_sdwan_manufacturer_name": "Cisco",
    "catalyst_sdwan_tenant_prefix": "Catalyst-SDWAN",
    "catalyst_sdwan_comments": "Imported from Catalyst SD-WAN",
}
```

### Secrets Configuration

The integration requires proper authentication credentials to access your vManage controller. This is configured through Nautobot's secrets management system.

#### Step 1: Create Individual Secrets

Create the following secrets in Nautobot (`Extras > Secrets`):

1. **Username Secret**:
   - **Name**: `vmanage-username` (or your preferred name)
   - **Provider**: `Environment Variable` or `Text File`
   - **Parameters**:
     - **Variable/File**: Contains your vManage username
   - **Description**: vManage authentication username

2. **Password Secret**:
   - **Name**: `vmanage-password` (or your preferred name)
   - **Provider**: `Environment Variable` or `Text File`
   - **Parameters**:
     - **Variable/File**: Contains your vManage password
   - **Description**: vManage authentication password

#### Step 2: Create Secrets Group

Create a Secrets Group (`Extras > Secrets Groups`) that combines the individual secrets:

- **Name**: `vmanage-credentials` (or your preferred name)
- **Description**: Credentials for vManage API access
- **Secrets**:
  - Add the username secret with **Access Type**: `HTTP(S)` and **Secret Type**: `Username`
  - Add the password secret with **Access Type**: `HTTP(S)` and **Secret Type**: `Password`

#### Step 3: Configure External Integration

When creating the ExternalIntegration object:

- **Name**: `vManage-Integration` (or your preferred name)
- **Remote URL**: `https://your-vmanage-server.example.com` (without `/dataservice` path)
- **Verify SSL**: Enable if using valid SSL certificates, disable for self-signed certificates
- **Secrets Group**: Select the secrets group created in Step 2
- **Extra Config**: (Optional JSON for additional settings)
  ```json
  {
    "tenant_prefix": "Catalyst-SDWAN",
    "ignore_certificate_errors": false,
    "timeout": 30
  }
  ```

#### Environment Variables (Alternative)

If using environment variables for secrets:

```bash
# Set these environment variables on the Nautobot server
export VMANAGE_USERNAME="your-vmanage-username"
export VMANAGE_PASSWORD="your-vmanage-password"
```

#### File-based Secrets (Alternative)

If using file-based secrets:

```bash
# Create secure files on the Nautobot server
echo "your-vmanage-username" > /opt/nautobot/secrets/vmanage_username.txt
echo "your-vmanage-password" > /opt/nautobot/secrets/vmanage_password.txt

# Set appropriate permissions
chmod 600 /opt/nautobot/secrets/vmanage_*.txt
chown nautobot:nautobot /opt/nautobot/secrets/vmanage_*.txt
```

#### Security Best Practices

1. **Use Strong Passwords**: Ensure vManage user has a strong, unique password
2. **Principle of Least Privilege**: Create a dedicated vManage user with minimum required permissions:
   - Read-only access to device inventory
   - Access to template information
   - Access to interface and VPN data
3. **Rotate Credentials**: Regularly rotate vManage passwords and update secrets
4. **Monitor Access**: Enable audit logging on vManage to track API access
5. **Network Security**: Ensure Nautobot can only access vManage over secure networks

#### Required vManage Permissions

The vManage user account needs the following minimum permissions:

- **Device Management**: Read access to device inventory
- **Template Management**: Read access to device and feature templates
- **Monitoring**: Read access to real-time monitoring data
- **Administration**: Read access to system information (for version detection)

You can create a custom user group in vManage with these specific permissions rather than using admin privileges.

### Custom Fields

The integration creates several custom fields on Device and Interface objects to store SD-WAN specific data:

**Device Custom Fields:**
- `catalyst_sdwan_system_ip`: Device system IP address
- `catalyst_sdwan_site_id`: SD-WAN site ID
- `catalyst_sdwan_personality`: Device personality (vmanage, vbond, vsmart, vedge, cedge)
- `catalyst_sdwan_reachability`: Device reachability status
- `catalyst_sdwan_device_model`: Specific device model
- `catalyst_sdwan_version`: Software version
- `catalyst_sdwan_uuid`: Unique device identifier

**Interface Custom Fields:**
- `catalyst_sdwan_vpn_id`: VPN ID the interface belongs to
- `catalyst_sdwan_admin_status`: Administrative status
- `catalyst_sdwan_oper_status`: Operational status

## Usage

1. **Create the Job**: The integration provides a `CatalystSdwanDataSource` job
2. **Configure Parameters**:
   - Select your vManage controller
   - Choose the target location for devices
   - Enable debug logging if needed
3. **Run the Job**: Execute the job to perform synchronization

## Data Mappings

| SD-WAN Object | Nautobot Object | Notes |
|---------------|-----------------|-------|
| Device | Device | Includes controllers and edge devices |
| Interface | Interface | Physical and logical interfaces |
| VPN | VRF | SD-WAN VPNs mapped to VRFs |
| Site | Location | Site information (planned) |
| Device Template | Config Context | Template assignments (planned) |

## Device Role Mapping

| SD-WAN Personality | Nautobot Role |
|-------------------|---------------|
| vmanage | vmanage |
| vbond | vbond |
| vsmart | vsmart |
| vedge | edge |
| cedge | edge |

## Interface Type Mapping

The integration automatically determines interface types based on naming conventions:

- `GigabitEthernet*` → `1000base-t`
- `TenGigabitEthernet*` → `10gbase-t`
- `FastEthernet*` → `100base-tx`
- `Management*` → `1000base-t`
- Others → `other`

## VPN/VRF Handling

SD-WAN VPNs are mapped to Nautobot VRFs with the following defaults:

- **VPN 0**: Transport VPN (for WAN connectivity)
- **VPN 512**: Management VPN (for device management)
- **Other VPNs**: Service VPNs (for user traffic)

## Testing in Lab Environment

### Prerequisites for Testing

Before testing the integration, ensure you have:

1. **Lab Nautobot Instance**: A working Nautobot installation with SSoT plugin enabled
2. **vManage Access**: Access to a Catalyst SD-WAN vManage controller (lab or production)
3. **Network Connectivity**: Nautobot server can reach your vManage instance
4. **Administrative Access**: Ability to create objects in Nautobot and vManage

### Step-by-Step Testing Guide

#### Step 1: Install and Enable the Integration

1. **Copy Integration Files**:

   ```bash
   # Copy the catalyst_sdwan directory to your Nautobot SSoT integrations
   cp -r /path/to/catalyst_sdwan /opt/nautobot/nautobot_ssot/integrations/
   ```

2. **Update Nautobot Configuration**:
   Add to your `nautobot_config.py`:

   ```python
   PLUGINS_CONFIG["nautobot_ssot"] = {
       # ... existing SSoT config ...

       # Catalyst SD-WAN settings
       "catalyst_sdwan_tag": "catalyst_sdwan",
       "catalyst_sdwan_manufacturer_name": "Cisco",
       "catalyst_sdwan_tenant_prefix": "LAB-SDWAN",
       "catalyst_sdwan_comments": "Lab Catalyst SD-WAN Import",
   }
   ```

3. **Restart Nautobot**:

   ```bash
   sudo systemctl restart nautobot
   # OR for Docker:
   docker-compose restart nautobot
   ```

#### Step 2: Create Required Nautobot Objects

1. **Create Tags** (via Admin UI or API):

   ```python
   # Via Django shell or Nautobot shell
   from nautobot.extras.models import Tag

   # Create main SD-WAN tag
   tag, created = Tag.objects.get_or_create(
       name="catalyst_sdwan",
       defaults={"description": "Catalyst SD-WAN objects"}
   )

   # Create site-specific tag
   site_tag, created = Tag.objects.get_or_create(
       name="lab-site",
       defaults={"description": "Lab site objects"}
   )
   ```

2. **Create Location** (if not exists):

   ```python
   from nautobot.dcim.models import Location, LocationType

   # Create location type if needed
   location_type, created = LocationType.objects.get_or_create(
       name="Site",
       defaults={"description": "Network Site"}
   )

   # Create location
   location, created = Location.objects.get_or_create(
       name="lab-site",
       location_type=location_type,
       defaults={"description": "Lab testing site"}
   )
   ```

3. **Create Cisco Manufacturer**:

   ```python
   from nautobot.dcim.models import Manufacturer

   cisco, created = Manufacturer.objects.get_or_create(
       name="Cisco",
       defaults={"description": "Cisco Systems"}
   )
   ```

4. **Create Custom Fields**:

   ```python
   from nautobot.extras.models import CustomField
   from nautobot.dcim.models import Device, Interface
   from django.contrib.contenttypes.models import ContentType

   # Device custom fields
   device_ct = ContentType.objects.get_for_model(Device)
   interface_ct = ContentType.objects.get_for_model(Interface)

   device_fields = [
       ("catalyst_sdwan_system_ip", "System IP Address"),
       ("catalyst_sdwan_site_id", "Site ID"),
       ("catalyst_sdwan_personality", "Device Personality"),
       ("catalyst_sdwan_reachability", "Reachability Status"),
       ("catalyst_sdwan_device_model", "Device Model"),
       ("catalyst_sdwan_version", "Software Version"),
       ("catalyst_sdwan_uuid", "Device UUID"),
   ]

   for field_name, description in device_fields:
       CustomField.objects.get_or_create(
           name=field_name,
           defaults={
               "label": description,
               "type": "text",
               "description": f"Catalyst SD-WAN {description}",
           }
       ).content_types.add(device_ct)

   # Interface custom fields
   interface_fields = [
       ("catalyst_sdwan_vpn_id", "VPN ID"),
       ("catalyst_sdwan_admin_status", "Admin Status"),
       ("catalyst_sdwan_oper_status", "Operational Status"),
   ]

   for field_name, description in interface_fields:
       CustomField.objects.get_or_create(
           name=field_name,
           defaults={
               "label": description,
               "type": "text",
               "description": f"Catalyst SD-WAN {description}",
           }
       ).content_types.add(interface_ct)
   ```

#### Step 3: Configure vManage Integration

1. **Create Secrets**:
   Navigate to `Extras > Secrets` and create:
   - **Username secret**: Name it `vmanage-lab-username`
   - **Password secret**: Name it `vmanage-lab-password`

2. **Create Secrets Group**:
   Navigate to `Extras > Secrets Groups` and create:
   - **Name**: `vmanage-lab-credentials`
   - Add both secrets with HTTP(S) access type

3. **Create External Integration**:
   Navigate to `Extras > External Integrations` and create:

   ```yaml
   Name: vManage-Lab
   Remote URL: https://your-lab-vmanage-ip-or-fqdn
   Verify SSL: False (for lab self-signed certs)
   Secrets Group: vmanage-lab-credentials
   Extra Config: {"tenant_prefix": "LAB-SDWAN"}
   ```

4. **Create Controller**:
   Navigate to `DCIM > Controllers` and create:

   ```yaml
   Name: Lab-vManage
   Controller Type: (create if needed)
   Location: lab-site
   External Integration: vManage-Lab
   ```

5. **Create Controller Managed Device Group**:
   Navigate to `DCIM > Controller Managed Device Groups` and create:

   ```yaml
   Name: Lab-SDWAN-Devices
   Controller: Lab-vManage
   Weight: 100
   ```

#### Step 4: Test the Integration

1. **Navigate to Jobs**:
   Go to `Extensibility > Jobs` and find "Cisco Catalyst SD-WAN Data Source"

2. **Run Initial Test**:

   ```yaml
   vManage: Lab-vManage
   Device Site: lab-site
   Debug: True (enable for detailed logging)
   Dry Run: True (for initial testing)
   ```

3. **Review Results**:
   Check the job logs for:
   - Successful vManage authentication
   - Device discovery count
   - Interface enumeration
   - Any error messages

4. **Run Live Sync**:
   If dry run looks good, run again with:

   ```yaml
   Dry Run: False
   ```

#### Step 5: Verify Results

1. **Check Created Objects**:
   - **Devices**: Navigate to `DCIM > Devices` and filter by tag "catalyst_sdwan"
   - **Interfaces**: Check that interfaces were created for each device
   - **VRFs**: Navigate to `IPAM > VRFs` to see created VPN mappings
   - **Device Types**: Check `DCIM > Device Types` for auto-created types

2. **Validate Custom Fields**:
   Open any synced device and verify custom fields are populated:
   - System IP, Site ID, Personality, etc.

3. **Check Relationships**:
   Verify devices are properly associated with:
   - Correct location
   - Controller managed device group
   - Appropriate tags

### Troubleshooting Test Issues

#### Common Lab Issues

1. **SSL Certificate Errors**:

   ```bash
   # If you see SSL errors, disable SSL verification in External Integration
   # Or add your lab CA certificate to Nautobot's trust store
   ```

2. **Authentication Failures**:

   ```bash
   # Test vManage credentials manually:
   curl -k -X POST https://your-vmanage/j_security_check \
        -d "j_username=your-user&j_password=your-pass"
   ```

3. **Import Errors**:

   ```bash
   # Check Nautobot logs for import issues:
   tail -f /opt/nautobot/logs/nautobot.log
   # Or for Docker:
   docker-compose logs -f nautobot
   ```

4. **Missing Dependencies**:

   ```bash
   # Install required packages if missing:
   pip install requests pyyaml
   ```

#### Debug Mode Output

When debug is enabled, look for these log entries:

- `Loading devices from vManage...`
- `Found X devices in vManage`
- `Creating device type for model Y`
- `Processing interfaces for device Z`

### Lab Testing Scenarios

#### Scenario 1: Basic Device Import

- **Goal**: Import all vManage-visible devices
- **Expected**: Controllers and edge devices appear in Nautobot
- **Validation**: Check device counts match between vManage and Nautobot

#### Scenario 2: Interface Synchronization

- **Goal**: Verify interface details are accurate
- **Expected**: Interface names, types, and statuses match vManage
- **Validation**: Compare interface lists between systems

#### Scenario 3: VPN/VRF Mapping

- **Goal**: Ensure VPNs become VRFs correctly
- **Expected**: Transport (0) and Management (512) VRFs created
- **Validation**: Check VRF namespace and tenant assignments

#### Scenario 4: Incremental Updates

- **Goal**: Test that subsequent runs only update changes
- **Expected**: No duplicate objects, only modified fields updated
- **Validation**: Run job twice, second run should show minimal changes

### Cleanup for Re-testing

To clean up and re-test:

```python
# Via Nautobot shell - CAUTION: This deletes data!
from nautobot.dcim.models import Device, Interface, DeviceType
from nautobot.ipam.models import VRF
from nautobot.extras.models import Tag

# Delete all SD-WAN tagged objects
tag = Tag.objects.get(name="catalyst_sdwan")
Device.objects.filter(tags=tag).delete()
Interface.objects.filter(tags=tag).delete()
DeviceType.objects.filter(tags=tag).delete()
VRF.objects.filter(tags=tag).delete()
```

### Success Criteria

Your lab test is successful when:

- [ ] vManage authentication works without errors
- [ ] All expected devices are imported with correct attributes
- [ ] Interfaces are created with proper types and custom field data
- [ ] VRFs are created for discovered VPNs
- [ ] Device roles are properly assigned based on personality
- [ ] Custom fields contain accurate vManage data
- [ ] Subsequent job runs complete quickly with no duplicates

## Troubleshooting

### Common Issues

1. **Authentication Failures**: Verify vManage credentials in the secrets group
2. **SSL Certificate Issues**: Check SSL verification settings in the External Integration
3. **Missing Device Types**: Add device type YAML files for unsupported models
4. **Custom Field Errors**: Ensure custom fields are created with correct names and types

### Debug Mode

Enable debug logging in the job parameters to get detailed information about the synchronization process.

## Extending the Integration

### Adding New Device Types

1. Create a YAML file in `device-types/` directory
2. Follow the existing format with manufacturer, model, interfaces, etc.
3. The integration will automatically load interface templates from the YAML

### Custom Field Extensions

You can extend the integration to sync additional SD-WAN attributes by:

1. Adding new custom fields to the Nautobot models
2. Updating the adapter to populate these fields
3. Modifying the DiffSync models to include the new attributes

## Future Enhancements

- **Policy Synchronization**: Sync SD-WAN policies as Config Contexts
- **Site Management**: Enhanced site/location synchronization
- **Template Details**: Detailed template configuration tracking
- **Overlay Topology**: Sync overlay network topology information
- **Performance Metrics**: Historical performance data integration
