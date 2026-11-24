# Azure hosting research

The user subsequently clarified this is a small university demo and prefers
one server. The current deployment is the
[single-VM deployment](azure_vm_deployment.md), with a verified alternative SKU
and an updated $33.50/month baseline. The comparisons below record the earlier
managed-services research and its original scope.

Verified 23 November 2026 against Microsoft/Azure sources and the public Retail
Prices API. Scope: existing Django/Python 3.13 Docker image, PostgreSQL 17,
low-traffic university demonstration, Azure for Students $100 credit. No Azure
resources were created. Canada Central was the initial research location.
Authenticated checks below supersede it for this subscription; deployment is
proposed in North Central US.

## Authenticated subscription findings

The Azure for Students subscription is enabled with `spendingLimit: On`.
Its assigned allowed-location policy permits `northcentralus`, `belgiumcentral`,
`swedencentral`, `denmarkeast`, and `norwayeast`. The Canada Central foundation
what-if was rejected by that policy; the North Central US what-if succeeded.
No resources were provisioned. Regional capability data advertises PG17 and
Standard_B1ms, but this does not reserve capacity or prove remaining quota.

North Central US is the closest permitted region. Its live retail meters are
Linux B1 $0.018/hour, PostgreSQL B1ms $0.017/hour, ordinary PostgreSQL storage
$0.115/GB-month, ACR Basic $0.1666/day, plus global private DNS $0.50/month.
The proposed 32 GB setup totals **$34.73 USD/month** at 730 hours and 30 registry
days, before usage-dependent extras and any confirmed free-service allowances.
Application data would be hosted in the United States. See the
[deployment proposal](azure_deployment.md) for the exact resources and stages.
Prices came from the [Microsoft Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices),
using the same filters described below with `armRegionName eq 'northcentralus'`.
The Canada Central comparisons below remain useful as research, rather than
the current subscription-specific deployment estimate.

## Recommendation

For a private database and a small predictable bill, prefer **App Service Linux
B1 + PostgreSQL Flexible Server B1ms + regional VNet integration**. The estimated
baseline is **$31.19 USD/month** before registry, logging, and transfer, or
**$13.64** if the subscription actually receives the PostgreSQL free allowance.
Regional App Service VNet integration supports Basic and has no separate feature
charge. Use separate App Service and PostgreSQL delegated subnets and linked
private DNS. [App Service VNet integration](https://learn.microsoft.com/en-us/azure/app-service/overview-vnet-integration)

**Container Apps Consumption** best matches the existing separate migration-job
workflow and intermittent traffic. With a public database and restricted firewall
rules, its database baseline is about **$17.55/month**, with app compute potentially
within the monthly free grant. However, ACA outbound public IPs can change; this
is an operational tradeoff, not a guaranteed static egress arrangement.
For private PostgreSQL, custom-VNet managed networking makes ACA's baseline
about **$43.60/month**, or **$26.05** with eligible free PostgreSQL, before registry,
logging, data processing, and compute exceeding the grant. These comparisons are
calculated estimates, not service quotations. [ACA networking](https://learn.microsoft.com/en-us/azure/container-apps/networking),
[custom-VNet managed resources](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks)

## Student credit and free services

The student offer provides $100 to spend within 12 months. Its **12-month free
services apply to new Azure customers**; do not infer eligibility merely from a
renewed student subscription or an available credit balance. The listed database
allowance is 750 monthly hours of Flexible Server Burstable B1MS, 32 GB storage,
and 32 GB backup storage. The same page lists **one Standard ACR registry with
100 GB storage** for 12 months. This is a Standard offer, not a promise that paid
Basic registry usage receives the same waiver. Verify the subscription's actual
Free services/offer dates before budgeting either resource at zero.
[Azure for Students offer](https://azure.microsoft.com/en-us/free/students/)

Usage beyond free quantities consumes credit. Credit exhaustion can disable the
subscription and services unless upgraded; annual student renewal does not
establish that the first-year database allowance starts again. With only $100
and no applicable free database/registry allowance, rough baseline runway is
5.7 months for public-DB ACA, 3.2 months for private-DB B1, or 2.3 months for
private-DB ACA, shortened by extras. [Student subscription billing](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/azurestudents-subscription-disabled)

## Verified price inputs

Retail USD, Consumption meters, Canada Central unless marked global; monthly
math uses 730 hours. Amounts exclude taxes, discounts, exchange rates, egress,
and any unrelated subscription consumption. Rates were retrieved live using
the [unauthenticated Microsoft Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices).

| Resource / meter | Retail price | Illustrative monthly amount |
| --- | --- | --- |
| PG Flexible Server Burstable B1MS compute | $0.0185/hour | $13.505 |
| PG Flex Server Storage, ordinary Storage meter | $0.1265/GB-month | $4.048 for 32 GB |
| PG Flexible Server Backup Storage LRS, excess | $0.105/GB-month | Usage dependent |
| App Service Basic Plan **Linux** B1 | $0.018/hour | $13.14 |
| ACA Standard vCPU Active Usage | $0.000034/vCPU-second | Usage dependent |
| ACA Standard Memory Active / Idle Usage | $0.000004/GiB-second | Usage dependent |
| ACA Standard vCPU Idle Usage | $0.000004/vCPU-second | Usage dependent |
| ACA Standard Requests | $0.40/million | After free grant |
| ACR Basic Registry Unit | $0.1666/day | $5.00 per 30 days |
| ACR Standard Registry Unit | $0.6666/day | $20.00 per 30 days before offer |
| Standard IPv4 Static Public IP | $0.005/hour each | $7.30 for two |
| Standard LB Included Rules / Outbound Rules, global | $0.025/hour | $18.25 |
| Standard LB Data Processed, global | $0.005/GB | Usage dependent |
| Private DNS zone, global | $0.50/zone-month | $0.50 |
| Private DNS queries, global | $0.40/million | Usage dependent |
| Log Analytics Analytics Logs ingestion | $2.76/GB after free tier | Usage dependent |
| Log Analytics Analytics Logs extra retention | $0.12/GB-month | After included retention |

Reproduce using `https://prices.azure.com/api/retail/prices` with `$filter` set to
`armRegionName eq 'canadacentral' and serviceName eq '<service>' and priceType eq 'Consumption'`.
Service names: `Azure Database for PostgreSQL`, `Azure App Service`,
`Azure Container Apps`, `Container Registry`, `Virtual Network`, `Log Analytics`.
Use region `Global` for Load Balancer; Private DNS has region-independent meters.
Follow `NextPageLink`. Do not substitute similarly named Single Server, Cosmos
DB for PostgreSQL, Windows B1, Premium SSD v2 IOPS, or reserved-instance meters.
[API schema and filtering](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices),
[load balancer pricing rules](https://azure.microsoft.com/en-us/pricing/details/load-balancer/)

ACA's grant is shared per subscription/calendar month: 180,000 vCPU-seconds,
360,000 GiB-seconds, and two million requests. At 0.5 vCPU/1 GiB that represents
100 aggregate replica-hours; at 0.25 vCPU/0.5 GiB it represents 200. This includes
startup, cooldown, and migration-job runtime, not just time serving a request.
At zero replicas there is no resource consumption charge. Jobs use active rates.
Keep `minReplicas=0`, initially `maxReplicas=1`, and benchmark 0.5 vCPU/1 GiB;
the current two-worker image should not be assumed to fit 0.5 GiB without testing.
[ACA billing](https://learn.microsoft.com/en-us/azure/container-apps/billing)

The first request after scaling to zero has a cold start; Microsoft does not
promise a fixed duration. Warm the site before a demonstration, or temporarily
use one minimum replica and account for its cost. PostgreSQL does not scale to
zero with the web app. Stopping PostgreSQL avoids compute charges while stopped,
but storage remains billable and it restarts automatically after seven days.
[ACA cold starts](https://learn.microsoft.com/en-us/azure/container-apps/cold-start),
[PostgreSQL limits](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-limits),
[backup costs](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore)

## Private ACA architecture and hidden fixed costs

Use an **external workload-profile (v2) environment with only its Consumption
profile**, attached to a dedicated subnet of at least `/27`, delegated to
`Microsoft.App/environments`. Put PostgreSQL in another subnet delegated to
`Microsoft.DBforPostgreSQL/flexibleServers`, with private DNS linked to that VNet.
Keep public web ingress; private database access does not require making the
web app private. A job in that ACA environment has the same network path to PG.
[ACA subnet configuration](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks),
[PostgreSQL VNet integration](https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private)

Microsoft explicitly bills an external custom-VNet workload-profile environment
for **one standard egress public IP, one standard ingress public IP, and one
standard load balancer**, plus processed data. At the verified rates this is
$25.55/month before DNS, even when app replicas are zero. The VNet itself does
not remove these managed-resource costs. Do not manually alter the provider's
managed resource group. Avoid adding NAT Gateway, a dedicated/Flex profile,
an ACA inbound private endpoint, or planned-maintenance features to this baseline.
The latter features can trigger additional management charges; the API currently
lists $0.10/hour management/feature meters, about $73/month each applicable meter.
[Managed resource billing](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks),
[management-fee applicability](https://learn.microsoft.com/en-us/azure/container-apps/billing)

For public PG, permit the actual app/job outbound addresses and separately any
temporary administrator address. ACA documents that outbound IPs may change.
The firewall's `0.0.0.0` Azure-services rule admits connections from **other
customers' Azure subscriptions** too; it is not scoped to this app/subscription.
Private PG cannot be reached from a normal public hosted CI runner or local
terminal without a network path. Run migrations inside its VNet instead of
temporarily exposing the database. [ACA egress IP behavior](https://learn.microsoft.com/en-us/azure/container-apps/networking),
[PG firewall semantics](https://learn.microsoft.com/en-us/azure/postgresql/security/security-firewall-rules)

## Image registry, backups, and logs

ACR Basic includes 10 GB; excess storage and builds can add cost. Prefer Standard
only when its applicable first-year offer is confirmed; after that, Basic has
the lower standing registry charge. GHCR is supported as an alternative that
avoids an ACR resource, but Microsoft documents **registry authentication even
for public GHCR images** in its ACA GitHub Actions workflow. Validate the chosen
deployment path and credential requirements. This research does not establish
GitHub billing/retention allowances. [ACR pricing](https://azure.microsoft.com/en-us/pricing/details/container-registry/),
[ACA and GHCR](https://learn.microsoft.com/en-us/azure/container-apps/github-actions)

Use locally redundant PG backups and seven-day retention for the initial demo.
Backup storage up to 100% of provisioned database storage is included; extra WAL
and backup growth can exceed it. Geo-redundancy adds storage consumption.
This is separate from the 12-month student offer.
[PostgreSQL backup accounting](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore)

ACA can store logs in Log Analytics, route them through Azure Monitor, or disable
storage while retaining live streaming. A workspace adds ingestion/retention
costs; the returned Canada Central ingestion meter has a zero-price first 5 GB
tier and $2.76/GB thereafter. Free allocations may already be shared/consumed.
Choose explicit retention and a daily cap if retaining logs; a cap is not a
guaranteed hard spending ceiling. For the lowest initial baseline choose
`appLogsConfiguration.destination='none'` and accept the lack of historical logs.
[Logging destinations](https://learn.microsoft.com/en-us/azure/container-apps/log-options),
[Monitor cost model](https://learn.microsoft.com/en-us/azure/azure-monitor/usage-estimated-costs)

## Deployment requirements

- **App Service migration alternative:** the current browser terminal and preview
  `az webapp exec` use an authenticated Kudu proxy and require no SSH daemon,
  embedded password, or SSH port in a Linux custom image. CLI 2.90.0+ is required;
  use the main app container, one instance, and its installed `/bin/sh`. The
  app must already run. Interactive execution can observe migration success;
  detached execution is fire-and-forget, needs separate exit-status verification,
  and can be interrupted by replacement. It does not itself provide a release
  gate before web startup. ACA's Manual Job gives the cleaner separate migration
  lifecycle; choose private ACA if that operational benefit justifies its extra
  fixed networking charge. [App Service container command execution](https://learn.microsoft.com/en-us/azure/app-service/configure-linux-open-ssh-session)
- **Avoid an unverified ACI shortcut:** Microsoft states that NAT Gateway is
  the only supported outbound configuration for VNet-injected Container Instances.
  Do not assume a transient private ACI migration runner can dispense with it
  because the migration itself mainly accesses private PostgreSQL.
  [ACI virtual network limitations](https://learn.microsoft.com/en-us/azure/container-instances/container-instances-virtual-network-concepts)
- **HTTPS proxy:** ACA HTTP ingress terminates TLS 1.2/1.3 and explicitly
  overwrites client-supplied `X-Forwarded-Proto` with `http` or `https`.
  `allowInsecure=false` redirects HTTP to HTTPS. For that direct ingress path,
  enable the existing `DJANGO_TRUST_X_FORWARDED_PROTO=true`; retain production
  cookies/redirects and exact generated hostname in `DJANGO_ALLOWED_HOSTS`.
  Reassess the trust boundary if another proxy is added.
  [Ingress header guarantee](https://learn.microsoft.com/en-us/azure/container-apps/ingress),
  [ingress settings](https://learn.microsoft.com/en-us/azure/container-apps/ingress-how-to)
- **PostgreSQL extension:** PG17 supports `btree_gist` 1.7. Set server parameter
  `azure.extensions` to include `btree_gist` **before** the existing Django
  `BtreeGistExtension` migration runs; allowlisting does not create the extension.
  [Supported versions](https://learn.microsoft.com/en-us/azure/postgresql/extensions/concepts-extensions-versions),
  [allowlist parameter](https://learn.microsoft.com/en-us/azure/postgresql/server-parameters/param-customized-options)
- **Migrations:** use a Manual ACA Job with the same image digest, DB secrets,
  and network as the app. Override command to `python manage.py migrate --noinput`,
  set parallelism/completion count to one, and wait for successful execution
  before updating web traffic. A deployed job resource does not mean it ran;
  serialize deployment invocations because manual jobs can run concurrently.
  [ACA jobs and execution](https://learn.microsoft.com/en-us/azure/container-apps/jobs)
- **TLS:** use the server FQDN, `PGSSLMODE=verify-full`, and a trusted-root bundle
  supplied through `PGSSLROOTCERT`; verify both Azure root chains in the actual
  image. The image has CA certificates, but a successful encrypted connection
  alone does not prove hostname verification. Do not pin intermediate/server
  certificates. [Azure PostgreSQL client TLS configuration](https://learn.microsoft.com/en-us/azure/postgresql/security/security-tls-how-to-connect)
- **Probes:** explicitly configure startup/liveness/readiness probes for port
  8000 and `/healthz/`, including a Host header allowed by Django. The Docker
  `HEALTHCHECK` is not the ACA probe configuration. Existing `/healthz/` proves
  process liveness, not DB/migration readiness; migration success remains a
  separate release gate. [ACA probe resource schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/jobs)

## Bicep resource sketch and remaining verification

Current documented stable API versions include `Microsoft.App/managedEnvironments`,
`containerApps`, and `jobs` **2026-07-01**, and PostgreSQL `flexibleServers`
**2026-10-01**. Pin explicit versions; do not copy the older sample version
embedded in a newer reference page. Minimal ACA resource set is environment,
web app, Manual migration job, PG server/database/extension configuration,
registry if required, secrets, and (for private PG) VNet/delegated subnets/private
DNS/link. A Log Analytics workspace is optional. Use `@secure()` deployment
parameters and app/job secret references; never outputs for passwords.
[Environment schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2026-07-01/managedenvironments),
[app schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps),
[job schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/jobs),
[PG schema](https://learn.microsoft.com/en-us/azure/templates/microsoft.dbforpostgresql/2026-10-01/flexibleservers)

Unverified subscription facts: active credit/expiry, first-year free-service
eligibility, provider registrations, permitted regions, PG B1ms/PG17 capability,
available quota, and deployment-time regional capacity. They require an
authenticated Azure subscription check; retail meters and documentation cannot
establish them. ACA quotas depend on subscription type/age and usage; inspect
the subscription/region quota and, after an environment exists,
`az containerapp env list-usages`. Capacity and quota are different checks.
[ACA quotas](https://learn.microsoft.com/en-us/azure/container-apps/quotas),
[PG regional capabilities API](https://learn.microsoft.com/en-us/rest/api/postgresql/capabilities-by-location/execute?view=rest-postgresql-2024-08-01),
[ACA capacity errors](https://learn.microsoft.com/en-us/azure/container-apps/troubleshoot-environment-capacity)

Validation performed: read the current Docker/settings/deployment files, checked
official documentation, retrieved live retail meters, and recomputed cost
arithmetic. No application code changed; application tests and live deployment
checks were not run for this documentation-only research.
