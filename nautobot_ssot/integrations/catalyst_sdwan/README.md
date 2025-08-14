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
