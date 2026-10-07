"""Views implementation for SSOT Infoblox Universal DDI."""

from nautobot.apps.views import (
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectEditViewMixin,
    ObjectListViewMixin,
)
from nautobot.extras.views import ObjectChangeLogView, ObjectNotesView

from .api.serializers import SSOTInfobloxUDDIConfigSerializer
from .filters import SSOTInfobloxUDDIConfigFilterSet
from .forms import SSOTInfobloxUDDIConfigFilterForm, SSOTInfobloxUDDIConfigForm
from .models import SSOTInfobloxUDDIConfig
from .tables import SSOTInfobloxUDDIConfigTable


class SSOTInfobloxUDDIConfigUIViewSet(
    ObjectDestroyViewMixin, ObjectDetailViewMixin, ObjectListViewMixin, ObjectEditViewMixin
):  # pylint: disable=abstract-method
    """SSOTInfobloxUDDIConfig UI ViewSet."""

    queryset = SSOTInfobloxUDDIConfig.objects.all()
    table_class = SSOTInfobloxUDDIConfigTable
    filterset_class = SSOTInfobloxUDDIConfigFilterSet
    filterset_form_class = SSOTInfobloxUDDIConfigFilterForm
    form_class = SSOTInfobloxUDDIConfigForm
    serializer_class = SSOTInfobloxUDDIConfigSerializer
    lookup_field = "pk"
    action_buttons = ("add",)

    def get_template_name(self):
        """Override inherited method to allow custom location for templates."""
        action = self.action
        app_label = "nautobot_ssot_infoblox_uddi"
        model_opts = self.queryset.model._meta
        if action in ["create", "update"]:
            template_name = f"{app_label}/{model_opts.model_name}_update.html"
        elif action == "retrieve":
            template_name = f"{app_label}/{model_opts.model_name}_retrieve.html"
        elif action == "list":
            template_name = f"{app_label}/{model_opts.model_name}_list.html"
        else:
            template_name = super().get_template_name()

        return template_name


class SSOTInfobloxUDDIConfigChangeLogView(ObjectChangeLogView):
    """SSOTInfobloxUDDIConfig ChangeLog View."""

    base_template = "nautobot_ssot_infoblox_uddi/ssotinfobloxuddiconfig_retrieve.html"


class SSOTInfobloxUDDIConfigNotesView(ObjectNotesView):
    """SSOTInfobloxUDDIConfig Notes View."""

    base_template = "nautobot_ssot_infoblox_uddi/ssotinfobloxuddiconfig_retrieve.html"
