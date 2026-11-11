"""Infoblox Universal DDI job tests."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.models import Status, Tag
from nautobot.ipam.models import Namespace, Prefix

from nautobot_ssot.integrations.infoblox_uddi import jobs
from nautobot_ssot.integrations.infoblox_uddi.diffsync.adapters.nautobot import SYNC_TAG_NAME


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

    def test_brownfield_adoption_matches_only_untagged_source_objects(self):
        """Only matching, untagged Nautobot objects should be returned for adoption."""
        namespace, _ = Namespace.objects.get_or_create(name="InfobloxUDDIBrownfieldUnitTest")
        status = Status.objects.get(name="Active")
        sync_tag, _ = Tag.objects.get_or_create(name=SYNC_TAG_NAME)
        sync_tag.content_types.add(ContentType.objects.get_for_model(Prefix))
        tagged_prefix = Prefix.objects.create(
            prefix="10.0.0.0/24", namespace=namespace, type="network", status=status
        )
        tagged_prefix.tags.add(sync_tag)
        matching_prefix = Prefix.objects.create(
            prefix="10.0.1.0/24", namespace=namespace, type="network", status=status
        )
        unrelated_prefix = Prefix.objects.create(
            prefix="10.0.2.0/24", namespace=namespace, type="network", status=status
        )

        job = jobs.InfobloxUDDIBrownfieldAdoption()
        matches = job._get_untagged_matches(
            Prefix.objects.filter(namespace=namespace),
            sync_tag,
            {("10.0.1.0/24", namespace.name)},
            lambda obj: (str(obj.prefix), obj.namespace.name),
        )

        self.assertEqual(matches, [matching_prefix])
        self.assertNotIn(tagged_prefix, matches)
        self.assertNotIn(unrelated_prefix, matches)
        self.assertNotIn(sync_tag, matching_prefix.tags.all())
