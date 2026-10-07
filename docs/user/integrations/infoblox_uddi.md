# Infoblox Universal DDI (BloxOne) SSoT Integration

The Infoblox Universal DDI SSoT integration syncs Prefixes, IP Addresses, DNS Zones, and DNS Records **one-way** from [Infoblox Universal DDI (BloxOne CSP)](https://www.infoblox.com/products/universal-ddi/) into [Nautobot](https://github.com/nautobot/nautobot). It is a separate, sibling integration to the existing [Infoblox (WAPI) integration](infoblox.md) and does not require or modify it.

## Usage

Below are the data mappings between objects within Infoblox Universal DDI and the corresponding objects within Nautobot:

| Infoblox Universal DDI (BloxOne)     | Nautobot                                        |
| ------------------------------------- | -------------------------------------------------- |
| Address Block                         | Prefix (container)                                  |
| Subnet                                | Prefix (network)                                    |
| Address                               | IP Address                                          |
| Auth Zone                             | DNS Zone (`nautobot-dns-models`) or no-op in fallback mode |
| Record (A/AAAA)                       | A/AAAA Record (`nautobot-dns-models`) or `IPAddress.dns_name` fallback |
| Record (CNAME)                        | CNAME Record (`nautobot-dns-models`); skipped with a warning in fallback mode |
| Record (PTR)                          | PTR Record (`nautobot-dns-models`); no-op in fallback mode |

VLAN sync is explicitly out of scope for this integration - Infoblox Universal DDI has no VLAN object.

## DNS Sync Modes

DNS sync automatically selects one of two modes at the start of every job run, logged for visibility:

- **Full-fidelity mode** - when the optional [`nautobot-dns-models`](https://github.com/nautobot/nautobot-app-dns-models) app is installed, DNS Zones and A/AAAA/CNAME/PTR Records are synced as first-class Nautobot objects.
- **Fallback mode** - when `nautobot-dns-models` is not installed, A/AAAA records set `IPAddress.dns_name` directly (matching the existing Infoblox WAPI integration's behavior), PTR records are a no-op, and CNAME records are skipped with a warning log (Nautobot core has no object equivalent to a CNAME).

## IP Space / Namespace Mapping

This integration currently supports mapping a single configured BloxOne IP Space to a single configured Nautobot Namespace. Multi-IP-Space mapping is planned for a future phase.

## Deletion Behavior

By default, objects no longer present in Infoblox Universal DDI are "safe deleted" - marked with a `Deprecated` status and tagged `SSoT Safe Delete` rather than being hard-deleted from Nautobot. This can be disabled per-configuration (`Safe Delete Mode`).
