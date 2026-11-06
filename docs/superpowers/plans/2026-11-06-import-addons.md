# Import Add-ons Beta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task.

**Goal:** Off-by-default, signed cloud add-on checkboxes and safe composition with imported base profiles.
**Architecture:** Independent signed add-on catalog below existing v1 origin; strict data-only domain scopes. Existing importer proof/apply/undo handles all mutation after one combined preview.
**Tech Stack:** PHP, JSON schemas, React/MUI/TypeScript, Python publisher/tests.
**Spec:** docs/superpowers/specs/2026-11-06-import-addons-design.md

## Global Constraints

- Build92 new immutable number, all22packages. Existing profile v1 unchanged.
- No automatic selections, DNS changes, service starts, new Lua, private profiles, or claims of playable Riot UDP.
- preserve AUTO/exclusions/client scope; global profiles must not be narrowed by adding positive lists.

## Review Focus

- Unrestricted/ALL vs positive scoped profiles: extension never narrows or disables existing sites.
- Multiple modules and repeat imports: no duplicates or swallowed exclusions.
- Forged/stale/changed catalog document: proof/apply rejects drift, no arbitrary URLs/paths.
- Partial imported block selection: shared effect visible and acknowledged.
- Catalog network errors and source switching: normal import stays usable, no stale silent selections.

### Task1 Backend and composition
Files: new public/import-addons.php, import-addon-catalog*.php, support/import-addon*.schema.json; modify import-api/plan and dispatcher whitelist as needed, backend tests.
Interface: `importaddoncatalog` -> `{schema_version:1,revision,build,addons:[entry]}`; optional selection.addons array{id,sha256}; plan.addons array{id,title,kind,domains,action,note}.
- [ ] Write failing signed catalog/selection/composition/proof tests; show RED.
- [ ] Implement fixed origin signed bounded fetch, strict source resolution, domain scope merge retaining all importer guarantees.
- [ ] Verify parser/init actual include-union semantics; test unrestricted, scoped, exclusions, duplicate, partial selection and apply/undo races. Run GREEN.
- [ ] Report source changes and limitations; no commits/deployments by worker.

### Task2 Frontend
Files: new api/importAddonClient.ts and components/ImportAddons.tsx; modify ImportDialog, ImportPreview, import client types and RU/EN translations; browser tests.
- [ ] RED tests for no default selection, Beta label, failure isolation, source reset, preview labels, hidden old duplicate torrent checkbox.
- [ ] Use exact Task1 API/types; display scope-limited Riot description and combined preview; preserve specialized torrent option inside same group.
- [ ] GREEN browser/TypeScript/lint; no commits/deployments.

### Task3 Publisher
Files: profile-catalog/addons.py + tests + example public seed definitions/docs only.
- [ ] RED envelope/schema/determinism/invalid-domain tests.
- [ ] Implement immutable content-hash writer and RSA signing via explicit key argument (never embed/read unrelated credentials). Existing profile v1 publisher unchanged.
- [ ] Seed Riot web-domain scope, with explicit game UDP limitation. Preserve attribution and signed revision/min_build92.
- [ ] GREEN tests; no deploy/signing with real keys by worker.

### Root integration/release
- [ ] Finish outstanding remote91 proof and own-channel lifecycle, preserve frozen best profile.
- [ ] Inspect/review composition/security/UI together; independent reviewer, fix findings and rerun meaningful checks.
- [ ] Deploy signed data only using authorized normal channel, validate existing profiles unchanged + new feed from LAN/external.
- [ ] Build92 full matrix + reproducibility, sign/archive/privacy scan, new commit/tag/release; never replace91.
- [ ] Deploy available owner panels with backup/preservation and fresh package+HTTP proof; test add-on preview without changing working strategy. Close own temporary connections on completion.
