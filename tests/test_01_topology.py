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
        assert response.status_code == 204, response.text

        # then we enable the OXPs and topology should be available
        self.net.wait_switches_connect()
        self.net.run_setup_topo()
        
        # give time so that messages are exchanged between components
        time.sleep(15)

        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data != {}, response.text
        assert len(data["nodes"]) == 8, str(data["nodes"])
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        assert len(ports) == 28, str(ports)
        assert len(data["links"]) == 10, str(data["links"])

    def test_015_check_topology_follows_model_2_0_0(self):
        expected_topos = self.net.get_converted_topologies()
        for idx, oxp in enumerate(["ampath", "sax", "tenet"]):
            response = requests.get(f"http://{oxp}:8181/api/kytos/sdx/topology/2.0.0")
            topo = response.json()
            for node in topo["nodes"]:
                node["ports"] = unordered(node["ports"])
            for attr in ["name", "id", "model_version", "nodes", "links", "services"]:
                assert attr in topo, str(topo)
                assert unordered(topo[attr]) == expected_topos[idx][attr], f"fount {attr}={topo[attr]}"

    # @pytest.mark.xfail
    def test_020_set_intra_link_down_check_topology(self):
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        links = {link["id"]: link for link in data["links"]}
        port1 = "urn:sdx:port:ampath.net:Ampath1:1"
        port2 = "urn:sdx:port:ampath.net:Ampath2:1"
        link1 = "urn:sdx:link:ampath.net:Ampath1/1_Ampath2/1"
        assert ports[port1]["status"] == "up", str(ports[port1])
        assert ports[port2]["status"] == "up", str(ports[port2])
        assert links[link1]["status"] == "up", str(links[link1])

        self.net.net.configLinkStatus('Ampath1', 'Ampath2', 'down')

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        assert ports[port1]["status"] == "down", str(ports[port1])
        assert ports[port2]["status"] == "down", str(ports[port2])
        assert links[link1]["status"] == "down", str(links[link1])
