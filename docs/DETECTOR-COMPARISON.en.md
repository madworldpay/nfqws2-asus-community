# Compare strategies with DPI Detector

[Русский](DETECTOR-COMPARISON.md)

**Detector helps identify what changed after importing a strategy and separate DNS, connections and data transfer. Judge the service you need, not just the OK percentage.**

This is a personal example on one DOM.RU connection in the Tula region. It is not a recommendation to select DOM.RU for another provider or region: filtering rules differ, including between customers of the same provider. Choose a profile for your own network and test it. This profile is not selected automatically.

## One completed comparison pair

The same ASUS GT-BE19000AI, official zapret2 1.0.7 with fastpath and DPI Detector v5.0.0-alpha.21. NFQWS2 was enabled on the ASUS in both runs; no additional bypass was used. Tests **1, 2, 3**, IPv4, concurrency **50**, timeout **8 seconds**.

- **Package default strategy:** November 5, 2026, **18:59:54 UTC**, configuration `f516be08…`.
- **Personal tuned strategy:** **19:01:02 UTC**, configuration `9964bf6a…`.

Both columns use a running NFQWS2 with different strategies. A “without / with bypass” experiment would be a separate pair with explicit OFF/ON states. Raw output from this pair was saved before extracting the numbers; the table retains successful checks and their full denominators.

| Check | Package default strategy | Personal DOM.RU example |
| --- | ---: | ---: |
| TCP / data transfer (TCP16) | 62/110 | 98/110 |
| HTTP | 15/35 | 32/35 |
| TLS 1.2 | 31/35 | 34/35 |
| TLS 1.3 | 29/35 | 33/35 |
| QUIC | 16/21 | 17/21 |
| DNS over HTTPS (DoH) | 33/37 | 33/37 |
| DNS over TLS (DoT) | 31/34 | 31/34 |
| Plain UDP DNS | 49/49 | 49/49 |

In this pair, the personal strategy improved HTTP, TLS and TCP16; DNS results were identical and QUIC changed by one check. Failures remain. These are two sequential runs on one connection: target DNS addresses, server state, load and filtering can vary. Repeat the comparison before drawing a stable conclusion; Detector duration is not an Internet speed measurement.

**The 98/110 result belongs to personal configuration `9964bf6a…`. The public DOM.RU v4 profile candidate differs: diagnostic IP branches and a separate tracker-website block were omitted. This table does not establish the same result for the public profile.**

## What the checks mean

| Layer | What to look for |
| --- | --- |
| DNS, DoH, DoT | Whether queries work through each transport. Unexpected resolvers or altered replies can help locate a problem, but the report does not prove the absence of all DNS leaks. |
| HTTP, TLS 1.2/1.3 | Test-site responses and different TLS variants. A successful handshake alone does not prove a complete response, video or voice. |
| TCP16 / data transfer | Helps detect interruptions after connecting, including around 16 KiB. An open TCP port or successful TLS is insufficient evidence of complete delivery. |
| QUIC | A separate protocol over UDP. A target that does not support it is not evidence of blocking; read the status as well as the total. |

One timeout, TLS alert or closed connection does not prove IP blocking. The OK percentage covers selected tests, not the share of all Internet websites that work.

## Test your own import

1. Open **DPI Detector**, run tests 1–3 and press **S** in the results menu. Save TXT before changing the strategy; note the date, profile and conditions.
2. In **Import profile**, choose a suitable signed cloud profile, your JSON or **Paste Keenetic strategy**. Check blocks, all required lists/blobs and missing dependencies. Review the before/after preview; DNS is selected separately. [Import guide](../IMPORT.en.md).
3. Save the selected changes, restart NFQWS2 and test new connections. Avoid changing the profile, DNS, VPN and test set together; otherwise differences are hard to explain.
4. Repeat the same Detector tests with the same parameters and no second bypass on the route; press **S** again. Compare individual report rows. If results vary, repeat the old and new variants.
5. Open the service from a selected device: check the page, video startup and seeking, messages or voice. Choose based on those tasks. If results worsen, undo the last import or restore your saved profile.

Closing Detector stops its current tests. Refresh **Export / share** to find saved TXT. Detector does not apply a strategy or start automatic selection. [Controls, help and reports](../DPI-DETECTOR.en.md).
