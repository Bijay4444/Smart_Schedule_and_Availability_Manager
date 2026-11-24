targetScope = 'subscription'

param resourceGroupName string = 'smart-schedule-demo'
param location string = 'northcentralus'
param adminUsername string = 'azureuser'
param sshPublicKey string
@description('Your current public IPv4 address followed by /32. Never use 0.0.0.0/0.')
param sshSourceCidr string
param vmSize string = 'Standard_B2als_v2'

resource group 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: { project: 'smart-schedule', environment: 'demo' }
}
module server 'vm-resources.bicep' = {
  name: 'smart-schedule-demo-vm'
  scope: group
  params: {
    location: location
    sshPublicKey: sshPublicKey
    sshSourceCidr: sshSourceCidr
    vmSize: vmSize
    adminUsername: adminUsername
  }
}
output connection object = {
  hostname: server.outputs.hostname
  publicAddress: server.outputs.publicAddress
  vmName: server.outputs.vmName
  sshUser: server.outputs.sshUser
}
