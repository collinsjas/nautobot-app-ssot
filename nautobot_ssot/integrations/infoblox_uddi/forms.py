"""Forms implementation for SSOT Infoblox Universal DDI."""

from django import forms
from nautobot.apps.forms import StaticSelect2Multiple, add_blank_choice
from nautobot.extras.forms import NautobotFilterForm, NautobotModelForm

from .choices import DnsRecordTypeChoices
from .models import SSOTInfobloxUDDIConfig


class SSOTInfobloxUDDIConfigForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """SSOTInfobloxUDDIConfig creation/edit form."""

    dns_record_types = forms.MultipleChoiceField(
        required=False,
        label="DNS Record Types",
        choices=add_blank_choice(DnsRecordTypeChoices),
        widget=StaticSelect2Multiple(),
    )

    class Meta:
        """Meta attributes for the SSOTInfobloxUDDIConfigForm class."""

        model = SSOTInfobloxUDDIConfig
        fields = "__all__"


class SSOTInfobloxUDDIConfigFilterForm(NautobotFilterForm):  # pylint: disable=too-many-ancestors
    """Filter form for SSOTInfobloxUDDIConfig filter searches."""

    model = SSOTInfobloxUDDIConfig

    class Meta:
        """Meta attributes for the SSOTInfobloxUDDIConfigFilterForm class."""

        model = SSOTInfobloxUDDIConfig
        fields = "__all__"
