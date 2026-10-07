"""Choicesets for Infoblox Universal DDI integration."""

from nautobot.apps.choices import ChoiceSet


class DnsRecordTypeChoices(ChoiceSet):
    """Choiceset used by SSOTInfobloxUDDIConfig.dns_record_types.

    Represents the BloxOne `dns_data.Record` types this integration knows how to sync.
    """

    A = "A"
    AAAA = "AAAA"
    CNAME = "CNAME"
    PTR = "PTR"

    CHOICES = (
        (A, "A"),
        (AAAA, "AAAA"),
        (CNAME, "CNAME"),
        (PTR, "PTR"),
    )
