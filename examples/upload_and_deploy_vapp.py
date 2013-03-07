#!/usr/bin/env python

from vcloudtools.api import VCloudAPIClient, vcd_connection
from vcloudtools.ova import OVA
import sys
import os

VCDURL = 'https://172.16.222.141/api'
VCDUSER = 'admin@eng'
VCDPASS = 'vmware'
ORG = 'eng'
CATALOG = 'engcat'
VDC = 'engvdc'
OVAFILE = '{}/Downloads/DS2Web-SLESVMWSP2-11132012.ova'.format(os.environ['HOME'])
TEMPLATE_NAME = 'ds2web'
TEMPLATE_DESC = 'DS2Web-SLESVMWSP2-11132012'
VAPP_NAME = 'ds2webtest'

if __name__ == '__main__':


    with vcd_connection(VCDURL, VCDUSER, VCDPASS) as vcd:
        org = vcd.orgs[ORG]
        vdc = org.vdcs[VDC]

        try:
            vapptmpl = vdc.vapp_templates[TEMPLATE_NAME]
        except KeyError:
            vapptmpl = vdc.uploadVAppTemplate(TEMPLATE_NAME, TEMPLATE_DESC)
            
        if vapptmpl.status == 0:
            print vapptmpl.files
            with OVA(OVAFILE) as ova:
                #print ova.descriptor
                descriptor = vapptmpl.files['descriptor.ovf']
                if not descriptor.uploaded:
                    descriptor.upload(ova.descriptor)
                vapptmpl.wait_for_files()
                for name, afile in vapptmpl.files.items():
                    if afile.name == 'descriptor.ovf':
                        # special file uploaded above
                        continue
                    if not afile.uploaded:
                        afile.upload(ova.streamfile(name))

        vapptmpl.wait_for_status(8)

        print org.xml
        print org.catalogs

        # need to verify template is in catalog before we can deploy it
        try:
            catalog = org.catalogs[CATALOG]
        except KeyError:
            print 'creating catalog'
            catalog = org.create_catalog(CATALOG)
            catalog.wait_for_all_tasks()

        print catalog.xml

        try:
            item = catalog[TEMPLATE_NAME]
            print 'GOT ITEM'
        except KeyError:
            item = catalog.add_vapp_template(vapptmpl)

        print item.xml

        if 1:
            try:
                vapp = vdc.vapps[VAPP_NAME]
            except:
                pass
            else:
                if not vapp.undeployed:
                    vapp.undeploy().wait_for_task()
                    vapp.refresh()
                vapp.remove().wait_for_task()
                vdc.refresh()
                print 'tried remove'

        print vdc.vapps
        try:
            vapp = vdc.vapps[VAPP_NAME]
            print 'found vapp'
        except KeyError:
            #print vapptmpl.xml
            params = vapptmpl.instantiateVAppTemplateParams(VAPP_NAME)
            params.map_network('VM Network', vdc.networks['engint'], fencemode='bridged')
            params.powerOn = "false"
            #print params.xml
            vapp = vdc.instantiateVAppTemplate(params)

        print vapp.xml
        print "Waiting for vApp to be instantiated"
        if vapp.wait_for_all_tasks():
            vapp.refresh()
        else:
            raise Exception('All vApp tasks did not complete successfully')

        # vm name inside of template is named the same
        vm = vapp.vms[TEMPLATE_NAME]
        print vm.xml
        if 1:
            vm.undeploy().wait_for_task()
            custom = vm.customize()
            custom.AdminPasswordEnabled = "false"
            custom.ComputerName = VAPP_NAME
            print custom.xml
            task = custom.commit()
            print "waiting for customization task to complete"
            if task.wait_for_task():
                vapp.refresh()
                import time
                time.sleep(2)
                vm.refresh()
            else:
                raise Exception('Update customization task failed')

            print vm.xml
            task = vm.deploy()
            if task.wait_for_task():
                vapp.refresh()
            else:
                raise Exception('vm deploy task failed')

        print vapp.xml
        print 'vApp {} is online'.format(vapp.name)

#        if 1:
#            if vapp.powerOn().wait_for_task():
#            else:
#                raise Exception('Power on task failed')

#        print vapptmpl.status   # 8 appears to be gtg offline, need to find the mapping of these in java reference most likely
        # 4 is gtg powered on

