# Export recovery implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users recover from a lost submission confirmation and clearly understand what they send to the developer.

**Architecture:** Keep the existing reviewed snapshot, explicit Send action and receiver deduplication. An uncertain result permits edits and a fresh preview, while the old uncertain snapshot cannot be sent automatically. Display a submission reference for support.

**Tech Stack:** React, TypeScript, MUI, Playwright; existing PHP API and Python receiver unchanged.

**Spec:** User requests in this task: working export, understandable conditions, developer as recipient, review wording before publication, new build after verification.

## Global constraints

- No automatic submissions or retries.
- Send only reviewed selected bytes; preserve router config and stopped service.
- Do not claim the other user's network failure is diagnosed by a successful local test.
- Show RU/EN conditions and recipient without protocol-version jargon.
- Prepare and verify the change before publishing a new build.

## Review focus

- Lost response: retain download and fresh-preview actions without automatic resend.
- New preview: require a new explicit Send click.
- Accepted submission: remain locked against a double click.
- Modified selection: invalidate the old snapshot and proof.
- Narrow mobile viewport: conditions and submission reference remain readable.

### Task 1: Recoverable export UI and conditions

**Files:** `source/project/webui/web/src/components/ShareDialog.tsx`, `source/project/webui/web/src/translations/{ru,en}.json`, `source/project/tests/test_share_retry_browser.mjs`, `source/project/tests/test_share_availability.mjs`.

**Interfaces:** Existing `prepareShare`, `sendShare`, `PreparedShare`, `SupportMailResult` remain unchanged. A fresh preview produces a new snapshot; uncertain snapshots retain their terminal client dedup guard.

- [x] Write and run a real browser regression for initial-strategy preview, uncertain response, fresh preview, explicit successful send and accepted lock.
- [x] Permit editing and fresh preview after uncertainty; disable Send for the uncertain snapshot. Show developer recipient, concise conditions, recovery guidance and submission reference.
- [x] Run browser regression, existing share API/UI tests, type checking, lint and build.
- [x] Review mobile layout and RU/EN copy.

### Task 2: Delivery evidence and release preparation

- [x] Send a minimal strategy and complete initial strategy from the authorized own ASUS without changing settings.
- [x] Verify at least the first exact submission reference in Gmail.
- [x] Verify full initial-strategy email and selected-resource export.
- [ ] Present final conditions to the user before publication. Build and publish only after the verified export change and wording review.
