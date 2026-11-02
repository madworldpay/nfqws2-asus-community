# Importing and sharing profiles

Import and export work on ASUS/Entware and OpenWrt. Known paths for lists, Lua, and blobs are adapted to the platform; WAN and local device selection are preserved from your router.

**JSON** is a file containing selected settings from our panel. The router owner saves it
to transfer settings to another device or share them with another user.
It may contain a strategy, the files it needs, and DNS settings. Before applying it, the panel
shows the contents and changes. The result depends on the network where the profile is used.

## Import

1. Save or discard your current edits. Click the import icon in the header.
2. Select **From computer (JSON)** for your own file or **From cloud** for a preset from the catalog. Select up to five JSON files totaling at most 4 MiB: a panel export or its strategy, resources and DNS attachments. Arbitrary JSON is not supported; diagnostics and DPI results are not applied as settings.
3. Strategy blocks, lists, blobs, and SmartDNS from the JSON are already selected. Clear any
   unwanted checkboxes. Use **Select all** to select everything again, or select all blobs separately.
4. Open **Preview**. Check replacements and missing dependencies.
5. Click **Save selection**, then **Restart** to apply the strategy.

When you first select a JSON file, the author's intent is preserved: all supplied blocks,
files, and DNS settings are selected. Clearing checkboxes changes this selection. If you select only some parts,
check in the preview that they have the shared parameters and files they need.

Strategy text is hidden until you click **Show strategies**.
File names and paths are shown as in the normal editor. Built-in Lua files are included in the package.
Local WAN, queue, and client settings are not replaced with someone else's settings.

SmartDNS is imported only into the draft. To apply DNS, open SmartDNS and click
**Check profile → Connect**, then confirm that DNS works. Importing does not switch the active DNS.
**Undo last import** restores the previous data if it has not been
edited separately since the import.

If the import save response is lost, use **Check result** or **Retry the same write**. Repeating that write does not create a second import. If recovery is required, preserve the error and import log before making further edits.

## Export and send

**Download JSON** saves the selected materials to your computer or phone.
**Send to developer** submits them to the project. Neither action changes the router settings.

Export starts from the saved configuration, so save the required edits in the main editor first. **Select all** collects diagnostics and selects available materials, including an existing DPI result; it does not run a new DPI test.

1. Open **Export / share** and select what you need: diagnostics,
   a DPI result, strategy, files, or SmartDNS. You can select just one item.
2. If **Router diagnostics** is selected, click **Collect diagnostics**
   and wait for the JSON file name to appear. Selecting the checkbox alone does not start collection.
3. For a strategy, files, or SmartDNS, fill in **Service or purpose**
   (for example, YouTube) and **Internet provider / operator** (for example, Dom.ru).
   In the comment, describe what works and under what conditions: whether the VPN is on or
   off, video quality, seeking, and voice. These fields are not needed for diagnostics or DPI alone.
4. Click **Preview** and check the included files.
5. Click **Download JSON** or **Send**.

**DPI is a separate network check.** The **Collect diagnostics** button does not run it.
Start a new test in **DPI Detector** using the command shown, save
the result with **S**, then click **Refresh results** in the panel
and select the required file.

Hover over or tap **Preview** to see what is still required for a JSON download. Check that the selected diagnostics have been collected,
strategy blocks or the entire configuration are selected, and the two required fields are filled in.
After changing the selection or text, you need to preview again.
**Send** becomes available after the preview; if the submission channel is not configured,
click **Connect sending**. You can download JSON without a channel.

If delivery confirmation is missing, prepare a fresh preview and send again. The earlier report may have arrived, so this can create a duplicate. Keep the submission ID to help trace the result.

To transfer a working profile, select the required lists and blobs manually or use each section’s selection buttons. You can save or send a single file or an incomplete set. Review missing dependencies in the preview and explain omissions in the comment if needed.

Lists, blobs, and DNS are selected separately. Text copies and DNS settings can be
edited before sending; this does not change the source files or the active DNS.
A ZIP download is also available for selected files.

The region is added with **Include location**; you can correct the automatic
value. An exact address is not needed. **Link to previous submissions**
adds a random installation code to associate repeat reports.
Both actions are selected by the user.

Before sending, check free-text fields, lists, and comments: they may still
contain information you entered. Connecting the channel does not send the prepared
materials. They are submitted to the project with **Send**, rather than posted in a public GitHub Issue.

On Windows, select downloaded `.json` files in the normal file dialog. Do not rename
the extension or manually copy parameters from a formatted email.
The preset catalog contains provider profiles and global strategies.
To share a successful profile, use **Export / share**: specify
the provider and result, check the preview, and click **Send**.

[Project documentation](README.en.md#documentation).

## A strategy from Keenetic

In Import, select “Paste a Keenetic strategy”, paste the complete NFQWS2 strategy
or configuration and choose “Convert for ASUS”. The panel adapts resource paths
and previews changes before saving. The other router’s interface, account, queue
and policy are not transferred. Paste NFQWS2 text up to 64 KiB without shell commands; strategies for the older NFQWS are not translated automatically. If a required file is missing, the panel names it. Add lists and blobs separately or correct their references, then preview again. A missing helper Lua requires a compatible package containing it: this import does not install arbitrary Lua files. Referenced files are not downloaded automatically.
