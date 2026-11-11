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

## Brownfield Adoption

The regular sync only manages Nautobot objects tagged `SSoT Synced from Infoblox Universal DDI`. To adopt existing records, run the **Infoblox Universal DDI Brownfield Adoption** job with the configuration whose IP Space and Namespace define the intended ownership scope.

The job fetches the currently configured Infoblox data and reports existing Nautobot objects with matching identities. It is preview-only by default. Review the matching objects first, then run it again with **Apply tags** enabled to mark those records as managed by the integration. Objects that do not match Infoblox are not tagged. When `nautobot-dns-models` is installed, DNS records whose zone name appears in multiple Infoblox DNS Views are excluded from adoption to avoid claiming an ambiguous record.

Infoblox Universal DDI is treated as the source of truth for everything it imports:

- IP Addresses are matched on host address and Namespace. If the mask in Nautobot differs from the mask Infoblox reports for the containing subnet, the mask in Nautobot is changed to match.
- When a record is adopted, tags that mark it as owned by another system (`SSoT Synced from ...`) and the `SSoT Safe Delete` tag are removed, so the Infoblox Universal DDI tag is the only SSoT ownership tag. The preview lists which tags would be removed. Run the sync afterwards to align the status and other attributes.
- The regular sync applies the same rule when it has to create an IP Address that already exists in the Namespace, for example with another mask or another system's tags: the existing record is updated and taken over instead of causing a duplicate error.

After tagging, run the regular sync in dry-run mode and review its proposed changes before applying them. The adoption job does not create, update, or delete Nautobot objects; it only applies the sync tag to matching existing objects.

## Deletion Behavior

By default, objects no longer present in Infoblox Universal DDI are "safe deleted" - marked with a `Deprecated` status and tagged `SSoT Safe Delete` rather than being hard-deleted from Nautobot. This can be disabled per-configuration (`Safe Delete Mode`).
