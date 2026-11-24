targetScope = 'resourceGroup'

param location string = resourceGroup().location
@description('Exact OIDC subject from this repository, including its immutable IDs and production environment.')
param githubSubject string
param roleDefinitionId string

resource networkSecurityGroup 'Microsoft.Network/networkSecurityGroups@2024-05-01' existing = {
  name: 'smart-schedule-demo-nsg'
}
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'smart-schedule-github-actions'
  location: location
  tags: { project: 'smart-schedule', environment: 'ci' }
}
resource federation 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: identity
  name: 'github-production'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: githubSubject
    audiences: ['api://AzureADTokenExchange']
  }
}
resource role 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: networkSecurityGroup
  name: guid(networkSecurityGroup.id, identity.id, roleDefinitionId)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleDefinitionId
  }
}

output clientId string = identity.properties.clientId
output tenantId string = identity.properties.tenantId
