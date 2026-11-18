# Torrent tracker websites as a search goal

Owner request: add tracker websites beside YouTube, Discord, Instagram and the
general goal, after checking the candidate sites on the owner's connection.
Generation is optional. This concerns website access, not BitTorrent transfers.

Start with the four candidates from AsusImportTorrentSites::SITES. Confirm
HTTPS delivery and site identity separately before finalizing that scope; record
private outcomes, dates, route/service state and limitations. The initial goal
contains nnmclub.to, rutracker.org, rutor.info and tapochek.net as required by the owner. Site access depends on the actual strategy and DNS context. Other candidates
are not described as accessible. Never infer that
another provider will get the same access. No automatic DNS/network change.

The canonical goal key is `torrents`. It can stand alone or combine with any of
the other three goals. `all` also covers these sites. The Detector keeps all
original control targets and adds missing domains from the four fixed tracker sites only for `all` or
goals containing `torrents`; unrelated selections retain their original target
set. Target coverage and time allowance must include the added domains.

Ranking uses the tracker rows, with repeated results and unchanged TLS/YouTube
regression protections. Missing or duplicate tracker coverage cannot yield an
improvement. No arbitrary hostname, shell input, Lua or remote matrix is accepted.
The generated package must retain its required lists/Lua/blobs in one export.

The optional four-site import extension remains separate; it uses the same
fixed sites as the new goal. Describe its scores as belonging to the base strategy before
the extension, instead of incorrectly saying none of its sites was measured.
Never relabel old reports as newly measured.

Implement in the common PHP/static picker files shared by ASUS/Entware and
OpenWrt. No router source replacement during a running measurement. Native
verification must be version-bound and restore original settings/resources;
the owner-approved final service state is restored. All-architecture release follows
the owner's existing requirement to finish meaningful checks first.

Approach chosen: a fourth fixed goal using all four required tracker websites. A free-text URL
field introduces unrelated input/security/coverage rules. A checkbox that only
appends rules after measuring cannot support a truthful measured tracker goal.

Owner correction: the mandatory scope includes NNMClub and RuTracker. Initial curl resets were measured with another active strategy, not the original main ASUS profile; they do not justify excluding required sites. Verification now compares the original main strategy and the upstream strategy separately, with SmartDNS/DNS state recorded.
