# Plan: Infoblox Universal DDI (BloxOne) SSoT Integration — Technical Design

A new sibling integration `infoblox_uddi` syncs Prefixes/IPs/DNS Zones/DNS Records one-way from Infoblox Universal DDI (BloxOne CSP) into Nautobot, reusing the existing Infoblox WAPI integration's structural pattern, IP Fabric's safe-delete + large-scale loading pattern, and the official `universal-ddi-python-client` SDK + `nautobot-dns-models` app for DNS objects (Nautobot core has no native DNS Zone/Record models). **VLAN sync is out of scope for this integration** — Infoblox Universal DDI has no VLAN object, and VLANs are not expected to be sourced from Infoblox in this design. **DNS sync has two modes, auto-selected at runtime**: full-fidelity Zone/Record objects when `nautobot-dns-models` is installed, or a `dns_name`-only fallback (matching the existing WAPI integration's approach) when it is not.

## 1–6. Prior-art review & reusable patterns (completed)

| Area | Reference | Reusable pattern |
|---|---|---|
| Infoblox WAPI | `nautobot_ssot/integrations/infoblox/` | Full dir layout (`diffsync/adapters`, `diffsync/models`, `utils/client.py`, `models.py`, `choices.py`, `jobs.py`, `forms.py`, `signals.py`); config→`ExternalIntegration`+`SecretsGroup`; `InfobloxDeletableModelChoices` delete-guard pattern |
| ServiceNow | `nautobot_ssot/integrations/servicenow/` | Streaming pagination (`stream=True`), `SKIP_UNMATCHED_DST` delete flag |
| IP Fabric | `nautobot_ssot/integrations/ipfabric/diffsync/diffsync_models.py` | `DiffSyncExtras.safe_delete()` (status+tag instead of hard delete), `safe_delete_mode` BooleanVar; `adapter_ipfabric.py load_data()` large-dataset loading via `defaultdict` + column-filtered fetches (matches our 150k IP / 5000 prefix scale) |
| Cloud integrations | meraki, dna_center | SDK-delegated rate limiting (`wait_on_rate_limit=True`); manual offset pagination fallback |
| Contrib base | `nautobot_ssot/contrib/adapter.py`, `model.py` | `NautobotAdapter`/`NautobotModel` generic ORM CRUD — available but existing Infoblox integration uses hand-written adapters instead for finer control; we'll follow Infoblox's precedent given custom delete/DNS-record logic needed |
| Soft-dependency | `nautobot_ssot/utils/__init__.py` `validate_dlm_installed()` | Template for new `validate_dns_models_installed()` |

**Critical finding during research**: Nautobot core has no DNS Zone/Record model — the existing Infoblox integration only ever sets `IPAddress.dns_name` (confirmed via grep — zero `DNSZone`/`DNSRecord` model classes anywhere in the repo). Since the user requires true DNS Zones + A/AAAA/CNAME/PTR records (CNAME has no IP, impossible via `dns_name`), this design targets the official **`nautobot-dns-models`** app (`DNSView`, `DNSZone`, `ARecord`, `AAAARecord`, `CNAMERecord`, `PTRRecord`) as an **optional dependency**, confirmed with the user. A fallback mode (see "DNS fallback mode" below) keeps the integration fully functional for Prefix/IPAddress/DNS-via-`dns_name` sync even when that app is absent.

## 7. Architecture overview

New package `nautobot_ssot/integrations/infoblox_uddi/`, enabled via `enable_infoblox_uddi` in `PLUGINS_CONFIG`, structurally mirroring `infoblox/`:
- `utils/client.py` — thin wrapper around the official `universal-ddi-python-client` SDK (`ipam`, `dns_config`, `dns_data` sub-packages), adding pagination looping, retry/backoff, and rate-limit handling the SDK doesn't provide natively.
- `diffsync/models/base.py` — shared DiffSyncModel field definitions (`Namespace`, `Prefix`, `IPAddress`, `DnsZone`, `DnsARecord`, `DnsAaaaRecord`, `DnsCnameRecord`, `DnsPtrRecord`). No VLAN model — out of scope.
- `diffsync/adapters/infoblox_uddi.py` — source adapter, loads from SDK. Always loads DNS Zone/Record data from `dns_config`/`dns_data` regardless of target mode; the Nautobot adapter decides how to persist it.
- `diffsync/adapters/nautobot.py` — target adapter, loads from ORM (`ipam.Prefix/IPAddress`, `nautobot_dns_models.*` if installed). Uses `nautobot_ssot.utils.validate_dlm_installed()`-style helper (new `validate_dns_models_installed()`) to pick between two Nautobot-side model sets at adapter construction time (see "DNS fallback mode" below).
- `models.py` — `SSOTInfobloxUDDIConfig` (Django model), `jobs.py` — `InfobloxUDDIDataSource(DataSource)`.

## 8–9. DiffSync models & object mappings (Scope-Phase-1)

| BloxOne UDDI (SDK) | Nautobot target | Notes |
|---|---|---|
| `ipam.IpSpaceApi` (IPSpace) | `ipam.Namespace` | Phase 1: single configured space→namespace only |
| `ipam.AddressBlockApi` (AddressBlock) | `ipam.Prefix` (type=container) | |
| `ipam.SubnetApi` (Subnet) | `ipam.Prefix` (type=network) | |
| `ipam.AddressApi` (Address) | `ipam.IPAddress` | status, description, tags |
| `dns_config.ViewApi` (View) | `nautobot_dns_models.DNSView` | optional dep |
| `dns_config.AuthZoneApi` (AuthZone) | `nautobot_dns_models.DNSZone` | SOA fields map directly |
| `dns_data.RecordApi` type=A | `nautobot_dns_models.ARecord` | FK to already-synced `IPAddress` |
| `dns_data.RecordApi` type=AAAA | `nautobot_dns_models.AAAARecord` | same |
| `dns_data.RecordApi` type=CNAME | `nautobot_dns_models.CNAMERecord` | `alias` field |
| `dns_data.RecordApi` type=PTR | `nautobot_dns_models.PTRRecord` | `ptrdname` field |

**VLAN is explicitly out of scope** — confirmed Infoblox Universal DDI will not be the source for VLAN data in this design; no `Vlan` DiffSync model, adapter, or config field is defined.

### DNS fallback mode (when `nautobot-dns-models` is NOT installed)

The Nautobot target adapter checks `validate_dns_models_installed()` once at `load()` time and switches its DNS handling accordingly — the Infoblox-side DiffSync models (`DnsZone`, `DnsARecord`, etc.) stay identical either way; only how the Nautobot adapter persists them changes:

| DNS Infoblox model | With `nautobot-dns-models` | Fallback (app absent) |
|---|---|---|
| `DnsZone` | Creates/updates `nautobot_dns_models.DNSZone` | No-op (no Nautobot object represents a bare zone) — logged once at debug level |
| `DnsARecord` / `DnsAaaaRecord` | Creates/updates `ARecord`/`AAAARecord` FK'd to the `IPAddress` | Sets `IPAddress.dns_name` directly on the matching `ipam.IPAddress` object (same behavior as the existing WAPI `infoblox` integration) |
| `DnsPtrRecord` | Creates/updates `PTRRecord` | No-op — the forward name already satisfies `dns_name`; a reverse-only `dns_name` value with no matching forward record is skipped with a job debug log (matches WAPI behavior for A+PTR mode) |
| `DnsCnameRecord` | Creates/updates `CNAMERecord` | **Not representable** — skipped with a job `logger.warning` per occurrence (count summarized at end of run); this is the only functional gap in fallback mode, since Nautobot core has nothing analogous to a CNAME |

The job's `run()` logs which mode is active at the start of every sync (`"DNS zone/record modules not found; falling back to IPAddress.dns_name-only DNS sync (CNAME records will be skipped)."`) so operators always know what to expect without reading code. No separate config toggle is needed — mode selection is fully automatic based on what's installed, matching the same `importlib`/`PackageNotFoundError` detection pattern already used for the optional `nautobot_device_lifecycle_mgmt` dependency.

Adapter `top_level` order must be: `namespace → prefix → ipaddress → dnszone → dnsarecord/dnsaaaarecord/dnscnamerecord/dnsptrrecord` — DNS A/AAAA records (or the fallback `dns_name` assignment) require the `IPAddress` to already exist.

## 10. API client design

Wraps SDK's `ApiClient`/`Configuration` (portal_key, portal_url). Each resource gets a thin loader function: `list_all_<resource>()` looping the generated `list()` method, `create/update/delete` pass-throughs. A shared decorator (`retry_on_api_exception`, modeled on `nautobot_ssot/integrations/itential/clients.py` `retry()`) wraps all calls, retrying on `ApiException` with status in {429, 500, 502, 503, 504}, honoring `Retry-After` for 429s, exponential backoff with capped attempts (constants in `constants.py`, same style as Itential's `BACKOFF`/`DELAY`/`RETRIES`).

## 11. Configuration model

`SSOTInfobloxUDDIConfig(PrimaryModel)` — mirrors `SSOTInfobloxConfig`: `name`, `description`, `default_status` FK, `uddi_instance` FK to `extras.ExternalIntegration` (remote_url defaults to `https://csp.infoblox.com`, region-overridable), `job_enabled`, `enable_sync_to_nautobot`, import toggles (`import_prefixes`, `import_ip_addresses`, `import_dns_zones`, `import_dns_records`), `uddi_ip_space` (str, Phase 1 single-space) + `default_namespace` FK (Phase 1 mapping target), `dns_record_types` JSON (which of A/AAAA/CNAME/PTR to sync), `safe_delete_mode` BooleanField default True. No VLAN import flag — out of scope. Secret: `SecretsGroupAccessTypeChoices.TYPE_HTTP` + `SecretsGroupSecretTypeChoices.TYPE_TOKEN` (same enum members as `slurpit`/`librenms`) holding the BloxOne API key — **no hardcoded tenant/token/username/password anywhere**, validated the same way `SSOTInfobloxConfig._clean_infoblox_instance()` validates secret presence.

## 12. Pagination strategy (CONFIRMED against official OpenAPI spec at https://csp.infoblox.com/apidoc/docs/Ipamsvc)

Every `ipam`/`dhcp` list endpoint supports these query parameters: `_filter` (logical expression string, e.g. `tag == "value" and cidr_block == "10.0.0.0/8"`), `_order_by`, `_fields` (comma-separated projection — critical for the 150k-address case to avoid pulling full objects), `_offset` (zero-origin integer, default 0), `_limit` (integer, service-imposed max), `_page_token` (opaque cursor, null = first page), plus tag-specific `_tfilter`/`_torder_by`.

**Two response shapes exist** — this matters for the pagination loop implementation:
- Paged resources that return a `page` object (`apiPageInfo`: `offset`, `page_token`, `size`, `total_size`) alongside `results`: `Address`, `Subnet`, `HAGroup`, `OptionGroup`, `OptionSpace`, `DHCPServiceInstance`, `IpamHost`, `Filter`, `SharedNetwork`. These can use `total_size` to know when to stop.
- Resources that return **only** `results` with no page metadata: `AddressBlock`, `IPSpace`, `Range`, `FixedAddress`, `HardwareFilter`, `MacAddressItem`, `OptionCode`, `OptionFilter`. For these, the pagination helper must keep incrementing `_offset` by `_limit` until a response shorter than `_limit` is returned (no `total_size` to short-circuit on).

Shared `utils/client.py` helper (`list_all(api_method, **params)`) implements both loop styles, requests `_fields` projections per resource (e.g. only `id,address,cidr,space,tags,comment` for `Subnet` list calls) to cut payload size for the 150k-IP-address case, and batches `dns_data.Record` loads per-zone (`_filter="zone=='<zone-id>'"`) rather than one global fetch.

**Provisional note**: This section's pagination design is provisional pending SDK kwarg verification; implementation must first inspect the installed package's generated API signatures (the generated `*_api.py` files) and adjust parameter names before coding `utils/client.py`, since GitHub blocked raw file access (403) during this design session and the exact kwarg names were never confirmed against the installed package.

## 13. Deletion strategy

Safe-delete by default (IP Fabric pattern): `DiffSyncExtras`-style mixin changes status (e.g., to "Deprecated") and tags with "SSoT Safe Delete" instead of hard-deleting; `safe_delete_mode` BooleanVar (default True) on the job, settable off for hard delete. Applies uniformly across Prefix/IPAddress/DNSZone/DNS records.

## 14. Testing strategy

Mirrors `nautobot_ssot/tests/infoblox/` and `nautobot_ssot/tests/ipfabric/`: JSON fixture files for each SDK list-response, `unittest.mock.patch` of the SDK `ApiClient`, adapter-level load tests, model create/update/delete tests, config-model validation tests, job-level `TransactionTestCase` tests. Add `databases = ("default", "job_logs")` per IP Fabric/Meraki convention. **DNS tests run in both modes**: one test class/fixture set with `nautobot_dns_models` importable (asserts `DNSZone`/`ARecord`/etc. created), and one with the import patched to raise `ImportError`/`PackageNotFoundError` (asserts `IPAddress.dns_name` set instead and CNAME records are skipped with a warning log, via `assertLogs`). Must pass Ruff/Black/MyPy/pylint per `pyproject.toml` `[tool.ruff]`/`[tool.pylint]` config (Google docstring convention, line-length 120).

## 15. Likely upstream reviewer concerns

1. **New hard dependency `universal-ddi-python-client` requires Python ≥3.10**, while nautobot-ssot supports ≥3.9.2 — needs a per-dependency python marker in the optional extra and explicit documentation of the raised floor for this integration only.
2. **New dependency on a second NetworkToCode app (`nautobot-dns-models`)** for full DNS fidelity — mitigated by the fallback mode: the app is purely optional, and the integration degrades gracefully to `dns_name`-only DNS sync (matching the existing WAPI integration's behavior) when it isn't installed, so no hard new dependency is forced on anyone.
3. Reviewers will likely ask for parity/non-duplication justification vs. the existing `infoblox/` integration (hence the new, clearly-named sibling package rather than modifying WAPI code).
4. Scale (150k IPs) — reviewers will scrutinize pagination/memory efficiency; the design's column/field-filtered fetch and per-zone DNS batching anticipates this.
5. Reviewers may ask why VLANs (listed in the original requirements) are absent from this integration — answer: Infoblox Universal DDI has no VLAN API, and per product decision VLANs are not expected to be sourced from Infoblox for this integration.

## Scope-Phase-2 / Scope-Phase-3 (brief outline, per user request structure)

- **Phase 2**: full IP-Space↔Namespace mapping table (JSON, like `infoblox_network_view_to_namespace_map`), Extensible Attribute↔Custom Field mapping config, Tag mapping, Tenant/Location/VRF mapping fields on config model.
- **Phase 3**: DHCP Ranges/Reservations/Options (SDK already exposes `RangeApi`, `FixedAddressApi`, `OptionCodeApi`/`OptionGroupApi`/`OptionSpaceApi` under `ipam`/`dhcp`), DNS Views/Policies (`ForwardZoneApi`, `AclApi`, `DelegationApi` already surfaced by SDK), advanced DDI features.

## Further Considerations

1. **VLAN — confirmed out of scope.** Infoblox Universal DDI has no VLAN object in its IPAM/DHCP OpenAPI spec anyway (closest analog `SharedNetwork` has no VLAN-ID semantic), and the user has confirmed VLAN data does not need to come from Infoblox for this integration. No VLAN DiffSync model, adapter, or config field is included in this design. If VLAN sync is needed later, it would come from a different source system (e.g. a dedicated VLAN management integration) rather than `infoblox_uddi`.
2. **Python 3.10 floor for this integration** — confirm you're fine with Nautobot 3.9 users simply being unable to enable `infoblox_uddi` (clean failure/guard), vs. any alternative.
3. `dns_data.Record` rdata schema per type (A/AAAA/CNAME/PTR) still needs confirmation against the DNS Data OpenAPI spec (not yet fetched in this session — only DNS Config/dns_data endpoint list was reviewed, not full schema); do this before writing the DNS record DiffSync models. Note: the `ipam.Address` object's `usage` field includes a `DNS` indicator ("Address is used by one or more DNS records"), which can be used to short-circuit DNS record loading to only addresses that actually have records.
4. Not yet specified: behavior if `nautobot-dns-models` is detected as installed mid-way through a long-running sync, or if its models have schema differences that leave required fields unpopulated by the mapping; also not yet specified: handling when `dns_record_types` config excludes a type that another synced record indirectly depends on. These edge cases need further definition before implementation.

## Decisions log (confirmed with user during design review)

- New sibling integration package: `nautobot_ssot/integrations/infoblox_uddi/` (does NOT touch existing WAPI `infoblox/` integration). Enable flag `enable_infoblox_uddi`. Config model `SSOTInfobloxUDDIConfig`.
- API client: depend on official SDK `universal-ddi-python-client` (PyPI), submodules `ipam`, `dns_config`, `dns_data`. Base URL default `https://csp.infoblox.com`, configurable for regions (EU: `https://csp.eu.infoblox.com`).
- Deletion strategy: Safe-delete (IP Fabric style) — status change + "SSoT Safe Delete" tag, `safe_delete_mode` BooleanVar on job, default True.
- IP Space -> Namespace mapping: Phase 1 = single configured IP Space name -> single configured Nautobot Namespace (config fields, not a full map). Full N:N mapping table is Scope-Phase-2.
- DNS Zones/Records: depend optionally on official app `nautobot-dns-models` (PyPI `nautobot-dns-models`, import `nautobot_dns_models`), same soft-dependency pattern as `nautobot_device_lifecycle_mgmt`. **Fallback decision**: when not installed, rather than skipping DNS sync entirely, the Nautobot adapter falls back to setting `IPAddress.dns_name` for A/AAAA records (matching the existing WAPI `infoblox` integration's behavior); PTR becomes a no-op and CNAME is skipped with a per-occurrence warning log (CNAME has no Nautobot core equivalent). Prefix/IPAddress sync is unaffected either way.
- VLAN sync: **out of scope** for `infoblox_uddi` — confirmed by user that VLAN data does not need to come from Infoblox.
- Design doc depth: Scope-Phase-1 detailed; Scope-Phase-2/3 brief outline only.

## nautobot-dns-models field facts (verified via GitHub blob fetch of `nautobot_dns_models/models.py`, develop branch)

- `DNSView(PrimaryModel)`: name (unique), description, `prefixes` M2M to `ipam.Prefix` through `DNSViewPrefixAssignment`.
- `DNSZone(DNSModel)`: name (FQDN), `dns_view` FK (default view auto-created), ttl, filename, description, soa_mname, soa_rname, soa_refresh, soa_retry, soa_expire, soa_serial, soa_minimum, tenant FK, auto_create_ptr bool. unique_together (name, dns_view). If an AuthZone name collides within the same DNS View during sync, log a job error and skip that zone rather than raising an unhandled IntegrityError.
- `DNSRecord(DNSModel)` abstract base: name, `zone` FK (PROTECT), `_ttl` (nullable, falls back to zone.ttl via property), description, comment, enabled.
- `ARecord(DNSRecord)`: `ip_address` FK to `ipam.IPAddress` (limited to IPv4). unique_together (name, ip_address, zone). Auto-creates PTR if `zone.auto_create_ptr`.
- `AAAARecord(DNSRecord)`: same but IPv6.
- `CNAMERecord(DNSRecord)`: `alias` CharField (target FQDN).
- `PTRRecord(DNSRecord)`: `ptrdname` CharField (target FQDN). `__str__` returns ptrdname.
- Also present (Scope-Phase-3/advanced, not needed Phase 1): `NSRecord`, `MXRecord`, `TXTRecord`, `SRVRecord`, `DNSRegistrar`, `DNSRegistration`.
- IMPORTANT ordering constraint: `ARecord`/`AAAARecord` require the Nautobot `IPAddress` to already exist (FK, CASCADE) — our adapter's `top_level` sync order MUST process Prefix → IPAddress before DNSZone → DNS records in the same job run.

## Key upstream object model facts (verified via web fetch against infobloxopen/universal-ddi-python-client GitHub repo + READMEs, Oct 2026)

- Auth: `Configuration(portal_key=..., portal_url=...)`, API key sent as `Authorization` HTTP header (ApiKeyAuth). Env vars `INFOBLOX_PORTAL_KEY` / `INFOBLOX_PORTAL_URL` (old `BLOXONE_*` deprecated).
- `ipam` package APIs: `IpSpaceApi`, `AddressBlockApi`, `SubnetApi`, `AddressApi`, `RangeApi`, `FixedAddressApi`, `IpamHostApi`, `DnsUsageApi`, `AsmApi`, DHCP-related (`DhcpHostApi`, `OptionCodeApi`, `HaGroupApi`, etc. — Scope-Phase-3 DHCP material).
  - No `VlanApi`/VLAN model exists in the `ipam` package — confirmed not a gap to solve since VLAN is out of scope for this integration per user decision.
- `dns_config` package APIs: `ViewApi` (DNS View), `AuthZoneApi` (zone w/ SOA-like fields), `ForwardZoneApi`, `AclApi`, `DelegationApi`, `ServerApi`. Maps well to `nautobot_dns_models.DNSView` / `DNSZone`.
- `dns_data` package APIs: single `RecordApi` (generic record object with a `type` discriminator field: A/AAAA/CNAME/PTR/NS/MX/TXT/SRV/etc., `list`/`create`/`read`/`update`/`delete`). Maps to `nautobot_dns_models.ARecord` / `AAAARecord` / `CNAMERecord` / `PTRRecord`.
- All packages generated by OpenAPI Generator 7.5.0; list() methods expected to support typical Infoblox CSP query params (`limit`, `offset`, `filter`, `fields`, `order_by`) — exact kwarg names must be confirmed against the installed package's generated `*_api.py` during implementation (not fully visible via web fetch, GitHub blocked raw file access with 403).

## Secrets pattern

- Use `SecretsGroupAccessTypeChoices.TYPE_HTTP` + `SecretsGroupSecretTypeChoices.TYPE_TOKEN` for the BloxOne API key (same enum members used by `nautobot_ssot/integrations/slurpit/jobs.py` and `nautobot_ssot/integrations/librenms/jobs.py` for their single-token cloud APIs). Config FK to `extras.ExternalIntegration` (remote_url = portal URL, secrets_group, verify_ssl, timeout) — same pattern as `nautobot_ssot/integrations/infoblox/models.py` `SSOTInfobloxConfig.infoblox_instance`.
