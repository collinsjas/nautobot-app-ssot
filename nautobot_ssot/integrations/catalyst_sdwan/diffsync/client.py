"""All interactions with Catalyst SD-WAN vManage."""

import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
import urllib3

from nautobot_ssot.exceptions import RequestConnectError, RequestHTTPError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class CatalystSdwanApi:
    """Representation and methods for interacting with Catalyst SD-WAN vManage."""

    def __init__(
        self,
        username: str,
        password: str,
        base_uri: str,
        verify: bool,
        site: str,
    ):
        """Initialization of Catalyst SD-WAN API class."""
        self.username = username
        self.password = password
        self.base_uri = base_uri.rstrip("/")
        self.verify = verify
        self.site = site
        self.session = requests.Session()
        self.session.verify = verify
        self.last_login = None
        self.token = None

    def _login(self):
        """Method to log into the vManage and retrieve the token."""
        login_url = f"{self.base_uri}/j_security_check"
        payload = {
            "j_username": self.username,
            "j_password": self.password,
        }
        
        try:
            resp = self.session.post(login_url, data=payload, timeout=30)
            if resp.status_code == 200:
                # Get XSRF token from cookies
                if "JSESSIONID" in self.session.cookies:
                    token_url = f"{self.base_uri}/dataservice/client/token"
                    token_resp = self.session.get(token_url, timeout=30)
                    if token_resp.status_code == 200:
                        self.token = token_resp.text
                        self.session.headers.update({"X-XSRF-TOKEN": self.token})
                        self.last_login = datetime.now()
                        return True
            return False
        except requests.exceptions.RequestException as error:
            raise RequestConnectError(f"Error occurred during login to {self.base_uri}:\n{error}") from error

    def _handle_request(self, url: str, params: dict = None, request_type: str = "get", data: dict = None) -> object:
        """Send a REST API call to the vManage."""
        if self._refresh_token():
            if not self._login():
                raise RequestConnectError(f"Failed to authenticate to {self.base_uri}")

        try:
            resp = self.session.request(
                method=request_type,
                url=url,
                params=params,
                json=data,
                timeout=30,
            )
        except requests.exceptions.RequestException as error:
            raise RequestConnectError(f"Error occurred communicating with {self.base_uri}:\n{error}") from error
        return resp

    def _refresh_token(self) -> bool:
        """Private method to check if the login token needs refresh. Returns True if login needs refresh."""
        if not self.last_login:
            return True
        # if time diff b/w now and last login greater than 30 minutes then refresh login
        if datetime.now() - self.last_login > timedelta(minutes=30):
            return True
        return False

    def _handle_error(self, response: object):
        """Private method to handle HTTP errors."""
        calling_func = sys._getframe().f_back.f_code.co_name  # pylint: disable=protected-access
        raise RequestHTTPError(
            f"There was an HTTP error while performing the {calling_func} operation on {self.base_uri}:\n"
            f"Error: {response.status_code}, Reason: {response.reason}"
        )

    def _get(self, uri: str, params: dict = None) -> dict:
        """Method to retrieve data from the vManage."""
        url = f"{self.base_uri}{uri}"
        resp = self._handle_request(url, params)
        if resp.status_code == 200:
            return resp.json()
        self._handle_error(resp)

    def _post(self, uri: str, params: dict = None, data=None) -> dict:
        """Method to post data to the vManage."""
        url = f"{self.base_uri}{uri}"
        resp = self._handle_request(url, params, request_type="post", data=data)
        if resp.status_code == 200:
            return resp.json()
        self._handle_error(resp)

    def get_devices(self) -> List[dict]:
        """Retrieve the list of devices from vManage."""
        try:
            resp = self._get("/dataservice/device")
            return resp.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get devices: {e}")
            return []

    def get_device_interfaces(self, device_id: str) -> List[dict]:
        """Retrieve interfaces for a specific device."""
        try:
            resp = self._get(f"/dataservice/device/interface", params={"deviceId": device_id})
            return resp.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get interfaces for device {device_id}: {e}")
            return []

    def get_device_template_config(self, device_id: str) -> dict:
        """Get template configuration for a device."""
        try:
            resp = self._get(f"/dataservice/template/config/attached/{device_id}")
            return resp
        except Exception as e:
            logger.error(f"Failed to get template config for device {device_id}: {e}")
            return {}

    def get_attached_devices(self, template_id: str) -> List[dict]:
        """Get devices attached to a specific template."""
        try:
            resp = self._get(f"/dataservice/template/device/config/attached/{template_id}")
            return resp.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get attached devices for template {template_id}: {e}")
            return []

    def get_device_templates(self) -> List[dict]:
        """Get all device templates."""
        try:
            resp = self._get("/dataservice/template/device")
            return resp.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get device templates: {e}")
            return []

    def get_feature_templates(self) -> List[dict]:
        """Get all feature templates."""
        try:
            resp = self._get("/dataservice/template/feature")
            return resp.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get feature templates: {e}")
            return []

    def get_device_models(self) -> List[dict]:
        """Get supported device models."""
        try:
            resp = self._get("/dataservice/device/models")
            return resp.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get device models: {e}")
            return []

    def get_site_list(self) -> List[dict]:
        """Get list of sites."""
        try:
            resp = self._get("/dataservice/device/site/list")
            return resp.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get site list: {e}")
            return []

    def get_vpn_list(self, device_id: str) -> List[dict]:
        """Get VPN list for a device."""
        try:
            resp = self._get("/dataservice/device/interface/vpn", params={"deviceId": device_id})
            return resp.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get VPN list for device {device_id}: {e}")
            return []

    def get_device_counters(self) -> List[dict]:
        """Get device counters/statistics."""
        try:
            resp = self._get("/dataservice/device/counters")
            return resp.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get device counters: {e}")
            return []

    def get_control_connections(self, device_id: str) -> List[dict]:
        """Get control connections for a device."""
        try:
            resp = self._get("/dataservice/device/control/connections", params={"deviceId": device_id})
            return resp.get("data", [])
        except Exception as e:
            logger.error(f"Failed to get control connections for device {device_id}: {e}")
            return []
