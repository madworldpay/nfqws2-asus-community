# Standalone Strategy Synthesis Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Existing isolated worktree is reused; the user opted out of further questions.

**Goal:** Generate and verify a strategy without reading catalog strategies or inheriting original methods.

**Architecture:** Pure bounded grammar/planner/compiler plus a guarded runtime branch. Existing picker recovery, locks and explicit Apply remain authoritative.

**Tech Stack:** PHP, existing native DPI jobs, static JS, Python unittest.

**Spec:** docs/superpowers/specs/2026-11-08-strategy-synthesis-design.md

## Global Constraints

- No catalog dependency or generated executable code; pinned standard Lua only.
- Preserve original bytes/resources on each tested device; final service states follow the latest private owner instructions. Isolate measurements from upstream bypass services.
- No Telegram goals/rules, topology/DNS changes, or public release in this task.
- Two repeated final measurements; discovery is not a recommendation.

## Review Focus

- Forged or unbounded method/parameter input must be rejected before compilation.
- Discovery noise or incomparable targets must not make an exportable winner.
- Per-host overrides must precede the general rules without hostlist union broadening.
- Existing strong original may outperform a valid from-zero generated result; distinguish these outcomes.
- Cancel/crash, stale report and changed dependency hashes must retain guard/CAS protections.

### Task 1: Independent grammar, feedback planner and compiler

Files: new `source/project/webui/web/public/strategy-synthesis.php`, new `source/project/tests/test_strategy_synthesis.py`; extend compact measurement rows in `strategy-picker-core.php`.

Interfaces: `NfqwsStrategySynthesis::matrix(array $budget):array`, `compile(array $recipe):array`, `refine(array $observations,array $budget):array`, `assemble(array $observations,string $goal):array`. Recipes contain only finite typed component descriptors, not CLI strings.

- [x] Write/run failing tests for empty-profile generation, independent protocol winners, changed targets, injection rejection, bounded hardware matrix, failed-target host overrides and stable fingerprints.
- [x] Implement finite primitive grammar, method+parameter matrix, feedback refinement and compiler.
- [x] Run unit/real pinned-engine syntax checks.

### Task 2: Guarded from-zero runner and dependency-bound result

Files: new `strategy-synthesis-runtime.php`, modify picker runtime/API and device profile library.

Interfaces: `pickersynthesize` uses the existing request contract; state `search=synthesis`, `generated`/`matrix` summary. Current, blank and finalist have repeated comparable measurements. Trial budget excludes the final verification reserve.

- [x] Test independent fresh library resources, API strictness, no catalog invocation and export binding.
- [x] Integrate current control, fresh pass-through, discovery/refinement/assembly, final repeat comparison, exact restoration and separate generated result.
- [x] Verify cancellation/fault recovery and dependency export; commit.

### Task 3: Interface, deployment and real no-catalog experiment

Files: picker HTML/JS, RU/EN help, private deployment/proof helpers outside repository.

- [x] Add generator mode, matrix progress and separate from-zero/current conclusions; label exploratory samples.
- [x] Run focused regression/build, independent review and responsive browser verification.
- [x] Install experimental extension with existing backups/rollback guard, run isolated real from-zero experiment on spare, verify both routers' settings and final requested service states.
- [x] Record actual results/limits without claiming unavailable gains or a public release; commit final documentation.

### Added user request: optional trackers in generator result

Default-off checkbox extends only generated HTTPS scope to the existing four tracker sites. Same generated TLS method, unchanged excludes/custom/HTTP/QUIC, no extra files or ports. Add-on is optional and its sites are not measured by the base run; mark export/apply metadata accordingly. Strict optional boolean for export/apply only; generated result still needs repeated verification.

Verification checkpoint: 65 selector/synthesis tests pass, including actual pinned engine parsing for seven engine families and tracker scope/export tests. Native dependency-bound exports pass on both device platforms; the tracker extension additionally passed on ASUS. The full suite has the same 37 failing/error test names as its previous complete baseline (no new failing names); it is not declared green. Two independent reviews completed; discovered scope, native-context, target normalization and persistent-addon attribution defects were fixed with reproducing tests.

Additional upgrade regression: optional tracker availability is checked against the actual stored program, so a report from an older compiler remains downloadable without incorrectly offering an incompatible add-on. Reproduced with an older stored program (RED), fixed and covered by the 65-test suite (GREEN).

Coverage-label correction: the shared parameter grid is computed from the declared axes and identified as factorized_grid; it is not a count of all distinct executable programs or domain overrides. A reproducing axis-product test failed44100 vs29400 before the fix;65 focused tests pass afterward. Legacy reports do not display their old grid estimate. This change does not alter generated methods or measured configurations.

Final experiment limits: the spare completed a genuine no-catalog run, including two final measurements and a downloadable dependency-bound bundle. The main device's full run failed while stopping the final trial; it restored its original settings and OFF state. This failed run is not a completed or recommended generated result. A separate real cancellation on the main device also restored original configuration, resources and metadata. No generated strategy was applied.

The failure investigation independently reproduced a process-exit race: one of 500 successful fast commands was incorrectly reported as exit -1. The handler now preserves an observed exit code or collects it from proc_close, keeps real nonzero failures, and drains bounded private diagnostics. The original native failure discarded this evidence, so its exact cause is not asserted. Two real-child regression tests cover success, exit7, stderr and the output limit. The updated focused suite has 67 passing tests, including seven pinned engine families. TypeScript and Vite builds pass; the full-suite baseline limitation above remains.

The final handler is installed experimentally on both platforms. An isolated native process fixture on each device passed 100 successful commands and 10 intentional exit7 failures, preserving stderr and the real report/configuration. No bypass service was started by these fixtures. Both final panel/package versions remain Build99, all original resources and metadata match the initial backups, no picker/probe actors remain, and both device services are OFF as requested. The main device's failed end-to-end synthesis has not been rerun after this fix; its old report remains failed. Nothing was published as a new public build.

## Additional owner-requested goal matrix

The owner subsequently authorized a longer isolated series: each single service, each pair, all three together, and the separate broad `all` control on both device platforms. This is 16 serial no-catalog generation jobs. It is coverage of service selections, not an exhaustive claim about every parameter-grid combination. Reports and dependency-bound exports must be archived before the next job replaces its working library. Failed operations stop the batch for investigation; no automatic Apply is used.

- [x] Verify controller ownership, ambiguous admission, isolation and restoration boundaries with private tests.
- [x] Reproduce and fix misleading failure/completion labels and search-mode help; name the exact mode and selected services in confirmation.
- [x] Exercise all seven selected service sets through the real UI on an explicitly isolated loopback fixture; keep these checks separate from native measurement evidence.
- [ ] Finish the 16 native jobs, classify per-service improvements and record any unresolved limitations.
- [ ] Install the final UI after active measurements settle and verify both panels.
- [ ] Verify final service states from the latest private owner instruction and stop the completion monitor.
