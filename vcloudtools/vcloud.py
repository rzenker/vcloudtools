from collections import namedtuple
import lxml.etree as etree
from lxml.builder import ElementMaker
import os.path
import time

from urlparse import urlparse

parser = etree.XMLParser(remove_blank_text=True)
Element = parser.makeelement

E = ElementMaker(namespace="http://www.vmware.com/vcloud/v1.5",
                 nsmap=dict(
                     xsi='http://www.w3.org/2001/XMLSchema-instance',
                     ovf='http://schemas.dmtf.org/ovf/envelope/1',
                 ),
                 makeelement=parser.makeelement)


def request(method, url, _raise=True, *args, **kwargs):

    from vcloudtools.api import CONNECTIONS
    urlobj = urlparse(url)
    baseurl = '{}://{}'.format(urlobj.scheme, urlobj.netloc)
    client = None
    for client in CONNECTIONS:
        if baseurl in client._baseurls:
            break

    if not client:
        raise Exception('active client not found for {}'.format(baseurl))

    return client.req(method, url, _raise=_raise, *args, **kwargs)



_Link = namedtuple('Link', 'type href rel name')
class OrigLink(_Link):
    def __new__(cls, type, href, rel, name=None):
        return super(cls, OrigLink).__new__(cls, type, href, rel, name)

#_Org = namedtuple('Org', 'type href name id full_name description links')
#class Org2(_Org):
#    def __new__(cls, type, href, name, id=None, full_name=None, description=None, links=None):
#        return super(cls, Org).__new__(cls, type, href, name, id, full_name, description, links)


#_OrgList = namedtuple('OrgList', 'orgs')
#class OrgList2(_OrgList):
#
#    def org_by_name(self, name):
#        for o in self.orgs:
#            if o.name == name:
#                return o
#        return None

def stripns(tag):
    return tag[tag.find('}')+1:]

def matchtags(name, single=False, inside=None):
    @property
    def inner(self):
        return getelements(self, name, single)
    return inner

def getelements(self, name, single=False, inside=None):
    #matched = VcdElement(self._client, 'GenericList')
    matched = []
    for item in self:
        if item.tag == name:
            matched.append(item)
    if single and len(matched) == 0:
        # allow to return None
        return None
    elif single and len(matched) == 1:
        return matched[0]
    elif single:
        raise ValueError('{} matched more than one element in message'.format(name))
    return matched

def expose_tag_text(tag):
    def get_inner_export_tag_text(self):
        child = self.one(tag)
        if child is None:
            return None
        return child.text

    def set_inner_export_tag_text(self, val):
        child = self.one(tag)
        if child is None:
            child = E(tag)
        child.text = val

    inner_export_tag_text = property(get_inner_export_tag_text, set_inner_export_tag_text)

    return inner_export_tag_text

def expose_attr(attr):
    def get_attr(self):
        return self.attrib.get(attr)

    def set_attr(self, val):
        self.attrib[attr] = val

    attrprop = property(get_attr, set_attr)

    return attrprop

def fetch2dict(subtype, key):
    typ = fulltype(subtype)
    @property
    def inner(self):
        matched = {}
        #print 'FINDALL'
        #print self.findall("*/[@type]".format(typ))
        #for child in self.findall(nstag('Link')):
        for child in self.iter():
            if child.get('type') == typ:
                res = request('get', child.href)
                top = fromstring(res.content)
                matched[top.attrib[key]] = top
        return matched
    return inner

def fetch2list(subtype):
    typ = fulltype(subtype)
    @property
    def inner(self):
        matched = []
        for child in self.iter():
            if child.attrib.get('type') == typ:
                res = request('get', child.href)
                top = fromstring(res.content)
                matched.append(top)
        return matched
    return inner

def fulltype(subtype):
    return 'application/vnd.vmware.{0}+xml'.format(subtype)

def nstag(tag):
    return '{{http://www.vmware.com/vcloud/v1.5}}{}'.format(tag)

def ovftag(tag):
    return '{{http://schemas.dmtf.org/ovf/envelope/1}}{}'.format(tag)

def fromstring(s):
    return etree.fromstring(s, parser)

def returnchild(key, forceload=False):
    def inner(self, value):
        for child in self.iter():
            if child.attrib.get(key) == value:
                if forceload or len(child) == 0:
                    return fromstring(request('get', child.href).content)
                else:
                    return child
        dict()[value]
    return inner

class VcdElement(etree.ElementBase):

    type = expose_attr('type')

    def _setattrs(self, attrs):
        for key, value in attrs.items():
            setattr(self, key, value)

    def refresh(self, usecache=False):
        if self.href:
            res = request('get', self.href)
            new = fromstring(res.content)
            self.clear()
            self.text = new.text
            self.tail = new.tail
            for attr, val in new.items():
                self.set(attr, val)
            for child in new:
                self.append(child)
            return True
        return False

    href = expose_attr('href')

    def replace_child(self, tag, newchild):
        for child in self:
            if child.tag == tag:
                self.remove(child)
        self.append(newchild)

    @property
    def xml(self):
        return etree.tostring(self, pretty_print=True)

    def one(self, tag):
        children = self.all(tag)
        if len(children) > 1:
            raise ValueError('more then one element found for {}'.format(tag))
        elif len(children) == 1:
            return children[0]

    def all(self, tag, local=False):
        children = []
        if local:
            src = self
        else:
            src = self.iter()
        for child in src:
            if child.tag == tag:
                children.append(child)
        return children

    @property
    def links_by_type(self):
        lnks = {}
        for link in self.all(nstag('Link')):
            if link.type is None:
                continue
            # dups can happen with common links, so you only get the first one in this dict
            if link.type in lnks:
                continue
                #raise ValueError('Duplicate link type {} found.'.format(link.type))
            lnks[link.attrib['type']] = link
        return lnks

    @property
    def links_by_rel(self):
        lnks = {}
        for link in self.links:
            # dups can happen with common links, so you only get the first one in this dict
            if link.rel in lnks:
                continue
                #raise ValueError('Duplicate link rel {} found.'.format(link.rel))
            lnks[link.rel] = link
        return lnks

    @property
    def links(self):
        lnks = []
        for link in self.all(nstag('Link'), local=True):
            lnks.append(link)
        return lnks

    tasks = fetch2list('vcloud.task')

    def wait_for_all_tasks(self):
        allgood = True
        for task in self.tasks:
            print '{} is {}'.format(task.get('operationName'), task.status)
            if not task.wait_for_task():
                allgood = False
        return allgood


class Task(VcdElement):

    status = expose_attr('status')
    progress = expose_tag_text(nstag('Progress'))

    def wait_for_task(self):
        while 1:
            if self.status == 'success':
                return True
            elif self.status != 'running':
                return False
            self.refresh()
            time.sleep(1)


class OrgList(VcdElement):
    __getitem__ = returnchild('name')

class Link(VcdElement):
    rel = expose_attr('rel')

    def __unicode__(self):
        if hasattr(self, 'type'):
            typ = self.type
        else:
            typ = None
        return "Link(type='{}', href='{}')".format(typ, self.href)


class CatalogItem(VcdElement):

    name = expose_attr('name')
    description = expose_tag_text('Description')

    @property
    def entity(self):
        ent = self.one(nstag('Entity'))
        res = request('get', ent.href)
        return fromstring(res.content)


class Catalog(VcdElement):

    catalog_items = fetch2dict('vcloud.catalogItem', key='name')
    __getitem__ = returnchild('name')

    def add_vapp_template(self, vapptmpl):
        typ = fulltype('vcloud.catalogItem')
        link = self.links_by_type[typ]
        item = E('CatalogItem', name=vapptmpl.name)
        desc = E('Description')
        desc.text = vapptmpl.description
        item.append(desc)
        ent = E('Entity')
        ent.set('href', vapptmpl.href)
        item.append(ent)
        res = request('post', link.href, data=item.xml)
        print "ADD"
        print res.content
        return fromstring(res.content)

class Org(VcdElement):

    catalogs = fetch2dict('vcloud.catalog', key='name')
    vdcs = fetch2dict('vcloud.vdc', key='name')

    def create_catalog(self, name, desc=""):
        typ = fulltype('admin.catalog')
        print self.links_by_type
        link = self.links_by_type[typ]
        catalog = E('AdminCatalog')
        catalog.set('name', name)
        catdesc = E('Description')
        catdesc.text = desc
        catalog.append(catdesc)
        print catalog.xml
        res = request('post', link.href, data=catalog.xml)
        return fromstring(res.content)


upload_vapp_xml = """
<UploadVAppTemplateParams
 name=""
 xmlns="http://www.vmware.com/vcloud/v1.5"
 xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1">
 <Description></Description>
</UploadVAppTemplateParams>
"""


class Vdc(VcdElement):

    vapp_templates = fetch2dict('vcloud.vAppTemplate', key='name')
    vapps = fetch2dict('vcloud.vApp', key='name')
    networks = fetch2dict('vcloud.network', key='name')

    def uploadVAppTemplate(self, name, desc):
        "returns a new vapp instance that allows you to upload"
        typ = fulltype('vcloud.uploadVAppTemplateParams')
        link = self.links_by_type[typ]
        params = fromstring(upload_vapp_xml)
        params.set('name', name)
        params[0].text = desc
        print params.xml
        res = request('post', link.href, _raise=True, headers={'Content-Type' : typ}, data=params.xml)
        print res.content
        return fromstring(res.content)

    def instantiateVAppTemplate(self, params):
        subtype = 'vcloud.instantiateVAppTemplateParams'
        res = request('post', self.links_by_type[fulltype(subtype)].href, data=params.xml)
        return fromstring(res.content)

instantiate_vapp_params_xml = """
<InstantiateVAppTemplateParams xmlns="http://www.vmware.com/vcloud/v1.5"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1"
    name="Linux FTP server" deploy="true" powerOn="true">
  <Description>Example FTP Server</Description>
  <InstantiationParams>
    <NetworkConfigSection>
      <ovf:Info>Configuration parameters for logical networks</ovf:Info>
    </NetworkConfigSection>
  </InstantiationParams>
  <Source href="https://vcloud.example.com/api/vAppTemplate/vappTemplate-111"/>
  <AllEULAsAccepted>true</AllEULAsAccepted>
</InstantiateVAppTemplateParams>
"""
network_config_xml = """
<NetworkConfig networkName="vAppNetwork" xmlns="http://www.vmware.com/vcloud/v1.5">
  <Configuration>
    <ParentNetwork href="https://vcloud.example.com/api/network/54"/>
    <FenceMode>bridged</FenceMode>
  </Configuration>
</NetworkConfig>
"""

class NetworkConfig(VcdElement):

    @property
    def parent(self):
        pass

    @parent.setter
    def parent(self, val):
        par = self.one(nstag('ParentNetwork'))
        par.href = val.href

    @property
    def fencemode(self):
        pass

    @fencemode.setter
    def fencemode(self, val):
        fm = self.one(nstag('FenceMode'))
        fm.text = val

    @property
    def name(self):
        return self.attrib['networkName']

    @classmethod
    def new(cls, name):
        top = fromstring(network_config_xml)
        top.attrib['networkName'] = name
        return top

#    type="application/vnd.vmware.vcloud.guestCustomizationSection+xml" href="" ovf:required="false">
guest_customization_xml = """
<GuestCustomizationSection xmlns="http://www.vmware.com/vcloud/v1.5"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1"
    ovf:required="false">
  <ovf:Info>Specifies Guest OS Customization Settings</ovf:Info>
  <Enabled>true</Enabled>
  <ChangeSid>false</ChangeSid>
  <JoinDomainEnabled>false</JoinDomainEnabled>
  <UseOrgSettings>false</UseOrgSettings>
  <AdminPasswordEnabled>true</AdminPasswordEnabled>
  <AdminPasswordAuto>true</AdminPasswordAuto>
  <ResetPasswordRequired>false</ResetPasswordRequired>
  <ComputerName>DS2Web-SLES-001</ComputerName>
</GuestCustomizationSection>
"""
#  <VirtualMachineId>2ab1fa37-1b1b-4d02-8db2-575acce01bb2</VirtualMachineId>

class GuestCustomizationSection(VcdElement):

    Enabled = expose_tag_text(nstag('Enabled'))
    ChangeSid = expose_tag_text(nstag('ChangeSid'))
    JoinDomainEnabled = expose_tag_text(nstag('JoinDomainEnabled'))
    AdminPasswordEnabled = expose_tag_text(nstag('AdminPasswordEnabled'))
    AdminPasswordAuto = expose_tag_text(nstag('AdminPasswordAuto'))
    ResetPasswordRequired = expose_tag_text(nstag('ResetPasswordRequired'))
    ComputerName = expose_tag_text(nstag('ComputerName'))
    CustomizationScript = expose_tag_text(nstag('CustomizationScript'))

    @classmethod
    def new(self):
        top = fromstring(guest_customization_xml)
        return top

    def commit(self):
        res = request('put', self.href, headers={'Content-type' : self.type}, data=self.xml)
        return fromstring(res.content)

class ProductSectionList(VcdElement):
    pass

class InstantiateVAppTemplateParams(VcdElement):

    powerOn = expose_attr('powerOn')

    @property
    def networks(self):
        nets = {}
        for child in self.iter():
            if child.tag == nstag('NetworkConfig'):
                nets[child.name] = child
        return nets

    def map_network(self, src, vcdnet, fencemode='bridged'):
        self.networks[src].parent = vcdnet
        self.networks[src].fencemode = fencemode

    @property
    def name(self):
        return self.attrib.get('name')

    @name.setter
    def name(self, val):
        self.attrib['name'] = val

    @classmethod
    def new(cls, name):
        top = fromstring(instantiate_vapp_params_xml)
        top.name = name
        #top = E("InstantiateVAppTemplateParams", name=name, deploy='true', powerOn='true')
        #top.append(E('Description'))
        return top

class VApp(VcdElement):

    vms = fetch2dict('vcloud.vm', key='name')
    name = expose_attr('name')

    def deploy(self):
        link = self.links_by_rel['deploy']
        res = request('post', link.href)
        return fromstring(res.content)

    def undeploy(self):
        link = self.links_by_rel['undeploy']
        res = request('post', link.href)
        return fromstring(res.content)

    def powerOn(self):
        link = self.links_by_rel['power:powerOn']
        res = request('post', link.href)
        return fromstring(res.content)

    def powerOff(self):
        link = self.links_by_rel['power:powerOff']
        res = request('post', link.href)
        return fromstring(res.content)

    def remove(self):
        link = self.links_by_rel['remove']
        res = request('delete', link.href)
        return fromstring(res.content)

class Vm(VApp):


    def customize(self):
        top = self.one(nstag('GuestCustomizationSection'))
        instantparams = self.one(nstag('InstantiationParams'))
        if top is None:
            top = GuestCustomizationSection.new()
            instantparams.append(top)
        return top


class VAppTemplate(VcdElement):

    files = fetch2dict_by_tag(nstag('File'), key='name')
    status = expose_attr('status')
    name = expose_attr('name')
    description = expose_tag_text('Description')


    @property
    def networks(self):
        nets = []
        for child in self.iter():
            if child.tag == ovftag('Network'):
                nets.append(child.attrib[ovftag('name')])
        return nets

    def instantiateVAppTemplateParams(self, name):
        params = InstantiateVAppTemplateParams.new(name)
        params.find(nstag('Source')).set('href', self.href)
        print self.networks
        #print self.xml
        #print self.find(nstag('NetworkConfig'))
        #netconfsec = params.find('.//{}'.format(nstag('NetworkConfigSection')))
        #netconfsec.replace_child('NetworkConfig', self.find(nstag('NetworkConfig')))
        netconfsec = params.one(nstag('NetworkConfigSection'))
        for netname in self.networks:
            netconfsec.append(NetworkConfig.new(netname))
        return params

    def wait_for_status(self, code):
        code = str(code)
        if self.status == code: return True
        while 1:
            self.refresh()
            if self.status == code:
                return True
            time.sleep(1)

    def wait_for_files(self):
        if len(self.files) > 1 or self.status != 0: return True
        while 1:
            self.refresh()
            if len(self.files) > 1:
                # descriptor is uploaded and processed
                return True
            else:
                time.sleep(1)


class File(VcdElement):

    name = expose_attr('name')
    size = expose_attr('size')
    bytesTransferred = expose_attr('bytesTransferred')

    @property
    def uploaded(self):
        return self.size == self.bytesTransferred

    def upload(self, stream_or_string):
        link = self.links_by_rel['upload:default']
        print stream_or_string
        if isinstance(stream_or_string, basestring):
            size = len(stream_or_string)
        elif hasattr(stream_or_string, "read"):
            # duck check for stream
            print dir(stream_or_string)
            stream_or_string.seek(0, 2)
            size = stream_or_string.tell()
            stream_or_string.seek(0, 0)
        res = request('put', link.href, data=stream_or_string, headers={'Content-length':str(size)})
        print res.content
        #return fromstring(res.content)

fallback = etree.ElementDefaultClassLookup(element=VcdElement)
lookup = etree.ElementNamespaceClassLookup(fallback)
parser.set_element_class_lookup(lookup)

namespace = lookup.get_namespace('http://www.vmware.com/vcloud/v1.5')
import inspect
for k,v in vars().items():
    if inspect.isclass(v) and issubclass(v, VcdElement):
            namespace[k] = v
