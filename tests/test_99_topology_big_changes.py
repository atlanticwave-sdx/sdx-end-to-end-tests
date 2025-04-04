import json
import re
import time
from datetime import datetime, timedelta
from pytest_unordered import unordered

import pytest
from random import randrange
import requests

from tests.helpers import NetworkTest

SDX_CONTROLLER = 'http://sdx-controller:8080/SDX-Controller'
KYTOS_TOPO_API = "http://%s:8181/api/kytos/topology/v3"
KYTOS_SDX_API  = "http://%s:8181/api/kytos/sdx"
KYTOS_API = 'http://%s:8181/api/kytos'

class TestE2ETopologyBigChanges:
    net = None

    @classmethod
    def setup_class(cls):
        cls.net = NetworkTest(["ampath", "sax", "tenet"])
        cls.net.wait_switches_connect()

    @classmethod
    def teardown_class(cls):
        cls.net.stop()

    @pytest.mark.xfail(reason="AssertionError")
    def test_040_add_intra_link_check_topology(self):
        """Add intra-domain Link and validate SDX controller topology update"""
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        assert response.status_code == 200, f"Failed to fetch SDX topology: {response.text}"
        initial_links = response.json()["links"]
        len_links_before = len(initial_links)

        # Add intra-domain link in TENET domain
        new_link = self.net.net.addLink('Tenet02', 'Tenet03', port1=3, port2=3)
        new_link.intf1.node.attach(new_link.intf1.name)
        new_link.intf2.node.attach(new_link.intf2.name)

        time.sleep(15)

        # Enable switches/interfaces/links in TENET
        tenet_api = KYTOS_TOPO_API % 'tenet'
        response = requests.get(f"{tenet_api}/switches")
        assert response.status_code == 200, f"Failed to get TENET switches: {response.text}"
        switches = response.json()["switches"]

        for sw_id in switches:
            r1 = requests.post(f"{tenet_api}/switches/{sw_id}/enable")
            r2 = requests.post(f"{tenet_api}/interfaces/switch/{sw_id}/enable")
            assert r1.status_code == 201, f"Failed to enable switch {sw_id}: {r1.text}"
            assert r2.status_code == 200, f"Failed to enable interfaces on {sw_id}: {r2.text}"

        time.sleep(10)

        # Enable newly discovered links
        response = requests.get(f"{tenet_api}/links")
        assert response.status_code == 200, f"Failed to get TENET links: {response.text}"
        for link_id in response.json()["links"]:
            r = requests.post(f"{tenet_api}/links/{link_id}/enable")
            assert r.status_code == 201, f"Failed to enable link {link_id}: {r.text}"

        # Force SDX controller to pull updated topology
        time.sleep(5)
        sdx_api = KYTOS_SDX_API % 'tenet'
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, f"Failed to push topology from TENET to SDX: {response.text}"
        time.sleep(15)

        # Confirm link count increased on SDX controller
        response = requests.get(api_url)
        assert response.status_code == 200, f"Failed to fetch updated SDX topology: {response.text}"
        links_after = response.json()["links"]
        assert len(links_after) == len_links_before + 1, (
            f"Expected {len_links_before + 1} links, found {len(links_after)}: {json.dumps(links_after, indent=2)}"
        )

    @pytest.mark.xfail(reason="AssertionError")
    def test_070_add_port_check_topology(self):
        """
        Add a new port (via link between two switches) and verify SDX controller sees the update.
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        assert response.status_code == 200, f"Failed to get SDX topology: {response.text}"
        controller_data = response.json()
        initial_ports = {
            port["id"]: port
            for node in controller_data["nodes"]
            for port in node["ports"]
        }
        len_ports_controller_before = len(initial_ports)

        # Collect existing ports from KYTOS SDX API
        sdx_api = KYTOS_SDX_API % 'ampath'
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, f"Failed to get AMPATH SDX topology: {response.text}"
        data = response.json()['nodes']
        initial_ports_kytos = {
            port['name'] for node in data for port in node['ports']
        }
        len_ports_kytos_before = len(initial_ports_kytos)

        # Add a link between Ampath1 and Ampath2 on port 60
        Ampath1 = self.net.net.get('Ampath1')
        Ampath2 = self.net.net.get('Ampath2')
        new_link = self.net.net.addLink(Ampath1, Ampath2, port1=60, port2=60)
        new_link.intf1.node.attach(new_link.intf1.name)
        new_link.intf2.node.attach(new_link.intf2.name)

        # Allow topology propagation
        time.sleep(15)

        # Push updated topology to SDX Controller
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, f"Failed to push updated topology to SDX controller: {response.text}"

        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, f"Failed to fetch updated topology from KYTOS: {response.text}"
        updated_kytos_ports = {
            port['name'] for node in response.json()['nodes'] for port in node['ports']
        }
        assert len(updated_kytos_ports) == len_ports_kytos_before + 2, (
            f"Expected {len_ports_kytos_before + 2} ports, got {len(updated_kytos_ports)}"
        )
        assert 'Ampath1-eth60' in updated_kytos_ports, "Port Ampath1-eth60 missing after update"
        assert 'Ampath2-eth60' in updated_kytos_ports, "Port Ampath2-eth60 missing after update"

        # Allow topology sync time
        time.sleep(15)

        # Final check on SDX controller's port count
        response = requests.get(api_url)
        assert response.status_code == 200, f"Failed to get updated SDX topology: {response.text}"
        final_ports = {
            port["id"]: port
            for node in response.json()["nodes"]
            for port in node["ports"]
        }
        assert len(final_ports) == len_ports_controller_before + 2, (
            f"Expected {len_ports_controller_before + 2} ports, got {len(final_ports)}"
        )

    @pytest.mark.xfail(reason="AssertionError")
    def test_040_add_intra_link_check_topology(self):
        """
        Add an intra-domain link and validate SDX controller's topology reflects the update.
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        assert response.status_code == 200, f"Failed to get SDX topology: {response.text}"
        data = response.json()
        len_links_before = len(data["links"])

        # Add new link between Tenet02 and Tenet03
        new_link = self.net.net.addLink('Tenet02', 'Tenet03', port1=3, port2=3)
        new_link.intf1.node.attach(new_link.intf1.name)
        new_link.intf2.node.attach(new_link.intf2.name)
        time.sleep(15)

        # Enable switches, interfaces, and links
        tenet_topo_api = KYTOS_TOPO_API % 'tenet'
        response = requests.get(f"{tenet_topo_api}/switches")
        assert response.status_code == 200, f"Failed to get switches: {response.text}"
        switches = response.json()["switches"]

        for sw_id in switches:
            res_sw = requests.post(f"{tenet_topo_api}/switches/{sw_id}/enable")
            assert res_sw.status_code == 201, f"Switch enable failed: {res_sw.text}"
            res_if = requests.post(f"{tenet_topo_api}/interfaces/switch/{sw_id}/enable")
            assert res_if.status_code == 200, f"Interface enable failed: {res_if.text}"

        time.sleep(10)

        response = requests.get(f"{tenet_topo_api}/links")
        assert response.status_code == 200, f"Failed to get links from Tenet: {response.text}"
        for link_id in response.json()["links"]:
            res_link = requests.post(f"{tenet_topo_api}/links/{link_id}/enable")
            assert res_link.status_code == 201, f"Link enable failed: {res_link.text}"

        time.sleep(5)

        # Push updated topology to SDX Controller
        sdx_api = KYTOS_SDX_API % 'tenet'
        res_push = requests.post(f"{sdx_api}/topology/2.0.0")
        assert res_push.status_code == 200, f"Topology push failed: {res_push.text}"

        time.sleep(15)

        # Verify updated link count
        response = requests.get(api_url)
        assert response.status_code == 200, f"Final SDX topology fetch failed: {response.text}"
        updated_data = response.json()
        assert len(updated_data["links"]) == len_links_before + 1, (
            f"Expected {len_links_before + 1} links, got {len(updated_data['links'])}"
        )

    @pytest.mark.xfail(reason="AssertionError")
    def test_070_add_port_check_topology(self):
        """
        Add a port (via new link between switches) and check SDX controller updates the topology accordingly.
        """
        # Initial fetch from SDX Controller
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        assert response.status_code == 200, f"Failed to fetch SDX topology: {response.text}"
        data = response.json()
        ports_before = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        len_ports_controller = len(ports_before)

        # Get port count from Kytos SDX API
        sdx_api = KYTOS_SDX_API % 'ampath'
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, f"Kytos SDX topology fetch failed: {response.text}"
        nodes = response.json()['nodes']
        ports_before_kytos = {port['name'] for node in nodes for port in node['ports']}
        len_ports_kytos = len(ports_before_kytos)

        # Add new link and attach interfaces
        Ampath1 = self.net.net.get('Ampath1')
        Ampath2 = self.net.net.get('Ampath2')
        new_link = self.net.net.addLink(Ampath1, Ampath2, port1=60, port2=60)
        new_link.intf1.node.attach(new_link.intf1.name)
        new_link.intf2.node.attach(new_link.intf2.name)
        time.sleep(15)

        # Trigger Kytos SDX topology update
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, f"Topology update push failed: {response.text}"

        # Validate new ports in Kytos
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, f"Kytos SDX topology fetch failed post-push: {response.text}"
        data = response.json()['nodes']
        ports_after_kytos = {port['name'] for node in data for port in node['ports']}

        assert len(ports_after_kytos) == len_ports_kytos + 2, (
            f"Expected {len_ports_kytos + 2} ports in Kytos, got {len(ports_after_kytos)}"
        )
        assert 'Ampath1-eth60' in ports_after_kytos, "Port 'Ampath1-eth60' not found in Kytos topology"
        assert 'Ampath2-eth60' in ports_after_kytos, "Port 'Ampath2-eth60' not found in Kytos topology"

        time.sleep(15)

        # Final verification from SDX Controller
        response = requests.get(api_url)
        assert response.status_code == 200, f"Failed to fetch SDX topology (post-port-add): {response.text}"
        data = response.json()
        ports_after = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        assert len(ports_after) == len_ports_controller + 2, (
            f"Expected {len_ports_controller + 2} ports in SDX, got {len(ports_after)}"
        )

