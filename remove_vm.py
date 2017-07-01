#!/usr/bin/python
import logging
import ovirtsdk4 as sdk
import ovirtsdk4.types as types
import time

from ovirtsdk4.services import VmsService, VmService

# API Settings

API_URL = 'https://example.com/ovirt-engine/api'
USERNAME = 'admin@internal'
PASSWORD = 'redhat123'
DEBUG = True

# Inputs
VM_NAME = 'testing'

logging.basicConfig(level=logging.DEBUG)

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

    vms_service = connection.system_service().vms_service()  # type: VmsService
    vms_list = vms_service.list(search=VM_NAME)
    if not vms_list:
        exit(0)

    if len(vms_list) > 1:
        raise ValueError('Found more than 1 VM to delete')

    vm_service = vms_service.service(vms_list[0].id)  # type: VmService
    vm = vm_service.get()
    if vm.status not in [types.VmStatus.DOWN, types.VmStatus.POWERING_DOWN]:
        vm_service.stop()

    while vm.status != types.VmStatus.DOWN:
        time.sleep(5)
        vm = vm_service.get()

    vm_service.remove()
