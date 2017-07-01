#!/usr/bin/python
import logging
import ovirtsdk4 as sdk
import ovirtsdk4.types as types
import time

from ovirtsdk4.services import ClustersService, VmsService, TemplatesService, InstanceTypesService, DisksService, \
    DiskService, VmService, DiskAttachmentService, VnicProfilesService


def get_bytes_from_gb(db):
    return db * (2 ** 30)

# API Settings

API_URL = 'https://example.com/ovirt-engine/api'
USERNAME = 'admin@internal'
PASSWORD = 'redhat123'
DEBUG = True

# Inputs
CLUSTER_NAME = 'Default'
TEMPLATE_NAME = 'GoldenTemplate'
INSTANCE_TYPE = 'Small'
VM_NAME = 'testing'
DISK_SIZE = get_bytes_from_gb(8)
SSH_KEY = ''

DNS_SEARCH_PATH = 'example.com'
DNS_SERVERS = '8.8.8.8'
HOSTNAME = '{}.{}'.format(VM_NAME, DNS_SEARCH_PATH)

NETWORK_NAME = 'ovirtmgmt'

STATIC_IP = '10.0.0.10'
NETMASK = '255.255.255.0'
GATEWAY = '10.0.0.1'

VM_USERNAME = 'centos'

logging.basicConfig(level=logging.DEBUG)


class TemplateError(Exception):
    """Template Exception"""


class ClusterError(Exception):
    """Cluster Exception"""


class InstanceTypeError(Exception):
    """Instance Type Exception"""


class VMError(Exception):
    """Virtual Machine Exception"""


class DiskAttachmentError(Exception):
    """Disk Attachment Exception"""


class NetworksServiceError(Exception):
    """Networks Service Exception"""


class ProfilesServiceError(Exception):
    """Profiles Service Exception"""


if __name__ == '__main__':
    connection = sdk.Connection(
        url=API_URL,
        username=USERNAME,
        password=PASSWORD,
        ca_file='pki-resource.cer',
        debug=True,
        log=logging.getLogger(),
    )
    logging.info('Connection Successful')

    # Cluster Validation
    clusters_service = connection.system_service().clusters_service()  # type: ClustersService
    clusters = clusters_service.list(search=CLUSTER_NAME)
    if len(clusters) != 1:
        raise ClusterError('Found {} Clusters, check the cluster name'.format(len(clusters)))
    cluster = clusters.pop()

    # Template Validation
    template_service = connection.system_service().templates_service()  # type: TemplatesService
    template = template_service.list(search=TEMPLATE_NAME)
    if len(template) != 1:
        raise TemplateError('Found {} Templates, check template name'.format(len(template)))
    template = template.pop()

    # Instance Type Validation
    instance_service = connection.system_service().instance_types_service()  # type: InstanceTypesService
    instance_type = instance_service.list(search=INSTANCE_TYPE)
    if len(instance_type) != 1:
        raise InstanceTypeError('Found {} Instance Types, check instance type')
    instance_type = instance_type.pop()

    # VM Creation
    vms_service = connection.system_service().vms_service()  # type: VmsService
    if vms_service.list(search=VM_NAME):
        raise VMError('Found VM with name {}, unable to proceed'.format(VM_NAME))
    # vm = vms_service.list(search=VM_NAME)[0]  # type: types.Vm

    vm = vms_service.add(  # type: types.Vm
        vm=types.Vm(
            cluster=cluster,
            template=template,
            instance_type=instance_type,
            name=VM_NAME,
            fqdn=HOSTNAME
        )
    )
    vm_service = vms_service.vm_service(vm.id)  # type: VmService
    while vm.status != types.VmStatus.DOWN:
        time.sleep(5)
        vm = vm_service.get()

    # Disk Configuration
    disk_attachments_service = vm_service.disk_attachments_service()
    disk_attachments = disk_attachments_service.list()
    if len(disk_attachments) != 1:
        raise DiskAttachmentError('Found {} disks instead of 1, fix template'.format(len(disk_attachments)))
    disk_attachment = disk_attachments.pop()  # type: types.DiskAttachment

    disks_service = connection.system_service().disks_service()  # type: DisksService
    disk_service = disks_service.service(disk_attachment.disk.id)  # type: DiskService
    disk = disk_service.get()  # type: types.Disk

    if disk.provisioned_size < DISK_SIZE:
        disk.provisioned_size = DISK_SIZE
        disk_attachment_service = disk_attachments_service.service(disk_attachment.id)  # type: DiskAttachmentService
        disk_attachment_service.update(
            types.DiskAttachment(disk=types.Disk(provisioned_size=DISK_SIZE))
        )
        while True:
            time.sleep(5)
            disk = disk_service.get()
            if disk.status == types.DiskStatus.OK:
                break

    # Network Configuration
    profiles_service = connection.system_service().vnic_profiles_service()  # type: VnicProfilesService

    profile = None
    for profile_item in profiles_service.list():
        if profile_item.name == NETWORK_NAME:
            profile = profile_item
            break
    if not profile:
        raise ProfilesServiceError('Unable to find profile {}, please check the name'.format(NETWORK_NAME))

    nics_service = vm_service.nics_service()
    nics_service.add(
        types.Nic(
            name='{}_nic'.format(VM_NAME),
            vnic_profile=types.VnicProfile(
                id=profile.id,
            ),
        ),
    )

    # VM Configuration
    vm_service.start(
        use_cloud_init=True,
        vm=types.Vm(
            initialization=types.Initialization(
                authorized_ssh_keys=SSH_KEY,
                nic_configurations=[
                    types.NicConfiguration(
                        boot_protocol=types.BootProtocol.STATIC,
                        on_boot=True,
                        name='eth0',
                        ip=types.Ip(
                            address=STATIC_IP,
                            gateway=GATEWAY,
                            netmask=NETMASK
                        )
                    )
                ],
                dns_search=DNS_SEARCH_PATH,
                dns_servers=DNS_SERVERS,
                host_name=HOSTNAME,
                user_name=VM_USERNAME
            )
        )
    )

    while vm.status != types.VmStatus.UP:
        time.sleep(5)
        vm = vm_service.get()

    # Making sure vm is up with proper IP
    ip = None
    limit = 10
    while limit > 0:
        limit -= 1
        time.sleep(5)
        rep_dev = connection.follow_link(vm.reported_devices)
        for reported_device in rep_dev:
            for dev_ip in reported_device.ips:
                if dev_ip.address == STATIC_IP:
                    limit = -1
    if not limit:
        raise ValueError('Something wrong with VM configuration, unable to get IP address of a VM')
