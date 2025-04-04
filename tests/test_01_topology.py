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

class TestE2ETopology:
    net = None

    @classmethod
    def setup_class(cls):
        cls.net = NetworkTest(["ampath", "sax", "tenet"])

    @classmethod
    def teardown_class(cls):
        cls.net.stop()

    def test_010_list_topology(self):
        """Test if the topology was loaded correctly."""
        api_url = SDX_CONTROLLER + '/topology'

        # initially the topology is empty, since no OXP was enabled
        response = requests.get(api_url)
        assert response.status_code == 204, f"Expected 204 but got {response.status_code} - {response.text}"

        # then we enable the OXPs and topology should be available
        self.net.wait_switches_connect()
        self.net.run_setup_topo()

        # give time so that messages are exchanged between components
        time.sleep(15)

        response = requests.get(api_url)
        assert response.status_code == 200, f"Expected 200 but got {response.status_code} - {response.text}"
        data = response.json()
        assert data != {}, f"Expected non-empty topology, got: {response.text}"
        assert len(data["nodes"]) == 8, f"Expected 8 nodes, got: {len(data['nodes'])} - {data['nodes']}"
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        assert len(ports) == 28, f"Expected 28 ports, got: {len(ports)} - {ports}"
        assert len(data["links"]) == 10, f"Expected 10 links, got: {len(data['links'])} - {data['links']}"

    def test_015_check_topology_follows_model_2_0_0(self):
        expected_topos = self.net.get_converted_topologies()
        for idx, oxp in enumerate(["ampath", "sax", "tenet"]):
            response = requests.get(f"http://{oxp}:8181/api/kytos/sdx/topology/2.0.0")
            topo = response.json()
            for node in topo["nodes"]:
                node["ports"] = unordered(node["ports"])
            for attr in ["name", "id", "model_version", "nodes", "links", "services"]:
                assert attr in topo, f"Missing attribute {attr} in topology: {topo}"
                assert unordered(topo[attr]) == expected_topos[idx][attr], f"Mismatch in {attr}: got {topo[attr]}"

    def test_020_set_intra_link_down_check_topology(self):
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        links = {link["id"]: link for link in data["links"]}
        port1 = "urn:sdx:port:ampath.net:Ampath1:1"
        port2 = "urn:sdx:port:ampath.net:Ampath2:1"
        link1 = "urn:sdx:link:ampath.net:Ampath1/1_Ampath2/1"
        assert ports[port1]["status"] == "up", f"Expected port1 up, got: {ports[port1]}"
        assert ports[port2]["status"] == "up", f"Expected port2 up, got: {ports[port2]}"
        assert links[link1]["status"] == "up", f"Expected link up, got: {links[link1]}"

        self.net.net.configLinkStatus('Ampath1', 'Ampath2', 'down')
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        links = {link["id"]: link for link in data["links"]}
        assert ports[port1]["status"] == "down", f"Expected port1 down, got: {ports[port1]}"
        assert ports[port2]["status"] == "down", f"Expected port2 down, got: {ports[port2]}"
        assert links[link1]["status"] == "down", f"Expected link down, got: {links[link1]}"

    def test_025_set_inter_link_down_check_topology(self):
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        links = {link["id"]: link for link in data["links"]}
        port1 = "urn:sdx:port:sax.net:Sax01:41"
        port2 = "urn:sdx:port:tenet.ac.za:Tenet01:41"
        link1 = "urn:sdx:link:interdomain:sax.net:Sax01:41:tenet.ac.za:Tenet01:41"
        assert ports[port1]["status"] == "up", f"Expected port1 up, got: {ports[port1]}"
        assert ports[port2]["status"] == "up", f"Expected port2 up, got: {ports[port2]}"
        assert links[link1]["status"] == "up", f"Expected link up, got: {links[link1]}"

        self.net.net.configLinkStatus('Sax01', 'Tenet01', 'down')
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        links = {link["id"]: link for link in data["links"]}
        assert ports[port1]["status"] == "down", f"Expected port1 down, got: {ports[port1]}"
        assert ports[port2]["status"] == "down", f"Expected port2 down, got: {ports[port2]}"
        assert links[link1]["status"] == "down", f"Expected link down, got: {links[link1]}"

    def test_030_location_change(self):
        """Test Location changes"""
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        version = float(data["version"])

        ampath_ctrl = 'ampath'
        ampath_topo_api = KYTOS_TOPO_API % ampath_ctrl
        response = requests.get(f"{ampath_topo_api}/switches")
        assert response.status_code == 200, f"Failed to get switches: {response.status_code} - {response.text}"
        ampath_switches = response.json()["switches"]
        key = next(iter(ampath_switches))
        item_to_change_id = ampath_switches[key]['id']

        new_metadata = {"lat": "1", "lng": "2", "address": "Miami", "iso3166_2_lvl4": "US-FL"}
        response = requests.post(f"{ampath_topo_api}/switches/{item_to_change_id}/metadata", json=new_metadata)
        assert 200 <= response.status_code < 300, f"Metadata update failed: {response.status_code} - {response.text}"

        sdx_api = KYTOS_SDX_API % ampath_ctrl
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, f"Topology sync failed: {response.status_code} - {response.text}"

        response = requests.get(f"{ampath_topo_api}/switches")
        assert response.status_code == 200, f"Switches fetch failed: {response.status_code} - {response.text}"
        ampath_switches = response.json()["switches"]
        metadata = ampath_switches[item_to_change_id]['metadata']
        assert metadata == new_metadata, f"Metadata mismatch: {metadata}"

        response = requests.get(api_url)
        data = response.json()
        assert version < float(data["version"]), f"Topology version did not increase: old={version}, new={data['version']}"
