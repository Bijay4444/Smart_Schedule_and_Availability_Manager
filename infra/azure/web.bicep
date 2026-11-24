targetScope = 'resourceGroup'

@minLength(3)
@maxLength(12)
param prefix string = 'smartsched'
param location string = resourceGroup().location
@description('Full ACR image reference, preferably repository@sha256:digest.')
param imageReference string
@secure()
param postgresPassword string
@secure()
@minLength(50)
param djangoSecretKey string
@description('Keep false until migrations and private verification have succeeded.')
param publishPublicly bool = false

var suffix = uniqueString(resourceGroup().id)
var webName = '${prefix}-web-${suffix}'
var hostName = web.properties.defaultHostName

resource plan 'Microsoft.Web/serverfarms@2024-04-01' existing = { name: '${prefix}-plan' }
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = { name: '${prefix}-web-identity' }
resource registry 'Microsoft.ContainerRegistry/registries@2025-04-01' existing = { name: '${replace(prefix, '-', '')}acr${suffix}' }
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' existing = { name: '${prefix}-pg-${suffix}' }
resource network 'Microsoft.Network/virtualNetworks@2024-05-01' existing = { name: '${prefix}-vnet' }

resource web 'Microsoft.Web/sites@2024-04-01' = {
  name: webName
  location: location
  kind: 'app,linux,container'
  tags: { project: 'smart-schedule', environment: 'presentation' }
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    clientAffinityEnabled: false
    virtualNetworkSubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', network.name, 'web')
    siteConfig: {
      linuxFxVersion: 'DOCKER|${imageReference}'
      acrUseManagedIdentityCreds: true
      acrUserManagedIdentityID: identity.properties.clientId
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      scmMinTlsVersion: '1.2'
      http20Enabled: true
      remoteDebuggingEnabled: false
      healthCheckPath: '/healthz/'
      vnetRouteAllEnabled: false
      // SCM still requires Azure authentication. Keep it distinct so the owner
      // can run supervised migrations while the public application is closed.
      scmIpSecurityRestrictionsUseMain: false
      ipSecurityRestrictionsDefaultAction: publishPublicly ? 'Allow' : 'Deny'
      ipSecurityRestrictions: []

    }
  }
}

resource appSettings 'Microsoft.Web/sites/config@2024-04-01' = {
  parent: web
  name: 'appsettings'
  properties: {
    DOCKER_REGISTRY_SERVER_URL: 'https://${registry.properties.loginServer}'
    WEBSITES_PORT: '8000'
    WEBSITES_ENABLE_APP_SERVICE_STORAGE: 'false'
    WEBSITES_CONTAINER_START_TIME_LIMIT: '600'
    DJANGO_SETTINGS_MODULE: 'config.django.production'
    DJANGO_SECRET_KEY: djangoSecretKey
    DJANGO_DEBUG: 'false'
    DJANGO_ALLOWED_HOSTS: '${hostName},localhost,127.0.0.1'
    DJANGO_CSRF_TRUSTED_ORIGINS: 'https://${hostName}'
    DJANGO_TRUST_X_FORWARDED_PROTO: 'true'
    DJANGO_SECURE_SSL_REDIRECT: 'true'
    DJANGO_SESSION_COOKIE_SECURE: 'true'
    DJANGO_CSRF_COOKIE_SECURE: 'true'
    DJANGO_SECURE_HSTS_SECONDS: '3600'
    PGDATABASE: 'smart_schedule'
    PGUSER: 'scheduleadmin'
    PGPASSWORD: postgresPassword
    PGHOST: postgres.properties.fullyQualifiedDomainName
    PGPORT: '5432'
    PGSSLMODE: 'verify-full'
    PGSSLROOTCERT: '/etc/ssl/certs/ca-certificates.crt'
  }
}

resource publishingScm 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: web
  name: 'scm'
  properties: { allow: false }
}
resource publishingFtp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: web
  name: 'ftp'
  properties: { allow: false }
}

output url string = 'https://${hostName}'
output webName string = web.name
output publicAccessEnabled bool = publishPublicly
