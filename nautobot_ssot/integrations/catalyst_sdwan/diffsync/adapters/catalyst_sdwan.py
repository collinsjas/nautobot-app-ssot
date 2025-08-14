"""DiffSync Adapter for Cisco Catalyst SD-WAN."""

import logging
import os
from typing import Optional

from diffsync import Adapter
from diffsync.exceptions import ObjectNotFound

from nautobot_ssot.integrations.catalyst_sdwan.constant import PLUGIN_CFG
from nautobot_ssot.integrations.catalyst_sdwan.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotDeviceRole,
    NautobotDeviceType,
    NautobotInterface,
    NautobotInterfaceTemplate,
    NautobotTenant,
    NautobotVrf,
)
from nautobot_ssot.integrations.catalyst_sdwan.diffsync.utils import (
    get_device_type_definition,
    map_sdwan_personality_to_role,
    determine_interface_type,
    normalize_interface_name,
    map_device_to_location_by_site_id,
)

logger = logging.getLogger(__name__)


class CatalystSdwanAdapter(Adapter):
    """DiffSync adapter for Cisco Catalyst SD-WAN."""

    tenant = NautobotTenant
    vrf = NautobotVrf
    device_type = NautobotDeviceType
    device_role = NautobotDeviceRole
    device = NautobotDevice
    interface_template = NautobotInterfaceTemplate
    interface = NautobotInterface

    top_level = [
        "tenant",
        "vrf",
        "device_type",
        "device_role",
        "interface_template",
        "device",
        "interface",
    ]

    def __init__(self, *args, job=None, sync=None, client, tenant_prefix, **kwargs):
        """Initialize Catalyst SD-WAN adapter.

        Args:
            job (object, optional): Catalyst SD-WAN job. Defaults to None.
            sync (object, optional): Catalyst SD-WAN DiffSync. Defaults to None.
            client (object): Catalyst SD-WAN credentials.
            tenant_prefix (str): Prefix for tenant names.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = client
        self.site = client.site
        self.tenant_prefix = tenant_prefix
        self.devices = {}
        self.device_templates = {}
        self.feature_templates = {}

    def load_tenants(self):
        """Load tenants from SD-WAN. Create a default tenant for SD-WAN objects."""
        tenant_name = f"{self.tenant_prefix}:Global"
        new_tenant = self.tenant(
            name=tenant_name,
            description="Global tenant for Catalyst SD-WAN objects",
            comments=PLUGIN_CFG.get("comments", ""),
            site_tag=self.site,
        )
        self.add(new_tenant)

    def load_vrfs(self):
        """Load VRFs from SD-WAN devices."""
        tenant_name = f"{self.tenant_prefix}:Global"
        
        # Create default VRFs commonly used in SD-WAN
        default_vrfs = [
            {"name": "0", "description": "Transport VPN"},
            {"name": "512", "description": "Management VPN"},
        ]
        
        # Get VPN information from devices
        for device_id, device_info in self.devices.items():
            try:
                vpn_list = self.conn.get_vpn_list(device_id)
                for vpn in vpn_list:
                    vrf_name = vpn.get("vpn-id", "0")
                    if not any(vrf["name"] == vrf_name for vrf in default_vrfs):
                        default_vrfs.append({
                            "name": vrf_name,
                            "description": f"VPN {vrf_name}"
                        })
            except Exception as e:
                self.job.logger.warning(f"Failed to get VPN list for device {device_id}: {e}")
        
        for vrf_info in default_vrfs:
            new_vrf = self.vrf(
                name=vrf_info["name"],
                namespace=tenant_name,
                tenant=tenant_name,
                description=vrf_info["description"],
                site_tag=self.site,
            )
            self.add(new_vrf)

    def load_devicetypes(self):
        """Load device types from SD-WAN device data."""
        device_models = set()
        for device_info in self.devices.values():
            model = device_info.get("device-model", "Unknown")
            if model and model != "Unknown":
                device_models.add(model)
        
        for model in device_models:
            _devicetype = self.device_type(
                model=model,
                manufacturer=PLUGIN_CFG.get("manufacturer_name", "Cisco"),
                part_nbr=model,  # Use model as part number if no specific part number
                comments=PLUGIN_CFG.get("comments", ""),
                u_height=1,  # Default height
            )
            self.add(_devicetype)

    def load_deviceroles(self):
        """Load device roles from SD-WAN device data."""
        device_roles = set()
        for device_info in self.devices.values():
            personality = device_info.get("personality", "unknown")
            role = map_sdwan_personality_to_role(personality)
            device_roles.add(role)
        
        for role in device_roles:
            new_devicerole = self.device_role(
                name=role, 
                description=f"Catalyst SD-WAN {role.title()} device"
            )
            self.add(new_devicerole)

    def load_devices(self):
        """Load devices from SD-WAN."""
        processed_devices = set()  # Track processed device names + sites to avoid duplicates
        
        self.job.logger.info(f"Loading {len(self.devices)} devices from SD-WAN")
        
        for device_info in self.devices.values():
            personality = device_info.get("personality", "unknown")
            role = map_sdwan_personality_to_role(personality)
            model = device_info.get("device-model", "Unknown")
            
            # Map device to location based on site ID using naming convention
            device_location, site_id, extracted_name = map_device_to_location_by_site_id(
                device_info, 
                default_location_name=self.site
            )
            
            device_name = device_info.get("host-name", device_info.get("deviceId", "Unknown"))
            device_key = f"{device_name}__{device_location}"
            
            # Skip if we've already processed this device
            if device_key in processed_devices:
                self.job.logger.warning(
                    f"Skipping duplicate device: {device_name} at site {device_location} "
                    f"(key: {device_key})"
                )
                continue
            
            processed_devices.add(device_key)
            
            self.job.logger.debug(f"Processing device: {device_name} at site {device_location}")
            
            # Log the mapping decision
            if site_id:
                if extracted_name and extracted_name != device_location:
                    self.job.logger.info(
                        f"Device {device_name} with site-id {site_id}: "
                        f"extracted location name '{extracted_name}' mapped to '{device_location}'"
                    )
                elif device_location != self.site:
                    self.job.logger.info(
                        f"Device {device_name} with site-id {site_id} "
                        f"mapped to location '{device_location}' (from site pattern)"
                    )
                else:
                    self.job.logger.debug(
                        f"Device {device_name} with site-id {site_id} "
                        f"using default location '{device_location}'"
                    )
            
            new_device = self.device(
                name=device_name,
                device_type=model,
                device_role=role,
                serial=device_info.get("board-serial", device_info.get("chassis-serial-number", "")),
                comments=PLUGIN_CFG.get("comments", ""),
                system_ip=device_info.get("system-ip"),
                site_id=site_id,  # Use the site_id from mapping
                site=device_location,  # Use mapped location
                site_tag=device_location,  # Use mapped location for tag
                controller_group=(
                    self.job.vmanage.controller_managed_device_groups.first().name
                    if self.job.vmanage.controller_managed_device_groups.count() != 0
                    else ""
                ),
                personality=personality,
                reachability=device_info.get("reachability"),
                device_model=device_info.get("device-model"),
                version=device_info.get("version"),
                status=device_info.get("status"),
                uuid=device_info.get("uuid"),
            )
            self.add(new_device)

    def load_interfaces(self):
        """Load interfaces from SD-WAN devices."""
        for device_id, device_info in self.devices.items():
            device_name = device_info.get("host-name", device_info.get("deviceId", "Unknown"))
            
            try:
                interfaces = self.conn.get_device_interfaces(device_id)
                for interface_info in interfaces:
                    interface_name = interface_info.get("ifname", interface_info.get("interface", "Unknown"))
                    
                    # Skip loopback and tunnel interfaces for now
                    if interface_name.lower().startswith(("loopback", "tunnel")):
                        continue
                    
                    # Normalize interface name
                    normalized_name = normalize_interface_name(interface_name)
                    
                    new_interface = self.interface(
                        name=normalized_name,
                        device=device_name,
                        site=self.site,
                        description=interface_info.get("description", ""),
                        type=determine_interface_type(interface_name),
                        site_tag=self.site,
                        admin_status=interface_info.get("admin-status"),
                        oper_status=interface_info.get("oper-status"),
                        vpn_id=interface_info.get("vpn-id"),
                        ip_address=interface_info.get("ip-address"),
                        mtu=interface_info.get("mtu"),
                    )
                    self.add(new_interface)
            except Exception as e:
                self.job.logger.warning(f"Failed to get interfaces for device {device_name}: {e}")

    def load_interfacetemplates(self):
        """Load interface templates from YAML files."""
        device_models = {device_info.get("device-model", "Unknown") for device_info in self.devices.values()}
        
        for model in device_models:
            if model and model != "Unknown":
                device_specs = get_device_type_definition(model)
                if device_specs and device_specs.get("interfaces"):
                    for intf in device_specs["interfaces"]:
                        new_interfacetemplate = self.interface_template(
                            name=intf["name"],
                            device_type=model,
                            type=intf["type"],
                            mgmt_only=intf.get("mgmt_only", False),
                            site_tag=self.site,
                        )
                        self.add(new_interfacetemplate)
                else:
                    self.job.logger.info(
                        f"No YAML descriptor file for device type {model}, skipping interface template creation."
                    )

    def load_device_templates(self):
        """Load device template information."""
        try:
            self.device_templates = {
                template["templateId"]: template 
                for template in self.conn.get_device_templates()
            }
            self.feature_templates = {
                template["templateId"]: template
                for template in self.conn.get_feature_templates()
            }
        except Exception as e:
            self.job.logger.warning(f"Failed to load templates: {e}")

    def load(self):
        """Method for one stop shop loading of all models."""
        # First get all devices
        devices_data = self.conn.get_devices()
        self.devices = {device["deviceId"]: device for device in devices_data}
        
        # Load device templates for reference
        self.load_device_templates()
        
        # Load all models
        self.load_tenants()
        self.load_vrfs()
        self.load_devicetypes()
        self.load_deviceroles()
        self.load_devices()
        self.load_interfacetemplates()
        self.load_interfaces()
