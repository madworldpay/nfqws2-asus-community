# Tracker Search Goal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure and generate for a fixed torrent-tracker website goal, alone or combined with the existing services.

**Architecture:** Extend the common goal parser, native target composition and ranking coverage, then expose the fourth checkbox. Existing measured and unmeasured tracker extensions stay distinct.

**Tech Stack:** PHP, native DPI Detector, static JavaScript, Python unittest.

**Spec:** `docs/superpowers/specs/2026-11-08-tracker-search-goal-design.md`

## Global Constraints

- Generation is optional; Telegram and MTProto stay excluded.
- Fixed goal scope nnmclub.to, rutracker.org, rutor.info and tapochek.net; no user-selected URL or command input.
- Preserve settings/resources and prove restoration. Never install code during an active measurement.
- Shared implementation for ASUS/Entware and OpenWrt; all22 release packages require final checks.

## Review Focus

- All15 nonempty combinations canonicalize and reject duplicates/unknown goals.
- A tracker absent from a result prevents a recommendation.
- `all` and tracker selections add targets without removing native controls.
- Budget bounds cover the expanded domain count on a small worker pool.
- Old reports keep their actual coverage; an unmeasured extension never acquires measured claims.

### Task 1: Confirm candidate websites and target/ranking contract

Files: common `strategy-picker-core.php`, `strategy-picker-runtime.php`, `tests/test_strategy_picker.py`.

Interfaces: consumes the existing native defaults/goal string; produces canonical
`torrents`, `NfqwsStrategyPickerGoals::probeDomains(array $stock,string $goal):array`,
`NfqwsStrategyPickerBudget::coverDomains(array $budget,int $count):array`, and a
private `probe_domains` job snapshot used by each native probe.

- [ ] After the current capacity series, record two HTTPS identity/delivery checks per candidate from the owner's router, with unchanged settings and explicit current upstream service state.
- [ ] Write failing tests for parsing all15 combinations, fixed tracker membership, expanded stock target union, missing tracker rejection and per-tracker gain independent of unrelated successes.
- [ ] Verify those tests fail for the missing goal/coverage behavior.
- [ ] Add canonical `torrents` and a pure fixed-target union helper; compose probe options and update group/probe time allowance for the actual domain count. Require every selected tracker row in ranking.
- [ ] Run focused tests and check existing three-service behavior remains valid; commit verified source only.

### Task 2: UI, report scope and complete exports

Files: `strategy-picker/index.html`, `strategy-picker/picker.js`, localized picker guides, relevant UI/export tests.

Interfaces: consumes the canonical `torrents` goal and fixed four-site scope from
Task 1; produces the fourth localized checkbox, canonical requests and report
labels. The separate optional four-site extension retains its actual status.

- [ ] Write failing tests for the fourth checkbox's canonical request and goal description, plus honest base-strategy wording for the separate four-site extension.
- [ ] Add the localized goal label, visible fixed site list, report name and preservation of the selected goal through refresh/confirmation. Keep older reports honest.
- [ ] Verify full export dependencies, existing TLS/YouTube guards, all15 selection combinations, empty selection, busy/recovery and cancellation behavior.
- [ ] Run the complete configured regression and build checks on the final source. Verify installed native tracker/all runs on both platforms only at a safe boundary; archive reports and restoration proofs.
- [ ] Publish/deploy only after those checks and the earlier matrix requirements are resolved; distinguish publication, installation and actual browser verification.
