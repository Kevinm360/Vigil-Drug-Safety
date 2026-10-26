# Public EC2 demo

The public demo is a separate container and named volume. The existing `vigil` container and `vigil-data` private library remain accessible through the owner's SSH tunnel. No private password, database URL, or investigation volume is passed to the demo.

## Deploy

1. Claim a free DuckDNS hostname and point its A record at the EC2 public IPv4 address. Keep the DuckDNS token private. After stopping/starting EC2, its public IP can change; update the DNS record before restarting HTTPS access.
2. Keep inbound SSH limited to My IP. Allow inbound TCP 80 and 443. Do not publish port 10000 to the internet.
3. On EC2, in `~/Vigil-Drug-Safety`, run `git pull --ff-only origin codex/v1-release`.
4. Run `bash scripts/deploy-public-demo.sh vigil-drug-safety.duckdns.org`.
5. Inspect `sudo docker logs --tail 30 vigil-caddy`. Caddy obtains and renews HTTPS certificates; DNS must resolve to the server first.
6. Check `curl -fsS https://vigil-drug-safety.duckdns.org/healthz` returns `{"status":"ok"}`. Open the URL in a private browser window: no sign-in should be required, and a read-only banner should appear.
7. Verify `/api/investigations` returns 403 and a model-training POST returns 403. Test FDA filters, chart tabs and CSV exports. Saved investigations and all POST endpoints (including narrative submissions) remain private-only.

Read-only here means no submissions, saved-library reads, or training. FDA queries and their separate cache still run. The public transport limits API requests globally to 60/minute per process and one active analysis. This is intended for the supplied single-worker Docker entry point, not a distributed anti-abuse service. Upstream FDA calls per analysis can exceed one. The demo container is capped at 700 MiB and 0.7 CPU; larger requests may need shorter date ranges. Watch memory, API quota and AWS credits after publishing. Additional containers run on the existing EC2 instance; no new AWS service is created. CPU, storage and data transfer still consume credits.

## Stop or roll back

`sudo docker stop vigil-caddy vigil-public` disables the public demo without stopping the private workspace. Keep the named volumes for recovery. Do not use `docker volume prune` or remove `vigil-data`. Ask whether to keep or remove demo resources once no longer needed; keeping them retains their disk usage.

## Portfolio link

Only after HTTPS and the anonymous smoke checks pass, add this to the GitHub README:

`[Live read-only demo](https://vigil-drug-safety.duckdns.org)`

Do not post the private workspace password or FDA key. The hostname is public and does not require a DuckDNS sign-in for visitors.

References: [DuckDNS](https://www.duckdns.org/), [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).
