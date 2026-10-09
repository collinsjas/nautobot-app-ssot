"""API client wrapper for Infoblox Universal DDI (BloxOne CSP).

Thin wrapper around the official `universal-ddi-python-client` SDK, adding pagination
looping and retry/backoff handling the SDK does not provide natively.

NOTE: Section 12 of the design doc calls this pagination design provisional pending SDK
kwarg verification - the parameter names below (`_filter`, `_fields`, `_offset`, `_limit`,
`_page_token`) match the documented BloxOne CSP OpenAPI spec, but the installed package's
generated `*_api.py` signatures should be checked before relying on this in production.
"""

import functools
import logging
import time
from typing import Any, Callable, Dict, Iterator, List, Optional

logger = logging.getLogger("nautobot.ssot.infoblox_uddi")

RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
DELAY = 1
RETRIES = 5
BACKOFF = 2


def retry_on_api_exception(delay: int = DELAY, tries: int = RETRIES, backoff: int = BACKOFF):
    """Retry decorator for BloxOne SDK calls, honoring `Retry-After` on 429s."""

    def decorator(function_to_retry):
        @functools.wraps(function_to_retry)
        def wrapper(*args, **kwargs):
            from universal_ddi_client.exceptions import ApiException  # pylint: disable=import-outside-toplevel

            current_delay = delay
            for attempt in range(tries):
                try:
                    return function_to_retry(*args, **kwargs)
                except ApiException as error:
                    status = getattr(error, "status", None)
                    if status not in RETRY_STATUS_CODES or attempt == tries - 1:
                        raise
                    retry_after = None
                    headers = getattr(error, "headers", None) or {}
                    if headers.get("Retry-After"):
                        try:
                            retry_after = int(headers["Retry-After"])
                        except ValueError:
                            retry_after = None
                    time.sleep(retry_after if retry_after is not None else current_delay)
                    current_delay *= backoff
            return None

        return wrapper

    return decorator


class InfobloxUDDIApi:  # pylint: disable=too-many-instance-attributes
    """Wrapper around the `universal-ddi-python-client` SDK."""

    def __init__(self, portal_url: str, portal_key: str, verify_ssl: bool = True, timeout: int = 30):
        """Initialize the Infoblox Universal DDI API client.

        Raises:
            ImportError: If the `universal-ddi-python-client` package is not installed.
        """
        try:
            from universal_ddi_client import ApiClient, Configuration  # pylint: disable=import-outside-toplevel
            from universal_ddi_client.dns_config import (  # pylint: disable=import-outside-toplevel
                AuthZoneApi,
                ViewApi,
            )
            from universal_ddi_client.dns_data import RecordApi  # pylint: disable=import-outside-toplevel
            from universal_ddi_client.ipam import (  # pylint: disable=import-outside-toplevel
                AddressApi,
                AddressBlockApi,
                IpSpaceApi,
                SubnetApi,
            )
        except ImportError as error:
            raise ImportError(
                "The `universal-ddi-python-client` package is required to use the Infoblox Universal DDI "
                "integration. Install it with `pip install nautobot-ssot[infoblox_uddi]` (requires Python >= 3.10)."
            ) from error

        configuration = Configuration(portal_key=portal_key, portal_url=portal_url)
        configuration.verify_ssl = verify_ssl
        self.api_client = ApiClient(configuration)
        self.timeout = timeout

        self._ip_space_api = IpSpaceApi(self.api_client)
        self._address_block_api = AddressBlockApi(self.api_client)
        self._subnet_api = SubnetApi(self.api_client)
        self._address_api = AddressApi(self.api_client)
        self._dns_view_api = ViewApi(self.api_client)
        self._dns_zone_api = AuthZoneApi(self.api_client)
        self._dns_record_api = RecordApi(self.api_client)

    @staticmethod
    def _list_all_paged(list_method: Callable, limit: int = 1000, **params) -> Iterator[Any]:
        """Paginate a list method whose response includes `page.total_size`."""
        offset = 0
        while True:
            response = list_method(_offset=offset, _limit=limit, **params)
            results = getattr(response, "results", []) or []
            yield from results
            page = getattr(response, "page", None)
            total_size = getattr(page, "total_size", None) if page else None
            offset += len(results)
            if not results or (total_size is not None and offset >= total_size) or len(results) < limit:
                break

    @staticmethod
    def _list_all_offset_only(list_method: Callable, limit: int = 1000, **params) -> Iterator[Any]:
        """Paginate a list method whose response only includes `results` (no page metadata)."""
        offset = 0
        while True:
            response = list_method(_offset=offset, _limit=limit, **params)
            results = getattr(response, "results", []) or []
            yield from results
            offset += len(results)
            if len(results) < limit:
                break

    def list_all(
        self, list_method: Callable, paged: bool = True, limit: int = 1000, **params
    ) -> List[Any]:
        """Loop over a BloxOne SDK list() method, returning all results.

        Args:
            list_method: Bound SDK `list()` method to call repeatedly (e.g. `self._subnet_api.list`).
            paged: True for resources returning `page.total_size` (Address, Subnet, etc.), False for
                resources returning only `results` (AddressBlock, IPSpace, etc.).
            limit: `_limit` page size to request.
            **params: Additional query params (`_filter`, `_fields`, `_order_by`) passed through.
        """
        loop = self._list_all_paged if paged else self._list_all_offset_only
        return list(loop(list_method, limit=limit, **params))

    @retry_on_api_exception()
    def get_ip_space(self, name: str) -> Optional[Any]:
        """Get a single IP Space by name."""
        results = self.list_all(self._ip_space_api.list, paged=False, _filter=f'name=="{name}"')
        return results[0] if results else None

    @retry_on_api_exception()
    def list_address_blocks(self, ip_space_id: str) -> List[Any]:
        """List all Address Blocks (containers) in the given IP Space."""
        return self.list_all(self._address_block_api.list, paged=False, _filter=f'space=="{ip_space_id}"')

    @retry_on_api_exception()
    def list_subnets(self, ip_space_id: str) -> List[Any]:
        """List all Subnets (networks) in the given IP Space."""
        return self.list_all(
            self._subnet_api.list,
            paged=True,
            _filter=f'space=="{ip_space_id}"',
            _fields="id,address,cidr,space,tags,comment",
        )

    @retry_on_api_exception()
    def list_addresses(self, ip_space_id: str) -> List[Any]:
        """List all Addresses in the given IP Space."""
        return self.list_all(
            self._address_api.list,
            paged=True,
            _filter=f'space=="{ip_space_id}"',
            _fields="id,address,space,tags,comment,usage",
        )

    @retry_on_api_exception()
    def list_dns_views(self) -> List[Any]:
        """List all DNS Views."""
        return self.list_all(self._dns_view_api.list, paged=True)

    @retry_on_api_exception()
    def list_dns_zones(self, view_id: Optional[str] = None) -> List[Any]:
        """List all DNS Zones, optionally scoped to a single DNS View."""
        params: Dict[str, Any] = {}
        if view_id:
            params["_filter"] = f'view=="{view_id}"'
        return self.list_all(self._dns_zone_api.list, paged=True, **params)

    @retry_on_api_exception()
    def list_dns_records(self, zone_id: str, record_type: Optional[str] = None) -> List[Any]:
        """List all DNS Records in a given zone, optionally filtered by record type."""
        dns_filter = f"zone=='{zone_id}'"
        if record_type:
            dns_filter += f" and type=='{record_type}'"
        return self.list_all(self._dns_record_api.list, paged=True, _filter=dns_filter)
