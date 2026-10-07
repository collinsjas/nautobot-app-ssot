# Infoblox Universal DDI (BloxOne) Integration Setup

This guide will walk you through the steps to set up the Infoblox Universal DDI integration with the `nautobot_ssot` app.

## Prerequisites

Before configuring the integration, please ensure that the `nautobot-ssot` app was installed with the Infoblox Universal DDI integration extra dependencies. This integration requires **Python >= 3.10**.

```shell
pip install nautobot-ssot[infoblox_uddi]
```

!!! note
    DNS Zone/Record sync has two modes, auto-selected at runtime: full-fidelity Zone/Record objects when the optional [`nautobot-dns-models`](https://github.com/nautobot/nautobot-app-dns-models) app is installed, or a `dns_name`-only fallback (matching the existing Infoblox WAPI integration's approach) when it is not. CNAME records cannot be represented without `nautobot-dns-models` installed and are skipped with a warning log in that case.

    ```shell
    pip install nautobot-ssot[infoblox_uddi] nautobot-dns-models
    ```

## Configuration

The integration utilizes [External Integrations](https://docs.nautobot.com/projects/core/en/stable/user-guide/platform-functionality/externalintegration/) to specify your Infoblox Universal DDI (BloxOne CSP) portal information. To enable this integration, activate it in the `nautobot_config.py` file:

```python
PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "enable_infoblox_uddi": True,
    }
}
```

The remaining integration configuration is defined in an instance of the `SSOTInfobloxUDDIConfig` model. Multiple configuration instances are supported; the sync job takes a `Config` parameter specifying which instance to use.

To access integration configuration navigate to `Apps -> Installed Apps` and click on the cog icon in the `Single Source of Truth` entry, then click `Infoblox Universal DDI Configuration List`.

Configuration instance contains the below settings:

| Setting                   | Default                       | Description                                                                                 |
| -------------------------- | ------------------------------ | --------------------------------------------------------------------------------------------- |
| Name                        | N/A                             | Unique name of the configuration instance.                                                     |
| Description                 | N/A                             | Description of the configuration instance.                                                     |
| Universal DDI Instance Config | N/A                          | External Integration object describing the remote BloxOne CSP instance.                        |
| Enabled for Sync Job        | False                           | Allows this config to be used in the sync job.                                                 |
| Sync to Nautobot            | True                            | Allows this config to be used in the job syncing from Infoblox Universal DDI to Nautobot.      |
| Import Prefixes             | True                            | Import Address Blocks/Subnets from the source system.                                          |
| Import IP Addresses         | True                            | Import Addresses from the source system.                                                       |
| Import DNS Zones            | True                            | Import DNS Auth Zones from the source system.                                                  |
| Import DNS Records          | True                            | Import DNS Records (A/AAAA/CNAME/PTR) from the source system.                                  |
| Universal DDI IP Space      | N/A                             | Name of the single BloxOne IP Space to sync from (Phase 1 supports one IP Space).               |
| Default Namespace           | N/A                             | Nautobot Namespace that the configured IP Space is mapped to.                                  |
| DNS Record Types            | `["A", "AAAA", "CNAME", "PTR"]` | Which DNS record types to sync.                                                                |
| Safe Delete Mode            | True                            | When enabled, objects no longer present in the source are tagged and marked Deprecated instead of hard-deleted. |
| Default object status       | N/A                             | Default Status to be assigned to imported objects.                                             |

Each Infoblox Universal DDI configuration must be linked to an External Integration describing the BloxOne CSP instance. The following External Integration fields must be defined for the integration to work correctly:

| Setting       | Description                                                                             |
| ------------- | ----------------------------------------------------------------------------------------- |
| Remote URL    | Portal URL of the BloxOne CSP instance to sync with (e.g. `https://csp.infoblox.com`).     |
| Verify SSL    | Toggle SSL verification when syncing data.                                                 |
| Secrets Group | Secrets Group defining the API token used when connecting (HTTP(S) access type, Token secret type). |
| Timeout       | How long HTTP requests should wait for a response before failing.                          |
