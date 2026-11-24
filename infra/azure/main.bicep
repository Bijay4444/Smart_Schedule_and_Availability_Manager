targetScope = 'subscription'

param resourceGroupName string = 'smart-schedule-prod'
param location string = 'northcentralus'
@minLength(3)
@maxLength(12)
param prefix string = 'smartsched'
@secure()
param postgresPassword string

resource group 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: { project: 'smart-schedule', environment: 'presentation' }
}
module foundation 'foundation.bicep' = {
  name: 'smart-schedule-foundation'
  scope: group
  params: { prefix: prefix, location: location, postgresPassword: postgresPassword }
}

output resources object = foundation.outputs
