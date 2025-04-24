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

    def test_010_send_topo_update_with_intra_domain_link_down_path_found(self):
        ''' Use case 1
            OXPO sends a topology update with an intra-domain link down.
            When possible, the SDX-Controller can find a path based on the exported topology. 

            - Create a L2VPN between Tenet01:50 and Tenet03:50
            - Check if that L2VPN status is UP (some wait may be required here)
            - Run a PING test between hosts to make sure we have connectivity
            - Config the Link Tenet01 — Tenet03 to down (some wait may be required here)
            - Query the L2VPN and check the status to validate it is down
            - Config the Link Tenet01 — Tenet03 to UP (some wait may be required here)
            - Query the L2VPN and check the status to validate it is back UP
            - Run a PING test between hosts to make sure we have connectivity
        '''
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation",
            "endpoints": [
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet01:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        # wait until status changes for under provisioning to up
        time.sleep(5)

        data = requests.get(api_url).json()
        assert len(data) == 1
        key = next(iter(data))
        assert data[key]["status"] == "up"

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

        '''
            HERE: The following code verifies that the link was set to down, 
            and that the current_path is Tenet01-Tenet03, 
            so the test fails because the L2VPN status is still up.
        '''

        ## Beginning of verification code
        api_url_topology = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url_topology)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        link1 = "urn:sdx:link:tenet.ac.za:Tenet01/2_Tenet03/2"
        assert links[link1]["status"] == "down", str(links[link1])
        ## End of verification code

        data = requests.get(api_url).json()
        key = next(iter(data))
        ## Beginning of verification code
        path = [item['port_id'] for item in data[key]['current_path']]
        assert path == ['urn:sdx:port:tenet.ac.za:Tenet01:50', 'urn:sdx:port:tenet.ac.za:Tenet03:50']
        ## End of verification code
        assert data[key]["status"] == "down"

        # set one link to down
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'up')

        time.sleep(15)

        data = requests.get(api_url).json()
        key = next(iter(data))
        assert data[key]["status"] == "down"

        # test connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.8')

    def test_011_send_topo_update_with_intra_domain_link_down_path_not_found(self):
        ''' Use case 1
            OXPO sends a topology update with an intra-domain link down.
            When not possible, the SDX Controller will only update the L2VPN’s status using the means available.

            - Create a L2VPN between Tenet01:50 and Tenet02:50
            - Check if that L2VPN status is UP (some wait may be required here)
            - Run a PING test between hosts to make sure we have connectivity
            - Config the Link Tenet01 — Tenet02 to down (some wait may be required here)
            - Query the L2VPN and check the status to validate it is UP (SDX should find another path using links from SAX)
            - Config the Link Tenet01 — Tenet02 to UP (some wait may be required here)
            - Query the L2VPN and check the status to validate it continue to be UP 
            - Run a PING test between hosts to make sure we have connectivity
        '''
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation",
            "endpoints": [
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet01:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet02:50","vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        # wait until status changes for under provisioning to up
        time.sleep(5)

        data = requests.get(api_url).json()
        assert len(data) == 1
        key = next(iter(data))
        assert data[key]["status"] == "up"

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
        data = requests.get(api_url).json()
        key = next(iter(data))
        assert data[key]["status"] == "up"

        # set one link to down
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'up')

        data = requests.get(api_url).json()
        key = next(iter(data))
        assert data[key]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.7')

    def test_020_send_topo_update_with_port_in_inter_domain_link_down(self):
        ''' Use case 2
            OXPO sends a topology update with a Port Down and 
            that port is part of an inter-domain link.
        '''

    def test_030_send_topo_update_with_port_in_uni_from_l2vpn_down(self):
        ''' Use case 3
            OXPO sends a topology update with a Port Down and 
            that port is an UNI for some L2VPN.
        '''

    def test_040_send_topo_update_with_node_down(self):
        ''' Use case 4
            OXPO sends a topology update with a Node down (switch down).
        '''
    
    def test_050_send_topo_update_with_port_in_inter_domain_link_up(self):
        ''' Use case 5
            OXPO sends a topology update with a Port UP and 
            that port is an inter-domain link.
        '''