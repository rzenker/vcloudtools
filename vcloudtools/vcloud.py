import logging
log = logging.getLogger(__name__)

from collections import namedtuple
import lxml.etree as etree
from lxml.builder import ElementMaker
import os.path
import time

from urlparse import urlparse

from vcloudtools.connections import request

parser = etree.XMLParser(remove_blank_text=True)
Element = parser.makeelement

E = ElementMaker(namespace="http://www.vmware.com/vcloud/v1.5",
                 nsmap=dict(
                     xsi='http://www.w3.org/2001/XMLSchema-instance',
                     ovf='http://schemas.dmtf.org/ovf/envelope/1',
                 ),
                 makeelement=parser.makeelement)


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

def expose_tag_text(*tags, **kwargs):
    """
    return property to expose direct access to a child tag's text
        *tags allows the default to be created at the right depth
    """

    default = kwargs.get('default')
    insert = kwargs.get('insert')
    commit_on_set = kwargs.get('commit_on_set', False)

    def get_element(self):
        cur = self
        for tag in tags:
            element = cur.one(tag)
            cur = element
        return element

    def set_inner_expose_tag_text(self, val):
        child = self.one(tags[-1])
        if child is None:
            child = E(tags[-1])
            last_element = self
            for tag in tags[0:-1]:
                element = self.one(tag)
                if element is None:
                    element = E(tag)
                    last_element.append(element)
                    last_element = element
            if insert:
                last_element.insert(insert, child)
            else:
                last_element.append(child)
        child.text = val
        if commit_on_set:
            self.commit(wait_for_task=True)

    def get_inner_expose_tag_text(self):
        #child = self.one(tags[-1])
        child = get_element(self)
        if child is None:
            if default is not None:
                set_inner_expose_tag_text(self, default)
            return default
        return child.text


    inner_expose_tag_text = property(get_inner_expose_tag_text, set_inner_expose_tag_text)
#    if default:
#        inner_expose_tag_text.hasdefault = True

    return inner_expose_tag_text

def expose_attr(attr, default=None, ignorens=False):
    """
    return a property to expose direct access to a tag attribute

    :param attr: name of attribute
    :param default: optional default value to set attr to on access
    :param ignorens: optionally ignore namespace prefix during compare
    :returns: property to get/set attribute
    """

    def get_attr_key(self, attr):
        for key in self.attrib:
            if key == attr:
                return key
            if ignorens and stripns(key) == attr:
                return key
        return attr

    def set_inner_attr(self, val):
        key = get_attr_key(self, attr)
        self.set(key, val)

    def get_inner_attr(self):
        key = get_attr_key(self, attr)
        if key is None:
            return None
        val = self.get(key, default)
        if val == default and default is not None:
            # set it just in case so it's stored in the xml tree
            set_inner_attr(self, val)
        return val


    attrprop = property(get_inner_attr, set_inner_attr)
#    if default:
#        print dir(attrprop)
#        setattr(attrprop, 'hasdefault', True)
#        attrprop.hasdefault = True

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

def fetch2list_by_tag(tag):
    @property
    def inner(self):
        matched = []
        for child in self.iter():
            if child.tag == tag:
                child.refresh()
                matched.append(child)
        return matched
    return inner

def fetch2dict_by_tag(tag, key):
    @property
    def inner(self):
        matched = {}
        for child in self.iter():
            if child.tag == tag:
                if child.href:
                    res = request('get', child.href)
                    top = fromstring(res.content)
                else:
                    top = child
                matched[child.get(key)] = top
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
                child.refresh()
                return child
#                if (forceload or len(child) == 0) and child.href:
#                    return fromstring(request('get', child.href).content)
#                else:
#                    return child
        dict()[value]
    return inner

class VcdElement(etree.ElementBase):


    type = expose_attr('type', ignorens=True)
    name = expose_attr('name')

    @property
    def baseurl(self):
        urlobj = urlparse(self.href)
        baseurl = '{}://{}'.format(urlobj.scheme, urlobj.netloc)
        return baseurl

    @property
    def metadata(self):
        try:
            mdlink = self.links_by_type[fulltype('vcloud.metadata')]
        except KeyError:
            # element has no metadata capability
            return None
        return fromstring(request('get', mdlink.href).content)

    def _init_failtest(self):
        print 'ENTERING _init'
        for itemname in dir(self):
            item = getattr(self, itemname)
            print itemname, item.__class__
            if isinstance(item, property):
                print 'PROPERTY'
                print item

    def query(self, **params):
        params.setdefault('format', 'records')
        query = "{}/api/query".format(self.baseurl)
        headers = {'Accept' : 'application/*+xml;version=5.1' }
        res = request('get', query, params=params, headers=headers)
        return res

    def refresh(self, usecache=False):
        if self.href:
            res = request('get', self.href)
            new = fromstring(res.content)
            self.clear()
            self.text = new.text
            self.tail = new.tail
            self.tag = new.tag
            for attr, val in new.items():
                self.set(attr, val)
            for child in new:
                self.append(child)
            return True
        return False

    href = expose_attr('href', ignorens=True)

    def commit(self, wait_for_task=False):
        if self.href is None:
            # noop
            return None
        res = request('put', self.href, headers={'Content-type' : self.type}, data=self.xml)
        task = fromstring(res.content)
        if wait_for_task:
            task.wait_for_task()
        return task

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
            log.info('{} is {}'.format(task.get('operationName'), task.status))
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
            time.sleep(5)


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
        return fromstring(res.content)

class Org(VcdElement):

    catalogs = fetch2dict('vcloud.catalog', key='name')
    vdcs = fetch2dict('vcloud.vdc', key='name')

    def create_catalog(self, name, desc=""):
        typ = fulltype('admin.catalog')
        link = self.links_by_type[typ]
        catalog = E('AdminCatalog')
        catalog.set('name', name)
        catdesc = E('Description')
        catdesc.text = desc
        catalog.append(catdesc)
        res = request('post', link.href, data=catalog.xml)
        return fromstring(res.content)



add_user_xml = """
<User
   xmlns="http://www.vmware.com/vcloud/v1.5"
   name="" >
   <FullName></FullName>
   <EmailAddress>user@example.com</EmailAddress>
   <IsEnabled>true</IsEnabled>
   <Role
      href="https://vcloud.example.com/api/admin/role/105" />
   <Password></Password>
   <GroupReferences />
</User>
"""

add_vdc_xml = """
<CreateVdcParams
   name=""
   xmlns="http://www.vmware.com/vcloud/v1.5">
   <Description></Description>
   <AllocationModel>AllocationVApp</AllocationModel>
   <ComputeCapacity>
      <Cpu>
         <Units>MHz</Units>
         <Allocated>0</Allocated>
         <Limit>0</Limit>
      </Cpu>
      <Memory>
         <Units>MB</Units>
         <Allocated>0</Allocated>
         <Limit>0</Limit>
      </Memory>
   </ComputeCapacity>
   <NicQuota>0</NicQuota>
   <NetworkQuota>1000</NetworkQuota>
   <VdcStorageProfile>
      <Enabled>true</Enabled>
      <Units>MB</Units>
      <Limit>0</Limit>
      <Default>true</Default>
      <ProviderVdcStorageProfile href="" />
   </VdcStorageProfile>
   <ResourceGuaranteedMemory>0</ResourceGuaranteedMemory>
   <ResourceGuaranteedCpu>0</ResourceGuaranteedCpu>
   <VCpuInMhz>1024</VCpuInMhz>
   <IsThinProvision>false</IsThinProvision>
   <NetworkPoolReference href=""/>
   <ProviderVdcReference name="" href="" />
   <UsesFastProvisioning>false</UsesFastProvisioning>
</CreateVdcParams>
"""

class AdminOrg(VcdElement):
    "Admin Org Object"

    users = fetch2dict_by_tag(nstag('UserReference'), key='name')
    vdcs = fetch2dict_by_tag(nstag('Vdc'), key='name')
    networks = fetch2dict_by_tag(nstag('Network'), key='name')

    def add_vdc(self, name, pvdc, storage_profile, network_pool):
        typ = fulltype('admin.createVdcParams')
        link = self.links_by_type[typ]
        vdc = fromstring(add_vdc_xml)
        vdc.set('name', name)
        pvdcref = vdc.find(nstag('ProviderVdcReference'))
        pvdcref.set('name', pvdc.name)
        pvdcref.set('href', pvdc.href)
        netpoolref = vdc.find(nstag('NetworkPoolReference'))
        netpoolref.set('name', network_pool.name)
        netpoolref.set('href', network_pool.href)
        pvdcspref = vdc.one(nstag('ProviderVdcStorageProfile'))
        pvdcspref.set('href', storage_profile.href)
        print vdc.xml
        res = request('post', link.href, data=vdc.xml)
        return fromstring(res.content)

    def add_user(self, username, password, role, full_name=None, email=None):
        typ = fulltype('admin.user')
        link = self.links_by_type[typ]
        user = fromstring(add_user_xml)
        user.set('name', username)
        user.find(nstag('Password')).text = password
        user.find(nstag('Role')).href = role.href
        if full_name is not None:
            user.find(nstag('FullName')).text = full_name
        if email is not None:
            user.find(nstag('EmailAddress')).text = email
        res = request('post', link.href, data=user.xml)
        return fromstring(res.content)

add_org_xml = """
<AdminOrg
   xmlns="http://www.vmware.com/vcloud/v1.5"
   name=""
   type="application/vnd.vmware.admin.organization+xml">
   <Description></Description>
   <FullName></FullName>
   <IsEnabled>true</IsEnabled>
   <Settings>
      <OrgGeneralSettings>
         <CanPublishCatalogs>true</CanPublishCatalogs>
         <DeployedVMQuota>0</DeployedVMQuota>
         <StoredVmQuota>0</StoredVmQuota>
         <UseServerBootSequence>false</UseServerBootSequence>
         <DelayAfterPowerOnSeconds>0</DelayAfterPowerOnSeconds>
      </OrgGeneralSettings>
      <OrgLdapSettings>
         <OrgLdapMode>SYSTEM</OrgLdapMode>
         <CustomUsersOu />
      </OrgLdapSettings>
      <OrgEmailSettings>
         <IsDefaultSmtpServer>true</IsDefaultSmtpServer>
         <IsDefaultOrgEmail>true</IsDefaultOrgEmail>
         <FromEmailAddress />
         <DefaultSubjectPrefix />
         <IsAlertEmailToAllAdmins>true</IsAlertEmailToAllAdmins>
        </OrgEmailSettings>
   </Settings>
</AdminOrg>
"""

class VCloud(VcdElement):
    "Main Admin Object"

    orgs = fetch2dict_by_tag(nstag('OrganizationReference'), key='name')
    roles = fetch2dict_by_tag(nstag('RoleReference'), key='name')
    networks = fetch2dict_by_tag(nstag('Network'), key='name')
    pvdcs = fetch2dict_by_tag(nstag('ProviderVdcReference'), key='name')

    def add_organization(self, name, full_name, desc=None):
        typ = fulltype('admin.organization')
        link = self.links_by_type[typ]
        org = fromstring(add_org_xml)
        org.set('name', name)
        org.find(nstag('FullName')).text = full_name
        if desc is not None:
            org.find(nstag('Description')).text = desc
        res = request('post', link.href, data=org.xml)
        return fromstring(res.content)


    @property
    def edge_gateways(self):
        res = self.query(type='edgeGateway')
        return fromstring(res.content).edge_gateway_records

    @property
    def storage_profiles(self):
        res = self.query(type='providerVdcStorageProfile')
        return fromstring(res.content).storage_profile_records

    @property
    def network_pools(self):
        res = self.query(type='networkPool')
        return fromstring(res.content).network_pool_records

    @property
    def vmw_external_networks(self):
        res = self.query(type='vMWExternalNetwork')
        print res.content
        return fromstring(res.content).network_pool_records

add_vse_xml = """
<EdgeGateway
   name=""
   xmlns="http://www.vmware.com/vcloud/v1.5">
   <Description></Description>
   <Configuration>
      <GatewayBackingConfig>compact</GatewayBackingConfig>
      <GatewayInterfaces>
      </GatewayInterfaces>
      <HaEnabled>false</HaEnabled>
      <UseDefaultRouteForDnsRelay>false</UseDefaultRouteForDnsRelay>
   </Configuration>
</EdgeGateway>
"""

vse_gw_xml = """
 <GatewayInterface xmlns="http://www.vmware.com/vcloud/v1.5">
    <Name></Name>
    <DisplayName></DisplayName>
    <Network href="" />
    <InterfaceType>uplink</InterfaceType>
    <SubnetParticipation>
       <Gateway></Gateway>
       <Netmask></Netmask>
       <IpAddress></IpAddress>
    </SubnetParticipation>
    <UseForDefaultRoute>true</UseForDefaultRoute>
 </GatewayInterface>
"""

org_net_xml = """
<OrgVdcNetwork
   name=""
   xmlns="http://www.vmware.com/vcloud/v1.5">
   <Description></Description>
   <Configuration>
      <IpScopes>
         <IpScope>
            <IsInherited>false</IsInherited>
            <Gateway></Gateway>
            <Netmask></Netmask>
            <Dns1>8.8.8.8</Dns1>
            <Dns2>8.8.4.4</Dns2>
            <IsEnabled>true</IsEnabled>
            <IpRanges>
               <IpRange>
                  <StartAddress></StartAddress>
                  <EndAddress></EndAddress>
               </IpRange>
            </IpRanges>
         </IpScope>
      </IpScopes>
      <FenceMode>natRouted</FenceMode>
   </Configuration>
   <EdgeGateway href="" />
   <IsShared>false</IsShared>
</OrgVdcNetwork>
"""


class AdminVdc(VcdElement):
    storage_profiles = fetch2dict_by_tag(nstag('VdcStorageProfile'), key='name')
    resource_guaranteed_memory = expose_tag_text(nstag('ResourceGuaranteedMemory'))
    resource_guaranteed_cpu = expose_tag_text(nstag('ResourceGuaranteedCpu'))
    vcpu_in_mhz = expose_tag_text(nstag('VCpuInMhz'))

    def add_edge_gateway(self, name, extnet): #, orgnet):
        href = "{}/edgeGateways".format(self.href)
        vse = fromstring(add_vse_xml)
        vse.set('name', name)
        gwintfs = vse.one(nstag('GatewayInterfaces'))

        extintf = fromstring(vse_gw_xml)
        print extintf.xml
        extintf.one(nstag('InterfaceType')).text = 'uplink'
        extintf.one(nstag('Name')).text = extnet.name
        extintf.one(nstag('DisplayName')).text = extnet.name
        extintf.one(nstag('Gateway')).text = extnet.start_address
        extintf.one(nstag('Netmask')).text = extnet.netmask
        extintf.one(nstag('IpAddress')).text = extnet.start_address
        extintf.one(nstag('Network')).set('href', extnet.href)

#        orgintf = fromstring(vse_gw_xml)
#        orgintf.one(nstag('InterfaceType')).text = 'internal'
#        orgintf.one(nstag('Name')).text = orgnet.name
#        orgintf.one(nstag('DisplayName')).text = orgnet.name
#        orgintf.one(nstag('Gateway')).text = orgnet.start_address
#        orgintf.one(nstag('Netmask')).text = orgnet.netmask
#        orgintf.one(nstag('IpAddress')).text = orgnet.start_address
#        orgintf.one(nstag('UseForDefaultRoute')).text = "false"
#        gwinfts.append(orgintf)

        gwintfs.append(extintf)
        print vse.xml
        res = request('post', href, data=vse.xml)
        return fromstring(res.content)


    def add_org_network(self, name, ip, netmask, start_address, end_address, edge):
        typ = fulltype('vcloud.orgVdcNetwork')
        link = self.links_by_type[typ]
        orgnet = fromstring(org_net_xml)
        orgnet.set('name', name)
        orgnet.one(nstag('Gateway')).text = ip
        orgnet.one(nstag('Netmask')).text = netmask
        orgnet.one(nstag('StartAddress')).text = start_address
        orgnet.one(nstag('EndAddress')).text = end_address
        orgnet.one(nstag('EdgeGateway')).set('href', edge.href)
        print orgnet.xml
        res = request('post', link.href, data=orgnet.xml)
        return fromstring(res.content)

    def query(self, **params):
        params.setdefault('format', 'records')
        query = "{}/api/query".format(self.baseurl)
        headers = {'Accept' : 'application/*+xml;version=5.1' }
        res = request('get', query, params=params, headers=headers)
        return res

    @property
    def edge_gateways(self):
        res = self.query(type='edgeGateway') #, filter='vdc=={}'.format(self.href))
        return fromstring(res.content).edge_gateway_records

vse_services_xml = """
<EdgeGatewayServiceConfiguration
   xmlns="http://www.vmware.com/vcloud/v1.5">
   <FirewallService>
      <IsEnabled>true</IsEnabled>
      <DefaultAction>allow</DefaultAction>
      <LogDefaultAction>false</LogDefaultAction>
   </FirewallService>
      <NatService>
        <IsEnabled>true</IsEnabled>
        <NatRule>
          <RuleType>SNAT</RuleType>
          <IsEnabled>true</IsEnabled>
          <Id>65537</Id>
          <GatewayNatRule>
            <Interface type="application/vnd.vmware.admin.network+xml" name="" href=""/>
            <OriginalIp></OriginalIp>
            <TranslatedIp></TranslatedIp>
          </GatewayNatRule>
        </NatRule>
      </NatService>
      <GatewayIpsecVpnService>
        <IsEnabled>true</IsEnabled>
        <Tunnel>
          <Name>intp3v4</Name>
          <Description/>
          <IpsecVpnThirdPartyPeer>
            <PeerId>64.20.105.30</PeerId>
          </IpsecVpnThirdPartyPeer>
          <PeerIpAddress>64.20.105.30</PeerIpAddress>
          <PeerId>64.20.105.30</PeerId>
          <LocalIpAddress>192.240.154.152</LocalIpAddress>
          <LocalId></LocalId>
          <LocalSubnet>
            <Name></Name>
            <Gateway></Gateway>
            <Netmask></Netmask>
          </LocalSubnet>
          <PeerSubnet>
            <Name>192.168.139.0/24</Name>
            <Gateway>192.168.139.0</Gateway>
            <Netmask>255.255.255.0</Netmask>
          </PeerSubnet>
          <SharedSecret></SharedSecret>
          <SharedSecretEncrypted>false</SharedSecretEncrypted>
          <EncryptionProtocol>AES256</EncryptionProtocol>
          <Mtu>1500</Mtu>
          <IsEnabled>true</IsEnabled>
          <IsOperational>true</IsOperational>
        </Tunnel>
      </GatewayIpsecVpnService>
</EdgeGatewayServiceConfiguration>
"""

add_tunnel_intpod_xml = """
<Tunnel xmlns="http://www.vmware.com/vcloud/v1.5">
  <Name></Name>
  <Description/>
  <IpsecVpnThirdPartyPeer>
    <PeerId></PeerId>
  </IpsecVpnThirdPartyPeer>
  <PeerIpAddress></PeerIpAddress>
  <PeerId></PeerId>
  <LocalIpAddress>64.20.105.30</LocalIpAddress>
  <LocalId>64.20.105.30</LocalId>
  <LocalSubnet>
    <Name>Perf-org-routed</Name>
    <Gateway>192.168.139.1</Gateway>
    <Netmask>255.255.255.0</Netmask>
  </LocalSubnet>
  <PeerSubnet>
    <Name></Name>
    <Gateway></Gateway>
    <Netmask>255.255.255.0</Netmask>
  </PeerSubnet>
  <SharedSecret></SharedSecret>
  <SharedSecretEncrypted>false</SharedSecretEncrypted>
  <EncryptionProtocol>AES256</EncryptionProtocol>
  <Mtu>1500</Mtu>
  <IsEnabled>true</IsEnabled>
  <IsOperational>true</IsOperational>
</Tunnel>
"""
class EdgeGateway(VcdElement):
    "edge gateway"

    status = expose_attr('status')

    @property
    def tunnels(self):
        tuns = {}
        for tun in self.all(nstag('Tunnel')):
            name = tun.find(nstag('Name')).text
            tuns[name] = tun
        return tuns

    def add_tunnel_intpod(self, name, peer_ip, peer_network, secret):
        services = self.one(nstag('EdgeGatewayServiceConfiguration'))
        tun = fromstring(add_tunnel_intpod_xml)
        tun.find(nstag('Name')).text = name
        tun.find(nstag('SharedSecret')).text = secret
        for peer_id in tun.all(nstag('PeerId')):
            peer_id.text = peer_ip
        tun.one(nstag('PeerIpAddress')).text = peer_ip
        peersub = tun.one(nstag('PeerSubnet'))
        peersub.one(nstag('Name')).text = "{}/24".format(peer_network)
        peersub.one(nstag('Gateway')).text = peer_network

        services.one(nstag('GatewayIpsecVpnService')).append(tun)
        print services.xml
        return self.update_services(services)

    def update_services_perf(self, extnet, orgnet, vpn_peer_ip, orgcidr, vpn_secret):
        typ = fulltype('admin.edgeGatewayServiceConfiguration')
        link = self.links_by_type[typ]
        orgnet = fromstring(org_net_xml)

    def update_services(self, services):
        typ = fulltype('admin.edgeGatewayServiceConfiguration')
        link = self.links_by_type[typ]
        res = request('post', link.href, data=services.xml)
        return fromstring(res.content)


class SubAllocation(VcdElement):
    start_address = expose_tag_text(nstag('IpRanges'), nstag('IpRange'), nstag('StartAddress'))

    #end_address = expose_tag_text(nstag('IpRanges'), nstag('IpRange'), nstag('EndAddress'))

    @property
    def end_address(self):
        return self.one(nstag('EndAddress')) 

    @end_address.setter
    def end_address(self, val):
        endaddr = self.end_address
        if endaddr is None:
            endaddr = E('EndAddress')
            endaddr.text = val
            ipr = self.one(nstag('IpRange'))
            ipr.append(endaddr)
        else:
            endaddr.text = val

sub_alloc_xml = '<SubAllocation xmlns="http://www.vmware.com/vcloud/v1.5" />'
class ExternalNetwork(VcdElement):
    name = expose_attr('name')
    gateway = expose_tag_text(nstag('Gateway'))
    netmask = expose_tag_text(nstag('Netmask'))
    dns1 = expose_tag_text(nstag('Dns1'))
    dns2 = expose_tag_text(nstag('Dns2'))

    sub_allocations = fetch2list_by_tag(nstag('SubAllocation'))

    def add_sub_allocation(self, vse, start_address, end_address=None):
        #vmwextnet = self.vmwextnet
        vmwextnet = self
        suballocs = vmwextnet.one(nstag('SubAllocations'))
        suballoc = fromstring(sub_alloc_xml)
        edge = E('EdgeGateway', type=vse.type, name=vse.name, href=vse.href)
        suballoc.append(edge)
        suballoc.start_address = start_address
        if end_address:
            suballoc.end_address = end_address
        else:
            suballoc.end_address = start_address
        suballocs.append(suballoc)
        print vmwextnet.xml
        href = self.vmwextnet_href
        res = request('put', self.href, data=vmwextnet.xml)
        vmwextnetret = fromstring(res.content)
        task = vmwextnetret.one(nstag("Task"))
        return task

    @property
    def vmwextnet_href(self):
        return self.href.replace("network", "extension/externalnet")

    @property
    def vmwextnet(self):
        href = self.vmwextnet_href
        res = request('get', href)
        return fromstring(res.content)

    @property
    def start_address(self):
       return self.all(nstag('StartAddress'))[0].text

    @property
    def end_address(self):
       return self.all(nstag('EndAddress'))[0].text
    #start_address = expose_tag_text(nstag('IpScope'), nstag('IpRanges'), nstag('StartAddress'))
    #stop_address = expose_tag_text(nstag('IpScope'), nstag('IpRanges'), nstag('StopAddress'))

class OrgVdcNetwork(ExternalNetwork):
    pass

class QueryResultRecords(VcdElement):
    edge_gateway_records = fetch2dict_by_tag(nstag('EdgeGatewayRecord'), key='name')
    storage_profile_records = fetch2dict_by_tag(nstag('ProviderVdcStorageProfileRecord'), key='name')
    network_pool_records = fetch2dict_by_tag(nstag('NetworkPoolRecord'), key='name')

class ProviderVdc(VcdElement):
    name = expose_attr('name')
    networks = fetch2dict_by_tag(nstag('Network'), key='name')
    network_pools = fetch2dict_by_tag(nstag('NetworkPoolReference'), key='name')
    cpu_total = expose_tag_text(nstag('ComputeCapacity'), nstag('Cpu'), nstag('Total'))
    memory_total = expose_tag_text(nstag('ComputeCapacity'), nstag('Memory'), nstag('Total'))
    storage_total = expose_tag_text(nstag('StorageCapacity'), nstag('Total'))

    @property
    def storage_profiles(self):
        exthref = self.href.replace("providervdc", "extension/providervdc")
        #exthref = self.href
        res = request('get', "{}/availableStorageProfiles".format(exthref))
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

    @property
    def edge_gateways(self):
        res = self.query(type='edgeGateway') #, filter='vdc=={}'.format(self.href))
        return fromstring(res.content).edge_gateway_records

    def uploadVAppTemplate(self, name, desc):
        "returns a new vapp instance that allows you to upload"
        typ = fulltype('vcloud.uploadVAppTemplateParams')
        link = self.links_by_type[typ]
        params = fromstring(upload_vapp_xml)
        params.set('name', name)
        params[0].text = desc
        res = request('post', link.href, _raise=True, headers={'Content-Type' : typ}, data=params.xml)
        return fromstring(res.content)

    def instantiateVAppTemplate(self, params):
        subtype = 'vcloud.instantiateVAppTemplateParams'
        res = request('post', self.links_by_type[fulltype(subtype)].href, data=params.xml)
        return fromstring(res.content)

network_connection_xml = """
      <NetworkConnectionSection ovf:required="false">
        <ovf:Info>Specifies the available VM network connections</ovf:Info>
        <NetworkConnection network="SupportNet" needsCustomization="false">
          <NetworkConnectionIndex>0</NetworkConnectionIndex>
          <IpAddress>192.168.0.23</IpAddress>
          <IsConnected>false</IsConnected>
          <IpAddressAllocationMode>MANUAL</IpAddressAllocationMode>
        </NetworkConnection>
      </NetworkConnectionSection>
"""

class NetworkConnection(VcdElement):

    network = expose_attr('network')
    needsCustomization = expose_attr('needsCustomization', default='false')
    NetworkConnectionIndex = expose_tag_text(nstag('NetworkConnectionIndex'))
    IpAddress = expose_tag_text(nstag('IpAddress'), insert=1)
    IsConnected = expose_tag_text(nstag('IsConnected'), default='true')
    IpAddressAllocationMode = expose_tag_text(nstag('IpAddressAllocationMode'), default='DHCP')

    @classmethod
    def new(cls, name, index=0, needsCustomization='false'):
        net = E('NetworkConnection', network=name, needsCustomization=needsCustomization)
        net.NetworkConnectionIndex = str(index)
        # set the defaults for these attributes by calling them
        # order of elements appears to be important...
        net.IsConnected
        net.IpAddressAllocationMode
        return net

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

    fencemode = expose_tag_text(nstag('Configuration'), nstag('FenceMode'), default='bridged')

    @property
    def name(self):
        return self.attrib['networkName']

    @classmethod
    def new(cls, name):
        top = fromstring(network_config_xml)
        top.attrib['networkName'] = name
        return top

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

class InstantiateVAppTemplateParams(VcdElement):

    powerOn = expose_attr('powerOn')
    deploy = expose_attr('deploy')

    network_maps = fetch2dict_by_tag(nstag('NetworkConfig'), key='networkName')

    def add_network(self, name, index=0, needsCustomization="false"):
        # we can't configure that at instantiate time
#        net = NetworkConnection.new(name, index=index, needsCustomization=needsCustomization)
#        netsect = self.one(nstag('NetworkConnectionSection'))
#        netsect.append(net)
        netconfsec = self.one(nstag('NetworkConfigSection'))
        netconfsec.append(NetworkConfig.new(name))
        return netconfsec

    def map_network(self, src, vcdnet, fencemode='bridged'):
        self.network_maps[src].parent = vcdnet
        self.network_maps[src].fencemode = fencemode

    @property
    def name(self):
        return self.get('name')

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
        #print self.xml
        #print self.find(nstag('NetworkConfig'))
        #netconfsec = params.find('.//{}'.format(nstag('NetworkConfigSection')))
        #netconfsec.replace_child('NetworkConfig', self.find(nstag('NetworkConfig')))
        #netconfsec = params.one(nstag('NetworkConfigSection'))
        for index, netname in enumerate(self.networks):
            params.add_network(netname, index)
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
        if len(self.files) > 1 or self.status != '0': return True
        while 1:
            self.refresh()
            if len(self.files) > 1:
                # descriptor is uploaded and processed
                return True
            else:
                time.sleep(1)


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
    AdminPassword = expose_tag_text(nstag('AdminPassword'), insert=8)
    AdminPasswordAuto = expose_tag_text(nstag('AdminPasswordAuto'))
    ResetPasswordRequired = expose_tag_text(nstag('ResetPasswordRequired'))
    ComputerName = expose_tag_text(nstag('ComputerName'))
    CustomizationScript = expose_tag_text(nstag('CustomizationScript'))

    @classmethod
    def new(self):
        top = fromstring(guest_customization_xml)
        return top

class ProductSectionList(VcdElement):
    pass

class VApp(VcdElement):

    #vms = fetch2dict('vcloud.vm', key='name')
    vms = fetch2dict_by_tag(nstag('Vm'), key='name')
    name = expose_attr('name')


    @property
    def poweredOn(self):
        try:
            self.links_by_rel['power:powerOn']
            return False
        except KeyError:
            return True
    powered_on = poweredOn

    @property
    def poweredOff(self):
        try:
            self.links_by_rel['power:powerOff']
            return False
        except KeyError:
            return True
    powered_off = poweredOff

    def powerOn(self):
        link = self.links_by_rel['power:powerOn']
        res = request('post', link.href)
        task = fromstring(res.content)
        task.wait_for_task()
        self.refresh()
        return task
    power_on = powerOn

    def powerOff(self):
        link = self.links_by_rel['power:powerOff']
        res = request('post', link.href)
        task = fromstring(res.content)
        task.wait_for_task()
        self.refresh()
        return task
    power_off = powerOff

    def shutdown(self):
        try:
            link = self.links_by_rel['power:shutdown']
        except KeyError:
            # already shutdown
            return
        res = request('post', link.href)
        task = fromstring(res.content)
        task.wait_for_task()
        self.refresh()
        return task

    def remove(self):
        try:
            link = self.links_by_rel['remove']
        except KeyError:
            raise Exception('{} is still deployed and cannot be removed'.format(self.name))
        res = request('delete', link.href)
        return fromstring(res.content)

    @property
    def deployed(self):
        typ = fulltype('vcloud.deployVAppParams')
        try:
            link = self.links_by_type[typ]
            return False
        except KeyError:
            return True

    @property
    def undeployed(self):
        typ = fulltype('vcloud.undeployVAppParams')
        try:
            link = self.links_by_type[typ]
            return False
        except KeyError:
            return True

    def undeploy(self):
        typ = fulltype('vcloud.undeployVAppParams')
        link = self.links_by_type[typ]
        dep = E('UndeployVAppParams')
        res = request('post', link.href, data=dep.xml)
        task = fromstring(res.content)
        task.wait_for_task()
        self.refresh()
        return task

class Vm(VApp):

    networks = fetch2list_by_tag(nstag('NetworkConnection'))
    description = expose_tag_text(nstag('Description'), commit_on_set=True)

    def get_hardware_item(self, name):
        for element in self.iter():
            if element.tag == ovftag('Item'):
                if not element.get(nstag('href')):
                    # not an element we care about atm
                    continue
                if element.get(nstag('href')).endswith(name):
                    return element
    @property
    def num_cpus(self):
        for sub in self.get_hardware_item('cpu'):
            if sub.tag.endswith('VirtualQuantity'):
                return int(sub.text)

    @num_cpus.setter
    def num_cpus(self, new_num_cpus):
        new_num_cpus = str(new_num_cpus)
        cpu_section = self.get_hardware_item('cpu')
        # must refresh here to get a valid xml representation for commit
        cpu_section.refresh()
        for sub in cpu_section:
            if sub.tag.endswith('VirtualQuantity'):
                sub.text = new_num_cpus
        cpu_section.commit().wait_for_task()

    @property
    def memory_mb(self):
        for sub in self.get_hardware_item('memory'):
            if sub.tag.endswith('VirtualQuantity'):
                return int(sub.text)

    @memory_mb.setter
    def memory_mb(self, new_memory_mb):
        new_memory_mb = str(new_memory_mb)
        memory_section = self.get_hardware_item('memory')
        # must refresh here to get a valid xml representation for commit
        memory_section.refresh()
        for sub in memory_section:
            if sub.tag.endswith('VirtualQuantity'):
                sub.text = new_memory_mb
        memory_section.commit().wait_for_task()

    def update_section(self, sectname):
        sect = self.one(nstag(sectname))
        print sect.xml
        res = request('put', sect.href, data=sect.xml)
        return fromstring(res.content)

    def update_networks(self):
        return self.update_section('NetworkConnectionSection')

    def deploy(self, powerOn="true", forceCustomization="true", deploymentLeaseSeconds="0"):
        typ = fulltype('vcloud.deployVAppParams')
        link = self.links_by_type[typ]
        dep = E('DeployVAppParams', powerOn=powerOn, forceCustomization=forceCustomization,
                deploymentLeaseSeconds=deploymentLeaseSeconds)
        print dep.xml
        res = request('post', link.href, data=dep.xml)
        print res.content
        return fromstring(res.content)

    def customize(self):
        top = self.one(nstag('GuestCustomizationSection'))
        instantparams = self.one(nstag('InstantiationParams'))
        if top is None:
            top = GuestCustomizationSection.new()
            instantparams.append(top)
        return top

class MetadataEntry(VcdElement):

    key = expose_tag_text(nstag('Key'))

    __value = expose_tag_text(nstag('Value'))

    # custom code for Value because to set it we need a new tag: MetadataValue
    @property
    def value(self):
        return self.__value

    @value.setter
    def value(self, newval):
        self.__value = newval
        if self.href is not None:
            # only call the update if this is a existing entry
            # (which we know because we have an href)
            element = self.one(nstag('Value'))
            top = E('MetadataValue')
            top.append(element)
            res = request('put', self.href, data=top.xml)
            task = fromstring(res.content)
            task.wait_for_task()

class Metadata(VcdElement):

    def _add(self, key, value):
        "add key/value to metadata object"
        # To add we post a Metadata object containing the new entry
        element = E('MetadataEntry')
        element.key = key
        element.value = value
        top = E('Metadata')
        top.type = self.type
        top.href = self.href
        top.append(element)
        res = request('post', self.href, headers={'Content-type' : top.type}, data=top.xml)
        task = fromstring(res.content)
        task.wait_for_task()
        # once it is added, it should show up on self with a refresh
        self.refresh()

    @property
    def entries(self):
        return self.all(nstag('MetadataEntry'))

    def __getitem__(self, key):
        for entry in self.entries:
            if entry.key == key:
                return entry.value
        # easy to raise exact version of dict KeyError
        dict()[key]

    def __setitem__(self, key, value):
        found = False
        for entry in self.entries:
            if entry.key == key:
                found = True
                break
        if found:
            entry.value = value
        else:
            self._add(key, value)

class File(VcdElement):

    name = expose_attr('name')
    size = expose_attr('size')
    bytesTransferred = expose_attr('bytesTransferred')

    @property
    def uploaded(self):
        return self.size == self.bytesTransferred

    def upload(self, stream_or_string):
        link = self.links_by_rel['upload:default']
        if isinstance(stream_or_string, basestring):
            size = len(stream_or_string)
        elif hasattr(stream_or_string, "read"):
            # duck check for stream
            stream_or_string.seek(0, 2)
            size = stream_or_string.tell()
            stream_or_string.seek(0, 0)
        log.info('uploading {} size {}'.format(self.name, size))
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
