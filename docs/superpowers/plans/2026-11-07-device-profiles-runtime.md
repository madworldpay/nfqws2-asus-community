# Device profiles runtime implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Finish and install the owner-authorized per-device experiment on the RT-AC87U, with actual activation and rollback rather than a draft-only editor.

**Architecture:** Keep the existing authenticated standalone editor and saved drafts. Run separate procd NFQWS2 instances for distinct selected strategies, with explicit first-match `goto` dispatch inside the existing native capture table. The normal configuration remains the fallback and is never overwritten. Keep changes isolated from frozen published Build97. Add a platform adapter for Entware, integrate into every package, reserve Build98 only after real feature validation.

**Tech Stack:** Existing PHP, POSIX shell/procd, nftables, plain JavaScript. No new installed package dependencies.

**Spec:** Owner messages in this chat: common/default mode, split profiles, known-device discovery, manual entry, draggable priority, full experimental installation on 87U without further design questions. Prior draft-only PLAN.md records what was deliberately deferred. Finishing runtime is now explicitly authorized.

## Global constraints

- Scope expanded by owner: install on main ASUS and87U, then publish all22 supported architectures with the new optional mode clearly marked beta. No topology/firmware changes.
- Common remains the default. Saving/previewing never applies traffic. Activation requires an explicit apply button.
- Preserve normal configuration/resources, IPv6 OFF and original service state during installation. Temporary runtime checks must clean up only their own objects.
- Use a maximum of four distinct additional strategy processes, eight library entries and sixteen ordered cards. Explain resource limits before activation.
- Separate queues are 41000–41003; refuse a queue owned by another process. Current-strategy cards use the existing main queue.
- Client exclusions apply before profile dispatch. Both directions use conntrack's original client address. No WAN discovery, shell evaluation, foreign process signals or blanket firewall flush.
- MAC profiles refresh from bounded local DHCP/neighbors; unresolved/ambiguous addresses fall back to common, never a different device's stale IP.
- Applying/reverting holds the ordinary package service lease. Validate engine arguments and the complete nft transaction before stopping a working service. Failed activation restores the exact previous active pointer and service state, and verifies recovery.
- A standard package replacing private runtime hooks must be detected as an unavailable experiment, not silently reported as active split routing.

## Review focus

1. First-match dispatch must not queue a selected packet again through common fallback, including reply packets.
2. Failed engine startup or queue collision must restore the old active profile without killing unrelated NFQUEUE users.
3. DHCP movement and duplicate/ambiguous address observations must never retain a stale identity mapping.
4. Imported profiles keep strategy resources separate and do not apply SmartDNS, router settings or foreign shell code.
5. Closed-tab/CGI termination must not strand a partial activation; job status exposes phase and a copyable cause.

## Tasks

### 1. Pure planner and address validation

Files: `source/project/experimental/device-profiles/device-profiles-plan.php`, `test_runtime.py`, existing `device-profiles-lab.php`.

Interface: `NfqwsDeviceProfilesPlan::compile(draft, discovery, strategies, baseQueue): array` returns ordered selectors, process definitions and capture ports; `arguments(config, queue): array` matches the pinned native startup function without evaluation.

- [ ] Write failing behavioral tests for common mode, first-match/current fallback, fixed queue limit, duplicate identities, moving MAC and loopback/mapped-address rejection.
- [ ] Implement the bounded plan and normalization fixes. Run planner and existing draft/compiler/frontend suites.
- [ ] Commit the planner.

### 2. Library and native activation lifecycle

Files: new `device-profiles-library.php`, `device-profiles-runtime.php`, `device-profiles-native.sh`, `test_runtime.py`, dispatcher hook.

Interfaces: library accepts current snapshots and validated exported/signed-catalog documents into isolated resource directories; runtime exposes status/job/apply and fixed CLI preflight/rules/instances/check/reconcile operations. Shell wrapper acquires the existing native service lease and starts a detached operation. Generated private overlays integrate only the native init/control/firewall hooks at known markers.

- [ ] Add failing tests for isolated resources, safe import, stale revisions, transaction failures/recovery, bounded native rendering and owned-instance identity checks.
- [ ] Implement library, job journal, isolated procd instances, native dispatch/flow-port integration and DHCP reconciliation. Use the existing strict import parser; never invoke ordinary global import apply.
- [ ] Verify real native `--dry-run`, nft check and first-match packet behavior in a disposable environment; regression suite and commit.

### 3. UI, installation and verification

Files: existing standalone HTML/JS/CSS, `test_frontend.mjs`, private deployment/evidence outside source.

- [ ] Add failing browser coverage for strategy library/catalog selection, explicit apply, polling, copyable failure, common-mode return, mobile priority controls and dirty/stale draft protection.
- [ ] Implement controls and truthful runtime state. Keep draft save separate from apply; explain fallback and router resource limits.
- [ ] Run full project tests plus experimental tests, request one fresh whole-feature review and resolve important findings with regression evidence.
- [ ] Back up current 87U files and nft/procd state, install only the experimental overlay with CAS checks; preserve user configuration/IPv6 and verify main ASUS unchanged.
- [ ] Verify real package/panel, common/split activation and rollback, restart/stop/boot behavior, DHCP refresh, screenshots and closure of owned sessions. Retain useful experiment without public publication.

## Execution ledger

Ruling: separate per-strategy processes replace the earlier single-engine mark compiler — independent Lua globals and blob definitions can coexist without rewriting user scripts; the cost is a clearly bounded four additional processes on the test router.

Ruling: user opted out of further questions and explicitly authorized finishing/installing the experiment on 87U; execute inline and review once at the end. Preserve the published 97 release unchanged.

## Scope extension — explicit owner instructions

Ruling: owner expanded from87U to bothASUS targets, then allarchitectures, and requested mainASUS installation. Publish one coherent Build98 for all22 supported packages only after real common/split/failure recovery and client packet tests. Clearly say beta in update notes and UI; default remains common, never auto-assign devices. Existing Build97 artifacts stay immutable.

Ruling: the new independent Entware adapter is delegated under dispatching-parallel-agents while the executor finishes shared PHP/native integration. The independent agent owns only Entware shell/overlay/tests; no shared PHP or builders. Native audit is read-only. One whole-branch fresh review still runs at end.

### 4. Entware adapter and packaged integration
- [ ] Prove symlinked firmware /opt reads/writes through one pinned boundary; share literal config parser and isolated imports, preserving allnormalconfig/files.
- [ ] Implement owned extra daemon lifecycle, ordered iptables goto selectors/reply and oldkernel validation; verify real packet classification and failed-start restoration.
- [ ] Package auth dispatcher, standalonebeta UI and permanent hook manifest for bothASUS and allOpenWrt packages; visible panel link, brief beginnerhelp and beta release notes.
- [ ] Full regression +22package build/reproduction, fresh whole-feature review, install and prove on mainASUS/87U, then publish and verify signed feed.


## Verified implementation checkpoint — Build98

- Planner, isolated library, native/Entware adapters, authenticated UI and package integration implemented.
- Targeted shared suite68 PASS; Entware ownership fixtures7 PASS; both browser behavior suites PASS. Fresh whole-feature review closed all Important findings, including incomplete discovery fallback.
- Real nativeARMv7 and ASUSAArch64 traffic demonstrated original/reply dispatch, priority/current routing, unlisted fallback and failed-start recovery. Evidence is private, not published with addresses or identities.
- Returned both owner routers to Common; primary service ON, spare OFF. Existing configuration hashes preserved. Latest owner instruction confirms Common with the new build.
- All22 packages rebuilt twice byte-for-byte; signatures and source archive inventory verified. Full core regression2004 checks PASS (166 environment-dependent skips); normal package deployment is tracked separately until it finishes.
- Physical reboot and ISP bypass performance are not claimed by these tests. IPv6 remains OFF on the spare at the owner's setting.
