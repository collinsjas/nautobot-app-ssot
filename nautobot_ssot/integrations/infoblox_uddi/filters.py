"""Filtering implementation for SSOT Infoblox Universal DDI."""

import django_filters
from django.db.models import Q
from nautobot.apps.filters import NautobotFilterSet

from .models import SSOTInfobloxUDDIConfig


class SSOTInfobloxUDDIConfigFilterSet(NautobotFilterSet):
    """FilterSet for SSOTInfobloxUDDIConfig model."""

    q = django_filters.CharFilter(method="search", label="Search")

    class Meta:
        """Meta attributes for filter."""

        model = SSOTInfobloxUDDIConfig
        fields = "__all__"

    def search(self, queryset, _name, value):
        """String search of SSOTInfobloxUDDIConfig records."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value))  # pylint: disable=unsupported-binary-operation
