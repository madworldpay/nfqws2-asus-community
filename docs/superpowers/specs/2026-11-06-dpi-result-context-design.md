# Clear Detector results and service checks

The native Detector's OK describes its protocol probe; a completed HTTP 400 can be OK. It does not establish that a browser application, its resources, login, video or voice works. Independent DNS availability also does not test the user's configured resolver chain.

The owner authorized implementation without further questions. Preserve the original terminal and its verdicts. Add a separate, bounded service-check view with exact HTTP status, redirect and response-size information for fixed public control domains. Existing native TXT files remain byte-identical and explicitly have no recorded historical NFQWS context. Do not infer test start/end from terminal open/close or filename time.

## Approach

Changing the upstream binary would change the original menu and require a separate native fork. Inferring run boundaries from terminal bytes would be unreliable. Use a separate control check whose request boundaries we own. Each target request captures NFQWS state, selected mode and configuration SHA256 before and after that request. The downloaded control-check TXT includes these snapshots and marks changes/unknown values. It remains an incomplete service check, never a claim that the whole service works.

## Interface

`POST index.php`: `cmd=dpisitecheck`, `csrf_token`, `target`. No URL, path, command, proxy, header or environment is accepted. Targets:

| ID | URL |
| --- | --- |
| facebook-main | https://www.facebook.com/ |
| facebook-mobile | https://m.facebook.com/ |
| facebook-cdn | https://static.xx.fbcdn.net/ |
| youtube-main | https://www.youtube.com/ |
| youtube-images | https://i.ytimg.com/ |
| youtube-static | https://www.gstatic.com/ |
| discord-main | https://discord.com/ |
| discord-cdn | https://cdn.discordapp.com/ |
| discord-gateway | https://gateway.discord.gg/ |

Reply JSON: `{type:'nfqws2_dpi_site_check',schema_version:1,target,url,started_at,finished_at,context:{before,after,changed},response:{outcome,http_status,bytes_read,body_limited,redirect,elapsed_ms,error_code},full_service_verified:false,dns_scope:'system_resolver'}`.

Context: `{nfqws:'running'|'stopped'|'unknown',mode:'auto'|'all'|'list'|'unknown',config_sha256:string|null}`. Outcome: `response|timeout|tls_error|connection_error|read_limited|unavailable|blocked_address`. HTTP status nullable integer100..599, bytes0..262144, redirect nullable bounded string, elapsed_ms nullable nonnegative integer, error_code nullable bounded code. UNIX seconds use integers. `context.changed` is true when a field known at both ends differs, false only when all three fields are known and equal, otherwise null. Redirect is at most2048 characters and error_code at most64. Unknown context stays unknown. Read configuration as data, never source/execute it. Detect mode only for an unambiguous recognized assignment.

## Safety and limits

- Existing panel authentication, CSRF, same-origin and update exclusion apply.
- Use the existing Detector admission/terminal idle gates. Do not overlap the native terminal or other Detector jobs. The UI stops its own terminal by unmount before starting control checks; busy remains a recoverable response.
- One target/request. Maximum target runtime10s including DNS; parent enforces deadline and terminates/reaps only its own child. The UI runs three targets sequentially, prevents duplicate runs and uses bounded responses.
- HTTPS only, trusted CA verification and hostname verification. No redirects followed, cookies, credentials, saved curl config or proxy inheritance. Return redirect information only.
- Resolve and pin public IPv4 addresses before connecting; reject private, loopback, link-local, CGNAT, reserved and multicast destinations. No arbitrary URL or browser-supplied resolver.
- Read at most256KiB of body; no HTML returned/rendered, no resource execution. A limit is partial, not success for the full page. CDN root HTTP errors are shown as such; no claim a specific asset loaded.
- No strategy, DNS, firewall, service-state or topology mutation. No new persistent report/secret store. Browser download contains server-provided observations and honest context only.
- ASUS/Entware and OpenWrt use platform paths; package all supported architectures. User's own authorized devices are updated and verified after a new release, preserving settings and ON/OFF states.

## UI

Original terminal is the default view. A second view provides Facebook/YouTube/Discord selection, a run button, result rows with HTTP code/redirect/bytes and before/after NFQWS context, and Download TXT. HTTP400 is explicitly a server error response, not a green service success. Native OK and DNS scope explanations are visible and expanded in help. Old/native TXT downloads remain unchanged; their missing historical context is stated clearly. Keep the Build94 single-terminal lifecycle fix and narrow mobile layout.

## Verification

Tests must expose HTTP400 versus full-service success, TLS/reset/timeouts, body limits, malformed replies, URL/field injection, private DNS answers, no redirect following, child deadline/cleanup, context changes/unknown legacy context, terminal/admission contention, repeat clicks/unmount, download contents, RU/EN and mobile scrolling. Verify both package payloads and live owner panels separately from publication. Private user reports and deployment evidence never enter public source.

Коррекция часов роутера назад не отменяет наблюдение: исходные started_at/finished_at сохраняются, интерфейс и TXT показывают предупреждение. Длительность elapsed_ms измеряется монотонным таймером. CGI-worker явно включает register_argc_argv независимо от php.ini. Браузер проверяет согласованность body_limited/outcome и наличие HTTP-кода для response/read_limited.
