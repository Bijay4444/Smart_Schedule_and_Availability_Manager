# Single Azure VM demo hosting research

Verified 2026-11-24 against official Microsoft, Docker, and Caddy documentation.
Scope: one Ubuntu VM in allowed `northcentralus`, running Django, PostgreSQL,
and Caddy through Compose. No infrastructure or credentials were changed.

## Sizing recommendation

**Deployment update (2026-11-24):** Azure preflight rejected B1ms in North
Central US; subscription SKU responses also restrict it in Sweden Central and
Norway East. The prepared default is now B2als v2 (2 vCPUs / 4 GiB, x64), whose
North Central US what-if succeeded. Its retail rate is $0.0376/hour, making the
disk/IP-inclusive baseline **$33.50/month**. The earlier $21.23 B1ms estimate below
is conditional on availability and is not the current deployable proposal.
See the [actual deployment guide](azure_vm_deployment.md).

Use **at least 2 GiB RAM**, with `Standard_B1ms` as the small candidate.
Microsoft lists B1ms as 1 vCPU / 2 GiB, B1s as 1 vCPU / 1 GiB, and
B2ats_v2 as 2 vCPUs / **1 GiB**, despite its larger CPU count.
[Bv1 sizes](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/bv1-series),
[Basv2 sizes](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/basv2-series).

The 2 GiB floor is an engineering recommendation, not a measured or official minimum. Ubuntu, Docker,
PostgreSQL, Gunicorn workers, and Caddy share RAM; dependency installation
and image builds add transient demand. Do not select the 1 GiB free sizes
as the default for the combined database/application/build workload.
Build elsewhere, start with few application workers, and measure memory
under the demo workload before claiming capacity. Burstable VM CPU credits
also limit sustained build or application throughput.
[B-series behavior](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/basv2-series).

## Images without a paid registry

Build the application image locally for the VM's `linux/amd64` platform,
save its tagged image with `docker image save`, transfer the archive over SSH,
then restore it with `docker image load`. Compose can reference that local tag.
This avoids requiring ACR and avoids compiling dependencies on the small VM;
it does not eliminate image storage or transfer. Keep runtime secrets outside
the image. Docker's image archive contains images/tags, not database volumes.
[Save](https://docs.docker.com/reference/cli/docker/image/save/),
[load](https://docs.docker.com/reference/cli/docker/image/load/),
[backup boundaries](https://docs.docker.com/desktop/settings-and-maintenance/backup-and-restore/).

## Persistent database and HTTPS

Use a PostgreSQL named volume on the **managed OS disk**, with a persistent
managed OS disk selected rather than an ephemeral OS disk. Docker volumes
survive container removal; on Linux their default data location remains
`/var/lib/docker`. Verify that this path is on the managed disk. Never relocate
the database to Azure's temporary/resource disk: its contents can disappear
on stop, redeploy, or maintenance. Keep an off-VM database backup; a volume
does not protect against disk/resource deletion.
[Docker storage](https://docs.docker.com/engine/storage/),
[Docker data directories](https://docs.docker.com/engine/daemon/),
[Azure disks](https://learn.microsoft.com/en-us/azure/virtual-machines/managed-disks-overview).

A purchased domain is optional: Azure's public-IP DNS label creates a managed
`label.northcentralus.cloudapp.azure.com` hostname; use the returned FQDN,
which may include a scope hash. Caddy can obtain and renew a
public certificate for public DNS names when DNS resolves to the VM, inbound
TCP 80/443 reaches Caddy, and its certificate data directory persists.
**Inference:** these documented capabilities make free HTTPS on the assigned
Azure hostname feasible; issuance has not been exercised for this deployment.
[Azure DNS labels](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/public-ip-addresses),
[Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).

## Cost boundaries and free-service limits

Live North Central US retail inputs supplied by the deployment price check:
B1ms Linux $0.0208/hour, E4 LRS Standard SSD 32 GiB $2.40/month, static Standard
IPv4 $0.005/hour. At 730 hours this is **$21.23 USD/month**, versus the earlier
managed proposal's $34.73. Excludes disk transactions ($0.002/10,000), backup,
egress, taxes, and unrelated usage. VM SKU availability/quota remains unconfirmed.
[Retail API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices).
Disk/IP are separate from compute; compare the total with a VPS bundle.
Shared-disk additional-mount fees do not apply to this ordinary single-VM disk.
[Disk pricing](https://azure.microsoft.com/en-us/pricing/details/managed-disks/).

Azure for Students advertises 750 monthly hours each of B1s, B2pts_v2, and
B2ats_v2 for 12 months for new customers. B1ms is not in that VM allowance.
Verify actual eligibility/expiry; student renewal does not establish renewed free services.
[Student offer](https://azure.microsoft.com/en-us/free/students/).

Guest OS shutdown leaves an allocated, billed VM. Confirm **Stopped
(Deallocated)** to stop compute billing. Managed disks and a retained static
public IP continue to incur charges while deallocated; deleting the IP stops
its charge but gives up that address. [VM billing states](https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing),
[static IP billing](https://azure.microsoft.com/en-us/pricing/details/ip-addresses/).
