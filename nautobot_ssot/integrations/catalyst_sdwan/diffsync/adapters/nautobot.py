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
        """Load Tenants from Nautobot that are tagged with SD-WAN."""
        try:
            main_tag = get_tag_if_exists(PLUGIN_CFG.get("tag"))
            site_tag = get_tag_if_exists(self.site_name)
            
            # Build tag filter - only include tags that exist
            tags_to_filter = [tag for tag in [main_tag, site_tag] if tag is not None]
            
            if tags_to_filter:
                tenants = Tenant.objects.filter(tags__in=tags_to_filter).distinct()
            else:
                # If no tags exist, load tenants by name pattern instead
                tenants = Tenant.objects.filter(name__startswith=f"{PLUGIN_CFG.get('tenant_prefix', 'Catalyst-SDWAN')}:")
            
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
        except Exception as e:
            self.job.logger.warning(f"Error loading tenants: {e}")

    def load_vrfs(self):
        """Load VRFs from Nautobot that are tagged with SD-WAN."""
        try:
            main_tag = get_tag_if_exists(PLUGIN_CFG.get("tag"))
            site_tag = get_tag_if_exists(self.site_name)
            
            # Build tag filter - only include tags that exist
            tags_to_filter = [tag for tag in [main_tag, site_tag] if tag is not None]
            
            if tags_to_filter:
                vrfs = VRF.objects.filter(tags__in=tags_to_filter).distinct()
            else:
                # If no tags exist, load all VRFs (or add other filtering logic)
                vrfs = VRF.objects.all()
            
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
        except Exception as e:
            self.job.logger.warning(f"Error loading VRFs: {e}")

    def load_device_types(self):
        """Load Device Types from Nautobot that are related to SD-WAN."""
        try:
            # Load device types that are used by SD-WAN devices only
            # This prevents loading unrelated device types that would be deleted
            device_types_in_use = set()
            
            # Get device types used by SD-WAN devices in our target locations
            devices_query = Device.objects.filter(
                location__in=Location.objects.filter(
                    name__in=[self.site_name, self.job.device_site.name if self.job.device_site else None]
                ).exclude(name=None)
            )
            
            # Filter to only SD-WAN devices using the same criteria as load_devices
            main_tag = get_tag_if_exists(PLUGIN_CFG.get("tag"))
            site_tag = get_tag_if_exists(self.site_name)
            
            for device in devices_query:
                is_sdwan_device = False
                
                # Check if device has SD-WAN tags
                if main_tag and device.tags.filter(id=main_tag.id).exists():
                    is_sdwan_device = True
                elif site_tag and device.tags.filter(id=site_tag.id).exists():
                    is_sdwan_device = True
                # Check if device has SD-WAN custom fields populated
                elif device.custom_field_data.get("catalyst_sdwan_system_ip"):
                    is_sdwan_device = True
                elif device.custom_field_data.get("catalyst_sdwan_site_id"):
                    is_sdwan_device = True
                elif device.custom_field_data.get("catalyst_sdwan_uuid"):
                    is_sdwan_device = True
                # Check if device type manufacturer suggests SD-WAN
                elif device.device_type and device.device_type.manufacturer.name == PLUGIN_CFG.get("manufacturer_name", "Cisco"):
                    # Additional check - look for device models that are typically SD-WAN
                    model = device.device_type.model.lower()
                    if any(sdwan_model in model for sdwan_model in ['vedge', 'c8200', 'c1111', 'isr', 'asr']):
                        is_sdwan_device = True
                
                if is_sdwan_device and device.device_type:
                    device_types_in_use.add(device.device_type.id)
            
            # Also check for device types tagged with SD-WAN
            if main_tag:
                tagged_device_types = DeviceType.objects.filter(tags=main_tag)
                for dt in tagged_device_types:
                    device_types_in_use.add(dt.id)
            
            # Load only the device types we identified
            device_types = DeviceType.objects.filter(id__in=device_types_in_use)
            
            self.job.logger.info(f"Loading {len(device_types)} SD-WAN device types")
            
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
        """Load Device Roles from Nautobot that are related to SD-WAN."""
        try:
            # Load device roles that are used by SD-WAN devices only
            # This prevents loading unrelated device roles that would be deleted
            device_roles_in_use = set()
            
            # Get device roles used by SD-WAN devices in our target locations
            devices_query = Device.objects.filter(
                location__in=Location.objects.filter(
                    name__in=[self.site_name, self.job.device_site.name if self.job.device_site else None]
                ).exclude(name=None)
            )
            
            # Filter to only SD-WAN devices using the same criteria as load_devices
            main_tag = get_tag_if_exists(PLUGIN_CFG.get("tag"))
            site_tag = get_tag_if_exists(self.site_name)
            
            for device in devices_query:
                is_sdwan_device = False
                
                # Check if device has SD-WAN tags
                if main_tag and device.tags.filter(id=main_tag.id).exists():
                    is_sdwan_device = True
                elif site_tag and device.tags.filter(id=site_tag.id).exists():
                    is_sdwan_device = True
                # Check if device has SD-WAN custom fields populated
                elif device.custom_field_data.get("catalyst_sdwan_system_ip"):
                    is_sdwan_device = True
                elif device.custom_field_data.get("catalyst_sdwan_site_id"):
                    is_sdwan_device = True
                elif device.custom_field_data.get("catalyst_sdwan_uuid"):
                    is_sdwan_device = True
                # Check if device type manufacturer suggests SD-WAN
                elif device.device_type and device.device_type.manufacturer.name == PLUGIN_CFG.get("manufacturer_name", "Cisco"):
                    # Additional check - look for device models that are typically SD-WAN
                    model = device.device_type.model.lower()
                    if any(sdwan_model in model for sdwan_model in ['vedge', 'c8200', 'c1111', 'isr', 'asr']):
                        is_sdwan_device = True
                
                if is_sdwan_device and device.role:
                    device_roles_in_use.add(device.role.id)
            
            # Also check for device roles tagged with SD-WAN
            if main_tag:
                tagged_roles = Role.objects.filter(tags=main_tag, content_types__model='device')
                for role in tagged_roles:
                    device_roles_in_use.add(role.id)
            
            # Load only the device roles we identified
            device_roles = Role.objects.filter(id__in=device_roles_in_use, content_types__model='device')
            
            self.job.logger.info(f"Loading {len(device_roles)} SD-WAN device roles")
            
            for role in device_roles:
                new_device_role = self.device_role(
                    name=role.name,
                    description=role.description or "",
                )
                self.add(new_device_role)
        except Exception as e:
            self.job.logger.warning(f"Error loading device roles: {e}")

    def load_devices(self):
        """Load SD-WAN Devices from target locations."""
        try:
            # Load devices from target locations, but only those that are SD-WAN related
            # This prevents loading non-SD-WAN devices that would cause unwanted deletions
            devices_query = Device.objects.filter(
                location__in=Location.objects.filter(
                    name__in=[self.site_name, self.job.device_site.name if self.job.device_site else None]
                ).exclude(name=None)
            )
            
            # Filter to only SD-WAN devices using multiple criteria
            sdwan_devices = []
            main_tag = get_tag_if_exists(PLUGIN_CFG.get("tag"))
            site_tag = get_tag_if_exists(self.site_name)
            
            for device in devices_query:
                is_sdwan_device = False
                
                # Check if device has SD-WAN tags
                if main_tag and device.tags.filter(id=main_tag.id).exists():
                    is_sdwan_device = True
                elif site_tag and device.tags.filter(id=site_tag.id).exists():
                    is_sdwan_device = True
                # Check if device has SD-WAN custom fields populated
                elif device.custom_field_data.get("catalyst_sdwan_system_ip"):
                    is_sdwan_device = True
                elif device.custom_field_data.get("catalyst_sdwan_site_id"):
                    is_sdwan_device = True
                elif device.custom_field_data.get("catalyst_sdwan_uuid"):
                    is_sdwan_device = True
                # Check if device type manufacturer suggests SD-WAN
                elif device.device_type and device.device_type.manufacturer.name == PLUGIN_CFG.get("manufacturer_name", "Cisco"):
                    # Additional check - look for device models that are typically SD-WAN
                    model = device.device_type.model.lower()
                    if any(sdwan_model in model for sdwan_model in ['vedge', 'c8200', 'c1111', 'isr', 'asr']):
                        is_sdwan_device = True
                
                if is_sdwan_device:
                    sdwan_devices.append(device)
                else:
                    self.job.logger.debug(f"Skipping non-SD-WAN device: {device.name} at {device.location.name}")
            
            self.job.logger.info(f"Loading {len(sdwan_devices)} SD-WAN devices from {len(devices_query)} total devices in target locations")
            
            for device in sdwan_devices:
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
        """Load Interface Templates from Nautobot that are related to SD-WAN."""
        try:
            # Load interface templates that belong to device types we're managing
            # This prevents loading unrelated interface templates that would be deleted
            interface_templates_in_use = set()
            
            # Get device types used by devices in our target locations
            devices_in_locations = Device.objects.filter(
                location__name__in=[self.site_name, self.job.device_site.name if self.job.device_site else None]
            ).exclude(location__name=None)
            
            device_type_ids = set()
            for device in devices_in_locations:
                if device.device_type:
                    device_type_ids.add(device.device_type.id)
            
            # Also check for device types tagged with SD-WAN
            main_tag = get_tag_if_exists(PLUGIN_CFG.get("tag"))
            if main_tag:
                tagged_device_types = DeviceType.objects.filter(tags=main_tag)
                for dt in tagged_device_types:
                    device_type_ids.add(dt.id)
            
            # Get interface templates for these device types or tagged templates
            interface_templates = InterfaceTemplate.objects.filter(device_type_id__in=device_type_ids)
            
            # Also include interface templates tagged with SD-WAN
            if main_tag:
                tagged_templates = InterfaceTemplate.objects.filter(tags=main_tag)
                interface_templates = interface_templates.union(tagged_templates)
            
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
        """Load Interfaces from Nautobot that are tagged with SD-WAN."""
        try:
            main_tag = get_tag_if_exists(PLUGIN_CFG.get("tag"))
            site_tag = get_tag_if_exists(self.site_name)
            
            # Build tag filter - only include tags that exist
            tags_to_filter = [tag for tag in [main_tag, site_tag] if tag is not None]
            
            if tags_to_filter:
                interfaces = Interface.objects.filter(tags__in=tags_to_filter).distinct()
            else:
                # If no tags exist, load interfaces from devices in our locations
                interfaces = Interface.objects.filter(
                    device__location__name__in=[self.site_name, self.job.device_site.name if self.job.device_site else None]
                ).exclude(device__location__name=None)
            
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
                    ip_address="",  # Will be populated separately
                    mtu=interface.mtu,
                )
                self.add(new_interface)
        except Exception as e:
            self.job.logger.warning(f"Error loading interfaces: {e}")

    def load(self):
        """Load all data from Nautobot."""
        self.load_tenants()
        self.load_vrfs()
        self.load_device_types()
        self.load_device_roles()
        self.load_devices()
        self.load_interface_templates()
        self.load_interfaces()