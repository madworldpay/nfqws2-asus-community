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

## Downloads and sharing

The catalog and profile files are downloaded over HTTPS. The panel verifies the catalog signature,
the size and SHA256 of the selected JSON, then shows the normal import preview.
Profiles submitted through **Export / share** arrive in the project mailbox
for manual review. They are not added to the catalog automatically. Router
administration panels are separate from the public strategy source.

[Project documentation](README.en.md#documentation).
