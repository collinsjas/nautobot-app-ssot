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


def get_tag_if_exists(tag_name):
    """Get tag if it exists, otherwise return None."""
    if not tag_name:
        return None
    try:
        return Tag.objects.get(name=tag_name)
    except Tag.DoesNotExist:
        return None


class NautobotAdapter(Adapter):
    """Nautobot adapter for Catalyst SD-WAN."""

    # Model mappings
    tenant = NautobotTenant
    vrf = NautobotVrf
    device_type = NautobotDeviceType
    device_role = NautobotDeviceRole
    device = NautobotDevice
    interface_template = NautobotInterfaceTemplate
    interface = NautobotInterface

    # DiffSync adapter configuration
    top_level = ["tenant", "vrf", "device_type", "device_role", "device", "interface_template", "interface"]

    def __init__(self, job=None, sync=None, site_name=None, *args, **kwargs):
        """Initialize Nautobot adapter."""
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.site_name = site_name
        self.objects_to_delete = {
            "tenant": [],
            "vrf": [],
            "device_type": [],
            "device_role": [],
            "device": [],
            "interface_template": [],
            "interface": [],
        }

    def load_tenants(self):
        """Load only Tenants that are actually needed for this sync operation."""
        # Skip loading tenants if not needed for this sync
        if not hasattr(self.job, 'tenant_objects_needed') or not self.job.tenant_objects_needed:
            self.job.logger.info("Skipping tenant loading - not needed for this sync operation")
            return
            
        try:
            # Only load specific tenants that will be referenced in the sync
            tenant_names = getattr(self.job, 'required_tenant_names', [])
            if not tenant_names:
                self.job.logger.info("No specific tenants required for sync")
                return
                
            tenants = Tenant.objects.filter(name__in=tenant_names)
            
            for tenant in tenants:
                new_tenant = self.tenant(
                    name=tenant.name,
                    description=tenant.description or "",
                    comments=tenant.comments or "",
                    site_tag=self.site_name,
                )
                self.add(new_tenant)
                
            self.job.logger.info(f"Loaded {len(tenants)} required tenants")
        except Exception as e:
            self.job.logger.warning(f"Error loading tenants: {e}")

    def load_vrfs(self):
        """Load only VRFs that are actually needed for this sync operation."""
        # Skip loading VRFs if not needed for this sync
        if not hasattr(self.job, 'vrf_objects_needed') or not self.job.vrf_objects_needed:
            self.job.logger.info("Skipping VRF loading - not needed for this sync operation")
            return
            
        try:
            # Only load specific VRFs that will be referenced in the sync
            vrf_names = getattr(self.job, 'required_vrf_names', [])
            if not vrf_names:
                self.job.logger.info("No specific VRFs required for sync")
                return
                
            vrfs = VRF.objects.filter(name__in=vrf_names)
            
            for vrf in vrfs:
                new_vrf = self.vrf(
                    name=vrf.name,
                    tenant=vrf.tenant.name if vrf.tenant else "",
                    description=vrf.description or "",
                    namespace=vrf.namespace.name,
                    site_tag=self.site_name,
                    rd=vrf.rd or "",
                )
                self.add(new_vrf)
                
            self.job.logger.info(f"Loaded {len(vrfs)} required VRFs")
        except Exception as e:
            self.job.logger.warning(f"Error loading VRFs: {e}")

    def load_device_types(self):
        """Load only Device Types that are actually in use by devices being synced."""
        try:
            # Only load device types for devices we're actually syncing
            device_type_models = getattr(self.job, 'required_device_type_models', [])
            if not device_type_models:
                self.job.logger.info("No device types required - will be determined from SD-WAN data")
                return
            
            device_types = DeviceType.objects.filter(model__in=device_type_models)
            
            self.job.logger.info(f"Loading {len(device_types)} required device types")
            
            for device_type in device_types:
                # Ensure part_nbr consistency - use model name if part_number is empty
                part_nbr = device_type.part_number or device_type.model
                
                new_device_type = self.device_type(
                    model=device_type.model,
                    manufacturer=device_type.manufacturer.name,
                    part_nbr=part_nbr,
                    comments=device_type.comments or "",
                    u_height=device_type.u_height or 1,
                )
                self.add(new_device_type)
        except Exception as e:
            self.job.logger.warning(f"Error loading device types: {e}")

    def load_device_roles(self):
        """Load only Device Roles that are actually in use by devices being synced."""
        try:
            # Only load device roles for devices we're actually syncing
            device_role_names = getattr(self.job, 'required_device_role_names', [])
            if not device_role_names:
                self.job.logger.info("No device roles required - will be determined from SD-WAN data")
                return
            
            device_roles = Role.objects.filter(name__in=device_role_names, content_types__model='device')
            
            self.job.logger.info(f"Loading {len(device_roles)} required device roles")
            
            for role in device_roles:
                new_device_role = self.device_role(
                    name=role.name,
                    description=role.description or "",
                )
                self.add(new_device_role)
        except Exception as e:
            self.job.logger.warning(f"Error loading device roles: {e}")

    def load_devices(self):
        """Load only devices that exist in the target location."""
        try:
            # Only load devices from the specific target location
            target_location = self.site_name
            if not target_location:
                self.job.logger.warning("No target location specified - no devices to load")
                return
            
            # Load devices only from the target location
            devices = Device.objects.filter(location__name=target_location)
            
            self.job.logger.info(f"Loading {len(devices)} devices from location: {target_location}")
            
            for device in devices:
                new_device = self.device(
                    name=device.name,
                    device_type=device.device_type.model,
                    device_role=device.role.name,
                    serial=device.serial or "",
                    site=device.location.name,
                    comments=device.comments or "",
                    system_ip=device.custom_field_data.get("catalyst_sdwan_system_ip"),
                    site_id=device.custom_field_data.get("catalyst_sdwan_site_id"),
                    site_tag=self.site_name,
                    controller_group="",
                    personality=device.custom_field_data.get("catalyst_sdwan_personality"),
                    reachability=device.custom_field_data.get("catalyst_sdwan_reachability"),
                    device_model=device.custom_field_data.get("catalyst_sdwan_device_model"),
                    version=device.custom_field_data.get("catalyst_sdwan_version"),
                    status=device.custom_field_data.get("catalyst_sdwan_status"),
                    uuid=device.custom_field_data.get("catalyst_sdwan_uuid"),
                )
                self.add(new_device)
        except Exception as e:
            self.job.logger.warning(f"Error loading devices: {e}")

    def load_interface_templates(self):
        """Load only Interface Templates for device types that are actually being synced."""
        # Skip loading interface templates unless specifically needed
        if not hasattr(self.job, 'interface_template_objects_needed') or not self.job.interface_template_objects_needed:
            self.job.logger.info("Skipping interface template loading - not needed for this sync operation")
            return
            
        try:
            # Only load interface templates for device types we're working with
            device_type_models = getattr(self.job, 'required_device_type_models', [])
            if not device_type_models:
                self.job.logger.info("No device types specified - skipping interface template loading")
                return
            
            interface_templates = InterfaceTemplate.objects.filter(device_type__model__in=device_type_models)
            
            self.job.logger.info(f"Loading {len(interface_templates)} interface templates for required device types")
            
            for interface_template in interface_templates:
                new_interface_template = self.interface_template(
                    name=interface_template.name,
                    device_type=interface_template.device_type.model,
                    type=interface_template.type,
                    mgmt_only=interface_template.mgmt_only or False,
                    site_tag=self.site_name,
                )
                self.add(new_interface_template)
        except Exception as e:
            self.job.logger.warning(f"Error loading interface templates: {e}")

    def load_interfaces(self):
        """Load only Interfaces from devices that are actually being synced."""
        try:
            # Only load interfaces from devices in the target location
            target_location = self.site_name
            if not target_location:
                self.job.logger.warning("No target location specified - no interfaces to load")
                return
            
            interfaces = Interface.objects.filter(device__location__name=target_location)
            
            self.job.logger.info(f"Loading {len(interfaces)} interfaces from devices in location: {target_location}")
            
            for interface in interfaces:
                new_interface = self.interface(
                    name=interface.name,
                    device=interface.device.name,
                    site=interface.device.location.name,
                    description=interface.description or "",
                    type=interface.type,
                    site_tag=self.site_name,
                    admin_status=interface.custom_field_data.get("catalyst_sdwan_admin_status"),
                    oper_status=interface.custom_field_data.get("catalyst_sdwan_oper_status"),
                    vpn_id=interface.custom_field_data.get("catalyst_sdwan_vpn_id"),
                    ip_address="",  # Will be populated separately if needed
                    mtu=interface.mtu,
                )
                self.add(new_interface)
        except Exception as e:
            self.job.logger.warning(f"Error loading interfaces: {e}")

    def load(self):
        """Load only the data that's actually needed for this sync operation."""
        self.job.logger.info(f"Starting optimized load for site: {self.site_name}")
        
        # Only load what's needed - most objects will be created by the source adapter
        # The Nautobot adapter mainly needs existing objects to avoid duplicates
        
        # Load devices first as they're the core objects
        self.load_devices()
        
        # Load interfaces for the devices we loaded
        self.load_interfaces()
        
        # Only load supporting objects if they're actually needed
        # These will typically be skipped since objects are created by signals/source
        self.load_device_types()
        self.load_device_roles()
        self.load_tenants()
        self.load_vrfs()
        self.load_interface_templates()
        
        self.job.logger.info(f"Optimized load complete - loaded only required objects for site: {self.site_name}")