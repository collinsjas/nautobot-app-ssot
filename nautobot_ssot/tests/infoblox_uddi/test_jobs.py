"""Infoblox Universal DDI job tests."""

from django.test import TestCase

from nautobot_ssot.integrations.infoblox_uddi import jobs


class InfobloxUDDIJobTest(TestCase):
    """Test the Infoblox Universal DDI job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("Infoblox Universal DDI ⟹ Nautobot", jobs.InfobloxUDDIDataSource.Meta.name)
        self.assertEqual("Infoblox Universal DDI", jobs.InfobloxUDDIDataSource.Meta.data_source)

    def test_data_mappings(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.InfobloxUDDIDataSource.data_mappings()
        self.assertEqual("Prefix", mappings[0].target_name)
        self.assertEqual("IP Address", mappings[1].target_name)
        self.assertEqual("DNS Zone", mappings[2].target_name)
