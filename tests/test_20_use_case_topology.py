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
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        response_json = response.json()
        for l2vpn in response_json:
            response = requests.delete(api_url+f'/{l2vpn}')
            assert response.status_code == 200, response.text

        # wait for L2VPN to be actually deleted
        time.sleep(2)

        cls.net.config_all_links_up()
        time.sleep(5)  # Allow time for topology to stabilize

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

    @pytest.mark.xfail(reason="The status of the L2VPN doesn't change to down after setting the link to down")
    def test_010_intra_domain_link_down(self):
        """
        Use Case 1: Intra-domain Link Status Change (Down)
        
        Verify that when an intra-domain link goes down:
        - SDX Controller updates the SDX topology with the link status
        - SDX Controller updates affected L2VPN statuses
        - No topology or service changes are made
        
        When possible, the SDX-Controller can find a path based on the exported topology.
        When not possible, the SDX Controller will only update the L2VPN’s status using the means available.
        """
        
        # Step 1: Get initial topology and create a test L2VPN that uses the intra-domain link
        response = requests.get(API_URL_TOPO)
        assert response.status_code == 200, response.text
        initial_topology = response.json()
        
        l2vpn_data = self.create_new_l2vpn(node1='Tenet01',node2='Tenet03')
        l2vpn_id = l2vpn_data['id']
        
        # Step 2: Set an intra-domain link down
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'down')
        
        # Step 3: Wait for topology update to propagate
        time.sleep(10)
        
        # Step 4: Verify topology is updated with link status down
        response = requests.get(API_URL_TOPO)
        assert response.status_code == 200, response.text
        updated_topology = response.json()
        
        # Find the specific link in the topology
        intra_domain_link_id = "urn:sdx:link:tenet.ac.za:Tenet01/2_Tenet03/2"
        links = {link["id"]: link for link in updated_topology["links"]}
        assert intra_domain_link_id in links, f"Link {intra_domain_link_id} not found in topology"
        assert links[intra_domain_link_id]["status"] == "down", f"Link status is not down: {links[intra_domain_link_id]}"
        
        # Step 5: Verify L2VPN status is updated to down
        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_status = response.json().get(l2vpn_id).get("status")
        assert l2vpn_status == "down", f"L2VPN status should be down, but is {l2vpn_status}"
        
        # test connectivity
        assert ', 100% packet loss,' in l2vpn_data['h'].cmd(l2vpn_data['ping_str'])

        # Step 6: Verify no topology changes were made (number of nodes and links should be the same)
        assert len(initial_topology["nodes"]) == len(updated_topology["nodes"]), "Number of nodes changed"
        assert len(initial_topology["links"]) == len(updated_topology["links"]), "Number of links changed"

    @pytest.mark.xfail(reason="Connectivity is not verified with a PING test between hosts after verifying that the L2VPN status remains up")
    def test_011_intra_domain_link_down_path_found(self):
        """
        Use Case 1: Intra-domain Link Status Change (Down)
        
        Verify that when an intra-domain link goes down:
        - SDX Controller updates the SDX topology with the link status
        - SDX Controller updates affected L2VPN statuses
        - No topology or service changes are made

        When possible, the SDX-Controller can find a path based on the exported topology.
        When not possible, the SDX Controller will only update the L2VPN’s status using the means available.
        """
        
        # Step 1: Get initial topology and create a test L2VPN that uses the intra-domain link
        response = requests.get(API_URL_TOPO)
        assert response.status_code == 200, response.text
        initial_topology = response.json()
        
        l2vpn_data = self.create_new_l2vpn(vlan='110',node1='Tenet01',node2='Tenet02')
        l2vpn_id = l2vpn_data['id']
        
        # Step 2: Set an intra-domain link down
        self.net.net.configLinkStatus('Tenet01', 'Tenet02', 'down')
        
        # Step 3: Wait for topology update to propagate
        time.sleep(10)
        
        # Step 4: Verify topology is updated with link status down
        response = requests.get(API_URL_TOPO)
        assert response.status_code == 200, response.text
        updated_topology = response.json()
        
        # Find the specific link in the topology
        intra_domain_link_id = "urn:sdx:link:tenet.ac.za:Tenet01/1_Tenet02/1"
        links = {link["id"]: link for link in updated_topology["links"]}
        assert intra_domain_link_id in links, f"Link {intra_domain_link_id} not found in topology"
        assert links[intra_domain_link_id]["status"] == "down", f"Link status is not down: {links[intra_domain_link_id]}"
        
        # Step 5: Verify L2VPN status is updated to up
        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_status = response.json().get(l2vpn_id).get("status")
        assert l2vpn_status == "up", f"SDX should find another path using links from SAX"
        
        # test connectivity
        assert ', 0% packet loss,' in l2vpn_data['h'].cmd(l2vpn_data['ping_str'])

        # Step 6: Verify no topology changes were made (number of nodes and links should be the same)
        assert len(initial_topology["nodes"]) == len(updated_topology["nodes"]), "Number of nodes changed"
        assert len(initial_topology["links"]) == len(updated_topology["links"]), "Number of links changed"

    def test_020_port_in_inter_domain_link_down(self):
        """ 
        Use case 2: OXPO sends a topology update with a Port Down and that port is part of an inter-domain link.
        """

        l2vpn_data = self.create_new_l2vpn(vlan='200')
        l2vpn_id = l2vpn_data['id']
        
        first_path = l2vpn_data['data']['current_path']

        Ampath1 = self.net.net.get('Ampath1')
        Ampath1.intf('Ampath1-eth40').ifconfig('down') 

        time.sleep(15)

        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_response = response.json().get(l2vpn_id)
        l2vpn_status = l2vpn_response.get("status")
        assert l2vpn_status == "up"
        assert l2vpn_response['current_path'] != first_path

        # test connectivity
        assert ', 0% packet loss,' in l2vpn_data['h'].cmd(l2vpn_data['ping_str'])

        ### Reset 
        Ampath1.intf('Ampath1-eth40').ifconfig('up') 

        time.sleep(15)

        data = requests.get(API_URL).json()
        assert data[l2vpn_id]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in l2vpn_data['h'].cmd(l2vpn_data['ping_str'])

    @pytest.mark.xfail(reason="The L2VPN is removed after changing nodes to down")
    def test_021_port_in_inter_domain_link_down_no_reprov(self):
        """ 
        Use case 2: OXPO sends a topology update with a Port Down and that port is part of an inter-domain link.
        """

        l2vpn_data = self.create_new_l2vpn(vlan='210')
        l2vpn_id = l2vpn_data['id']

        # Port Down: Ampath1-eth40      

        #  Cause no further (re)provisioning to be possible       
        Tenet01, Tenet02 = self.net.net.get('Tenet01', 'Tenet02')
        Tenet01.intf('Tenet01-eth41').ifconfig('down') 
        Tenet02.intf('Tenet02-eth41').ifconfig('down') 

        time.sleep(15)

        response = requests.get(API_URL_TOPO)
        assert response.status_code == 200, response.text
        topology = response.json()
        ports = {p['name']: p['status'] for node in topology['nodes'] for p in node['ports']}
        assert ports['Tenet01-eth41'] == 'down'
        assert ports['Tenet02-eth41'] == 'down'

        data = requests.get(API_URL).json() 

        # test connectivity
        assert ', 100% packet loss,' in l2vpn_data['h'].cmd(l2vpn_data['ping_str'])

        ### Reset
        Tenet01.intf('Tenet01-eth41').ifconfig('up') 
        Tenet02.intf('Tenet02-eth41').ifconfig('up') 

        time.sleep(15)

        response = requests.get(API_URL_TOPO)
        assert response.status_code == 200, response.text
        topology = response.json()
        ports = {p['name']: p['status'] for node in topology['nodes'] for p in node['ports']}
        assert ports['Tenet01-eth41'] == 'up'
        assert ports['Tenet02-eth41'] == 'up'

        assert l2vpn_id in data
        assert data[l2vpn_id]["status"] == "down", str(data)

        data = requests.get(API_URL).json()
        assert data[l2vpn_id]["status"] == "up", str(data)

        # test connectivity
        assert ', 0% packet loss,' in l2vpn_data['h'].cmd(l2vpn_data['ping_str'])

    def test_030_uni_port_down(self):
        """ 
        Use case 3: OXPO sends a topology update with a Port Down and that port is an UNI for some L2VPN.
        """
        l2vpn_data = self.create_new_l2vpn(vlan='300')
        l2vpn_id = l2vpn_data['id']

        # Get UNI ports
        port = 'urn:sdx:port:tenet.ac.za:Tenet01:50'
        response = requests.get(API_URL_TOPO)
        data = response.json()
        ports = {port["id"] for node in data["nodes"] for port in node["ports"] if port['nni'] == ''} 
        assert port in ports

        Tenet01 = self.net.net.get('Tenet01')
        Tenet01.intf('Tenet01-eth50').ifconfig('down') 

        time.sleep(15)

        data = requests.get(API_URL).json()
        assert data[l2vpn_id]["status"] == "down"  

        # test connectivity
        assert ', 100% packet loss,' in l2vpn_data['h'].cmd(l2vpn_data['ping_str'])

        ### Reset 
        Tenet01.intf('Tenet01-eth50').ifconfig('up') 

        time.sleep(15)

        data = requests.get(API_URL).json()
        assert data[l2vpn_id]["status"] == "up"

        # test connectivity
        assert ', 0% packet loss,' in l2vpn_data['h'].cmd(l2vpn_data['ping_str'])

    @pytest.mark.xfail(reason="The L2VPN status remains up after changing the status of an associated node to down")
    def test_040_node_down(self):
        """
        Use Case 4: Node Status Change (Down)
        
        Verify that when a node goes down:
        1. SDX Controller updates the status of the node, its ports, and links
        2. SDX Controller updates affected L2VPN statuses to "error"
        3. SDX Controller refuses to provision new services on the node
        """

        l2vpn_data = self.create_new_l2vpn(vlan='400')
        l2vpn_id = l2vpn_data['id']

        node_name = 'Ampath1'
        node = self.net.net.get(node_name)
        
        config = self.net.change_node_status(node_name)

        time.sleep(15)
        
        # status of the node should be down
        response_topology = requests.get(API_URL_TOPO)

        response_l2vpn = requests.get(API_URL)
        l2vpn_status = response_l2vpn.json()

        # Step 5: Attempt to provision a new L2VPN using the down node
        new_l2vpn_payload = {
            "name": "Test L2VPN for node down - should fail",
            "endpoints": [
                {
                    "port_id": "urn:sdx:port:ampath.net:Ampath1:50",
                    "vlan": "401",
                },
                {
                    "port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50",
                    "vlan": "401",
                }
            ]
        }
        response_newl2vpn = requests.post(API_URL, json=new_l2vpn_payload)

        ### Reset (before any assertion to avoid failures)
        self.net.change_node_status(node_name, config)

        assert response_topology.status_code == 200, response_topology.text
        nodes = response_topology.json().get('nodes', [])
        for n in nodes:
            if n['name'] == node:
                assert n['status'] == "down", f"Node {n['name']} status should be down, but is {n['status']}"
                break

        assert l2vpn_status.get(l2vpn_id).get("status") == "down", str(l2vpn_status)

        assert response_newl2vpn.status_code != 201, str(response_newl2vpn)

        time.sleep(15)

        # status of the node should be up
        response_topology = requests.get(API_URL_TOPO)
        assert response_topology.status_code == 200, response_topology.text
        nodes = response_topology.json().get('nodes', [])
        for n in nodes:
            if n['name'] == node:
                assert n['status'] == "up", f"Node {n['name']} status should be up, but is {n['status']}"
                break

    @pytest.mark.xfail(reason="The L2VPN status remains up after changing the status of an associated port to down")
    def test_050_port_up_inter_domain(self):
        """
        Use Case 5: OXPO sends a topology update with a Port UP and that port is an inter-domain link.

        Expected behavior:
        SDX Controller: if the port UP can benefit the environment (L2VPNs were down because of the lack of paths),
        activate the L2VPNs. If the port is just an addition (a new inter-domain path), do nothing. 
        """
        
        l2vpn_data = self.create_new_l2vpn(vlan='500',node2='Tenet03')
        l2vpn_id = l2vpn_data['id']

        # Bring down a inter-domain port to simulate a scenario where L2VPNs might be down
        # due to lack of paths, then bring it back up.
        Tenet01 = self.net.net.get('Tenet01')
        Tenet01.intf('Tenet01-eth2').ifconfig('down') 

        time.sleep(15)

        # Verify L2VPN status is down after link goes down
        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_response = response.json()
        assert l2vpn_response.get(l2vpn_id).get("status") == "down", "L2VPN status should be down after inter-domain port goes down"

        # Bring the inter-domain port back up
        Tenet01.intf('Tenet01-eth2').ifconfig('up') 

        time.sleep(15)

        # Verify L2VPN status is up after link comes back up
        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_response = response.json()
        assert l2vpn_response.get(l2vpn_id).get("status") == "up", "L2VPN status should be up after inter-domain port comes back up"
        assert ', 0% packet loss,' in l2vpn_data['host1'].cmd(l2vpn_data['ping_str'])

    def test_060_port_up_uni(self):
        """
        Use Case 6: OXPO sends a topology update with a Port UP and that port is UNI for some L2VPNs.

        Expected behavior:
        SDX Controller: update the statuses involved. Use Case 3 is explicit saying the configs should not be removed in case of a Port Down 
        which means the data plane config is already there.
        """
        
        l2vpn_data = self.create_new_l2vpn(vlan='600')
        l2vpn_id = l2vpn_data['id']

        # Simulate UNI port going down
        ampath_node = self.net.net.get('Ampath1')
        ampath_node.intf('Ampath1-eth50').ifconfig('down')

        time.sleep(15)

        # Verify L2VPN status is down
        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_response = response.json()
        assert l2vpn_id in l2vpn_response
        assert l2vpn_response.get(l2vpn_id).get("status") == "down", str(l2vpn_response)

        # Simulate UNI port coming back up
        ampath_node.intf('Ampath1-eth50').ifconfig('up')

        time.sleep(15)

        # Verify L2VPN status is up again
        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_response = response.json()
        assert l2vpn_response.get(l2vpn_id).get("status") == "up", str(l2vpn_response)
        assert ', 0% packet loss,' in l2vpn_data['h'].cmd(l2vpn_data['ping_str'])

    def test_070_port_uni_up_no_l2vpn_associated(self):
        """
            Use case 7: OXPO sends a topology update with a Port UP and that port has no L2VPN associated with it. 
            Expected behavior: For a UNI port, the SDX-Controller does nothing.
        """
        
        port = 'urn:sdx:port:ampath.net:Ampath2:50'
        response = requests.get(API_URL_TOPO)
        data = response.json()
        # Get UNI ports
        ports = {port["id"] for node in data["nodes"] for port in node["ports"] if port['nni'] == ''} 
        assert port in ports

        # Port status to down initially
        Ampath2 = self.net.net.get('Ampath2')
        Ampath2.intf('Ampath2-eth50').ifconfig('down') 
        
        time.sleep(10)

        # Create a L2VPN that is not associated with the port
        l2vpn_data = self.create_new_l2vpn(vlan='700')
        l2vpn_id = l2vpn_data['id']

        path_ports = [p['port_id'] for p in l2vpn_data['data']['current_path']]
        # port is not associated with the L2VPN 
        assert port not in path_ports

        # Update port UP to trigger topology update
        Ampath2.intf('Ampath2-eth50').ifconfig('up') 
        time.sleep(15)

        # Verify no L2VPN was created or modified
        final_data = requests.get(API_URL).json()
        assert final_data[l2vpn_id] == l2vpn_data['data'], "L2VPN state changed unexpectedly"

    @pytest.mark.xfail(reason="The L2VPN with VLAN 1000 remains up even after modifying the VLAN range to [100–200].")
    def test_100_shrinking_vlan_uni(self):
        """
        Use Case 10: OXPO sends a topology update with a changed VLAN range is for any of the services supported.
        """

        l2vpn_data = self.create_new_l2vpn(vlan='1000')
        l2vpn_id = l2vpn_data['id']

        interfaces_id = 'aa:00:00:00:00:00:00:01:50'
        interface_name = 'Ampath1-eth50'
        ampath_api = KYTOS_API % 'ampath'
        api_url_ampath = f'{ampath_api}/topology/v3'
        payload = {
            "sdx_vlan_range": [[100,200]]
        }
        response = requests.post(f"{api_url_ampath}/interfaces/{interfaces_id}/metadata", json=payload)
        assert response.status_code == 201, response.text

        # Force to send the topology to the SDX-LC
        sdx_api = KYTOS_SDX_API % 'ampath'
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, response.text

        time.sleep(15)

        response = requests.get(API_URL_TOPO)
        data = response.json()
        for node in data['nodes']: 
            for port in node['ports']:
                if port['name'] == interface_name:
                    assert port['services']['l2vpn_ptp']['vlan_range'] == [[100,200]], port

        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_response = response.json()
        l2vpn_response = l2vpn_response.get(l2vpn_id)
        assert l2vpn_response.get("status") == "error", l2vpn_response

    @pytest.mark.xfail(reason="l2vpn is created successfully with vlan=1010 even though the vlan_range was changed to [100–200].")
    def test_101_shrinking_vlan_new_l2vpn_with_wrong_vlan(self):
        """
        Use Case 10: OXPO sends a topology update with a changed VLAN range is for any of the services supported.
        """
        
        interfaces_id = 'aa:00:00:00:00:00:00:01:50'
        interface_name = 'Ampath1-eth50'
        ampath_api = KYTOS_API % 'ampath'
        api_url_ampath = f'{ampath_api}/topology/v3'
        payload = {
            "sdx_vlan_range": [[100,200]]
        }
        response = requests.post(f"{api_url_ampath}/interfaces/{interfaces_id}/metadata", json=payload)
        assert response.status_code == 201, response.text

        # Force to send the topology to the SDX-LC
        sdx_api = KYTOS_SDX_API % 'ampath'
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, response.text

        time.sleep(15)

        response = requests.get(API_URL_TOPO)
        data = response.json()
        for node in data['nodes']: 
            for port in node['ports']:
                if port['name'] == interface_name:
                    assert port['services']['l2vpn_ptp']['vlan_range'] == [[100,200]], port

        l2vpn_payload = {
            "name": "Test L2VPN",
            "endpoints": [
                {
                    "port_id": "urn:sdx:port:ampath.net:Ampath1:50",
                    "vlan": "1010",
                },
                {
                    "port_id": "urn:sdx:port:sax.net:Sax01:50",
                    "vlan": "1010",
                }
            ]
        }
        response = requests.post(API_URL, json=l2vpn_payload)
        assert response.status_code == 400, response.text

    @pytest.mark.xfail(reason="The L2VPN path associated with VLAN 1020 remains unchanged after modifying the VLAN range to [100–200]")
    def test_102_shrinking_vlan_nni_with_alternate_path(self):
        """
        Use Case 10: OXPO sends a topology update with a changed VLAN range is for any of the services supported.
        """

        l2vpn_data = self.create_new_l2vpn(vlan='1020')
        l2vpn_id = l2vpn_data['id']

        interfaces_id = 'aa:00:00:00:00:00:00:01:40'
        interface_name = 'Ampath1-eth40'
        ampath_api = KYTOS_API % 'ampath'
        api_url_ampath = f'{ampath_api}/topology/v3'
        payload = {"sdx_vlan_range": [[100,200]]}
        response = requests.post(f"{api_url_ampath}/interfaces/{interfaces_id}/metadata", json=payload)
        assert response.status_code == 201, response.text

        # Force to send the topology to the SDX-LC
        sdx_api = KYTOS_SDX_API % 'ampath'
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, response.text

        time.sleep(15)

        response = requests.get(API_URL_TOPO)
        data = response.json()
        for node in data['nodes']: 
            for port in node['ports']:
                if port['name'] == interface_name:
                    assert port['services']['l2vpn_ptp']['vlan_range'] == [[100,200]], port

        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        l2vpn_response = response.json()
        l2vpn_response = l2vpn_response.get(l2vpn_id)
        assert l2vpn_response.get("status") == "up", l2vpn_response

        current_path = '-'.join(['_'.join(n['port_id'].split(':')[-2:]) for n in l2vpn_response['current_path']])
        assert 'Ampath1_40' not in current_path, current_path

    @pytest.mark.xfail(reason="EVCs from OXPs where L2VPN creation does not fail are not empty")
    def test_120_l2vpn_provisioning_failure(self):
        """
        Tests Use Case 12: L2VPN provisioning fails gracefully when no path exists.

        A L2VPN that spans through three OXPs is requested , and 
        at the installation time everything was going well until one OXP fails to create that breakdown
        To simulate that: instantiate an EVC on the Kytos controller of the OXP using the same vlan 
        """
        # Simulate a control plane failure on tenet: Create an EVC on the Kytos controller of tenet using vlan 1200
        tenet_api = KYTOS_API % 'tenet'
        api_url_tenet_evc = f'{tenet_api}/mef_eline/v2/evc/'
        payload = {
            "name": "Vlan_1200",
            "enabled": True,
            "dynamic_backup_path": True,
            "uni_a": {
                "interface_id": "cc:00:00:00:00:00:00:06:50",
                "tag": {"tag_type": "vlan", "value": 1200}
            },
            "uni_z": {
                "interface_id": "cc:00:00:00:00:00:00:08:50",
                "tag": {"tag_type": "vlan", "value": 1200}
            }
        }
        response = requests.post(api_url_tenet_evc, data=json.dumps(payload), headers={'Content-type': 'application/json'})
        assert response.status_code == 201, response.text

        ampath_api = KYTOS_API % 'ampath'
        ampath_url = ampath_api + '/mef_eline/v2/evc/'
        response = requests.get(ampath_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 0

        sax_api = KYTOS_API % 'sax'
        sax_url = sax_api + '/mef_eline/v2/evc/'
        response = requests.get(sax_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 0

        # Request a L2VPN with vlan 1200
        l2vpn_payload = {
            "name": "Test L2VPN with out-of-range VLAN",
            "endpoints": [
                {
                    "port_id": "urn:sdx:port:ampath.net:Ampath1:50",
                    "vlan": "1200", 
                },
                {
                    "port_id": "urn:sdx:port:tenet.ac.za:Tenet01:50",
                    "vlan": "1200",
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
        assert l2vpn_data.get("status") == 'down', l2vpn_data

        h1, h6 = self.net.net.get('h1', 'h6')
        h1.cmd(f"ip link add link {h1.intfNames()[0]} name vlan1200 type vlan id 1200")
        h1.cmd(f"ip link set up vlan1200")
        h1.cmd(f"ip addr add 10.120.1.1/24 dev vlan1200")
        h6.cmd(f"ip link add link {h6.intfNames()[0]} name vlan1200 type vlan id 1200")
        h6.cmd(f"ip link set up vlan1200")
        h6.cmd(f"ip addr add 10.120.1.6/24 dev vlan1200")

        # test connectivity
        assert ', 100% packet loss,' in h1.cmd(f"ping -c4 10.120.1.6")

        response = requests.get(ampath_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 0, data

        response = requests.get(sax_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 0, data

        response = requests.delete(f"{API_URL}/{l2vpn_id}")
        assert response.status_code == 200, response.text

        response = requests.get(API_URL)
        assert response.status_code == 200, response.text
        assert l2vpn_id not in response.json()

