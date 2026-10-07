"""URL patterns for nautobot-ssot-infoblox-uddi."""

from django.urls import path
from nautobot.apps.urls import NautobotUIViewSetRouter

from . import models, views

router = NautobotUIViewSetRouter()
router.register("config/infoblox-uddi", viewset=views.SSOTInfobloxUDDIConfigUIViewSet)

urlpatterns = [
    path(
        "config/infoblox-uddi/<uuid:pk>/changelog/",
        views.SSOTInfobloxUDDIConfigChangeLogView.as_view(),
        name="ssotinfobloxuddiconfig_changelog",
        kwargs={"model": models.SSOTInfobloxUDDIConfig},
    ),
    path(
        "config/infoblox-uddi/<uuid:pk>/notes/",
        views.SSOTInfobloxUDDIConfigNotesView.as_view(),
        name="ssotinfobloxuddiconfig_notes",
        kwargs={"model": models.SSOTInfobloxUDDIConfig},
    ),
]

urlpatterns += router.urls
