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
        links = {link["id"]: link for link in data["links"]}
        assert ports[port1]["status"] == "down", str(ports[port1])
        assert ports[port2]["status"] == "down", str(ports[port2])
        assert links[link1]["status"] == "down", str(links[link1])

    def test_020_set_inter_link_down_check_topology(self):
        """ Set one inter-domain links down and see how SDX controller exports the topology"""
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        links = {link["id"]: link for link in data["links"]}
        port1 = "urn:sdx:port:sax.net:Sax01:41"
        port2 = "urn:sdx:port:tenet.ac.za:Tenet01:41"
        link1 = "urn:sdx:link:interdomain:sax.net:Sax01:41:tenet.ac.za:Tenet01:41"
        assert ports[port1]["status"] == "up", str(ports[port1])
        assert ports[port2]["status"] == "up", str(ports[port2])
        assert links[link1]["status"] == "up", str(links[link1])
   
        self.net.net.configLinkStatus('Sax01', 'Tenet01', 'down')

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        links = {link["id"]: link for link in data["links"]}
        assert ports[port1]["status"] == "down", str(ports[port1])
        assert ports[port2]["status"] == "down", str(ports[port2])
        assert links[link1]["status"] == "down", str(links[link1])

    @pytest.mark.skip(reason="Test is currently failing and needs to be addressed.")
    def test_030_add_intra_link_check_topology(self):
        """ Add an intra-domain Link and see how SDX controller exports the topology
            This is failing: requests.get(api_url) obtains the same topology as before addLink
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        len_links_controller = len(links)
        len_links_net = len(self.net.net.links)

        self.net.net.addLink('Tenet02', 'Tenet03', port1=3, port2=3)

        # give time so that messages are propagated
        time.sleep(15)
        
        # Enable interfaces and links
        tenet_ctrl = 'tenet'
        tenet_topo_api = KYTOS_TOPO_API % tenet_ctrl
        response = requests.get(f"{tenet_topo_api}/switches")
        assert response.status_code == 200
        tenet_switches = response.json()["switches"]

        for sw_id in tenet_switches:
            response = requests.post(f"{tenet_topo_api}/switches/{sw_id}/enable")
            assert response.status_code == 201, response.text
            response = requests.post(f"{tenet_topo_api}/interfaces/switch/{sw_id}/enable")
            assert response.status_code == 200, response.text

        time.sleep(10)   # Allow time for Kytos to discover the new link

        response = requests.get(f"{tenet_topo_api}/links")
        assert response.status_code == 200
        tenet_links = response.json()["links"]
        for link_id in tenet_links:
            response = requests.post(f"{tenet_topo_api}/links/{link_id}/enable")
            assert response.status_code == 201
        
        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        assert len(self.net.net.links) == len_links_net+1, str(self.net.net.links)
        assert len(links) == len_links_controller+1, str(data['links']) ### FAIL
    
    @pytest.mark.skip(reason="Test is currently failing and needs to be addressed.")
    def test_030_add_inter_link_check_topology(self):
        """ Add an inter-domain Link and see how SDX controller exports the topology
            This is failing: requests.get(api_url) obtains the same topology as before addLink
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        len_links_controller = len(links)
        len_links_net = len(self.net.net.links)

        self.net.net.addLink('Ampath1', 'Tenet01', port1=42, port2=42)
        
        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        assert len(self.net.net.links) == len_links_net+1, str(self.net.net.links)
        assert len(links) == len_links_controller+1, str(data['links']) ### FAIL
    
    @pytest.mark.skip(reason="Test is currently failing and needs to be addressed.")
    def test_035_del_intra_link_check_topology(self):
        """ Remove an intra-domain Link and see how SDX controller exports the topology
            This is failing: requests.get(api_url) obtains the same topology as before delLinkBetween
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        len_links_net = len(self.net.net.links)
        len_links_controller = len(links)

        link = "urn:sdx:link:ampath.net:Ampath1/1_Ampath2/1"
        assert link in links, str(data["links"])

        node1 = self.net.net.get('Ampath1')
        node2 = self.net.net.get('Ampath2')
        self.net.net.delLinkBetween(node1, node2)

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        assert len(self.net.net.links) == len_links_net-1, str(self.net.net.links)
        assert len(links) == len_links_controller-1, str(data['links']) ### FAIL

    @pytest.mark.skip(reason="Test is currently failing and needs to be addressed.")
    def test_035_del_inter_link_check_topology(self):
        """ Remove an inter-domain Link and see how SDX controller exports the topology
            This is failing: requests.get(api_url) obtains the same topology as before delLinkBetween
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        len_links_net = len(self.net.net.links)
        len_links_controller = len(links)

        link = "urn:sdx:link:interdomain:sax.net:Sax01:41:tenet.ac.za:Tenet01:41"
        assert link in links, str(data["links"])

        node1 = self.net.net.get('Sax01')
        node2 = self.net.net.get('Tenet01')
        self.net.net.delLinkBetween(node1, node2)

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        assert len(self.net.net.links) == len_links_net-1, str(self.net.net.links)
        assert len(links) == len_links_controller-1, str(data['links']) ### FAIL

    @pytest.mark.skip(reason="Test is currently failing and needs to be addressed.")
    def test_040_add_node_check_topology(self):
        """ Add a Node (switch) and see how SDX controller exports the topology.
            This is failing: requests.get(api_url) obtains the same topology as before addSwitch
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        len_nodes_controller = len(data['nodes'])
        len_nodes_net = len(self.net.net.switches)

        self.net.net.addSwitch('Ampath4', listenPort=6604, dpid='aa00000000000004')

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        nodes = {node["name"]: node for node in data["nodes"]}
        assert len(self.net.net.switches) == len_nodes_net+1, str(self.net.net.switches)
        assert len(nodes) == len_nodes_controller+1, str(data['nodes']) ### FAIL
        assert 'Ampath4' in nodes, str(data["nodes"])

    @pytest.mark.skip(reason="Test is currently failing and needs to be addressed.")
    def test_041_add_node_check_topology(self):
        """ Add a Node (host) and see how SDX controller exports the topology.
            This is failing: requests.get(api_url) obtains the same topology as before addHost
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        len_nodes_controller = len(data['nodes'])
        len_nodes_net = len(self.net.net.hosts)

        self.net.net.addHost('h4', mac='00:00:00:00:00:04')

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        nodes = {node["name"]: node for node in data["nodes"]}
        assert len(self.net.net.hosts) == len_nodes_net+1, str(self.net.net.hosts)
        assert len(nodes) == len_nodes_controller+1, str(data['nodes']) ### FAIL

    @pytest.mark.skip(reason="Test is currently failing and needs to be addressed.")
    def test_045_del_node_check_topology(self):
        """ Remove a Node (switch) and see how SDX controller exports the topology.
            This is failing: requests.get(api_url) obtains the same topology as before delNode
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        nodes = {node["name"]: node for node in data["nodes"]}
        len_nodes_controller = len(data['nodes'])
        len_nodes_net = len(self.net.net.switches)

        assert 'Ampath3' in nodes, str(data["nodes"])
        Ampath3 = self.net.net.get('Ampath3')
        self.net.net.delNode(Ampath3)

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        nodes = {node["name"]: node for node in data["nodes"]}
        assert len(self.net.net.switches) == len_nodes_net-1, str(self.net.net.switches)
        assert len(nodes) == len_nodes_controller-1, str(data['nodes'])
        assert 'Ampath3' not in nodes, str(data["nodes"])

    @pytest.mark.skip(reason="Test is currently failing and needs to be addressed.")
    def test_050_add_port_check_topology(self):
        """ Add a Port (link between a host and a switch) and see how SDX controller exports the topology.
            This is failing: requests.get(api_url) obtains the same topology as before addLink
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        len_ports_controller = len(ports)
        ports_net = set()
        for link in self.net.net.links:
            ports_net.add(link.intf1.name)
            ports_net.add(link.intf2.name)
        len_ports_net = len(ports_net)

        # Create one host and one switch
        h9 = self.net.net.addHost('h9', ip='10.0.0.9')
        Ampath5 = self.net.net.addSwitch('Ampath5',listenPort=6605, dpid='aa00000000000005')

        # Add a link between host and switch and create the specific ports
        self.net.net.addLink(h9, Ampath5, port1=1, port2=1)

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        ports_net = set()
        for link in self.net.net.links:
            ports_net.add(link.intf1.name)
            ports_net.add(link.intf2.name)
        assert len(ports_net) == len_ports_net+2, str(self.net.net.ports)
        assert 'h9-eth1' in ports_net, str(ports_net)
        assert 'Ampath5-eth1' in ports_net, str(ports_net)
        assert len(ports) == len_ports_controller+2, str(ports) ### FAIL

    @pytest.mark.skip(reason="Test is currently failing and needs to be addressed.")
    def test_055_del_port_check_topology(self):
        """ Remove a Port (link between a host and a switch) and see how SDX controller exports the topology.
            This is failing: requests.get(api_url) obtains the same topology as before delLinkBetween
        """
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        len_ports_controller = len(ports)
        ports_net = set()
        for link in self.net.net.links:
            ports_net.add(link.intf1.name)
            ports_net.add(link.intf2.name)
        len_ports_net = len(ports_net)

        # Remove a link
        h1 = self.net.net.get('h1')
        Ampath1 = self.net.net.get('Ampath1')
        self.net.net.delLinkBetween(h1, Ampath1)

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        ports_net = set()
        for link in self.net.net.links:
            ports_net.add(link.intf1.name)
            ports_net.add(link.intf2.name)
        assert len(ports_net) == len_ports_net-2, str(self.net.net.ports)
        assert 'h1-eth1' not in ports_net, str(ports_net)
        assert 'Ampath1-eth50' not in ports_net, str(ports_net)
        assert len(ports) == len_ports_controller-2, str(ports) ### FAIL

    @pytest.mark.xfail(reason="Version has to change.")
    def test_060_location_change(self):
        """Test Location changes""" 
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        version = float(data["version"])

        ampath_ctrl = 'ampath'
        ampath_topo_api = KYTOS_TOPO_API % ampath_ctrl
        response = requests.get(f"{ampath_topo_api}/switches")
        assert response.status_code == 200
        tenet_switches = response.json()["switches"]
        key = next(iter(tenet_switches))
        item_to_change_id = tenet_switches[key]['id']

        new_metadata = {"lat": "1", "lng": "2", "address": "New", "iso3166_2_lvl4": "New"}
        response = requests.post(f"{ampath_topo_api}/switches/{item_to_change_id}/metadata", json=new_metadata)
        assert 200 <= response.status_code < 300, response.text

        # give time so that messages are propagated
        time.sleep(15)
    
        response = requests.get(f"{ampath_topo_api}/switches")
        assert response.status_code == 200
        tenet_switches = response.json()["switches"]
        metadata = tenet_switches[item_to_change_id]['metadata']
        assert metadata == new_metadata, str(metadata)

        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        assert float(data["version"]) < version, str(data['version']) # NO CHANGE - has to change 
