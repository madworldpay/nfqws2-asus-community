# Community links

- Keep the project chat visible near the top of both `README.md` and `README.en.md`: https://t.me/nfqws2AsusCommunityChat.
- End every new or updated GitHub release description with `[Чат сообщества в Telegram](https://t.me/nfqws2AsusCommunityChat)` (use `Telegram community chat` for English descriptions).
- Keep the localized community chat link in the panel footer, separate from the MTProto installer and the temporary technical access channel.
- After a successful panel update, show the same unobtrusive chat link and a copy-link action in the update dialog. Reuse the LAN HTTP-compatible clipboard helper and report copy failures honestly.
- The footer change is prepared for the next build. Do not republish existing binary packages or increment the build just for this link unless the user asks.

# Strategy publication evidence

- When adding or updating a catalog strategy, include compact DPI Detector results in its description: test date, confirmed provider/region, mode, repeated-run count and separate raw success ratios for TCP, HTTP, TLS 1.2, TLS 1.3 and QUIC. Preserve denominators and ranges; mark unknown information explicitly.
- Bind reported metrics to the tested configuration/resources and retain the original TXT and hashes privately. Distinguish original-profile measurements from an anonymized public copy whose lists or parameters changed. Do not publish learned browsing history or router identity.
- Never reuse another provider's result, infer a region from an IP lookup, or present an unrecorded service state as a verified before/after baseline. Follow `source/project/profile-catalog/README.md` for the publication protocol.
