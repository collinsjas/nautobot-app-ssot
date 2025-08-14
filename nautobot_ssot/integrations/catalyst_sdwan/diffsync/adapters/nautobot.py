"""DiffSync Nautobot Adapter for Cisco Catalyst SD-WAN integration with SSoT app."""

from diffsync import Adapter
from nautobot.dcim.models import Controller, Device, DeviceType, Interface, Location
from nautobot.dcim.models import InterfaceTemplate
from nautobot.extras.models import Role, Status, Tag
from nautobot.ipam.models import IPAddress, Namespace, Prefix, VRF
from nautobot.tenancy.models import Tenant

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


class NautobotAdapter(Adapter):
    """DiffSync adapter using Nautobot as the data source."""

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

    def __init__(self, *args, job=None, sync=None, site_name, **kwargs):
        """Initialize the NautobotAdapter.
        
        Args:
            job: The SSoT job instance
            sync: DiffSync instance
            site_name: Name of the site/location to sync
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.site_name = site_name
        self.objects_to_delete = {
            "tenant": [],
            "vrf": [],
            "device": [],
            "interface": [],
            "prefix": [],
            "ipaddress": [],
        }

    def load_tenants(self):
        """Load Tenants from Nautobot that are tagged with SD-WAN."""
        try:
            tag = Tag.objects.get(name=PLUGIN_CFG.get("tag"))
            site_tag = Tag.objects.get(name=self.site_name)
            tenants = Tenant.objects.filter(tags__in=[tag, site_tag]).distinct()
            
            for tenant in tenants:
                tenant_name = tenant.name
                # Only load tenants that match our naming pattern
                if tenant_name.startswith(f"{PLUGIN_CFG.get('tenant_prefix', 'Catalyst-SDWAN')}:"):
                    new_tenant = self.tenant(
                        name=tenant_name,
                        description=tenant.description or "",
                        comments=tenant.comments or "",
                        site_tag=self.site_name,
                    )
                    self.add(new_tenant)
        except Tag.DoesNotExist:
            self.job.logger.warning(f"Tag {PLUGIN_CFG.get('tag')} not found in Nautobot")

    def load_vrfs(self):
        """Load VRFs from Nautobot that are tagged with SD-WAN."""
        try:
            tag = Tag.objects.get(name=PLUGIN_CFG.get("tag"))
            site_tag = Tag.objects.get(name=self.site_name)
            vrfs = VRF.objects.filter(tags__in=[tag, site_tag]).distinct()
            
            for vrf in vrfs:
                tenant_name = vrf.tenant.name if vrf.tenant else "Global"
                new_vrf = self.vrf(
                    name=vrf.name,
                    tenant=tenant_name,
                    description=vrf.description or "",
                    namespace=vrf.namespace.name if vrf.namespace else "Global",
                    site_tag=self.site_name,
                    rd=vrf.rd or "",
                )
                self.add(new_vrf)
        except Tag.DoesNotExist:
            self.job.logger.warning(f"Tag {PLUGIN_CFG.get('tag')} not found in Nautobot")

    def load_devicetypes(self):
        """Load Device Types from Nautobot that are tagged with SD-WAN."""
        try:
            tag = Tag.objects.get(name=PLUGIN_CFG.get("tag"))
            device_types = DeviceType.objects.filter(tags=tag)
            
            for device_type in device_types:
                new_device_type = self.device_type(
                    model=device_type.model,
                    manufacturer=device_type.manufacturer.name,
                    part_nbr=device_type.part_number or "",
                    comments=device_type.comments or "",
                    u_height=device_type.u_height or 1,
                )
                self.add(new_device_type)
        except Tag.DoesNotExist:
            self.job.logger.warning(f"Tag {PLUGIN_CFG.get('tag')} not found in Nautobot")

    def load_deviceroles(self):
        """Load Device Roles from Nautobot."""
        # Get roles that are applicable to devices and match SD-WAN patterns
        sdwan_role_names = ["vmanage", "vbond", "vsmart", "edge"]
        
        for role_name in sdwan_role_names:
            try:
                role = Role.objects.get(name=role_name)
                new_device_role = self.device_role(
                    name=role.name,
                    description=role.description or "",
                )
                self.add(new_device_role)
            except Role.DoesNotExist:
                # Role doesn't exist yet, will be created by the adapter
                pass

    def load_devices(self):
        """Load Devices from Nautobot from the target location."""
        try:
            tag = Tag.objects.get(name=PLUGIN_CFG.get("tag"))
            location = Location.objects.get(name=self.site_name)
            
            # Load ALL devices from the location, not just tagged ones
            # This allows the integration to take over existing devices
            devices = Device.objects.filter(location=location)
            
            self.job.logger.info(f"Loading {devices.count()} devices from location {self.site_name}")
            
            for device in devices:
                # Check if device has SD-WAN tag to determine if it's managed
                is_managed = tag in device.tags.all()
                
                new_device = self.device(
                    name=device.name,
                    device_type=device.device_type.model,
                    device_role=device.role.name,
                    serial=device.serial or "",
                    comments=device.comments or "",
                    site=self.site_name,
                    site_tag=self.site_name,
                    controller_group=(
                        device.controller_managed_device_group.name 
                        if device.controller_managed_device_group else ""
                    ),
                    system_ip=device.custom_field_data.get("catalyst_sdwan_system_ip"),
                    site_id=device.custom_field_data.get("catalyst_sdwan_site_id"),
                    personality=device.custom_field_data.get("catalyst_sdwan_personality"),
                    reachability=device.custom_field_data.get("catalyst_sdwan_reachability"),
                    device_model=device.custom_field_data.get("catalyst_sdwan_device_model"),
                    version=device.custom_field_data.get("catalyst_sdwan_version"),
                    status=device.status.name,
                    uuid=device.custom_field_data.get("catalyst_sdwan_uuid"),
                )
                self.add(new_device)
                
                if not is_managed:
                    self.job.logger.info(f"Device {device.name} is not currently SD-WAN managed but will be included in sync")
                    
        except (Tag.DoesNotExist, Location.DoesNotExist) as e:
            self.job.logger.warning(f"Error loading devices: {e}")

    def load_interfaces(self):
        """Load Interfaces from Nautobot that are tagged with SD-WAN."""
        try:
            tag = Tag.objects.get(name=PLUGIN_CFG.get("tag"))
            site_tag = Tag.objects.get(name=self.site_name)
            location = Location.objects.get(name=self.site_name)
            
            interfaces = Interface.objects.filter(
                tags__in=[tag, site_tag],
                device__location=location
            ).distinct()
            
            for interface in interfaces:
                new_interface = self.interface(
                    name=interface.name,
                    device=interface.device.name,
                    site=self.site_name,
                    description=interface.description or "",
                    type=interface.type,
                    site_tag=self.site_name,
                    admin_status=interface.custom_field_data.get("catalyst_sdwan_admin_status"),
                    oper_status=interface.custom_field_data.get("catalyst_sdwan_oper_status"),
                    vpn_id=interface.custom_field_data.get("catalyst_sdwan_vpn_id"),
                    ip_address=None,  # We'll handle IP addresses separately
                    mtu=interface.mtu,
                )
                self.add(new_interface)
        except (Tag.DoesNotExist, Location.DoesNotExist) as e:
            self.job.logger.warning(f"Error loading interfaces: {e}")

    def load_interface_templates(self):
        """Load Interface Templates from Nautobot for SD-WAN device types."""
        try:
            tag = Tag.objects.get(name=PLUGIN_CFG.get("tag"))
            device_types = DeviceType.objects.filter(tags=tag)
            
            for device_type in device_types:
                interface_templates = InterfaceTemplate.objects.filter(device_type=device_type)
                for intf_template in interface_templates:
                    new_interface_template = self.interface_template(
                        name=intf_template.name,
                        device_type=device_type.model,
                        type=intf_template.type,
                        mgmt_only=intf_template.mgmt_only,
                        site_tag=self.site_name,
                    )
                    self.add(new_interface_template)
        except Tag.DoesNotExist:
            self.job.logger.warning(f"Tag {PLUGIN_CFG.get('tag')} not found in Nautobot")

    def load(self):
        """Load all data from Nautobot."""
        self.load_tenants()
        self.load_vrfs()
        self.load_devicetypes()
        self.load_deviceroles()
        self.load_devices()
        self.load_interface_templates()
        self.load_interfaces()
