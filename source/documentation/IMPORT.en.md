# Importing and sharing profiles

Import and export work on ASUS/Entware and OpenWrt. Known paths for lists, Lua, and blobs are adapted to the platform; WAN and local device selection are preserved from your router.

**JSON** is a file containing selected settings from our panel. The router owner saves it
to transfer settings to another device or share them with another user.
It may contain a strategy, the files it needs, and DNS settings. Before applying it, the panel
shows the contents and changes. The result depends on the network where the profile is used.

## Import

1. Save or discard your current edits. Click the import icon in the header.
2. Select **From computer (JSON)** for your own file or **From cloud** for a preset from the catalog. From your computer, you can open one export or up to five JSON attachments from an email.
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

## Export and send

**Download JSON** saves the selected materials to your computer or phone.
**Send** submits them to the project. Neither action changes the router settings.

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

If **Preview** is unavailable, check that the selected diagnostics have been collected,
strategy blocks or the entire configuration are selected, and the two required fields are filled in.
After changing the selection or text, you need to preview again.
**Send** becomes available after the preview; if the submission channel is not configured,
click **Connect sending**. You can download JSON without a channel.

To transfer a working profile, attach the files referenced by the strategy.
**Select available dependencies** helps collect the dependencies found.
You can also submit a single file or an incomplete set: if the panel finds missing
dependencies, explain why in the field provided.

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
