# Preset catalog

> **The strategy catalog has moved to a new source.** Use the current package to import and submit profiles. Strategies already applied continue to work; you can also open your own JSON through **From computer (JSON)**.

The catalog is used in the ASUS/Entware and OpenWrt panels. Supported resource paths are adapted during import; selection and preview remain available.

In the panel, click **import → From cloud**. The catalog has two sections:

- **Provider profiles** — settings for a specific connection, for example,
  `DOM.RU-TulskayOblast` and `Rostelekom-DalniyVostok`.
- **Global strategies** — options to try on your own network. This is the
  section name, not a promise of the same result with every provider.

Select a profile: its blocks, lists, blobs, and SmartDNS are already selected as
supplied by the author. You can deselect anything you do not need. Compare changes in
**Preview**, then click **Save selection** and restart NFQWS2.
Loading a preset does not enable anything by itself. DNS is saved to the SmartDNS draft
and connected separately through its wizard.

Open your own JSON through **From computer (JSON)**. This option is available
even when the catalog is unavailable. You can undo the last import as long as its data
has not been edited separately.

Check the result from the intended device: website loading, video playback and
seeking, and voice connections. If you find an option that works well, **share
the strategy and your test result** — this helps improve the catalog.
Open **Export / share**, select the strategy and its files, specify
the provider and result, check the preview, and click **Send**.

## Profiles with Detector results

Signed catalog revision 6 was published on 7 November 2026 and contains 30 profiles. **DOM.RU · Тульская область** was updated and **Билайн · Москва** was added. Their descriptions show separate TCP, HTTP, TLS and QUIC results.

DOM.RU was tested twice with an empty `auto.list`: TCP 93/110 and 89/110; HTTP 16/35 and 15/35; TLS 1.2 24/35 and 19/35; TLS 1.3 24/35 and 20/35; QUIC 6/21 and 5/21. AUTO learns afresh. These measurements apply to the public copy on one connection; the personal 97/110 result in the [historical example](docs/DETECTOR-COMPARISON.en.md) belongs to a different configuration.

Beeline retains the original configuration's measurements: TCP 86/110, HTTP 32/35, TLS 1.2 and TLS 1.3 both 31/35, and QUIC 16/21. Accumulated AUTO history was removed from the public copy, which has not been separately tested with traffic. Save your own lists and review the import preview. User-modified Lua requires review and explicit acknowledgement; the profile does not replace it automatically.

## Add-ons and checking results

**Add-ons · Beta** below the base strategy provides checkboxes that start off. Riot adds web domains to the selected strategy; the separate tracker-website add-on keeps its own limited scope. All selections go through the combined preview. [Add-on contents and limits](IMPORT.en.md#add-ons--beta).

Descriptions of measured profiles should include the date, provider, region, mode, repeated-run count and separate TCP, HTTP, TLS 1.2, TLS 1.3 and QUIC success ratios with original denominators. These metrics belong to the measured configuration and resources. If parameters or lists change for publication, earlier figures do not establish the new copy’s result. A Detector percentage does not replace checking pages, video or voice.

## Downloads and sharing

The catalog and profile files are downloaded over HTTPS. The panel verifies the catalog signature,
the size and SHA256 of the selected JSON, then shows the normal import preview.
Profiles submitted through **Export / share** arrive in the project mailbox
for manual review. They are not added to the catalog automatically. Router
administration panels are separate from the public strategy source.

[Project documentation](README.en.md#documentation).
