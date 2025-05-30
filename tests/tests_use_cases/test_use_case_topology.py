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


class TestTopologyManagement:
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

    @pytest.mark.xfail(reason="Connectivity is not verified with a PING test between hosts after creating an L2VPN")
    def test_010_intra_domain_link_down(self):
        """
        Test Use Case 1: Intra-domain Link Status Change (Down)
        
        Verify that when an intra-domain link goes down:
        - SDX Controller updates the SDX topology with the link status
        - SDX Controller updates affected L2VPN statuses
        - No topology or service changes are made

        When possible, the SDX-Controller can find a path based on the exported topology.
        When not possible, the SDX Controller will only update the L2VPN’s status using the means available.
        """
        
        # Step 1: Get initial topology and create a test L2VPN that uses the intra-domain link
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        initial_topology = response.json()
        
        # Create a L2VPN that will use the intra-domain link
        l2vpn_api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        l2vpn_payload = {
            "name": "Test L2VPN for intra-domain link",
            "endpoints": [
                {
                    "port_id": "urn:sdx:port:tenet.ac.za:Tenet01:50",
                    "vlan": "400",
                },
                {
                    "port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50",
                    "vlan": "400",
                }
            ]
        }
        response = requests.post(l2vpn_api_url, json=l2vpn_payload)
        assert response.status_code == 201, response.text
        l2vpn_id = response.json().get("service_id")

        # Wait for L2VPN to be provisioned
        time.sleep(15)

        response = requests.get(l2vpn_api_url)
        assert response.status_code == 200, response.text
        l2vpn_status = response.json().get(l2vpn_id).get("status")
        assert l2vpn_status == "up", f"L2VPN status should be up, but is {l2vpn_status}"

        h6, h8 = self.net.net.get('h6', 'h8')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')
        h8.cmd('ip link add link %s name vlan100 type vlan id 100' % (h8.intfNames()[0]))
        h8.cmd('ip link set up vlan100')
        h8.cmd('ip addr add 10.1.1.8/24 dev vlan100')

        # test connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.8')
        
        # Step 2: Set an intra-domain link down
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'down')
        
        # Step 3: Wait for topology update to propagate
        time.sleep(15)
        
        # Step 4: Verify topology is updated with link status down
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        updated_topology = response.json()
        
        # Find the specific link in the topology
        intra_domain_link_id = "urn:sdx:link:tenet.ac.za:Tenet01/2_Tenet03/2"
        links = {link["id"]: link for link in updated_topology["links"]}
        assert intra_domain_link_id in links, f"Link {intra_domain_link_id} not found in topology"
        assert links[intra_domain_link_id]["status"] == "down", f"Link status is not down: {links[intra_domain_link_id]}"
        
        # Step 5: Verify L2VPN status is updated to down
        response = requests.get(l2vpn_api_url)
        assert response.status_code == 200, response.text
        l2vpn_status = response.json().get(l2vpn_id).get("status")
        assert l2vpn_status == "down", f"L2VPN status should be down, but is {l2vpn_status}"
        
        # test connectivity
        assert ', 100% packet loss,' in h6.cmd('ping -c4 10.1.1.8')

        # Step 6: Verify no topology changes were made (number of nodes and links should be the same)
        assert len(initial_topology["nodes"]) == len(updated_topology["nodes"]), "Number of nodes changed"
        assert len(initial_topology["links"]) == len(updated_topology["links"]), "Number of links changed"

    @pytest.mark.xfail(reason="Connectivity is not verified with a PING test between hosts after creating an L2VPN")
    def test_011_intra_domain_link_down_path_found(self):
        """
        Test Use Case 1: Intra-domain Link Status Change (Down)
        
        Verify that when an intra-domain link goes down:
        - SDX Controller updates the SDX topology with the link status
        - SDX Controller updates affected L2VPN statuses
        - No topology or service changes are made

        When possible, the SDX-Controller can find a path based on the exported topology.
        When not possible, the SDX Controller will only update the L2VPN’s status using the means available.
        """
        
        # Step 1: Get initial topology and create a test L2VPN that uses the intra-domain link
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        initial_topology = response.json()
        
        # Create a L2VPN that will use the intra-domain link
        l2vpn_api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        l2vpn_payload = {
            "name": "Test L2VPN for intra-domain link",
            "endpoints": [
                {
                    "port_id": "urn:sdx:port:tenet.ac.za:Tenet01:50",
                    "vlan": "400",
                },
                {
                    "port_id": "urn:sdx:port:tenet.ac.za:Tenet02:50",
                    "vlan": "400",
                }
            ]
        }
        response = requests.post(l2vpn_api_url, json=l2vpn_payload)
        assert response.status_code == 201, response.text
        l2vpn_id = response.json().get("service_id")

        # Wait for L2VPN to be provisioned
        time.sleep(15)

        response = requests.get(l2vpn_api_url)
        assert response.status_code == 200, response.text
        l2vpn_status = response.json().get(l2vpn_id).get("status")
        assert l2vpn_status == "up", f"L2VPN status should be up, but is {l2vpn_status}"

        h6, h7 = self.net.net.get('h6', 'h7')
        h6.cmd('ip link add link %s name vlan100 type vlan id 100' % (h6.intfNames()[0]))
        h6.cmd('ip link set up vlan100')
        h6.cmd('ip addr add 10.1.1.6/24 dev vlan100')
        h7.cmd('ip link add link %s name vlan100 type vlan id 100' % (h7.intfNames()[0]))
        h7.cmd('ip link set up vlan100')
        h7.cmd('ip addr add 10.1.1.7/24 dev vlan100')

        # test connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.7')
        
        # Wait for L2VPN to be provisioned
        time.sleep(10)
        
        # Step 2: Set an intra-domain link down
        self.net.net.configLinkStatus('Tenet01', 'Tenet02', 'down')
        
        # Step 3: Wait for topology update to propagate
        time.sleep(15)
        
        # Step 4: Verify topology is updated with link status down
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        updated_topology = response.json()
        
        # Find the specific link in the topology
        intra_domain_link_id = "urn:sdx:link:tenet.ac.za:Tenet01/1_Tenet02/1"
        links = {link["id"]: link for link in updated_topology["links"]}
        assert intra_domain_link_id in links, f"Link {intra_domain_link_id} not found in topology"
        assert links[intra_domain_link_id]["status"] == "down", f"Link status is not down: {links[intra_domain_link_id]}"
        
        # Step 5: Verify L2VPN status is updated to down
        response = requests.get(l2vpn_api_url)
        assert response.status_code == 200, response.text
        l2vpn_status = response.json().get(l2vpn_id).get("status")
        assert l2vpn_status == "up", f"SDX should find another path using links from SAX"
        
        # test connectivity
        assert ', 0% packet loss,' in h6.cmd('ping -c4 10.1.1.7')

        # Step 6: Verify no topology changes were made (number of nodes and links should be the same)
        assert len(initial_topology["nodes"]) == len(updated_topology["nodes"]), "Number of nodes changed"
        assert len(initial_topology["links"]) == len(updated_topology["links"]), "Number of links changed"



