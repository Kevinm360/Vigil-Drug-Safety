# Free private deployment for Vigil v1

The selected setup is **Render Free + Neon Free**, with required password protection. React and the Python API run together on Render. Hosted investigations and revision history use Neon PostgreSQL so they survive the web server’s disposable filesystem. The local app keeps SQLite, and all original research tools remain available.

No service is created by cloning this repository or running CI. The manifest selects `plan: free`, has no paid disk, and disables automatic deploys. Stay on both providers’ Free plans; stop if setup asks you to approve an upgrade or payment.

## What free hosting means

Render Free supports Docker web apps and HTTPS. It sleeps after 15 idle minutes and can take about a minute to wake. Its local files are lost on restarts and redeploys. See [Render Free limits](https://render.com/docs/free). We therefore use its filesystem only for disposable aggregate caching.

Neon currently offers a [Free PostgreSQL plan](https://neon.com/pricing) without a time limit or credit card requirement, with compute/storage quotas and scale-to-zero. Keep this project on Free. Quotas or provider pauses can affect availability; this setup is a personal research preview, not an always-on service guarantee.

Do not use Render’s expiring free PostgreSQL database for the durable investigation library. The included configuration requires a separate `VIGIL_DATABASE_URL` and refuses to start without it, instead of silently saving notes in ephemeral SQLite.

## Launch steps

1. Confirm the release PR’s **regression** and **container** checks pass. Merge the reviewed release to `main`, or deliberately select its release branch.
2. Sign in to [Neon](https://console.neon.tech/) and create a **Free** PostgreSQL project for Vigil. Select a nearby region. Copy the provider’s connection URL with TLS (`sslmode=require` or stronger). Treat the entire URL as a secret.
3. Sign in to [Render](https://dashboard.render.com/), connect `Kevinm360/Vigil-Drug-Safety`, and create a Blueprint from `render.yaml` using the chosen branch. Verify that it selects a **Free** web service and creates no paid disk or other paid resource.
4. Enter the environment secrets in Render:

   | Setting | Value |
   | --- | --- |
   | `OPENFDA_API_KEY` | Your existing FDA key; never place it in Git or frontend variables. |
   | `VIGIL_AUTH_USER` | Your chosen owner username. |
   | `VIGIL_AUTH_PASSWORD` | A unique password of at least 20 characters. |
   | `VIGIL_DATABASE_URL` | The Neon connection URL with TLS. |
   | `VIGIL_REQUIRE_REMOTE_STORE` | `1` (already configured). |
   | `VIGIL_DATA_DIR` | `/tmp/vigil`, for disposable cache only (already configured). |

5. Render supplies its canonical HTTPS origin via `RENDER_EXTERNAL_URL`. Vigil accepts that exact host/origin and requires sign-in for research/API routes. If adding a custom domain later, set `VIGIL_PUBLIC_ORIGIN` to its exact HTTPS origin before deploying it. Render can use a custom domain for health checks.
6. Deploy. `/healthz` should return only `{"status":"ok"}`; it checks database connectivity. The other pages should prompt for the owner credentials. The UI identifies this as a **Private hosted workspace** and explains that notes are in the private hosted database.
7. Complete the [walkthrough](DEMO.md), save a small investigation, then manually redeploy. Verify the investigation, notes, reaction focus, and timeline remain available. Only call the hosted launch verified after this check.

Account creation, provider terms, and choosing the new workspace password require the owner’s participation. The release does not upload local credentials or investigations. The hosted library starts empty; importing personal saved investigations is a separate deliberate action.

## Architecture and privacy

- Gunicorn runs the Flask WSGI transport with one worker and four threads, serving the same routes/calculations as the local app. The Flask development server is not used. Render handles HTTPS before forwarding to the container’s `0.0.0.0:$PORT` listener.
- Hosted notes, cohort/filter context, and revisions go to the configured Neon database. Everyone given the workspace credential can access the same library. This is one owner workspace, not separate visitor accounts.
- Remote database connections require TLS. Database failures return a generic error and do not fall back to local storage. Save/update/history are transactional and preserve revision conflict checks.
- Raw case text, uploaded narratives, and model outputs are not added to the hosted investigation store. API/database passwords remain server-side. User-provided narrative text is processed by the Vigil server, without persistence or transmission to a language-model service.
- The Docker image excludes local secrets, personal databases, original pickle artifacts, and local runtime data. It retains the scientific packages for all existing model variants and the synthetic CSV as an explicit offline exploration option.
- Basic authentication is cached by the browser. Close its private browsing session or clear site authentication data after use on a shared computer.
- Free compute is limited. Model studio remains included; verify the desired training sample on the actual instance. Do not automatically upgrade a plan if its resource limits are reached.

## Backups and recovery

On the hosted service, with `VIGIL_DATABASE_URL` configured:

```sh
python scripts/backup_investigations.py --output /tmp/vigil-investigations-YYYY-MM-DD.json
```

This exports the current documents and full recorded history in one read-only, repeatable-read transaction. It excludes the connection URL and other credentials. The JSON export is for private portability/recovery and is not an executable SQL dump; importing it is a deliberate maintenance task. Download the file privately before the free instance stops; keeping a copy on its disposable filesystem is not a durable backup. Neon’s own snapshot/export tools are another option; inspect their current Free-plan limits.

The local SQLite backup remains:

```powershell
.\.venv\Scripts\python.exe scripts/backup_investigations.py --output backups/investigations-YYYY-MM-DD.sqlite3
```

It uses SQLite’s online backup API and verifies the copy. Both backup modes refuse to overwrite an existing file. Backups contain research notes; keep them private and out of Git. For SQLite restoration, stop writes, keep a backup of the current database, restore a verified copy and remove only obsolete sidecars for that database while stopped, then restart and check its library/history.

A code rollback redeploys the earlier Git commit while retaining the same Neon database. Do not delete the database project as part of a code rollback. Hosted schema additions are additive; the local SQLite schema remains supported.

## Automated deployment verification

The **regression** CI job builds the frontend, runs its tests and the Python suite, and runs real PostgreSQL contracts against an isolated PostgreSQL 17 service. It checks saved-context parity, two revisions, stale writes, rollback after a failed revision write, delete/history behavior, and the authenticated hosted API.

The **container** job builds the actual Docker image, starts it with a separate test PostgreSQL container and no FDA key, verifies authentication and the synthetic dashboard, and creates two saved revisions. It then destroys and recreates the web container with an empty filesystem and verifies that the same notes and timeline still exist in PostgreSQL. Test containers/network are cleaned up afterwards. No real hosting credentials are used.

Local Docker Desktop’s Linux engine was unavailable during preparation, so CI is the image/recreation verification authority. A successful CI run is required before cloud launch; the cloud instance also needs the post-deployment check above.

## Public demo later

The GitHub repository and walkthrough can be public while this hosted workspace stays password-protected. Do not disable authentication to publish it. A public interactive demo needs separate visitor libraries or deliberate read-only behavior and resource controls; that mode is outside this release.
