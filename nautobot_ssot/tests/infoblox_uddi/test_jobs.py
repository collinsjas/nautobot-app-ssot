"""Infoblox Universal DDI job tests."""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.extras.models import ExternalIntegration, Status, Tag
from nautobot.ipam.models import IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.infoblox_uddi import jobs
from nautobot_ssot.integrations.infoblox_uddi.diffsync.adapters.nautobot import SYNC_TAG_NAME
from nautobot_ssot.integrations.infoblox_uddi.models import SSOTInfobloxUDDIConfig


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
        tagged_prefix = Prefix.objects.create(prefix="10.0.0.0/24", namespace=namespace, type="network", status=status)
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


class InfobloxUDDIBrownfieldAdoptionRunTest(TestCase):
    """Test running the Infoblox Universal DDI Brownfield Adoption job."""

    def setUp(self):
        """Create Nautobot data and stub out the Infoblox Universal DDI client and adapter."""
        self.status = Status.objects.get(name="Active")
        self.namespace = Namespace.objects.create(name="InfobloxUDDIBrownfieldRunUnitTest")
        self.matching_prefix = self._create_prefix("10.0.1.0/24")
        self.unrelated_prefix = self._create_prefix("10.0.2.0/24")
        self.config = SSOTInfobloxUDDIConfig.objects.create(
            name="InfobloxUDDIBrownfieldRunUnitTest",
            default_status=self.status,
            uddi_instance=ExternalIntegration.objects.create(
                name="InfobloxUDDIBrownfieldRunUnitTest", remote_url="https://csp.infoblox.com"
            ),
            uddi_ip_space="default",
            default_namespace=self.namespace,
            import_ip_addresses=False,
            import_ip_ranges=False,
            import_dns_zones=False,
            import_dns_records=False,
        )

        self.addCleanup(patch.stopall)
        patch.object(jobs, "_get_uddi_client_config", return_value={}).start()
        self.api_class = patch.object(jobs, "InfobloxUDDIApi").start()
        adapter_class = patch.object(jobs.infoblox_uddi, "InfobloxUDDIAdapter").start()
        self.source_objects = {
            "prefix": [SimpleNamespace(network="10.0.1.0/24", namespace=self.namespace.name)],
            "ipaddress": [],
        }
        adapter_class.return_value.get_all.side_effect = lambda model_name: self.source_objects.get(model_name, [])

    def _create_prefix(self, prefix):
        return Prefix.objects.create(prefix=prefix, namespace=self.namespace, type="network", status=self.status)

    def _run_job(self, **kwargs):
        jobs.InfobloxUDDIBrownfieldAdoption().run(config=self.config, **kwargs)

    def _create_other_system_tags(self):
        prefix_type = ContentType.objects.get_for_model(Prefix)
        ipfabric_tag, _ = Tag.objects.get_or_create(name="SSoT Synced from IPFabric")
        safe_delete_tag, _ = Tag.objects.get_or_create(name="SSoT Safe Delete")
        for other_tag in (ipfabric_tag, safe_delete_tag):
            other_tag.content_types.add(prefix_type)
        return ipfabric_tag, safe_delete_tag

    def test_apply_makes_infoblox_the_only_owner(self):
        """Another system's sync tag and a Safe Delete tag should be removed from adopted objects."""
        ipfabric_tag, safe_delete_tag = self._create_other_system_tags()
        self.matching_prefix.tags.add(ipfabric_tag, safe_delete_tag)
        self.unrelated_prefix.tags.add(ipfabric_tag)

        self._run_job(apply_tags=True)

        sync_tag = Tag.objects.get(name=SYNC_TAG_NAME)
        self.assertEqual(set(self.matching_prefix.tags.all()), {sync_tag})
        self.assertEqual(set(self.unrelated_prefix.tags.all()), {ipfabric_tag})

    def test_preview_keeps_other_systems_tags(self):
        """A preview should leave the tags of other systems untouched."""
        ipfabric_tag, safe_delete_tag = self._create_other_system_tags()
        self.matching_prefix.tags.add(ipfabric_tag, safe_delete_tag)

        self._run_job(apply_tags=False)

        self.assertEqual(set(self.matching_prefix.tags.all()), {ipfabric_tag, safe_delete_tag})

    def _create_ip_address(self, address):
        return IPAddress.objects.create(address=address, namespace=self.namespace, status=self.status)

    def _enable_ip_import(self, source_address, source_prefix_length):
        self.config.import_ip_addresses = True
        self.source_objects["ipaddress"] = [
            SimpleNamespace(address=source_address, prefix_length=source_prefix_length, namespace=self.namespace.name)
        ]

    def test_apply_corrects_the_mask_to_match_infoblox(self):
        """An untagged IP Address whose mask differs from Infoblox should be re-masked and adopted."""
        ip_address = self._create_ip_address("10.0.1.255/32")
        self._enable_ip_import("10.0.1.255", 24)

        self._run_job(apply_tags=True)

        ip_address.refresh_from_db()
        self.assertEqual(ip_address.mask_length, 24)
        self.assertEqual(ip_address.parent, self.matching_prefix)
        self.assertEqual(list(ip_address.tags.values_list("name", flat=True)), [SYNC_TAG_NAME])

    def test_preview_does_not_change_the_mask(self):
        """A preview should report a mask change without making it."""
        ip_address = self._create_ip_address("10.0.1.255/32")
        self._enable_ip_import("10.0.1.255", 24)

        self._run_job(apply_tags=False)

        ip_address.refresh_from_db()
        self.assertEqual(ip_address.mask_length, 32)
        self.assertEqual(ip_address.tags.count(), 0)

    def test_ip_address_outside_infoblox_is_left_alone(self):
        """An IP Address that Infoblox does not have should not be adopted or re-masked."""
        ip_address = self._create_ip_address("10.0.1.77/32")
        self._enable_ip_import("10.0.1.255", 24)

        self._run_job(apply_tags=True)

        ip_address.refresh_from_db()
        self.assertEqual(ip_address.mask_length, 32)
        self.assertEqual(ip_address.tags.count(), 0)

    def test_preview_makes_no_changes(self):
        """A preview run should neither create the sync tag nor tag any object."""
        Tag.objects.filter(name=SYNC_TAG_NAME).delete()

        self._run_job(apply_tags=False)

        self.assertFalse(Tag.objects.filter(name=SYNC_TAG_NAME).exists())
        self.assertFalse(Prefix.objects.filter(namespace=self.namespace, tags__isnull=False).exists())

    def test_apply_tags_only_matching_untagged_objects(self):
        """Applying should tag the matching Prefix and leave every other Prefix as it was."""
        sync_tag, _ = Tag.objects.get_or_create(name=SYNC_TAG_NAME)
        sync_tag.content_types.clear()
        already_tagged = self._create_prefix("10.0.0.0/24")
        already_tagged.tags.add(sync_tag)

        self._run_job(apply_tags=True)

        self.assertEqual(
            set(Prefix.objects.filter(namespace=self.namespace, tags=sync_tag)),
            {already_tagged, self.matching_prefix},
        )
        self.assertEqual(self.unrelated_prefix.tags.count(), 0)
        self.assertEqual(Prefix.objects.filter(namespace=self.namespace).count(), 3)
        self.assertEqual(set(sync_tag.content_types.all()), {ContentType.objects.get_for_model(Prefix)})

    def test_apply_creates_the_sync_tag_when_missing(self):
        """Applying should create the sync tag if it does not exist yet."""
        Tag.objects.filter(name=SYNC_TAG_NAME).delete()

        self._run_job(apply_tags=True)

        sync_tag = Tag.objects.get(name=SYNC_TAG_NAME)
        self.assertEqual(list(Prefix.objects.filter(namespace=self.namespace, tags=sync_tag)), [self.matching_prefix])
        self.assertEqual(set(sync_tag.content_types.all()), {ContentType.objects.get_for_model(Prefix)})

    def test_requires_sync_to_nautobot_enabled(self):
        """A configuration without sync to Nautobot should be rejected before Infoblox is contacted."""
        self.config.enable_sync_to_nautobot = False

        with self.assertRaises(ValueError):
            self._run_job(apply_tags=True)

        self.api_class.assert_not_called()
        self.assertFalse(Prefix.objects.filter(namespace=self.namespace, tags__isnull=False).exists())
