targetScope = 'resourceGroup'

param location string = resourceGroup().location
param sshPublicKey string
param sshSourceCidr string
param vmSize string = 'Standard_B2als_v2'
param adminUsername string = 'azureuser'

var name = 'smart-schedule-demo'
var tags = { project: 'smart-schedule', environment: 'demo' }

resource firewall 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: '${name}-nsg'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'OwnerSSH'
        properties: {
          priority: 100
          access: 'Allow'
          direction: 'Inbound'
          protocol: 'Tcp'
          sourceAddressPrefix: sshSourceCidr
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '22'
        }
      }
      {
        name: 'PublicWeb'
        properties: {
          priority: 110
          access: 'Allow'
          direction: 'Inbound'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRanges: ['80', '443']
        }
      }
    ]
  }
}
resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: '${name}-vnet'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.43.0.0/16'] }
    subnets: [{ name: 'server', properties: { addressPrefix: '10.43.0.0/24', networkSecurityGroup: { id: firewall.id } } }]
  }
}
resource publicIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: '${name}-ip'
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Regional' }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
    dnsSettings: { domainNameLabel: 'schedule-${uniqueString(resourceGroup().id)}' }
  }
}
resource interface 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: '${name}-nic'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [{
      name: 'primary'
      properties: {
        privateIPAllocationMethod: 'Dynamic'
        subnet: { id: resourceId('Microsoft.Network/virtualNetworks/subnets', network.name, 'server') }
        publicIPAddress: { id: publicIp.id }
      }
    }]
  }
}
resource vm 'Microsoft.Compute/virtualMachines@2024-11-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    hardwareProfile: { vmSize: vmSize }
    storageProfile: {
      imageReference: { publisher: 'Canonical', offer: 'ubuntu-24_04-lts', sku: 'server', version: 'latest' }
      osDisk: {
        name: '${name}-os'
        createOption: 'FromImage'
        diskSizeGB: 32
        caching: 'ReadWrite'
        managedDisk: { storageAccountType: 'StandardSSD_LRS' }
        // Retain the database disk if just the VM is deleted. Deleting the
        // resource group still deletes the disk: an off-VM backup is required.
        deleteOption: 'Detach'
      }
    }
    osProfile: {
      computerName: name
      adminUsername: adminUsername
      customData: base64(replace(loadTextContent('../../docker/vm/cloud-init.yaml'), '__ADMIN_USERNAME__', adminUsername))
      linuxConfiguration: {
        disablePasswordAuthentication: true
        provisionVMAgent: true
        ssh: { publicKeys: [{ path: '/home/${adminUsername}/.ssh/authorized_keys', keyData: sshPublicKey }] }
      }
    }
    networkProfile: { networkInterfaces: [{ id: interface.id, properties: { primary: true, deleteOption: 'Delete' } }] }
  }
}

output hostname string = publicIp.properties.dnsSettings.fqdn
output publicAddress string = publicIp.properties.ipAddress
output vmName string = vm.name
output sshUser string = adminUsername
