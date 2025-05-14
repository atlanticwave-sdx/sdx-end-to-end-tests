import json
import re
import time
from datetime import datetime, timedelta
import uuid

import pytest
from random import randrange
import requests

from tests.helpers import NetworkTest

SDX_CONTROLLER = 'http://sdx-controller:8080/SDX-Controller'
KYTOS_TOPO_API = "http://%s:8181/api/kytos/topology/v3"
KYTOS_SDX_API  = "http://%s:8181/api/kytos/sdx"
KYTOS_API = 'http://%s:8181/api/kytos'

class TestUseCases:
    net = None

    @classmethod
    def setup_class(cls):
        cls.net = NetworkTest(["ampath", "sax", "tenet"])
        cls.net.wait_switches_connect()
        cls.net.run_setup_topo()

    @classmethod
    def teardown_class(cls):
        cls.net.stop()

    @classmethod
    def setup_method(cls):
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        response_json = response.json()
        for l2vpn in response_json:
            response = requests.delete(api_url+f'/{l2vpn}')
        cls.net.config_all_links_up()
        cls.net.config_all_ports_up()
        time.sleep(15)

    def _create_l2vpn(self, port_1, port_2, vlan1="100", vlan2="100"):
        '''Auxiliar function'''
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation",
            "endpoints": [
                {"port_id": port_1,"vlan": vlan1},
                {"port_id": port_2,"vlan": vlan2}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        # wait until status changes for under provisioning to up
        time.sleep(5)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        key = next(iter(data))
        assert data[key]["status"] == "up"
        return key

    @pytest.mark.xfail(reason="The status of the L2VPN doesn't change to down after setting the link to down")
    def test_010_update_intra_domain_link_down(self):
        ''' Use case 1
            OXPO sends a topology update with an intra-domain link down.
            When possible, the SDX-Controller can find a path based on the exported topology. 
        '''
        key = self._create_l2vpn("urn:sdx:port:tenet.ac.za:Tenet01:50","urn:sdx:port:tenet.ac.za:Tenet03:50")

        h6, h8 = self.net.net.get('h6', 'h8')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')
        h8.cmd('ip link add link %s name vlan100 type vlan id 100' % (h8.intfNames()[0]))
        h8.cmd('ip link set up vlan100')
        h8.cmd('ip addr add 10.1.1.8/24 dev vlan100')

        # test connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.8')

        # set one link to down
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'down')

        time.sleep(15)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert data[key]["status"] == "down"   ### FAIL HERE

        # test connectivity
        assert ', 100% packet loss,' in h6.cmd('ping -c4 10.1.1.8')

        ### Reset
        # set one link to up
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'up')

        time.sleep(15)

        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.8')

    @pytest.mark.xfail(reason="After setting a link down and finding an alternate path, connectivity between hosts is not checked.")
    def test_011_update_intra_domain_link_down_path_found(self):
        ''' Use case 1
            OXPO sends a topology update with an intra-domain link down.
            When not possible, the SDX Controller will only update the L2VPN’s status using the means available.
        '''
        key = self._create_l2vpn("urn:sdx:port:tenet.ac.za:Tenet01:50","urn:sdx:port:tenet.ac.za:Tenet02:50")

        h6, h7 = self.net.net.get('h6', 'h7')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')
        h7.cmd('ip link add link %s name vlan100 type vlan id 100' % (h7.intfNames()[0]))
        h7.cmd('ip link set up vlan100')
        h7.cmd('ip addr add 10.1.1.7/24 dev vlan100')

        # test connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.7')

        # set one link to down
        self.net.net.configLinkStatus('Tenet01', 'Tenet02', 'down')

        time.sleep(15)

        # SDX should find another path using links from SAX
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.7')  ### FAIL HERE
        
        ### Reset 
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'up')

        time.sleep(15)
        
        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.7')

    def test_015_update_port_in_inter_domain_link_down(self):
        ''' Use case 2
            OXPO sends a topology update with a Port Down and 
            that port is part of an inter-domain link.
        '''
        key = self._create_l2vpn("urn:sdx:port:ampath.net:Ampath1:50","urn:sdx:port:tenet.ac.za:Tenet01:50")
        
        h1, h6 = self.net.net.get('h1', 'h6')
        h1.cmd('ip link add link %s name vlan100 type vlan id 100' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan100')
        h1.cmd('ip addr add 10.1.1.1/24 dev vlan100')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

        Ampath1 = self.net.net.get('Ampath1')
        Ampath1.intf('Ampath1-eth40').ifconfig('down') 

        time.sleep(15)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

        ### Reset - use case 5 (port is just an addition - a new inter-domain path)
        Ampath1.intf('Ampath1-eth40').ifconfig('up') 

        time.sleep(15)

        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

    @pytest.mark.xfail(reason="The status of the L2VPN doesn't change to down after setting the link to down and ensure that provisioning is not possible")
    def test_016_update_port_in_inter_domain_link_down_no_reprov(self):
        ''' Use case 2, use case 5
            OXPO sends a topology update with a Port Down and 
            that port is part of an inter-domain link.
        '''
        key = self._create_l2vpn("urn:sdx:port:ampath.net:Ampath1:50","urn:sdx:port:tenet.ac.za:Tenet01:50")

        h1, h6 = self.net.net.get('h1', 'h6')
        h1.cmd('ip link add link %s name vlan100 type vlan id 100' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan100')
        h1.cmd('ip addr add 10.1.1.1/24 dev vlan100')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

        # Ampath1-eth40
        self.net.net.configLinkStatus('Ampath1', 'Sax01', 'down')

        #  Cause no further (re)provisioning to be possible
        self.net.net.configLinkStatus('Tenet01', 'Sax01', 'down')
        self.net.net.configLinkStatus('Tenet01', 'Tenet02', 'down')

        time.sleep(15)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()

        # test connectivity
        assert ', 100% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

        ### Reset - use case 5 (port UP can benefit the environment (L2VPNs were down because of the lack of paths)
        self.net.net.configLinkStatus('Ampath1', 'Sax01', 'up')
        self.net.net.configLinkStatus('Tenet01', 'Sax01', 'up')
        self.net.net.configLinkStatus('Tenet01', 'Tenet02', 'up')

        time.sleep(15)

        assert data[key]["status"] == "down" ### FAIL HERE

        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

    @pytest.mark.xfail(reason="The status of the L2VPN doesn't change to down after setting the port to down")
    def test_020_update_uni_port_down(self):
        ''' Use case 3, use case 6
            OXPO sends a topology update with a Port Down and 
            that port is an UNI for some L2VPN.
        '''
        key = self._create_l2vpn("urn:sdx:port:ampath.net:Ampath1:50","urn:sdx:port:tenet.ac.za:Tenet01:50")
        
        h1, h6 = self.net.net.get('h1', 'h6')
        h1.cmd('ip link add link %s name vlan100 type vlan id 100' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan100')
        h1.cmd('ip addr add 10.1.1.1/24 dev vlan100')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

        Tenet01 = self.net.net.get('Tenet01')
        Tenet01.intf('Tenet01-eth50').ifconfig('down') 

        time.sleep(15)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert data[key]["status"] == "down"  ### FAIL HERE

        # test connectivity
        assert ', 100% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

        ### Reset - use case 6 - configs should not be removed in case of a Port Down (data plane config is already there)
        Tenet01.intf('Tenet01-eth50').ifconfig('up') 

        time.sleep(15)

        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

    def test_025_update_node_down(self):
        ''' Use case 4
            OXPO sends a topology update with a Node down (switch down).
        '''
        def set_node(node, status, target):
            if status == 'down':
                node.cmd(f"ovs-vsctl set-controller {node.name} {target}")
                node.cmd(f"ovs-vsctl get-controller {node.name}") 
            else:
                node.cmd(f"ovs-vsctl set-controller {node.name} {target}")
                node.cmd(f"ovs-vsctl get-controller {node.name}")

        key = self._create_l2vpn("urn:sdx:port:ampath.net:Ampath1:50","urn:sdx:port:tenet.ac.za:Tenet01:50")

        h1, h6 = self.net.net.get('h1', 'h6')
        h1.cmd('ip link add link %s name vlan100 type vlan id 100' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan100')
        h1.cmd('ip addr add 10.1.1.1/24 dev vlan100')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

        node_name = 'Ampath1'
        node = self.net.net.get(node_name)
        config = node.cmd('ovs-vsctl get-controller', node.name).split()
        set_node(node, 'down', "tcp:127.0.0.1:6654")

        time.sleep(15)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        ### Reset
        set_node(node, 'up', " ".join(config))

        time.sleep(15)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

    def test_030_update_port_in_inter_domain_link_up_new_path(self):
        ''' Use case 5
            OXPO sends a topology update with a Port UP and 
            that port is an inter-domain link.
            If the port is just an addition (a new inter-domain path), do nothing 
        '''
        key = self._create_l2vpn("urn:sdx:port:ampath.net:Ampath1:50","urn:sdx:port:tenet.ac.za:Tenet01:50")

        h1, h6 = self.net.net.get('h1', 'h6')
        h1.cmd('ip link add link %s name vlan100 type vlan id 100' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan100')
        h1.cmd('ip addr add 10.1.1.1/24 dev vlan100')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

        # Ampath1-eth40
        self.net.net.configLinkStatus('Ampath1', 'Sax01', 'down')

        time.sleep(15)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

        ### Reset - use case 5 (If the port is just an addition (a new inter-domain path), do nothing )
        self.net.net.configLinkStatus('Ampath1', 'Sax01', 'up')

        time.sleep(15)

        assert data[key]["status"] == "up" ### FAIL HERE

        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd('ping -c4 10.1.1.6')

    @pytest.mark.xfail(reason="The status of the L2VPN doesn't change to down after setting the link to down")
    def test_40_update_port_uni_up_no_l2vpn_associated(self):
        ''' Use case 7
            OXPO sends a topology update with a Port UP and 
            that port has no L2VPN associated with it. 
            
            Expected behavior: For a UNI port, the SDX-Controller does nothing.
        '''
        key = self._create_l2vpn("urn:sdx:port:ampath.net:Ampath1:50","urn:sdx:port:tenet.ac.za:Tenet01:50")
        port = 'urn:sdx:port:ampath.net:Ampath2:50'

        api_url_topology = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url_topology)
        data = response.json()
        ports = {port["id"] for node in data["nodes"] for port in node["ports"] if port['nni'] == ''}
        # UNI port
        assert port in ports

        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'down') 
        time.sleep(15)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        initial_data = requests.get(api_url).json()
        path_ports = [p['port_id'] for p in initial_data[key]['current_path']]
        # Port has no L2VPN associated
        assert port not in path_ports
        assert initial_data[key]["status"] == "down"   ### FAIL HERE

        # Simulate port UP to trigger topology update
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'up')
        time.sleep(15)

        # Verify no L2VPN was created or modified
        final_data = requests.get(api_url).json()
        assert final_data == initial_data, "L2VPN state changed unexpectedly"

    @pytest.mark.xfail(reason="Link is not removed from topology after being deleted")
    def test_50_update_link_missing(self):
        ''' Use case 8
            OXPO sends a topology update with a Link missing (deleted by the OXP)

            Expected behavior: 
            Topology version number increases, 
            link is removed from topology,
            L2VPN status changes to down due to no alternate path exists,
            the Link is not exported by the OXP and SDX-LC,
        '''
        # Create L2VPN
        key = self._create_l2vpn("urn:sdx:port:tenet.ac.za:Tenet01:50", "urn:sdx:port:tenet.ac.za:Tenet03:50")
        link = 'urn:sdx:link:tenet.ac.za:Tenet01/2_Tenet03/2' 

        # Configure hosts
        h6, h8 = self.net.net.get('h6', 'h8')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')
        h8.cmd('ip link add link %s name vlan100 type vlan id 100' % (h8.intfNames()[0]))
        h8.cmd('ip link set up vlan100')
        h8.cmd('ip addr add 10.1.1.8/24 dev vlan100')

        # Test initial connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.8')

        # Get initial topology version
        api_url_topology = SDX_CONTROLLER + '/topology'
        initial_topology = requests.get(api_url_topology).json()
        initial_version = float(initial_topology["version"])
        links = {link["id"] for link in initial_topology["links"]}
        assert link in links

        # Simulate link deletion by setting link to down
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'down')
        time.sleep(15) 

        # Verify topology version increased
        updated_topology = requests.get(api_url_topology).json()
        updated_version = float(updated_topology["version"])
        assert updated_version > initial_version, "Topology version did not increase"

        links = {link["id"]: link for link in updated_topology["links"]}
        assert link not in links   ### FAIL HERE

        # Verify L2VPN status is down (no alternate path)
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert data[key]["status"] == "down", "L2VPN status did not change to down"

        # Test connectivity (should fail)
        assert ', 100% packet loss,' in h6.cmd('ping -c4 10.1.1.8')

        # Verify Link is not exported by tenet and SDX-LC
        tenet_api = KYTOS_API % 'tenet'
        response = requests.get(f'{tenet_api}/topology/v3/links')
        assert response.status_code == 200
        data = response.json()
        for _, link_ in data['links'].items():
            ep_a = link_['endpoint_a']['name'].split('-')[0]
            ep_b = link_['endpoint_b']['name'].split('-')[0]
            assert set(['Tenet01', 'Tenet03']) != set([ep_a, ep_b]), link_

        sdx_api = KYTOS_SDX_API % 'tenet'
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200
        data = response.json()
        links = [l['id'] for l in data['links']]
        assert link not in links

        # Reset: Restore link
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'up')
        time.sleep(15)

        # Verify L2VPN status is up
        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # Test connectivity (should succeed)
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.8')
        
    @pytest.mark.xfail(reason="Link is not removed from topology after being deleted")
    def test_55_update_link_missing_with_alternate_path(self):
        ''' Use case 8
            OXPO sends a topology update with a Link missing (deleted by the OXP)

            Expected behavior: 
            Topology version number increases, 
            link is removed from topology,
            the Link is not exported by the OXP and SDX-LC,
        '''
        # Create L2VPN
        key = self._create_l2vpn("urn:sdx:port:tenet.ac.za:Tenet01:50", "urn:sdx:port:tenet.ac.za:Tenet02:50")
        link = 'urn:sdx:link:tenet.ac.za:Tenet01/1_Tenet02/1' 

        # Configure hosts
        h6, h7 = self.net.net.get('h6', 'h7')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')
        h7.cmd('ip link add link %s name vlan100 type vlan id 100' % (h7.intfNames()[0]))
        h7.cmd('ip link set up vlan100')
        h7.cmd('ip addr add 10.1.1.7/24 dev vlan100')

        # Test initial connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.7')

        # Get initial topology version
        api_url_topology = SDX_CONTROLLER + '/topology'
        initial_topology = requests.get(api_url_topology).json()
        initial_version = float(initial_topology["version"])
        links = {link["id"] for link in initial_topology["links"]}
        assert link in links

        # Simulate link deletion by setting link to down
        self.net.net.configLinkStatus('Tenet01', 'Tenet02', 'down')
        time.sleep(15) 

        # Verify topology version increased
        updated_topology = requests.get(api_url_topology).json()
        updated_version = float(updated_topology["version"])
        assert updated_version > initial_version, "Topology version did not increase"

        links = {link["id"]: link for link in updated_topology["links"]}
        assert link not in links   ### FAIL HERE

        # Verify L2VPN status is up (alternate path)
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # Test connectivity (should fail)
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.8')

        # Verify Link is not exported by tenet and SDX-LC
        tenet_api = KYTOS_API % 'tenet'
        response = requests.get(f'{tenet_api}/topology/v3/links')
        assert response.status_code == 200
        data = response.json()
        for _, link_ in data['links'].items():
            ep_a = link_['endpoint_a']['name'].split('-')[0]
            ep_b = link_['endpoint_b']['name'].split('-')[0]
            assert set(['Tenet01', 'Tenet02']) != set([ep_a, ep_b]), link_

        sdx_api = KYTOS_SDX_API % 'tenet'
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200
        data = response.json()
        links = [l['id'] for l in data['links']]
        assert link not in links

        # Reset: Restore link
        self.net.net.configLinkStatus('Tenet01', 'Tenet02', 'up')
        time.sleep(15)

        # Verify L2VPN status is up
        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # Test connectivity (should succeed)
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.8')
        
    def test_70_update_port_nni_missing(self):
        ''' Use case 9
            OXPO sends a topology update with a Port missing
        '''

    def test_75_update_port_uni_missing(self):
        ''' Use case 9
            OXPO sends a topology update with a Port missing
        '''

    def test_80_update_changed_vlan_range_on_nni(self):
        ''' Use case 10
            OXPO sends a topology update with a changed VLAN range 
            for any of the services supported.
        '''

    def test_85_update_changed_vlan_range_on_uni(self):
        ''' Use case 10
            OXPO sends a topology update with a changed VLAN range 
            for any of the services supported.
        '''