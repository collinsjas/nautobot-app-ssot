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
        """Load Device Types from Nautobot that are tagged with SD-WAN."""
        try:
            main_tag = get_tag_if_exists(PLUGIN_CFG.get("tag"))
            
            if main_tag:
                device_types = DeviceType.objects.filter(tags=main_tag)
            else:
                # If no tag exists, don't load any device types
                device_types = DeviceType.objects.none()
            
            for device_type in device_types:
                new_device_type = self.device_type(
                    model=device_type.model,
                    manufacturer=device_type.manufacturer.name,
                    part_nbr=device_type.part_number or "",
                    comments=device_type.comments or "",
                    u_height=device_type.u_height or 1,
                )
                self.add(new_device_type)
        except Exception as e:
            self.job.logger.warning(f"Error loading device types: {e}")

    def load_device_roles(self):
        """Load Device Roles from Nautobot that are tagged with SD-WAN."""
        try:
            main_tag = get_tag_if_exists(PLUGIN_CFG.get("tag"))
            
            if main_tag:
                device_roles = Role.objects.filter(tags=main_tag)
            else:
                # If no tag exists, don't load any device roles
                device_roles = Role.objects.none()
            
            for role in device_roles:
                new_device_role = self.device_role(
                    name=role.name,
                    description=role.description or "",
                )
                self.add(new_device_role)
        except Exception as e:
            self.job.logger.warning(f"Error loading device roles: {e}")

    def load_devices(self):
        """Load Devices from target locations."""
        try:
            # Load ALL devices from the target locations, not just tagged ones
            # This prevents "already exists" errors when devices exist but aren't tagged
            devices = Device.objects.filter(
                location__in=Location.objects.filter(
                    name__in=[self.site_name, self.job.device_site.name if self.job.device_site else None]
                ).exclude(name=None)
            )
            
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
        """Load Interface Templates from Nautobot that are tagged with SD-WAN."""
        try:
            main_tag = get_tag_if_exists(PLUGIN_CFG.get("tag"))
            
            if main_tag:
                interface_templates = InterfaceTemplate.objects.filter(tags=main_tag)
            else:
                # If no tag exists, don't load any interface templates
                interface_templates = InterfaceTemplate.objects.none()
            
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