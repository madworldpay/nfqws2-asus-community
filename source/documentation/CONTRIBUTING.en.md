# How to contribute

**Share working strategies and test results.** The same strategy
may behave differently across ISPs and regions. A profile
with a description of the conditions helps improve settings and expand the preset catalog.

## Share a strategy

1. Open **“Export / share”** in the panel and select a strategy.
2. Include the required lists, blobs, and DNS. You can submit just an individual block
   or a single setting; the panel will show any missing dependencies.
3. Specify the service and ISP. In the comment, describe the result: which services
   work, how video playback and seeking behave, whether voice works, and whether a VPN is enabled.
4. If you want to share your region, check the field and enable **“Include location”**.
5. Click **“Preview”**, check the file copies, and select **“Send”**.
   If the channel is not connected yet, use **“Connect sending”**.

**“Download JSON”** saves the profile for you — for example, to share with another
user. **“Send”** sends the materials to the developer. These are separate actions.
Exporting does not change the router's active settings.

If the strategy depends on DNS or files, include them together. An unsuccessful
result is also useful: describe exactly what did not work. You can include
router diagnostics and a DPI Detector result: select them in **“Export / share”**.
First collect diagnostics using the corresponding button; select the completed DPI report after **“Refresh results”**.

Submission is voluntary. Profiles are not added to the cloud catalog automatically:
their contents are reviewed before publication. Passwords and your exact address are not needed for the report;
check free-text fields and files in the preview.

## Report a bug

To describe a problem publicly, open an
[Issue](https://github.com/madworldpay/nfqws2-asus-community/issues/new/choose).
Useful details include:

- the model, firmware, and installed Build;
- what you clicked or which command you ran;
- the expected result, actual result, and exact error text;
- any VPN, DNS, or other traffic-processing tools running alongside it.

Send configurations, profiles, and full diagnostics through the panel's preview.
For a public Issue, a description and the relevant error excerpt without secrets are enough.
If your version is old, click **“Check for updates”** in the panel.
You can still describe the problem if some details are missing.

## Improve the code or instructions

Suggestions, documentation fixes, and Pull Requests are welcome. Describe
the problem your change solves and how you tested it. For the project code, use
[source/project/](source/project/); the current instructions are in the repository root.
Component origins and licenses are documented in [UPSTREAM.en.md](UPSTREAM.en.md).

[Project documentation](README.en.md#documentation).
