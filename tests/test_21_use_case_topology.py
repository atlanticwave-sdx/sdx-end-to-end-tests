"""
End-to-end tests for AtlanticWave-SDX Topology Management use cases.

This module contains tests that verify the SDX Controller's behavior when handling
topology updates from SDX Local Controllers, including link status changes, node status
changes, and topology element removals.
"""

import json
import re
import time
from datetime import datetime, timedelta
import pytest
import requests

from tests.helpers import NetworkTest

SDX_CONTROLLER = 'http://sdx-controller:8080/SDX-Controller'
API_URL = SDX_CONTROLLER + '/l2vpn/1.0'
API_URL_TOPO = SDX_CONTROLLER + '/topology'
KYTOS_API = 'http://%s:8181/api/kytos'
KYTOS_SDX_API  = "http://%s:8181/api/kytos/sdx"

UNI2HOST = {
    "Ampath1": {"id":"urn:sdx:port:ampath.net:Ampath1:50", "host":"1"},
    "Ampath2": {"id":"urn:sdx:port:ampath.net:Ampath2:50", "host":"2"},
    "Ampath3": {"id":"urn:sdx:port:ampath.net:Ampath3:50", "host":"3"},
    "Sax01": {"id":"urn:sdx:port:sax.net:Sax01:50", "host":"4"},
    "Sax02": {"id":"urn:sdx:port:sax.net:Sax02:50:50", "host":"5"},
    "Tenet01": {"id":"urn:sdx:port:tenet.ac.za:Tenet01:50", "host":"6"},
    "Tenet02": {"id":"urn:sdx:port:tenet.ac.za:Tenet02:50", "host":"7"},
    "Tenet03": {"id":"urn:sdx:port:tenet.ac.za:Tenet03:50", "host":"8"}
}


class TestE2ETopologyUseCases:
    net = None

    @classmethod
    def setup_class(cls):
        """Set up the test environment with all OXPs."""
        cls.net = NetworkTest(["ampath", "sax", "tenet"])
        cls.net.wait_switches_connect()
        cls.net.run_setup_topo()
        
        # Give time for topology to be fully established
        time.sleep(15)

    @classmethod
    def teardown_class(cls):
        """Clean up the test environment."""
        cls.net.stop()

    @classmethod
    def setup_method(cls):
        """Reset network configuration before each test."""
        cls.setup_class()

    def create_new_l2vpn(self, vlan='100', node1='Ampath1', node2='Tenet01'):
        l2vpn_payload = {
            "name": "Test L2VPN",
            "endpoints": [
                {
                    "port_id": UNI2HOST[node1]['id'],
                    "vlan": vlan,
                },
                {
                    "port_id": UNI2HOST[node2]['id'],
                    "vlan": vlan,
                }
            ]
        }
        response = requests.post(API_URL, json=l2vpn_payload)
        assert response.status_code == 201, response.text
        l2vpn_id = response.json().get("service_id")

        # Wait for L2VPN to be provisioned
        time.sleep(5)

        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_data = response.json().get(l2vpn_id)
        l2vpn_status = l2vpn_data.get("status")
        assert l2vpn_status == "up", f"L2VPN status should be up, but is {l2vpn_status}"

        add1 = f"10.{int(int(vlan)/10)}.1.{UNI2HOST[node1]['host']}"
        add2 = f"10.{int(int(vlan)/10)}.1.{UNI2HOST[node2]['host']}"
        h1, h2 = self.net.net.get(f"h{UNI2HOST[node1]['host']}", f"h{UNI2HOST[node2]['host']}")
        h1.cmd(f"ip link add link {h1.intfNames()[0]} name vlan{vlan} type vlan id {vlan}")
        h1.cmd(f"ip link set up vlan{vlan}")
        h1.cmd(f"ip addr add {add1}/24 dev vlan{vlan}")
        h2.cmd(f"ip link add link {h2.intfNames()[0]} name vlan{vlan} type vlan id {vlan}")
        h2.cmd(f"ip link set up vlan{vlan}")
        h2.cmd(f"ip addr add {add2}/24 dev vlan{vlan}")

        # test connectivity
        assert ', 0% packet loss,' in h1.cmd(f"ping -c4 {add2}")
        return {'id':l2vpn_id, 'data':l2vpn_data, 'h':h1, 'ping_str':f"ping -c4 {add2}"}

    @pytest.mark.xfail(reason="L2VPN remains up after a link is removed from topology and no alternate path exists")
    def test_080_link_missing(self):
        """
        Use case 8: Test Remove Link (because it was deleted by the OXP)

        1. Topology version number increases, 
        2. link is removed from topology,
        3. L2VPN status changes to down due to no alternate path exists,
        4. the Link is not exported by the OXP and SDX-LC,
        """
        endp1 = 'Tenet01-eth2'
        endp2 = 'Tenet03-eth2'

        # Get link id
        tenet_api = KYTOS_API % 'tenet'
        api_url_tenet = f'{tenet_api}/topology/v3/links'
        response = requests.get(api_url_tenet)
        assert response.status_code == 200
        data = response.json()
        link_id = None
        for key, value in data['links'].items():
            endpoint_a = value["endpoint_a"]["name"]
            endpoint_b = value["endpoint_b"]["name"]
            if set([endpoint_a, endpoint_b]) == set([endp1, endp2]):
               link_name = 'urn:sdx:link:tenet.ac.za:Tenet01/2_Tenet03/2'
               link_id = key
               break
        assert link_id

        l2vpn_data = self.create_new_l2vpn(vlan='800', node1='Tenet01', node2='Tenet03')
        l2vpn_id = l2vpn_data['id']

        # Get initial topology version
        initial_topology = requests.get(API_URL_TOPO).json()
        initial_version = float(initial_topology["version"])
        links = {link["id"] for link in initial_topology["links"]}
        assert link_name in links

        # Disabling link
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'down')
        api_url_disable = f'{api_url_tenet}/{link_id}/disable'
        response = requests.post(api_url_disable)
        assert response.status_code == 201, response.text
    
        # Deleting link
        api_url = f'{api_url_tenet}/{link_id}'
        response = requests.delete(api_url)
        assert response.status_code == 200, response.text
            
        time.sleep(15) 
    
        # Verify topology version increased
        updated_topology = requests.get(API_URL_TOPO).json()
        updated_version = float(updated_topology["version"])
        assert updated_version > initial_version, "Topology version did not increase"

        links = {link["id"]: link for link in updated_topology["links"]}
        assert link_name not in links 

        # Verify L2VPN status is down (no alternate path)
        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_response = response.json()
        l2vpn_status = l2vpn_response.get(l2vpn_id).get("status")
        assert l2vpn_status == "down", f"L2VPN status should be down, but is {l2vpn_status}"

        # Test connectivity (should fail)
        assert ', 100% packet loss,' in l2vpn_data['host1'].cmd(l2vpn_data['ping_str'])

        # Verify Link is not exported by tenet and SDX-LC
        response = requests.get(f'{tenet_api}/topology/v3/links')
        assert response.status_code == 200
        data = response.json()
        for _, link in data['links'].items():
            ep_a = link['endpoint_a']['name']
            ep_b = link['endpoint_b']['name']
            assert set(['Tenet01', 'Tenet03']) != set([ep_a, ep_b]), link

        sdx_api = KYTOS_SDX_API % 'tenet'
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200
        data = response.json()
        links = [link['id'] for link in data['links']]
        assert link_name not in links
    
    def test_081_link_missing_with_alternate_path(self):
        """
        Use case 8: Test Remove Link (because it was deleted by the OXP)
        """
        endp1 = 'Tenet01-eth1'
        endp2 = 'Tenet02-eth1'

        # Get link id
        tenet_api = KYTOS_API % 'tenet'
        api_url_tenet = f'{tenet_api}/topology/v3/links'
        response = requests.get(api_url_tenet)
        assert response.status_code == 200
        data = response.json()
        link_id = None
        for key, value in data['links'].items():
            endpoint_a = value["endpoint_a"]["name"]
            endpoint_b = value["endpoint_b"]["name"]
            if set([endpoint_a, endpoint_b]) == set([endp1, endp2]):
                link_id = key
                link_name = 'urn:sdx:link:tenet.ac.za:Tenet01/1_Tenet02/1'
                break
        assert link_id

        l2vpn_data = self.create_new_l2vpn(vlan='810', node1='Tenet01', node2='Tenet02')
        l2vpn_id = l2vpn_data['id']

        # Get initial topology version
        initial_topology = requests.get(API_URL_TOPO).json()
        initial_version = float(initial_topology["version"])
        links = {link["id"] for link in initial_topology["links"]}
        assert link_name in links

        # Disabling link
        self.net.net.configLinkStatus('Tenet01', 'Tenet02', 'down')
        api_url_disable = f'{api_url_tenet}/{link_id}/disable'
        response = requests.post(api_url_disable)
        assert response.status_code == 201, response.text
    
        # Deleting link
        api_url = f'{api_url_tenet}/{link_id}'
        response = requests.delete(api_url)
        assert response.status_code == 200, response.text
            
        time.sleep(15) 
    
        # Verify topology version increased
        updated_topology = requests.get(API_URL_TOPO).json()
        updated_version = float(updated_topology["version"])
        assert updated_version > initial_version, "Topology version did not increase"

        links = {link["id"]: link for link in updated_topology["links"]}
        assert link_name not in links 

        # Verify L2VPN status is down (alternate path)
        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_response = response.json()
        l2vpn_status = l2vpn_response.get(l2vpn_id).get("status")
        assert l2vpn_status == "up", f"L2VPN status should be up, but is {l2vpn_status}"
    
    @pytest.mark.xfail(reason="Interface could not be deleted. Reason: There is a flow installed,")
    def test_090_port_missing_uni(self):
        """
        Use Case 9: OXPO sends a topology update with a Port missing

        Expected behavior:
        SDX Controller:
        If that Port is a UNI: Change statuses of the services to down.
        """
        
        self.create_new_l2vpn(vlan='900',node1 = 'Tenet01', node2='Tenet03')
        port_id_missing =  'urn:sdx:port:tenet.ac.za:Tenet03:50'
        endp = 'Tenet03-eth50'
        node = self.net.net.get('Tenet03')
        
        response = requests.get(API_URL_TOPO)
        assert response.status_code == 200, response.text
        topology = response.json()
        port_found = False
        for node_ in topology['nodes']:
            if node_['name'] == endp.split('-')[0]:
                port_found = True
                break
        assert port_found

        # Get interfaces
        tenet_api = KYTOS_API % 'tenet'
        api_url_tenet_interface = f'{tenet_api}/topology/v3/interfaces'
        response = requests.get(api_url_tenet_interface)
        assert response.status_code == 200
        data = response.json()
        interfaces_id = None
        for key, value in data['interfaces'].items():
           if endp == value["name"]:
               interfaces_id = key
               break
        assert interfaces_id

        # Disabling interfaces
        node.cmd(f'ip link set dev {endp} down')
        api_url = f'{api_url_tenet_interface}/{interfaces_id}/disable'
        response = requests.post(api_url)
        assert response.status_code == 200, response.text

        # Deleting interfaces
        api_url = f'{api_url_tenet_interface}/{interfaces_id}'
        response = requests.delete(api_url)
        assert response.status_code == 200, response.text
        
        time.sleep(5)
        
        # Force to send the topology to the SDX-LC
        sdx_api = KYTOS_SDX_API % 'tenet'
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200

        # Verify the topology to confirm interface is not listed anymore.
        response = requests.get(API_URL_TOPO)
        assert response.status_code == 200, response.text
        updated_topology = response.json()

        port_found = False
        for node in updated_topology['nodes']:
            if node['name'] == endp.split('-')[0]:
                for port in node['ports']:
                    if port['id'] == port_id_missing:
                        port_found = True
                        break
                if port_found:
                    break
        assert not port_found

    @pytest.mark.xfail(reason="Interface could not be deleted. Reason: There is a flow installed")
    def test_091_port_missing_nni(self):
        """
        Use Case 9: OXPO sends a topology update with a Port missing

        Expected behavior:
        SDX Controller:
        If that Port was a NNI and then it is changed to UNI by just one side, 
        then the SDX Link should have set to status = error and that Link should not be considered a link from the SDX perspective. 
        
        - Remove the link from the topology
        - Handle the link removal as if it was a link down

        """
        self.create_new_l2vpn(vlan='910',node1 = 'Tenet01', node2='Tenet02')
        port_id_missing =  'urn:sdx:port:tenet.ac.za:Tenet02:1'
        endp = 'Tenet02-eth1'
        node = self.net.net.get('Tenet02')
               
        # Get initial topology
        response = requests.get(API_URL_TOPO)
        assert response.status_code == 200, response.text
        initial_topology = response.json()
        port_found_uni = None
        for node_ in initial_topology['nodes']:
            if node_['name'] == endp.split('-')[0]:
                for port in node_['ports']:
                    if port['id'] == port_id_missing:
                        assert port['nni'] != '', port
                        port_found_uni = port
                        break
                if port_found_uni:
                    break
        assert port_found_uni

        # Get interfaces id
        tenet_api = KYTOS_API % 'tenet'
        api_url_tenet_interface = f'{tenet_api}/topology/v3/interfaces'
        response = requests.get(api_url_tenet_interface)
        assert response.status_code == 200
        data = response.json()
        interfaces_id = None
        for key, value in data['interfaces'].items():
           if endp == value["name"]:
               interfaces_id = key
               break
        assert interfaces_id

        # Disabling interfaces
        node.cmd(f'ip link set dev {endp} down')
        api_url = f'{api_url_tenet_interface}/{interfaces_id}/disable'
        response = requests.post(api_url)
        assert response.status_code == 200, response.text
        
        time.sleep(15)
        
        # Deleting link
        api_url_tenet_links = f'{tenet_api}/topology/v3/links'
        response = requests.get(api_url_tenet_links)
        assert response.status_code == 200
        data = response.json()
        links_name = None
        for key, value in data['links'].items():
            endpoint_a = value["endpoint_a"]["name"]
            endpoint_b = value["endpoint_b"]["name"]
            if endp in [endpoint_a, endpoint_b]:
                self.net.net.configLinkStatus(endpoint_a.split('-')[0], endpoint_b.split('-')[0], 'down')
                api_url_disable = f'{api_url_tenet_links}/{key}/disable'
                response = requests.post(api_url_disable)
                assert response.status_code == 201, response.text
                api_url = f'{api_url_tenet_links}/{key}'
                response = requests.delete(api_url)
                assert response.status_code == 200, response.text
                links_name = '_'.join(['/'.join(endpoint_a.split('-')), '/'.join(endpoint_b.split('-'))])
                break
        assert links_name

        # Deleting installed flows
        node.cmd(f'ovs-ofctl del-flows {node.name}')
        result = node.cmd(f'ovs-ofctl dump-flows {node.name}')
        assert result == ''
        
        # Deleting interfaces
        api_url = f'{api_url_tenet_interface}/{interfaces_id}'
        response = requests.delete(api_url)
        assert response.status_code == 200, response.text
        
        time.sleep(5)

        # Force to send the topology to the SDX-LC
        sdx_api = KYTOS_SDX_API % 'tenet'
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200
        
        # Verify the link is removed in the topology
        response = requests.get(API_URL_TOPO)
        assert response.status_code == 200, response.text
        updated_topology = response.json()
        port_found_nni = False
        links = [link['name'] for link in updated_topology['links']]
        for node_ in updated_topology['nodes']:
            if node_['name'] == endp.split('-')[0]:
                for port in node_['ports']:
                    if port['id'] == port_id_missing and port['nni'] == '':
                        assert links_name in links
                        port_found_nni = True
                        break
                if port_found_nni:
                    break
        assert not port_found_nni
    