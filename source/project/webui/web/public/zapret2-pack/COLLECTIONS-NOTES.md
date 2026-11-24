# Supplemental strategy collections

The Build105 Magisk library remains byte-for-byte unchanged. `collections.json`
adds entries through `AsusZapret2Pack::catalog()` and `documents()`; existing IDs,
resources, sections and import document bytes remain intact. Public attribution
is simply `avatarDD/zapret-gui`.

## Avatar

Source: [avatarDD/zapret-gui](https://github.com/avatarDD/zapret-gui/tree/582e518cddde85187bec0aac9b38dee94f9a4186),
commit `582e518cddde85187bec0aac9b38dee94f9a4186`, snapshot
`2026-11-21T20:49:20Z`. The card date denotes this exact snapshot, not a locally
measured result or a claimed per-file modification date. Original raw JSON bytes,
SHA-256 and Git blob SHA-1 are retained in `collections.json`. Their Git blob SHAs
and the LICENSE blob were checked against the GitHub contents API at that commit.

Copyright (c) 2026 avatarDD. MIT permission applies to these source JSON files;
the complete copyright, permission and warranty notice is embedded unchanged in
`collections.json` under `collections.avatar.license_text` so it travels with the
package data. Its SHA-256 is
`7d77b4d431ad88152fab3e33550437729df283dbd9a1dea5ea1776dc8e82b2de`.

Four combined templates are accepted:

- `tcp_alt1`: HTTP/TLS fake with MD5 + multisplit; QUIC fake ×6.
- `tcp_hostfake`: HTTP/TLS MD5 fake ×3 + hostfakesplit; QUIC fake ×6.
- `full_combo`: HTTP/TLS fake + multidisorder, TLS sequence offset −10000;
  QUIC fake ×6. `tcp_alt2` has identical enabled profile arguments and is recorded
  as a source alias, not a second template. Both original raw files and hashes
  are retained.
- `tcp_oob`: preserve the source HTTP marker `method+2`, both fixed TTL values 4,
  and the effective TLS split offset 1. Source `fakedsplit:pos=1,midsld` is
  canonicalized to the single marker `pos=1`. Pinned zapret2 v1.0.7 commit
  `038c97e5819df10f8e8c22a2f1fffe57f2f7379b` calls `resolve_pos()` from
  `fakedsplit`; its C `posmarker_parse()` first calls `parse_int16()`, whose
  `atoi()` accepts numeric prefix 1. Thus the original resolves to `PM_ABS,1`
  (Lua's returned position is 2), not `midsld`. A test compiles only these pure
  unchanged parser functions to verify that equivalence. No TCP urgent/OOB flag
  is invented, despite the upstream template's name.

Every accepted template uses exactly the already packaged `zapret-lib.lua` and
`zapret-antidpi.lua` by their existing resource IDs, lengths and SHA-256 hashes.
`fake_default_http`, `fake_default_tls`, and `fake_default_quic` are built-in blob
names of the pinned engine and the importer's closed `BUILTIN_BLOBS` list. No new
Lua, blob bytes, guessed aliases, fallback files, DNS changes or service actions
are introduced. HTTP/TLS ports remain 80/443 and QUIC remains UDP 443. Import
preview resolves the full dependency closure and rejects missing package bytes.

Not added:

- `quic_only`: the existing Build105 `fake_2_n2` entry
  `4f3785fd6c53a9be63480cd6` already provides `fake_default_quic` ×6. The Avatar
  profile's additional L7/payload guards do not establish a new technique.
- `tcp_default`: omitted for technique-level novelty, **not** asserted to be an
  identical full-program duplicate. Build105 already provides fake+multisplit
  examples, including `ac89334af827a86e8b3a7d64` and
  `797e2b590e9de155191490eb`; its exact three-profile assembly was not matched.
- `tcp_syndata`: its `--filter-l7=http/tls` and nonempty payload restrictions
  prevent SYN from reaching `syndata`. A useful phase-zero/window adaptation
  requires an explicit limited host/IP scope, hostname cache and warm-up, as in
  the existing synthesis semantics. The source supplies no such target scope;
  no arbitrary targets, global phase-zero rule or inert success claim is added.

Local DPI Detector measurements: **0 runs**. Date, confirmed provider, region,
mode and separate TCP/HTTP/TLS 1.2/TLS 1.3/QUIC success ratios are unknown. Parsing
and dependency checks are not connectivity tests. No strategy or device was run.

## Zemidala

Snapshot: `zemidala/nfqws2-strategies` commit
`ceb68b94cecf3494eba202a64c54dce5243fef8c`. The full Git tree, pinned README and
`.github/ISSUE_TEMPLATE/strategy.yml` were inspected. The Build 106 maintainer
confirmed permission to bundle the selected rules with Zemidala attribution.

The package index contains 67 distinct rules from 134 records, including 53
whose source record is in the submission queue. Build 106 packages the
selected rule chains alongside the index. Contributor hashes and submitted
targets stay at the upstream source.

The common packager checks the roster and the content of each bundled rule
against the index. The `NFQWS_ZEMIDALA_OFFLINE_INPUT` option supports local
verification with the same hash checks.

The adapter scopes each rule to its HTTP or TLS payload and the user's existing
`user.list`. Eleven distinct rules reference `tls_clienthello` and use the
verified vendor stock file under a separate resource name. Seven distinct
rules require other blobs with unavailable original bytes and are omitted.
The submitted checks lack the information needed to report our own DPI Detector
results. Provider labels identify the submitters' reported networks. Regions
and protocol-specific raw denominators are unknown.
