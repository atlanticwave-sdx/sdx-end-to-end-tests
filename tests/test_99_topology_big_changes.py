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
        cls.net.run_setup_topo()

    @classmethod
    def teardown_class(cls):
        cls.net.stop()

    def test_040_add_intra_link_check_topology(self):
        """ Add an intra-domain Link and see how SDX controller exports the topology"""
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        len_links_controller = len(data["links"])

        new_link = self.net.net.addLink('Tenet02', 'Tenet03', port1=3, port2=3)
        new_link.intf1.node.attach(new_link.intf1.name)
        new_link.intf2.node.attach(new_link.intf2.name)

        # give time so that messages are propagated
        time.sleep(15)
    
        # Enable interfaces and links
        tenet_topo_api = KYTOS_TOPO_API % 'tenet'
        response = requests.get(f"{tenet_topo_api}/switches")
        assert response.status_code == 200
        switches = response.json()["switches"]

        for sw_id in switches:
            response = requests.post(f"{tenet_topo_api}/switches/{sw_id}/enable")
            assert response.status_code == 201, response.text
            response = requests.post(f"{tenet_topo_api}/interfaces/switch/{sw_id}/enable")
            assert response.status_code == 200, response.text

        time.sleep(10)   # Allow time for Kytos to discover the new link

        response = requests.get(f"{tenet_topo_api}/links")
        assert response.status_code == 200
        links = response.json()["links"]
        for link_id in links:
            response = requests.post(f"{tenet_topo_api}/links/{link_id}/enable")
            assert response.status_code == 201
    
        # give time for Kytos to process topology update
        time.sleep(5)

        sdx_api = KYTOS_SDX_API % 'tenet'
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        assert len(data["links"]) == len_links_controller+1, str(data['links'])
    
    # def test_045_add_inter_link_check_topology(self):
    #    """ Add an inter-domain Link and see how SDX controller exports the topolog"""
    #    api_url = SDX_CONTROLLER + '/topology'
    #    response = requests.get(api_url)
    #    data = response.json()
    #    len_links_controller = len(data['links'])

    #    new_link = self.net.net.addLink('Ampath1', 'Tenet01', port1=42, port2=42)
    #    new_link.intf1.node.attach(new_link.intf1.name)
    #    new_link.intf2.node.attach(new_link.intf2.name)

    #    # give time so that messages are propagated
    #    time.sleep(15)

    #    # Enable interfaces and links -> interdomain ????????? 
    #    """
    #    tenet_topo_api = KYTOS_TOPO_API % 'tenet'
    #    response = requests.get(f"{tenet_topo_api}/switches")
    #    assert response.status_code == 200
    #    tenet_switches = response.json()["switches"]

    #    for sw_id in tenet_switches:
    #        response = requests.post(f"{tenet_topo_api}/switches/{sw_id}/enable")
    #        assert response.status_code == 201, response.text
    #        response = requests.post(f"{tenet_topo_api}/interfaces/switch/{sw_id}/enable")
    #        assert response.status_code == 200, response.text

    #    time.sleep(10)   # Allow time for Kytos to discover the new link

    #    response = requests.get(f"{tenet_topo_api}/links")
    #    assert response.status_code == 200
    #    links = response.json()["links"]
    #    for link_id in links:
    #        response = requests.post(f"{tenet_topo_api}/links/{link_id}/enable")
    #        assert response.status_code == 201
    #    """
    #    # give time so that messages are propagated
    #    time.sleep(30)

    #    response = requests.get(api_url)
    #    data = response.json()
    #    assert len(data['links']) == len_links_controller+1#, str(data['links'])
   
    @pytest.mark.xfail(reason="AssertionError: assert 11 == (11 - 1) -> link is not removed in sdx-controller")
    def test_050_del_intra_link_check_topology(self):
       """ Remove an intra-domain Link and see how SDX controller exports the topology"""
       api_url = SDX_CONTROLLER + '/topology'
       response = requests.get(api_url)
       data = response.json()
    #    print('--------- 1rt from SDX-C')
    #    print(data["links"])
       len_links_controller = len(data['links'])

       sdx_api = KYTOS_SDX_API % 'tenet'
       response = requests.get(f"{sdx_api}/topology/2.0.0")
       data = response.json()
       len_links_kytos_sdx_api = len(data["links"])
    #    print('--------- 1rt from tenet (KYTOS_SDX_API)')
    #    print(data["links"])

       # Get the link_id (Tenet02-Tenet03 if exists)
       tenet_api = KYTOS_API % 'tenet'
       api_url = f'{tenet_api}/topology/v3/links'
       response = requests.get(api_url)
       assert response.status_code == 200
       data = response.json()
       #print('--------- 1rt from tenet (KYTOS_API)')
       #print(data["links"])
       link_id = None
       for key, value in data['links'].items():
           link_id = key
           endpoint_a = value["endpoint_a"]["name"].split('-')[0]
           endpoint_b = value["endpoint_b"]["name"].split('-')[0]
           if endpoint_a in ['Tenet01', 'Tenet02'] and endpoint_b in ['Tenet01', 'Tenet02']:
               break
       assert link_id
       
       # Disabling link
       self.net.net.configLinkStatus(endpoint_a, endpoint_b, 'down')
       api_url = f'{tenet_api}/topology/v3/links/{link_id}/disable'
       response = requests.post(api_url)
       assert response.status_code == 201, response.text

       # Deleting link
       api_url = f'{tenet_api}/topology/v3/links/{link_id}'
       response = requests.delete(api_url)
       assert response.status_code == 200, response.text

       # Verify absence of link
       api_url = f'{tenet_api}/topology/v3/links'
       response = requests.get(api_url)
       assert response.status_code == 200
       data = response.json()
       assert link_id not in data["links"]
       #print('------ link deleted ---------')
       #print(link_id)
       #print('--------- 2nd from tenet (KYTOS_API)')
       #print(data["links"])

       # give time so that messages are propagated
       time.sleep(15)
       
       # Force to send the topology to the SDX-LC
       response = requests.post(f"{sdx_api}/topology/2.0.0")
       assert response.status_code == 200
       response = requests.get(f"{sdx_api}/topology/2.0.0")
       assert response.status_code == 200
       data = response.json()
    #    print('--------- 2nd from tenet (KYTOS_SDX_API)')
    #    print(data["links"])
       assert len(data['links']) == len_links_kytos_sdx_api-1

       # give time so that messages are propagated
       time.sleep(15)
    
       # Verify absence of link with SDX_CONTROLLER
       api_url = SDX_CONTROLLER + '/topology'
       response = requests.get(api_url)
       data = response.json()
    #    print('--------- 2nd from SDX-C')
    #    print(data["links"])
       assert len(data['links']) == len_links_controller-1#, str(data['links'])

    # def test_055_del_inter_link_check_topology(self):
    #    """ Remove an inter-domain Link and see how SDX controller exports the topology"""
    #    api_url = SDX_CONTROLLER + '/topology'
    #    response = requests.get(api_url)
    #    data = response.json()
    #    #print('--------- 1rt from SDX-C')
    #    #print(data["links"])
    #    len_links_controller = len(data['links'])

    #    sdx_api = KYTOS_SDX_API % 'tenet'
    #    response = requests.get(f"{sdx_api}/topology/2.0.0")
    #    data = response.json()
    #    len_links_kytos_sdx_api = len(data["links"])
    #    #print('--------- 1rt from tenet (KYTOS_SDX_API)')
    #    #print(data["links"])

    #    # Get the link_id -> how get an interdomain link_id ?????????
    #    tenet_api = KYTOS_API % 'tenet'
    #    api_url = f'{tenet_api}/topology/v3/links'
    #    response = requests.get(api_url)
    #    assert response.status_code == 200
    #    data = response.json()
    #    #print('--------- 1rt from tenet (KYTOS_API)')
    #    #print(data["links"])
    #    link_id = None
    #    for key, value in data['links'].items():
    #        link_id = key
    #        endpoint_a = value["endpoint_a"]["name"].split('-')[0]
    #        endpoint_b = value["endpoint_b"]["name"].split('-')[0]
    #        if endpoint_a in ['Ampath1', 'Tenet01'] and endpoint_b in ['Ampath1', 'Tenet01']:
    #            break
    #    assert link_id
       
    #    # Disabling link
    #    self.net.net.configLinkStatus(endpoint_a, endpoint_b, 'down')
    #    api_url = f'{tenet_api}/topology/v3/links/{link_id}/disable'
    #    response = requests.post(api_url)
    #    assert response.status_code == 201, response.text

    #    # Deleting link
    #    api_url = f'{tenet_api}/topology/v3/links/{link_id}'
    #    response = requests.delete(api_url)
    #    assert response.status_code == 200, response.text

    #    # Verify absence of link
    #    api_url = f'{tenet_api}/topology/v3/links'
    #    response = requests.get(api_url)
    #    assert response.status_code == 200
    #    data = response.json()
    #    assert link_id not in data["links"]
    #    #print('------ link deleted ---------')
    #    #print(link_id)
    #    #print('--------- 2nd from tenet (KYTOS_API)')
    #    #print(data["links"])

    #    # give time so that messages are propagated
    #    time.sleep(15)
       
    #    # Force to send the topology to the SDX-LC
    #    response = requests.post(f"{sdx_api}/topology/2.0.0")
    #    assert response.status_code == 200
    #    response = requests.get(f"{sdx_api}/topology/2.0.0")
    #    assert response.status_code == 200
    #    data = response.json()
    #    #print('--------- 2nd from tenet (KYTOS_SDX_API)')
    #    #print(data["links"])
    #    assert len(data['links']) == len_links_kytos_sdx_api-1

    #    # give time so that messages are propagated
    #    time.sleep(15)
    
    #    # Verify absence of link with SDX_CONTROLLER
    #    api_url = SDX_CONTROLLER + '/topology'
    #    response = requests.get(api_url)
    #    data = response.json()
    #    #print('--------- 2nd from SDX-C')
    #    #print(data["links"])
    #    assert len(data['links']) == len_links_controller-1#, str(data['links'])

    # def test_060_add_node_check_topology(self):
    #     """ Add a switch and see how SDX controller exports the topology"""
    #     api_url = SDX_CONTROLLER + '/topology'
    #     response = requests.get(api_url)
    #     data = response.json()
    #     len_nodes_controller = len(data["nodes"])

    #     sdx_api = KYTOS_SDX_API % 'tenet'
    #     response = requests.get(f"{sdx_api}/topology/2.0.0")
    #     assert response.status_code == 200
    #     data = response.json()['nodes']
    #     nodes = [node['name'] for node in data]
    #     len_nodes = len(nodes)

    #     sax_sw = self.net.net.addSwitch('Tenet04')
    #     TenetController = self.net.net.get('tenet_ctrl')
    #     tenet_sw.start([TenetController])
    #     Tenet01 = self.net.net.get('Tenet01')
    #     new_link = self.net.net.addLink(Tenet01, tenet_sw, port1=60, port2=60)
    #     new_link.intf1.node.attach(new_link.intf1.name)
    #     new_link.intf2.node.attach(new_link.intf2.name)

    #     # give time so that messages are propagated
    #     time.sleep(15)
    
    #     # Enable interfaces and links
    #     sax_topo_api = KYTOS_TOPO_API % 'tenet'
    #     response = requests.get(f"{sax_topo_api}/switches")
    #     assert response.status_code == 200
    #     switches = response.json()["switches"]

    #     for sw_id in switches:
    #         response = requests.post(f"{sax_topo_api}/switches/{sw_id}/enable")
    #         assert response.status_code == 201, response.text
    #         response = requests.post(f"{sax_topo_api}/interfaces/switch/{sw_id}/enable")
    #         assert response.status_code == 200, response.text

    #     time.sleep(10)   # Allow time for Kytos to discover the new link

    #     response = requests.get(f"{sax_topo_api}/links")
    #     assert response.status_code == 200
    #     links = response.json()["links"]
    #     for link_id in links:
    #         response = requests.post(f"{sax_topo_api}/links/{link_id}/enable")
    #         assert response.status_code == 201
    
    #     # give time for Kytos to process topology update
    #     time.sleep(5)

    #     response = requests.post(f"{sdx_api}/topology/2.0.0")
    #     assert response.status_code == 200
    #     response = requests.get(f"{sdx_api}/topology/2.0.0")
    #     assert response.status_code == 200
    #     data = response.json()['nodes']
    #     nodes = [node['name'] for node in data]
    #     assert len(nodes) == len_nodes+1, str(nodes)

    #     # give time so that messages are propagated
    #     time.sleep(15)

    #     response = requests.get(api_url)
    #     data = response.json()
    #     assert len(data["nodes"]) == len_nodes_controller+1, str(data['nodes'])

    # def test_065_del_node_check_topology(self):
    #    """ Remove a switch and see how SDX controller exports the topology"""
    #    api_url = SDX_CONTROLLER + '/topology'
    #    response = requests.get(api_url)
    #    data = response.json()
    #    len_nodes_controller = len(data['nodes'])

    #    sdx_api = KYTOS_SDX_API % 'ampath'
    #    response = requests.get(f"{sdx_api}/topology/2.0.0")
    #    data = response.json()
    #    len_nodes_kytos_sdx_api = len(data["nodes"])

    #    # Get the switch
    #    ampath_api = KYTOS_API % 'ampath'
    #    api_url = f'{ampath_api}/topology/v3/switches'
    #    response = requests.get(api_url)
    #    assert response.status_code == 200
    #    data = response.json()
    #    switch = None
    #    for key, value in data['switches'].items():
    #        switch = key
    #        if value['data_path'] ==  'Ampath4':
    #            break
    #    assert switch
  
    #    # Disabling switch
    #    api_url = f'{ampath_api}/topology/v3/switches/{switch}/disable'
    #    response = requests.post(api_url)
    #    assert response.status_code == 201

    #    # Get the links
    #    api_url = f'{ampath_api}/topology/v3/links'
    #    response = requests.get(api_url)
    #    assert response.status_code == 200
    #    data = response.json()
    #    links_id = list()
    #    for key, value in data['links'].items():
    #        if (value["endpoint_a"]["switch"] == switch or 
    #            value["endpoint_b"]["switch"] == switch):
    #            links_id.append(key)
    #    assert links_id

    #    for link in links_id:
    #        # Disabling links
    #        api_url = f'{ampath_api}/topology/v3/links/{link}/disable'
    #        response = requests.post(api_url)
    #        assert response.status_code == 201, response.text
    
    #        # Deleting links
    #        api_url = f'{ampath_api}/topology/v3/links/{link}'
    #        response = requests.delete(api_url)
    #        assert response.status_code == 200, response.text

    #    time.sleep(10)
       
    #    # Delete switch
    #    api_url = f'{ampath_api}/topology/v3/switches/{switch}'
    #    response = requests.delete(api_url)
    #    assert response.status_code == 200, response.text

    #    # give time so that messages are propagated
    #    time.sleep(15)
       
    #    # Force to send the topology to the SDX-LC
    #    response = requests.post(f"{sdx_api}/topology/2.0.0")
    #    assert response.status_code == 200
    #    response = requests.get(f"{sdx_api}/topology/2.0.0")
    #    assert response.status_code == 200
    #    data = response.json()
    #    assert len(data['nodes']) == len_nodes_kytos_sdx_api-1

    #    # give time so that messages are propagated
    #    time.sleep(15)
    
    #    # Verify absence of link with SDX_CONTROLLER
    #    api_url = SDX_CONTROLLER + '/topology'
    #    response = requests.get(api_url)
    #    data = response.json()
    #    assert len(data['nodes']) == len_nodes_controller-1#, str(data['links'])

    def test_070_add_port_check_topology(self):
        """ Add a Port (link between two switches) and see how SDX controller exports the topology"""
        api_url = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        len_ports_controller = len(ports)

        sdx_api = KYTOS_SDX_API % 'ampath'
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200
        data = response.json()['nodes']
        ports = {port['name'] for node in data for port in node['ports']}
        len_ports = len(ports)
        
        Ampath1 = self.net.net.get('Ampath1')
        Ampath2 = self.net.net.get('Ampath2')
        new_link = self.net.net.addLink(Ampath1, Ampath2, port1=60, port2=60)
        new_link.intf1.node.attach(new_link.intf1.name)
        new_link.intf2.node.attach(new_link.intf2.name)

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200
        data = response.json()['nodes']
        ports = {port['name'] for node in data for port in node['ports']}
        assert len(ports) == len_ports+2, str(ports)
        assert 'Ampath1-eth60' in ports, str(ports)
        assert 'Ampath2-eth60' in ports, str(ports)

        # give time so that messages are propagated
        time.sleep(15)

        response = requests.get(api_url)
        data = response.json()
        ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
        assert len(ports) == len_ports_controller+2, str(ports)

    # def test_075_del_port_check_topology(self):
    #    """ Remove a Port (link between a nodes) and see how SDX controller exports the topology"""
    #    api_url = SDX_CONTROLLER + '/topology'
    #    response = requests.get(api_url)
    #    data = response.json()
    #    ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
    #    len_ports_controller = len(ports)

    #    sdx_api = KYTOS_SDX_API % 'ampath'
    #    response = requests.get(f"{sdx_api}/topology/2.0.0")
    #    assert response.status_code == 200
    #    data = response.json()['nodes']
    #    ports = {port['name'] for node in data for port in node['ports']}
    #    len_ports = len(ports)
    
    #    # Get the link_id 
    #    ampath_api = KYTOS_API % 'ampath'       
    #    api_url = f'{ampath_api}/topology/v3/links'
    #    response = requests.get(api_url)
    #    assert response.status_code == 200
    #    data = response.json()
    #    link_id = None
    #    for key, value in data['links'].items():
    #        link_id = key
    #        endpoint_a = value["endpoint_a"]["name"].split('-')[0]
    #        endpoint_b = value["endpoint_b"]["name"].split('-')[0]
    #        if endpoint_a in ['Ampath5', 'h10'] and endpoint_b in ['Ampath5', 'h10']:
    #            break
    #    assert link_id
       
    #    # Disabling link
    #    self.net.net.configLinkStatus(endpoint_a, endpoint_b, 'down')
    #    api_url = f'{ampath_api}/topology/v3/links/{link_id}/disable'
    #    response = requests.post(api_url)
    #    assert response.status_code == 201, response.text

    #    # Deleting link
    #    api_url = f'{ampath_api}/topology/v3/links/{link_id}'
    #    response = requests.delete(api_url)
    #    assert response.status_code == 200, response.text

    #    # Verify absence of link
    #    api_url = f'{ampath_api}/topology/v3/links'
    #    response = requests.get(api_url)
    #    assert response.status_code == 200
    #    data = response.json()
    #    assert link_id not in data["links"]

    #    # give time so that messages are propagated
    #    time.sleep(15)
       
    #    # Force to send the topology to the SDX-LC
    #    response = requests.post(f"{sdx_api}/topology/2.0.0")
    #    assert response.status_code == 200
    #    response = requests.get(f"{sdx_api}/topology/2.0.0")
    #    assert response.status_code == 200

    #    # give time so that messages are propagated
    #    time.sleep(15)
    
    #    sdx_api = KYTOS_SDX_API % 'ampath'
    #    response = requests.get(f"{sdx_api}/topology/2.0.0")
    #    assert response.status_code == 200
    #    data = response.json()['nodes']
    #    ports = {port['name'] for node in data for port in node['ports']}
    #    assert len(ports) == len_ports, str(ports)

    #    api_url = SDX_CONTROLLER + '/topology'
    #    response = requests.get(api_url)
    #    data = response.json()
    #    ports = {port["id"]: port for node in data["nodes"] for port in node["ports"]}
    #    assert len(ports) == len_ports_controller-2#, str(ports)
