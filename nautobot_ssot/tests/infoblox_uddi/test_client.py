"""Infoblox Universal DDI API client tests."""

import unittest
from dataclasses import dataclass, field
from typing import Any, List, Optional
from unittest import mock

from nautobot_ssot.integrations.infoblox_uddi.utils.client import InfobloxUDDIApi


@dataclass
class FakePage:
    """Fake BloxOne `apiPageInfo` object."""

    total_size: int


@dataclass
class FakeResponse:
    """Fake BloxOne list() response object."""

    results: List[Any]
    page: Optional[FakePage] = field(default=None)


class ListAllPaginationTestCase(unittest.TestCase):
    """Tests for InfobloxUDDIApi's pagination helpers (resource-agnostic, no SDK required)."""

    def test_list_all_paged_stops_on_total_size(self):
        """Validate `_list_all_paged` stops once `total_size` items have been yielded."""
        all_items = list(range(5))

        def fake_list(_offset=0, _limit=2, **_kwargs):
            chunk = all_items[_offset : _offset + _limit]
            return FakeResponse(results=chunk, page=FakePage(total_size=len(all_items)))

        results = list(InfobloxUDDIApi._list_all_paged(fake_list, limit=2))
        self.assertEqual(results, all_items)

    def test_list_all_offset_only_stops_on_short_page(self):
        """Validate `_list_all_offset_only` stops once a short page is returned."""
        all_items = list(range(5))

        def fake_list(_offset=0, _limit=2, **_kwargs):
            chunk = all_items[_offset : _offset + _limit]
            return FakeResponse(results=chunk)

        results = list(InfobloxUDDIApi._list_all_offset_only(fake_list, limit=2))
        self.assertEqual(results, all_items)

    def test_list_all_empty_results(self):
        """Validate pagination helpers handle an empty result set without error."""

        def fake_list(_offset=0, _limit=2, **_kwargs):
            return FakeResponse(results=[])

        self.assertEqual(list(InfobloxUDDIApi._list_all_paged(fake_list, limit=2)), [])
        self.assertEqual(list(InfobloxUDDIApi._list_all_offset_only(fake_list, limit=2)), [])


class InfobloxUDDIApiImportGuardTestCase(unittest.TestCase):
    """Tests for the clean-failure guard when `universal-ddi-python-client` is not installed."""

    def test_init_raises_import_error_when_sdk_missing(self):
        """Validate instantiating the client without the SDK installed raises a clear ImportError."""
        with mock.patch.dict("sys.modules", {"universal_ddi_client": None}):
            with self.assertRaises(ImportError) as ctx:
                InfobloxUDDIApi(portal_url="https://csp.infoblox.com", portal_key="fake-key")
            self.assertIn("universal-ddi-python-client", str(ctx.exception))
