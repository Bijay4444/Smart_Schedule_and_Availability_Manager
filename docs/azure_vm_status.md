# Azure VM deployment status

Deployed and verified at **2026-11-24T22:56:49.642152+00:00**.

**Application:** [Open Smart Schedule](https://schedule.khadkabijay.com.np/).
The original [Azure address](https://schedule-4xebi5nxn46wq.northcentralus.cloudapp.azure.com/)
continues to work. Both names have verified public HTTPS certificates and passed
the authenticated scheduling checks. The Cloudflare DNS-only A record points
to the same VM; no additional Azure service was provisioned. Credentials and
database data were preserved. The 58 relevant deployment/settings tests passed.
Authentication is required for scheduling pages. Private owner credentials are
saved locally in ignored `.azure-deploy/vm/owner-login.txt`; keep the owner password
out of documentation and Git. The database was initialized fresh; local personal
records were not copied. The public guest login below was provisioned separately.

## Public guest login

Username: **`schedule_demo`**. Shareable password: **`DemoSchedule!2026`**.
This account has fictional data for 23–29 November 2026: five sources, five
one-time commitments, six recurring series, and working-window examples.
It has no admin access or permissions. The other three local demo accounts were
not created. Other users' scheduling records were verified unchanged during
provisioning. Visitors share guest edits; personal data belongs in separate accounts.
The existing demo-fixture tests passed (28 tests). See the
[demo walkthrough](demo_data.md#hosted-guest-account).

## Running architecture

- Resource group: `smart-schedule-demo`; VM: `smart-schedule-demo`.
- Region: North Central US; application data is hosted in the United States.
- Ubuntu 24.04 LTS, B2als v2: 2 vCPUs, 4 GiB RAM, 32 GiB Standard SSD OS disk.
- Docker Compose runs PostgreSQL 17, Django/Gunicorn and Caddy on that VM.
- Image: `smart-schedule:vm-prep-20261124`, built/tested locally and transferred
  with checksum verification. No paid image registry or managed database.
- PostgreSQL data and TLS certificates use persistent named volumes on `/dev/sda1`.
- Only Caddy publishes app ports 80/443. SSH uses a pinned host key, private key
  authentication and the deployment operator's public IPv4 /32 allowlist.
- All migrations completed, including the PostgreSQL `btree_gist` extension.
- Services were healthy at verification. Estimated baseline is **US$33.50/month**
  before disk transactions, traffic, backups and taxes. Billing is now active.

## Live checks passed

- Public HTTPS certificate and health.
- HTTP redirects to HTTPS.
- Private pages require authentication.
- Owner login and secure session cookie.
- Scheduling pages load.
- Proxy replaces client forwarded-protocol headers.
- Versioned static CSS served.
- CSRF-protected commitment creation and account isolation.
- Cross-account access denied.
- Form changes persisted to PostgreSQL.

The check created and removed only its temporary accounts/commitments. The owner
account remains; its password is random and stored in the private local file.
The first custom-format PostgreSQL backup completed and was downloaded to
`.azure-deploy/vm/backups/` with mode 0600 and a recorded SHA-256 checksum.
Local backup and restore rehearsals passed before provisioning.

## Operational notes

The [deployment guide](azure_vm_deployment.md) covers later releases, backups,
deallocation and deletion. Detailed private logs, connection metadata and the
verification/backup record are in ignored `.azure-deploy/vm/`.

A template output adjustment unwraps individual ARM module output values so
future deployment connection fields are plain strings. The 20 focused VM tests
passed after this change. The original deployment's nested output shape remains
supported by the guide's hostname query; this required no VM reprovisioning.

Django deployment checks emitted only W005/W021 for HSTS include-subdomains and
preload, which remain deliberately disabled for this initial Azure hostname.
This demo has one VM, a maintenance window for releases, manual off-VM backups,
and no automatic failover. The initial backup is not a scheduled backup service.
No automatic shutdown or deletion was configured; deallocation stops compute
billing, while retained disk and public IP still incur charges.
