# Single-VM Azure demo deployment

**Deployed:** [Open Smart Schedule](https://schedule.khadkabijay.com.np/).
HTTPS and authenticated scheduling checks passed; the initial database backup
has been downloaded off the VM. See [deployment status](azure_vm_status.md).

One Ubuntu VM runs Django, PostgreSQL 17, and Caddy using Docker Compose.
Only Caddy publishes application ports (80/443); PostgreSQL and Django have no
host port. SSH uses a private key and an owner IP allowlist. The managed 32 GiB
OS disk stores Ubuntu, Docker images, database data and bounded container logs.
Application dependencies and scheduling behavior are unchanged.

## Validated proposal and cost

Azure preflight rejected the original B1ms / 2 GiB size in North Central US.
SKU responses also restrict it in Sweden Central and Norway East. Therefore
the original $21.23 quote is not the deployable default.

The template now uses **Standard_B2als_v2, 2 vCPUs / 4 GiB RAM**, Ubuntu 24.04,
in **North Central US**. Its what-if preview succeeded on 24 November 2026,
proposing a resource group, VM, public IP, NIC, VNet and network security group.
The VM creates its managed disk. Resources were provisioned after cost approval.
The earlier what-if preview did not reserve capacity.
Application data will reside in the United States.

| Resource | Estimated USD/month |
| --- | ---: |
| B2als v2 Linux, $0.0376/hour × 730 | $27.45 |
| 32 GiB E4 LRS Standard SSD | $2.40 |
| Standard public IPv4, $0.005/hour × 730 | $3.65 |
| **Baseline** | **$33.50** |

Live quotes came from the [Microsoft Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices),
Consumption meters in `northcentralus`: `Virtual Machines Basv2 Series / B2als v2`,
`Standard SSD Managed Disks / E4 LRS Disk`, and `IP Addresses / Standard IPv4 Static
Public IP`. Disk transactions ($0.002/10,000), traffic, backups and taxes add cost.
No free allowance is assumed; B2als v2 is not in the advertised student free VM
sizes. $100 covers about three baseline months without other consumption. Keep
the subscription spending limit on. See [research](azure_vm_research.md).

## Components and behavior

- `infra/azure/vm.bicep` and `vm-resources.bicep` define the VM, network, key-based
  SSH, persistent disk and Azure DNS hostname. No paid registry or managed DB.
- `docker/vm/cloud-init.yaml` installs Docker/Compose from Docker's official
  repository and creates private `/opt/smart-schedule`. It contains no app secrets.
- `compose.vm.yaml` defines one Gunicorn worker, a private database network,
  persistent PostgreSQL/certificate volumes and rotated logs.
- `docker/vm/Caddyfile` terminates HTTPS and replaces untrusted forwarded headers.
  Django trusts this sole public proxy path. Public ACME issuance requires the
  actual DNS name to resolve and inbound ports 80/443 to reach Caddy.
- `scripts/prepare_vm_deploy.py` makes a private release bundle with independent
  random credentials; reruns refuse to overwrite an existing environment.
- `docker/vm/deploy.sh` locks deployments, closes public access, waits for DB,
  runs migrations/checks, waits for Django, then starts the proxy. A migration
  failure leaves access closed. It discards exported development overrides.
- `docker/vm/backup.sh` makes a private custom-format dump and reports success
  only after the dump completes. Copy backups off the VM separately.

Database traffic is unencrypted only inside this VM's isolated Docker network;
public traffic uses HTTPS. This differs from remote managed PostgreSQL's TLS
setup. The existing migration creates `btree_gist`; no Azure extension allowlist
is involved. Application containers receive no Docker socket. Runtime images
exclude VM setup scripts, private environments and backup files.

## Custom domain

The primary address is `schedule.khadkabijay.com.np`. Cloudflare has a DNS-only
A record named `schedule` pointing to the VM's static IP `20.88.56.187`.
Caddy obtains and renews its public certificate. The original Azure hostname
remains available as an alias, with its own valid certificate.

The existing private environment contains:

```dotenv
APP_HOST=schedule.khadkabijay.com.np
APP_HOST_ALIAS=schedule-4xebi5nxn46wq.northcentralus.cloudapp.azure.com
```

Compose configures both Django allowed hosts and HTTPS CSRF origins. Caddy serves
both names. `APP_HOST_ALIAS` is optional for fresh deployments that use only one
name. Keep the existing database credentials and Django secret when changing
hostnames; do not regenerate the environment. No image rebuild is required.
After a domain/configuration change, recreate `web` first and then `proxy` using
`docker compose --env-file .env up -d --wait --no-deps <service>`. PostgreSQL
does not need restarting. Both domains passed live HTTPS, login, scheduling form,
asset and isolation checks after this change. The username/password are unchanged.

## Preview and provision

The ignored private SSH key is already at `.azure-deploy/vm/id_rsa`. Keep it
locally and securely backed up. For a fresh checkout create a key with
`ssh-keygen -t rsa -b 3072 -f .azure-deploy/vm/id_rsa`; never overwrite an existing
deployment key. The Azure CLI must be signed into the student subscription.

Set the actual subscription and your current public IPv4 address:

```bash
AZURE_VM_SUBSCRIPTION='<student-subscription-id>'
AZURE_VM_SSH_SOURCE='<your-current-public-ipv4>/32'
az deployment sub what-if --subscription "$AZURE_VM_SUBSCRIPTION" \
  --name smart-schedule-demo-vm --location northcentralus \
  --template-file infra/azure/vm.bicep \
  --parameters sshPublicKey="$(cat .azure-deploy/vm/id_rsa.pub)" \
  sshSourceCidr="$AZURE_VM_SSH_SOURCE"
```

Preparation used non-routable test address `192.0.2.1/32` for what-if; replace
it before creation. Do not open SSH to `0.0.0.0/0`. **Only after the updated
billable proposal is approved**, repeat the command with `create` replacing
`what-if`. Then retrieve the actual generated hostname:

```bash
AZURE_VM_HOST=$(az deployment sub show --subscription "$AZURE_VM_SUBSCRIPTION" \
  --name smart-schedule-demo-vm \
  --query 'properties.outputs.connection.value.hostname.value || properties.outputs.connection.value.hostname' -o tsv)
ssh -i .azure-deploy/vm/id_rsa "azureuser@$AZURE_VM_HOST"
# On the VM:
sudo cloud-init status --wait
sudo test -f /var/lib/smart-schedule-bootstrap-complete
sudo docker compose version
findmnt -T /var/lib/docker
exit
```

SSH uses normal host-key verification. Inspect bootstrap errors in
`/var/log/cloud-init-output.log`. Docker data must be on the persistent OS disk,
not Azure's temporary/resource disk. Use the returned FQDN, not a guessed URL.

## Build, upload and deploy

Build locally with a unique release tag; there is no image build on the small VM:

```bash
AZURE_VM_IMAGE="smart-schedule:vm-$(date -u +%Y%m%dT%H%M%SZ)"
docker build --platform linux/amd64 --target runtime -t "$AZURE_VM_IMAGE" .
uv run python scripts/prepare_vm_deploy.py --hostname "$AZURE_VM_HOST" --image "$AZURE_VM_IMAGE"
docker image save --output .azure-deploy/vm/app-image.tar "$AZURE_VM_IMAGE"
scp -i .azure-deploy/vm/id_rsa .azure-deploy/vm/app-image.tar "azureuser@$AZURE_VM_HOST:/opt/smart-schedule/"
scp -i .azure-deploy/vm/id_rsa -r .azure-deploy/vm/bundle/. "azureuser@$AZURE_VM_HOST:/opt/smart-schedule/"
ssh -i .azure-deploy/vm/id_rsa "azureuser@$AZURE_VM_HOST"
# On the VM:
cd /opt/smart-schedule
sudo docker image load --input app-image.tar
sudo sh deploy.sh
sudo docker compose --env-file .env exec web python manage.py createsuperuser
```

Bundle directory permissions are 0700; `.env` is 0600. Keep the file and its
credentials for later releases. Expanded `docker compose config` contains secrets;
do not paste it into shared logs. Enter the owner password privately. Local
development data is not copied. Account-specific scheduling screens require login.
The explicitly provisioned public guest account is now `schedule_demo`, with the
shareable password `DemoSchedule!2026`. It has fictional data and no admin access;
see the [hosted demo guide](demo_data.md#hosted-guest-account). The other local
fixture accounts were not created on the VM. Owner credentials remain private.

Before sharing the URL verify public HTTPS `/healthz/`, HTTP redirect, login,
CSRF-protected forms, CSS, commitments and account isolation. Caddy's container
health alone does not prove public certificate issuance. `/healthz/` deliberately
does not query the DB. The local rehearsal uses a trusted local CA, not public ACME.

For later releases back up first, load a new tagged image and update only
`APP_IMAGE` in the existing remote `.env`, then rerun `deploy.sh`. Preserve the
other fields and volumes. There is a maintenance window and no automatic schema
rollback. Inspect interrupted migrations or a stale `.deploy-lock` before retrying.

## Backups, stopping and validation

Run `sudo sh /opt/smart-schedule/backup.sh` on the VM. Copy its private dump off
the VM through SSH (`sudo cat` into a local file under `umask 077`) or another
private destination. Restore-test into a separate empty database using
`pg_restore --exit-on-error`. A volume or dump stored only on the server cannot
protect against deleting the server disk. Keep Ubuntu/Docker security updates
current and monitor disk usage; this setup has no automatic failover or managed backup.

`docker compose down` preserves volumes; **`down --volumes` deletes the database
and certificates**. Deleting just the VM retains its OS disk here; deleting the
resource group deletes the disk too. Resource deletion needs explicit approval.
Deallocate to stop compute billing: guest shutdown alone is insufficient. Disk
and retained public IP charges continue, and capacity is not reserved for restart.
Leave the VM running around the presentation.

```bash
BICEP_BIN=/path/to/bicep uv run pytest tests/test_vm_deployment.py tests/test_docker_setup.py tests/test_deployment.py tests/test_config.py
# Opt-in real Docker rehearsal, after building the image:
VM_TEST_IMAGE="$AZURE_VM_IMAGE" uv run pytest tests/test_vm_docker_integration.py
```

The rehearsal uses a random project, temporary credentials, loopback ports and
its own volumes. It checks TLS, login/CSRF, assets, account isolation, container
recreation and real backup restoration, then removes only those test volumes.
