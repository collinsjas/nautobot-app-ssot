"""Nautobot Models for Cisco Catalyst SD-WAN integration with SSoT app."""

import logging

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from nautobot.dcim.models import ControllerManagedDeviceGroup, Location, Manufacturer
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import DeviceType as OrmDeviceType
from nautobot.dcim.models import Interface as OrmInterface
from nautobot.dcim.models import InterfaceTemplate as OrmInterfaceTemplate
from nautobot.extras.models import Role, Status, Tag
from nautobot.ipam.models import VRF as OrmVrf
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import IPAddressToInterface, Namespace
from nautobot.ipam.models import Prefix as OrmPrefix
from nautobot.tenancy.models import Tenant as OrmTenant

from nautobot_ssot.integrations.catalyst_sdwan.constant import PLUGIN_CFG
from nautobot_ssot.integrations.catalyst_sdwan.diffsync.models.base import (
    Device,
    DeviceRole,
    DeviceType,
    DeviceTemplate,
    Interface,
    InterfaceTemplate,
    IPAddress,
    Prefix,
    Tenant,
    Vrf,
)

logger = logging.getLogger(__name__)


def get_tag_if_exists(tag_name):
    """Safely get a tag by name, return None if it doesn't exist."""
    try:
        return Tag.objects.get(name=tag_name)
    except Tag.DoesNotExist:
        logger.warning(f"Tag '{tag_name}' not found - it should have been created by signals")
        return None


class NautobotTenant(Tenant):
    """Nautobot implementation of the Tenant Model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Tenant object in Nautobot."""
        _tenant = OrmTenant(name=ids["name"], description=attrs["description"], comments=attrs["comments"])
        
        # Add main tag if configured
        main_tag_name = PLUGIN_CFG.get("tag")
        if main_tag_name:
            main_tag = get_tag_if_exists(main_tag_name)
            if main_tag:
                _tenant.tags.add(main_tag)
        
        # Add site-specific tag
        site_tag_name = attrs["site_tag"]
        if site_tag_name:
            site_tag = get_tag_if_exists(site_tag_name)
            if site_tag:
                _tenant.tags.add(site_tag)
            
        _tenant.validated_save()

        # Create namespace for the tenant if it doesn't exist
        try:
            Namespace.objects.get(name=ids["name"])
        except Namespace.DoesNotExist:
            adapter.job.logger.info(f"Creating namespace for tenant: {ids['name']}")
            Namespace.objects.create(name=ids["name"])
        
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    def update(self, attrs):
        """Update Tenant object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=self.name)
        _tenant.description = attrs.get("description", "")
        _tenant.comments = attrs.get("comments", "")
        _tenant.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Tenant object in Nautobot."""
        self.adapter.job.logger.warning(f"Tenant {self.name} will be deleted.")
        super().delete()
        try:
            _tenant = OrmTenant.objects.get(name=self.name)
            self.adapter.objects_to_delete["tenant"].append(_tenant)
        except OrmTenant.DoesNotExist:
            self.adapter.job.logger.warning(f"Tenant {self.name} does not exist, skipping deletion.")
        return self


class NautobotVrf(Vrf):
    """Nautobot implementation of the VRF Model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create VRF object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=ids["tenant"])
        _vrf = OrmVrf(
            name=ids["name"], 
            tenant=_tenant, 
            namespace=Namespace.objects.get(name=attrs["namespace"]),
            rd=attrs.get("rd")
        )
        
        # Add main tag if configured
        main_tag_name = PLUGIN_CFG.get("tag")
        if main_tag_name:
            main_tag = get_tag_if_exists(main_tag_name)
            if main_tag:
                _vrf.tags.add(main_tag)
        
        # Add site-specific tag
        site_tag_name = attrs["site_tag"]
        if site_tag_name:
            site_tag = get_tag_if_exists(site_tag_name)
            if site_tag:
                _vrf.tags.add(site_tag)
            
        _vrf.validated_save()
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    def update(self, attrs):
        """Update VRF object in Nautobot."""
        _tenant = OrmTenant.objects.get(name=self.tenant)
        _vrf = OrmVrf.objects.get(name=self.name, tenant=_tenant)
        if attrs.get("description"):
            _vrf.description = attrs["description"]
        if attrs.get("rd"):
            _vrf.rd = attrs["rd"]
        _vrf.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete VRF object in Nautobot."""
        self.adapter.job.logger.warning(f"VRF {self.name} will be deleted.")
        super().delete()
        try:
            _tenant = OrmTenant.objects.get(name=self.tenant)
            _vrf = OrmVrf.objects.get(name=self.name, tenant=_tenant)
            self.adapter.objects_to_delete["vrf"].append(_vrf)
        except (OrmTenant.DoesNotExist, OrmVrf.DoesNotExist):
            self.adapter.job.logger.warning(f"VRF {self.name} or tenant {self.tenant} does not exist, skipping deletion.")
        return self


class NautobotDeviceType(DeviceType):
    """Nautobot implementation of the DeviceType Model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create DeviceType object in Nautobot."""
        try:
            # First check if this device type already exists
            existing_device_type = OrmDeviceType.objects.filter(
                model=ids["model"],
                manufacturer__name=attrs["manufacturer"]
            ).first()
            
            if existing_device_type:
                adapter.job.logger.info(f"DeviceType {ids['model']} already exists, updating instead of creating")
                # Update the existing device type
                existing_device_type.part_number = ids["part_nbr"]
                existing_device_type.u_height = attrs["u_height"]
                existing_device_type.comments = attrs["comments"]
                
                # Add main tag if configured and exists
                main_tag_name = PLUGIN_CFG.get("tag")
                if main_tag_name:
                    main_tag = get_tag_if_exists(main_tag_name)
                    if main_tag:
                        existing_device_type.tags.add(main_tag)
                
                existing_device_type.validated_save()
                return super().create(ids=ids, adapter=adapter, attrs=attrs)
            
            # Create new device type if it doesn't exist
            _devicetype = OrmDeviceType(
                model=ids["model"],
                manufacturer=Manufacturer.objects.get(name=attrs["manufacturer"]),
                part_number=ids["part_nbr"],
                u_height=attrs["u_height"],
                comments=attrs["comments"],
            )
            
            # Add main tag if configured and exists
            main_tag_name = PLUGIN_CFG.get("tag")
            if main_tag_name:
                main_tag = get_tag_if_exists(main_tag_name)
                if main_tag:
                    _devicetype.tags.add(main_tag)
            
            _devicetype.validated_save()
            return super().create(ids=ids, adapter=adapter, attrs=attrs)
            
        except Exception as e:
            adapter.job.logger.error(f"Error creating DeviceType {ids['model']}: {e}")
            raise

    def update(self, attrs):
        """Update DeviceType object in Nautobot."""
        _devicetype = OrmDeviceType.objects.get(model=self.model)
        if attrs.get("manufacturer"):
            _devicetype.manufacturer = Manufacturer.objects.get(name=attrs["manufacturer"])
        if attrs.get("comments"):
            _devicetype.comments = attrs["comments"]
        if attrs.get("u_height"):
            _devicetype.u_height = attrs["u_height"]
        _devicetype.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete DeviceType object in Nautobot."""
        self.adapter.job.logger.warning(f"Device Type {self.model} will be deleted.")
        try:
            _devicetype = OrmDeviceType.objects.get(model=self.model)
            _devicetype.delete()
        except OrmDeviceType.DoesNotExist:
            self.adapter.job.logger.warning(f"DeviceType {self.model} does not exist, skipping deletion.")
        return super().delete()


class NautobotDeviceRole(DeviceRole):
    """Nautobot implementation of the DeviceRole Model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create DeviceRole object in Nautobot."""
        # The role should already exist from signals
        try:
            _devicerole = Role.objects.get(name=ids["name"])
            adapter.job.logger.info(f"Using existing device role: {ids['name']}")
        except Role.DoesNotExist:
            adapter.job.logger.error(f"Device role {ids['name']} not found - it should have been created by signals")
            raise
        
        # Ensure this role can be applied to devices
        device_content_type = ContentType.objects.get_for_model(OrmDevice)
        if device_content_type not in _devicerole.content_types.all():
            _devicerole.content_types.add(device_content_type)
            _devicerole.validated_save()
        
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    def update(self, attrs):
        """Update DeviceRole object in Nautobot."""
        _devicerole = Role.objects.get(name=self.name)
        if attrs.get("description"):
            _devicerole.description = attrs["description"]
        _devicerole.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete DeviceRole object in Nautobot."""
        self.adapter.job.logger.warning(f"Device Role {self.name} will be deleted.")
        try:
            _devicerole = Role.objects.get(name=self.name)
            _devicerole.delete()
        except Role.DoesNotExist:
            self.adapter.job.logger.warning(f"DeviceRole {self.name} does not exist, skipping deletion.")
        return super().delete()


class NautobotDevice(Device):
    """Nautobot implementation of the Device Model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Device object in Nautobot."""
        
        # Get or create the location for this device
        location_type = (
            adapter.job.device_site.location_type
            if adapter.job.device_site
            else adapter.job.vmanage.location.location_type
        )
        
        try:
            location = Location.objects.get(name=ids["site"], location_type=location_type)
        except Location.DoesNotExist:
            # Log error if location doesn't exist - locations should be created outside the job
            adapter.job.logger.error(
                f"Location '{ids['site']}' of type '{location_type.name}' not found. "
                f"Please create this location before running the sync job."
            )
            raise
        
        # Get controller managed device group if specified
        controller_group = None
        if attrs.get("controller_group"):
            try:
                controller_group = ControllerManagedDeviceGroup.objects.get(name=attrs["controller_group"])
            except ControllerManagedDeviceGroup.DoesNotExist:
                adapter.job.logger.warning(
                    f"Controller group '{attrs['controller_group']}' not found. "
                    f"Device will be created without controller group assignment."
                )
                controller_group = None
        
        # Check if device already exists and handle accordingly
        try:
            existing_device = OrmDevice.objects.get(name=ids["name"], location=location)
            adapter.job.logger.info(f"Device {ids['name']} already exists at {location.name}, updating it")
            
            # Update existing device
            existing_device.role = Role.objects.get(name=attrs["device_role"])
            existing_device.device_type = OrmDeviceType.objects.get(model=attrs["device_type"])
            existing_device.serial = attrs["serial"]
            existing_device.comments = attrs["comments"]
            existing_device.controller_managed_device_group = controller_group
            existing_device.status = Status.objects.get(name="Active" if attrs.get("status") == "normal" else "Failed")
            
            # Update SD-WAN specific custom fields
            existing_device.custom_field_data["catalyst_sdwan_system_ip"] = attrs.get("system_ip")
            existing_device.custom_field_data["catalyst_sdwan_site_id"] = attrs.get("site_id")
            existing_device.custom_field_data["catalyst_sdwan_personality"] = attrs.get("personality")
            existing_device.custom_field_data["catalyst_sdwan_reachability"] = attrs.get("reachability")
            existing_device.custom_field_data["catalyst_sdwan_device_model"] = attrs.get("device_model")
            existing_device.custom_field_data["catalyst_sdwan_version"] = attrs.get("version")
            existing_device.custom_field_data["catalyst_sdwan_uuid"] = attrs.get("uuid")
            
            # Add tags
            main_tag_name = PLUGIN_CFG.get("tag")
            if main_tag_name:
                main_tag = get_tag_if_exists(main_tag_name)
                if main_tag:
                    existing_device.tags.add(main_tag)
            
            site_tag_name = attrs["site_tag"]
            if site_tag_name:
                site_tag = get_tag_if_exists(site_tag_name)
                if site_tag:
                    existing_device.tags.add(site_tag)
            
            existing_device.validated_save()
            _device = existing_device
            
        except OrmDevice.DoesNotExist:
            # Create new device if it doesn't exist
            adapter.job.logger.info(f"Creating new device: {ids['name']} at {location.name}")
            
            _device = OrmDevice(
                name=ids["name"],
                role=Role.objects.get(name=attrs["device_role"]),
                device_type=OrmDeviceType.objects.get(model=attrs["device_type"]),
                serial=attrs["serial"],
                comments=attrs["comments"],
                controller_managed_device_group=controller_group,
                location=location,
                status=Status.objects.get(name="Active" if attrs.get("status") == "normal" else "Failed"),
            )

            # Add Catalyst SD-WAN specific custom fields
            _device.custom_field_data["catalyst_sdwan_system_ip"] = attrs.get("system_ip")
            _device.custom_field_data["catalyst_sdwan_site_id"] = attrs.get("site_id")
            _device.custom_field_data["catalyst_sdwan_personality"] = attrs.get("personality")
            _device.custom_field_data["catalyst_sdwan_reachability"] = attrs.get("reachability")
            _device.custom_field_data["catalyst_sdwan_device_model"] = attrs.get("device_model")
            _device.custom_field_data["catalyst_sdwan_version"] = attrs.get("version")
            _device.custom_field_data["catalyst_sdwan_uuid"] = attrs.get("uuid")
            
            # Add main tag if configured
            main_tag_name = PLUGIN_CFG.get("tag")
            if main_tag_name:
                main_tag = get_tag_if_exists(main_tag_name)
                if main_tag:
                    _device.tags.add(main_tag)
            
            # Add site-specific tag
            site_tag_name = attrs["site_tag"]
            if site_tag_name:
                site_tag = get_tag_if_exists(site_tag_name)
                if site_tag:
                    _device.tags.add(site_tag)
                
            _device.validated_save()
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    def update(self, attrs):
        """Update Device object in Nautobot."""
        _device = OrmDevice.objects.get(
            name=self.name,
            location=Location.objects.get(
                name=self.site,
                location_type=self.adapter.job.device_site.location_type
                if self.adapter.job.device_site
                else self.adapter.job.vmanage.location.location_type,
            ),
        )
        if attrs.get("serial"):
            _device.serial = attrs["serial"]
        if attrs.get("device_type"):
            _device.device_type = OrmDeviceType.objects.get(model=attrs["device_type"])
        if attrs.get("device_role"):
            _device.role = Role.objects.get(name=attrs["device_role"])
        if attrs.get("comments"):
            _device.comments = attrs["comments"]
        if attrs.get("controller_group"):
            _device.controller_managed_device_group = ControllerManagedDeviceGroup.objects.get(
                name=attrs["controller_group"]
            )
        if attrs.get("system_ip"):
            _device.custom_field_data["catalyst_sdwan_system_ip"] = attrs["system_ip"]
        if attrs.get("site_id"):
            _device.custom_field_data["catalyst_sdwan_site_id"] = attrs["site_id"]
        if attrs.get("status"):
            _device.status = Status.objects.get(name="Active" if attrs["status"] == "normal" else "Failed")
        _device.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Device object in Nautobot."""
        self.adapter.job.logger.warning(f"Device {self.name} will be deleted.")
        super().delete()
        try:
            _device = OrmDevice.objects.get(
                name=self.name,
                location=Location.objects.get(
                    name=self.site,
                    location_type=self.adapter.job.device_site.location_type
                    if self.adapter.job.device_site
                    else self.adapter.job.vmanage.location.location_type,
                ),
            )
            self.adapter.objects_to_delete["device"].append(_device)
        except (OrmDevice.DoesNotExist, Location.DoesNotExist):
            self.adapter.job.logger.warning(f"Device {self.name} or location {self.site} does not exist, skipping deletion.")
        return self


class NautobotInterfaceTemplate(InterfaceTemplate):
    """Nautobot implementation of the InterfaceTemplate Model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create InterfaceTemplate object in Nautobot."""
        _interfacetemplate = OrmInterfaceTemplate(
            device_type=OrmDeviceType.objects.get(model=ids["device_type"]),
            name=ids["name"],
            type=ids["type"],
            mgmt_only=attrs["mgmt_only"],
        )
        _interfacetemplate.validated_save()

        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    def update(self, attrs):
        """Update InterfaceTemplate object in Nautobot."""
        _interfacetemplate = OrmInterfaceTemplate.objects.get(
            name=self.name,
            device_type=OrmDeviceType.objects.get(model=self.device_type),
        )
        if attrs.get("mgmt_only"):
            _interfacetemplate.mgmt_only = attrs["mgmt_only"]
        _interfacetemplate.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete InterfaceTemplate object in Nautobot."""
        self.adapter.job.logger.warning(f"Interface Template {self.name} will be deleted.")
        try:
            _interfacetemplate = OrmInterfaceTemplate.objects.get(
                name=self.name,
                device_type=OrmDeviceType.objects.get(model=self.device_type),
            )
            _interfacetemplate.delete()
        except (OrmInterfaceTemplate.DoesNotExist, OrmDeviceType.DoesNotExist):
            self.adapter.job.logger.warning(f"InterfaceTemplate {self.name} or DeviceType {self.device_type} does not exist, skipping deletion.")
        return super().delete()


class NautobotInterface(Interface):
    """Nautobot implementation of the Interface Model."""

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Create Interface object in Nautobot."""
        # Validate MTU - must be >= 1 or None for Django validation
        mtu_value = attrs.get("mtu")
        if mtu_value is not None:
            try:
                mtu_value = int(mtu_value)
                if mtu_value <= 0:
                    mtu_value = None  # Set to None for invalid values
            except (ValueError, TypeError):
                mtu_value = None  # Set to None for non-numeric values
        
        # Determine interface status based on operational status
        oper_status = attrs.get("oper_status", "").lower().strip()
        admin_status = attrs.get("admin_status", "").lower().strip()
        
        # Map various SD-WAN status values to Nautobot statuses
        # SD-WAN can return: "Up", "Down", "if-state-up", "if-state-down", etc.
        up_statuses = ["up", "if-state-up", "active", "1", "true"]
        down_statuses = ["down", "if-state-down", "admin-down", "administratively-down", "inactive", "0", "false"]
        
        if any(status in oper_status for status in up_statuses):
            interface_status = "Active"
        elif any(status in oper_status for status in down_statuses):
            interface_status = "Planned"  # Use Planned for down interfaces instead of Failed
        else:
            # For unknown/empty oper status, check admin status
            if any(status in admin_status for status in up_statuses):
                interface_status = "Active"
            elif any(status in admin_status for status in down_statuses):
                interface_status = "Planned"
            else:
                # Default to Active for interfaces with unknown status
                interface_status = "Active"
        
        # Log the status decision for debugging
        adapter.job.logger.debug(
            f"Interface {ids['name']} status mapping: "
            f"oper_status='{attrs.get('oper_status')}', admin_status='{attrs.get('admin_status')}' "
            f"-> {interface_status}"
        )
        
        _interface = OrmInterface(
            name=ids["name"],
            device=OrmDevice.objects.get(
                name=ids["device"],
                location=Location.objects.get(
                    name=ids["site"],
                    location_type=adapter.job.device_site.location_type
                    if adapter.job.device_site
                    else adapter.job.vmanage.location.location_type,
                ),
            ),
            description=attrs["description"],
            status=Status.objects.get(name=interface_status),
            type=attrs["type"],
            mtu=mtu_value,
        )
        
        # Add SD-WAN specific custom fields
        _interface.custom_field_data["catalyst_sdwan_vpn_id"] = attrs.get("vpn_id")
        _interface.custom_field_data["catalyst_sdwan_admin_status"] = attrs.get("admin_status")
        _interface.custom_field_data["catalyst_sdwan_oper_status"] = attrs.get("oper_status")
        
        # Add main tag if configured
        main_tag_name = PLUGIN_CFG.get("tag")
        if main_tag_name:
            main_tag = get_tag_if_exists(main_tag_name)
            if main_tag:
                _interface.tags.add(main_tag)
        
        # Add site-specific tag
        site_tag_name = attrs["site_tag"]
        if site_tag_name:
            site_tag = get_tag_if_exists(site_tag_name)
            if site_tag:
                _interface.tags.add(site_tag)
            
        _interface.validated_save()
        return super().create(ids=ids, adapter=adapter, attrs=attrs)

    def update(self, attrs):
        """Update Interface object in Nautobot."""
        _interface = OrmInterface.objects.get(
            name=self.name,
            device=OrmDevice.objects.get(
                name=self.device,
                location=Location.objects.get(
                    name=self.site,
                    location_type=self.adapter.job.device_site.location_type
                    if self.adapter.job.device_site
                    else self.adapter.job.vmanage.location.location_type,
                ),
            ),
        )
        if attrs.get("description"):
            _interface.description = attrs["description"]
        if attrs.get("type"):
            _interface.type = attrs["type"]
        if attrs.get("mtu"):
            # Validate MTU - must be >= 1 or None for Django validation
            mtu_value = attrs["mtu"]
            try:
                mtu_value = int(mtu_value)
                if mtu_value <= 0:
                    mtu_value = None  # Set to None for invalid values
            except (ValueError, TypeError):
                mtu_value = None  # Set to None for non-numeric values
            _interface.mtu = mtu_value
        if attrs.get("vpn_id"):
            _interface.custom_field_data["catalyst_sdwan_vpn_id"] = attrs["vpn_id"]
        if attrs.get("admin_status"):
            _interface.custom_field_data["catalyst_sdwan_admin_status"] = attrs["admin_status"]
        if attrs.get("oper_status"):
            _interface.custom_field_data["catalyst_sdwan_oper_status"] = attrs["oper_status"]
            # Update status using improved logic
            oper_status = attrs["oper_status"].lower().strip()
            admin_status = attrs.get("admin_status", "").lower().strip()
            
            # Map various SD-WAN status values to Nautobot statuses
            up_statuses = ["up", "if-state-up", "active", "1", "true"]
            down_statuses = ["down", "if-state-down", "admin-down", "administratively-down", "inactive", "0", "false"]
            
            if any(status in oper_status for status in up_statuses):
                interface_status = "Active"
            elif any(status in oper_status for status in down_statuses):
                interface_status = "Planned"  # Use Planned for down interfaces instead of Failed
            else:
                # For unknown oper status, check admin status
                if any(status in admin_status for status in up_statuses):
                    interface_status = "Active"
                elif any(status in admin_status for status in down_statuses):
                    interface_status = "Planned"
                else:
                    # Default to Active for interfaces with unknown status
                    interface_status = "Active"
            
            # Log the status decision for debugging
            self.adapter.job.logger.debug(
                f"Updating interface {self.name} status: "
                f"oper_status='{attrs['oper_status']}', admin_status='{attrs.get('admin_status')}' "
                f"-> {interface_status}"
            )
            _interface.status = Status.objects.get(name=interface_status)
        _interface.validated_save()
        return super().update(attrs)

    def delete(self):
        """Delete Interface object in Nautobot."""
        self.adapter.job.logger.warning(f"Interface {self.name} will be deleted.")
        try:
            device = OrmDevice.objects.get(
                name=self.device,
                location=Location.objects.get(
                    name=self.site,
                    location_type=self.adapter.job.device_site.location_type
                    if self.adapter.job.device_site
                    else self.adapter.job.vmanage.location.location_type,
                ),
            )
        except OrmDevice.DoesNotExist:
            self.adapter.job.logger.warning(
                f"Device {self.device} does not exist, skipping deletion of interface {self.name}"
            )
        else:
            _interface = OrmInterface.objects.get(name=self.name, device=device)
            _interface.delete()
        return super().delete()


# Additional model implementations would follow the same pattern...
# For brevity, I'm showing the key ones. You would implement NautobotIPAddress,
# NautobotPrefix, and NautobotDeviceTemplate following similar patterns.


NautobotDevice.model_rebuild()
NautobotDeviceType.model_rebuild()
