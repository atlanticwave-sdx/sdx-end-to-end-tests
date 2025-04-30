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
        assert data[key]["status"] == "down" ### FAIL HERE

        # test connectivity
        result1 = h6.cmd('ping -c4 10.1.1.8')

        ### Reset
        # set one link to up
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'up')

        time.sleep(15)

        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        result2 = h6.cmd('ping -c4 10.1.1.8')

        assert ', 100% packet loss,' in result1
        assert ', 0% packet loss,' in result2

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
        result_1 = h6.cmd('ping -c4 10.1.1.7')
        
        ### Reset 
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'up')

        time.sleep(15)
        
        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        result_2 = h6.cmd('ping -c4 10.1.1.7')

        assert ', 0% packet loss,' in result_1  ### FAIL HERE
        assert ', 0% packet loss,' in result_2

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
        result_1 = h1.cmd('ping -c4 10.1.1.6')

        ### Reset 
        Ampath1.intf('Ampath1-eth40').ifconfig('up') 

        time.sleep(15)

        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        result_2 = h1.cmd('ping -c4 10.1.1.6')

        assert ', 0% packet loss,' in result_1
        assert ', 0% packet loss,' in result_2

    def test_016_update_port_in_inter_domain_link_down_no_reprov(self):
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

        #  Cause no further (re)provisioning to be possible
        Sax01 = self.net.net.get('Sax01')
        Sax01.intf('Sax01-eth41').ifconfig('down') 
        Tenet02 = self.net.net.get('Tenet02')
        Tenet02.intf('Tenet02-eth1').ifconfig('down') 

        time.sleep(15)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()

        # test connectivity
        result1 = h1.cmd('ping -c4 10.1.1.6')

        ### Reset 
        Ampath1.intf('Ampath1-eth40').ifconfig('up') 
        Sax01.intf('Sax01-eth41').ifconfig('up') 
        Tenet02.intf('Tenet02-eth1').ifconfig('up') 

        time.sleep(15)

        assert data != {}  ### FAIL HERE
        assert data[key]["status"] == "down"

        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        result2 = h1.cmd('ping -c4 10.1.1.6')

        assert ', 100% packet loss,' in result1
        assert ', 0% packet loss,' in result2

    def test_020_update_uni_port_down(self):
        ''' Use case 3
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
        result_1 = h1.cmd('ping -c4 10.1.1.6')

        ### Reset 
        Tenet01.intf('Tenet01-eth50').ifconfig('up') 

        time.sleep(15)

        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

        # test connectivity
        result_2 = h1.cmd('ping -c4 10.1.1.6')

        assert ', 100% packet loss,' in result_1
        assert ', 0% packet loss,' in result_2

    def test_025_update_with_node_down(self):
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

        api_url_topology = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url_topology)
        data = response.json()
        print({node['name']:node['status'] for node in data['nodes']})

        Ampath1 = self.net.net.get('Ampath1')
        set_node(Ampath1, 'down', "tcp:127.0.0.1:6654")

        time.sleep(15)

        api_url_topology = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url_topology)
        data = response.json()
        print({node['name']:node['status'] for node in data['nodes']})

        ### Reset
        set_node(Ampath1, 'down', "tcp:127.0.0.1:6653")

        time.sleep(15)

        api_url_topology = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url_topology)
        data = response.json()
        print({node['name']:node['status'] for node in data['nodes']})

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert data[key]["status"] == "up"

    def test_030_send_topo_update_with_port_in_inter_domain_link_up(self):
        ''' Use case 5
            OXPO sends a topology update with a Port UP and 
            that port is an inter-domain link.
        '''
