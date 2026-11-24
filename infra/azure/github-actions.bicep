targetScope = 'subscription'

param resourceGroupName string = 'smart-schedule-demo'
param location string = 'northcentralus'
@description('Exact immutable repository OIDC subject for the production environment.')
param githubSubject string

resource group 'Microsoft.Resources/resourceGroups@2024-03-01' existing = {
  name: resourceGroupName
}
resource ruleRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(group.id, 'smart-schedule-ci-ssh-rule')
  properties: {
    roleName: 'Smart Schedule CI SSH rule'
    description: 'Manage SSH rules on the project NSG; no VM, identity, database or subscription administration.'
    type: 'CustomRole'
    assignableScopes: [group.id]
    permissions: [{
      actions: [
        'Microsoft.Network/networkSecurityGroups/read'
        'Microsoft.Network/networkSecurityGroups/securityRules/read'
        'Microsoft.Network/networkSecurityGroups/securityRules/write'
        'Microsoft.Network/networkSecurityGroups/securityRules/delete'
      ]
      notActions: []
      dataActions: []
      notDataActions: []
    }]
  }
}

module identity 'github-actions-resources.bicep' = {
  name: 'smart-schedule-ci-identity'
  scope: group
  params: { location: location, githubSubject: githubSubject, roleDefinitionId: ruleRole.id }
}
output clientId string = identity.outputs.clientId
output tenantId string = identity.outputs.tenantId
output subscriptionId string = subscription().subscriptionId
