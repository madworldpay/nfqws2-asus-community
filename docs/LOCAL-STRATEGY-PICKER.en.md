# Local strategy generation and selection (beta)

Choose 2–10 consecutive runs. The default is two. Enter the number of concurrent requests in the field. Usually 10–100 is enough. Larger values do not guarantee faster selection.

## Start from the panel

Selection requires DPI Detector and common strategy mode with AUTO or LIST.

1. Open **Strategy selection**. Choose **Develop a strategy**, the request pool and **Number of runs — 2 to 10**.
2. Keep **All services**, or select the services you need. Adding custom sites is optional.
3. Click **Start selection**, check the goals, request pool and run count, then **Continue**. Subsequent runs start automatically after restoring settings and rechecking conditions.
4. Wait for the result and **Original settings restored**. Use **Stop and restore** to cancel. Closing the tab also starts restoration.
5. If the panel recommends replacing the original strategy, choose **Apply this strategy** and confirm. To transfer the result, choose **Download strategy with files**, then open the JSON through the panel's regular import.

**No confirmed improvement** means the comparison finished without a recommendation to replace the original strategy. On failure, the panel shows the reason and restoration state. An unconfirmed restoration blocks a new run; **Download report** remains available.

Custom sites accept up to **10 public domains or IPv4 addresses**. The adjacent availability button transfers the list to diagnostics: choose DNS and start the checks manually. It does not change the strategy or start generation.

An **assembled strategy** is the final candidate built from tested components. “Without bypass methods” means an ordinary connection control, not a discovered bypass. Repeating selection may improve the result as network conditions change, but there is no guarantee; wait for the current run to finish and restore first.

The JSON report becomes available after completion, cancellation or failure and stays hidden while selection is running. **Share with Frank** beside report and strategy downloads opens a review of the same file, with its original name and contents. Sending requires a separate confirmation; applying a strategy remains a separate action.

Two runs are the minimum and the default. Choose a third or later run beforehand if needed. Every run takes fresh measurements; useful methods guide the next search. An error, cancellation or unconfirmed restoration stops the series. The final report shows the selected best result and a summary of every run. Improvement is not guaranteed; applying a strategy is a separate step.

## How the matrix works

The standalone generator does not require the catalog. Its embedded zapret2 1.0.7 method grammar covers HTTP transformations, TCP splitting/disorder, fake prefixes with valid fooling, split positions and bounded repeats. It assembles independent HTTP/TLS/QUIC components from measurements on this connection, with specific domain overrides before the general AUTO fallback where appropriate. It never generates executable Lua; verified standard libraries and engine-provided blobs are used.

The matrix varies methods and parameters without allocating every combination. It rechecks a few successful methods and reserves other slots for new candidates informed by previous coverage. New candidates start from an empty basis; the original configuration is used for comparison and restoration. Every candidate receives the same warm-up before measurement. Small or busy devices get up to 16 exploratory candidates, larger devices 24; custom-site runs get up to 11. Leading candidates and the final assembly are measured repeatedly. One run does not exhaust the matrix.

The original is measured twice as a control. New candidate strategies are assembled independently from an empty basis; the original is only a control and a restoration snapshot. Pass-through is measured separately. Original user files and settings are restored after each run. New rules exclude Telegram; checks and generated rules use IPv4. The generator does not change DNS or MTProto.

The report separately states improvement over pass-through and improvement over the existing tuned strategy. A verified generated kit downloads as one importable JSON containing required lists and Lua, excluding unrelated personal files. Apply is recommended only if the generated result additionally improves the original under TLS/YouTube regression protections. The original configuration and former service state are restored after the experiment.

## Choose a goal

Select YouTube, Discord, Instagram and Torrent trackers individually or in combinations. The tracker goal checks nnmclub.to, rutracker.org, rutor.info and tapochek.net; the general goal includes them too. All original Detector control domains remain. Selected goals are ranked by their own checks; a missing required tracker cannot count as an improvement.

The optional “Add torrent tracker websites” extension after generation remains a separate action: it extends HTTPS scope to nnmclub.to, rutracker.org, rutor.info and tapochek.net. Reported scores describe the kit before adding that extension; repeat the checks afterwards.

## Router load

Device capacity shows the test budget; a separate block shows live readings for the whole router, including NFQWS2, Detector and other services. CPU utilization comes from two samples. Load average is shown separately and is not a percentage. RAM shows available, total and used memory. On older kernels without MemAvailable, the estimate is explicitly labeled. Temperature is shown only for an identified CPU or SoC sensor, with its name; a missing sensor does not mean zero degrees.

Readings refresh every 8 seconds while the page is visible. Returning to it requires two fresh samples for CPU utilization. Data age is conservatively counted from the start of the request, including delivery delay. When this exceeds 20 seconds, the last readings are marked stale. These readings describe current load; they do not predict memory cost or speed gains from increasing concurrency.

## Compare existing profiles

The “Strategy selection” tab compares strategies on the router. DPI Detector must be installed. Use common strategy mode with AUTO or LIST; per-device mode and ALL are excluded from this operation.

The controller backs up the exact original configuration and service state. It tests the current strategy, stock strategy and compatible global profiles from the signed catalog. Each profile has isolated lists, blobs, Lua and AUTO history. Packaged Lua is recognized by its recorded checksum; modified or unknown Lua is not trusted automatically. Incomplete profiles are skipped with a reason.

DNS is checked separately and does not influence strategy ranking. Each candidate receives the same AUTO warmup and two recorded domain/TCP runs. Results show successful/total checks separately for TCP, HTTP, TLS 1.2, TLS 1.3 and QUIC. Truncated results, duplicate targets, changed targets or changed context cannot yield a recommendation. A recommendation needs repeatable improvement without TLS regression or loss of previously successful YouTube checks.

CPU count, available memory and load determine the workload. Small or busy devices use lower concurrency; small devices also test fewer profiles. Storage, profile count, runtime and resource size are bounded. Low memory aborts the operation and restores the original configuration.

Optional extended search currently tests at most three bounded separate and combined repeat-count variations of existing TCP/QUIC methods, preserving custom service and game rules when ready profiles do not improve the result. It does not invent Lua or exhaustively combine methods. Results on another ISP or router are not guarantees.

Connections can briefly interrupt while profiles switch. Leaving the selection screen or closing the page starts restoration. You can also choose “Stop and restore”. Original settings and the former service state are restored after comparison. DNS settings, interfaces, IPv6 and client exclusions are preserved. A recommendation requires a separate “Apply” action, which checks the original configuration and resource fingerprints again under the shared writer lock. Existing original resource files are preserved.

Download the JSON report directly to your device, including after cancellation or failure. Unconfirmed recovery blocks further changes. Automatic restoration never overwrites foreign configuration edits.

After applying, check video playback and seeking, games and your actual applications. A successful YouTube domain check does not prove video playback. Keeping the original strategy when no improvement is confirmed is a normal outcome.

Before starting, confirmation names the search method and exact service selection. “No confirmed improvement” describes a completed comparison without sufficient evidence of a gain. “Selection did not finish” describes an error, not a final recommendation. Cancellation and unconfirmed restoration have separate states. A new run is disabled while restoration remains unconfirmed.

## Selection goal

“All services” is the default. Select one or more of YouTube, Discord, Instagram and Torrent trackers to rank only improvements in their fixed native domain checks. Telegram and MTProto settings are excluded. An unrelated TCP improvement cannot win this mode, and an improvement in one selected service cannot hide a regression in another. Global TLS and previously successful YouTube checks remain protected. The full control test set is retained.

The goal is fixed at admission and recorded in the report alongside per-service HTTP/TLS/QUIC counts. Domain checks do not verify YouTube playback, Discord voice sessions or Instagram feeds. When the checks do not confirm an improvement, the original strategy is retained. Verify the features you use in your apps after applying.

The winning AUTO list is frozen after stopping its daemon, before later recipes can change the private working copy. An old report without a matching winner snapshot cannot be applied; run selection again.

The normal signed technical channel remains available for diagnosis and closure during selection or recovery; its existing sign-in, CSRF and invitation checks still apply. Configuration mutations remain blocked.

After repeat validation, the result window offers **“Add torrent tracker websites”**, off by default. It extends only the generated HTTPS method to nnmclub.to, rutracker.org, rutor.info and tapochek.net. Excludes, HTTP, QUIC and specific domain overrides remain intact. The displayed measurements describe the base strategy before the extension; repeat the website checks after adding it. Downloads include the referenced lists and standard Lua in one kit; referenced built-in blobs ship with the engine.
