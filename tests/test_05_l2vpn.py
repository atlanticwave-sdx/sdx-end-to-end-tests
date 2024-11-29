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

class TestE2EL2VPN:
    net = None

    @classmethod
    def setup_class(cls):
        cls.net = NetworkTest(["ampath", "sax", "tenet"])
        cls.net.wait_switches_connect()
        cls.net.run_setup_topo()

    @classmethod
    def teardown_class(cls):
        cls.net.stop()

    def test_010_list_l2vpn_empty(self):
        """Test if list all L2VPNs return empty."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        assert response.json() == {}

    def test_020_create_l2vpn_successfully(self):
        """Test creating a L2VPN successfully."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request 1",
            "endpoints": [
                {
                    "port_id": "urn:sdx:port:ampath.net:Ampath3:50",
                    "vlan": "300",
                },
                {
                    "port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50",
                    "vlan": "300",
                },
            ],
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        response_json = response.json()
        assert response_json.get("status") == "OK", response_json
        service_id = response_json.get("service_id")
        assert service_id != None, response_json

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        response_json = response.json()
        assert len(response_json) == 1, response_json
        assert service_id in response_json, response_json

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        # make sure OXPs have the new EVCs
        ## -> ampath
        response = requests.get("http://ampath:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        assert len(evcs) == 1, response.text
        found = 0
        for evc in evcs.values():
            if evc.get("uni_a", {}).get("tag", {}).get("value") == 300:
                found += 1
        assert found == 1, evcs
        ## -> sax
        response = requests.get("http://sax:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 1, response.json()
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        assert len(evcs) == 1, response.text
        found = 0
        for evc in evcs.values():
            if evc.get("uni_z", {}).get("tag", {}).get("value") == 300:
                found += 1
        assert found == 1, evcs

    def test_030_create_l2vpn_with_any_vlan(self):
        """Test creating a L2VPN successfully."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request 2",
            "endpoints": [
                {
                    "port_id": "urn:sdx:port:ampath.net:Ampath3:50",
                    "vlan": "any",
                },
                {
                    "port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50",
                    "vlan": "any",
                },
            ],
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        response_json = response.json()
        assert response_json.get("status") == "OK", response_json
        service_id = response_json.get("service_id")
        assert service_id != None, response_json

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        response_json = response.json()
        assert len(response_json) == 2, response_json
        assert service_id in response_json, response_json

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        # make sure OXPs have the new EVCs
        ## -> ampath
        response = requests.get("http://ampath:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 2, response.text
        ## -> sax
        response = requests.get("http://sax:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 2, response.text
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 2, response.text

    def test_040_edit_vlan_l2vpn_successfully(self):
        """Test change the vlan of endpoints of an existing L2vpn connection."""
        
        ## -> ampath
        response = requests.get("http://ampath:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        found = 0
        for evc in evcs.values():
            if evc.get("uni_a", {}).get("tag", {}).get("value") == 100:
                found += 1
        assert found == 0, evcs
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        found = 0
        for evc in evcs.values():
            if evc.get("uni_z", {}).get("tag", {}).get("value") == 100:
                found += 1
        assert found == 0, evcs

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        data = response.json()

        # Change vlan
        key = list(data.keys())[0]
        current_data = data[key]  
        payload = {
            "name": "New vlan in endpoints",
            "endpoints": [
                {
                    "port_id": current_data["endpoints"][0]["port_id"],
                    "vlan": "100",
                },
                {
                    "port_id": current_data["endpoints"][1]["port_id"],
                    "vlan": "100",
                },
            ],
        }
        response = requests.patch(f"{api_url}/{key}", json=payload)
        assert response.status_code == 201, response.text

        response = requests.get(api_url)
        data = response.json()
        current_data = data[key]  
        assert current_data["name"] == "New vlan in endpoints", str(data)
        assert current_data["endpoints"][0]["vlan"] == "100", str(data)
        assert current_data["endpoints"][1]["vlan"] == "100", str(data)

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        # make sure OXPs have the new EVCs

        ## -> ampath
        response = requests.get("http://ampath:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        found = 0
        for evc in evcs.values():
            if evc.get("uni_a", {}).get("tag", {}).get("value") == 100:
                found += 1
        assert found == 1, evcs
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        found = 0
        for evc in evcs.values():
            if evc.get("uni_z", {}).get("tag", {}).get("value") == 100:
                found += 1
        assert found == 1, evcs

    def test_045_edit_port_l2vpn_successfully(self):
        """Test change the port_id of endpoints of an existing L2vpn connection."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        data = response.json()
        key = list(data.keys())[0]
        current_data = data[key]  
        assert current_data["endpoints"][0]["port_id"] in ["urn:sdx:port:tenet.ac.za:Tenet03:50", \
                                                           "urn:sdx:port:ampath.net:Ampath3:50"], str(data)
        assert current_data["endpoints"][1]["port_id"] in ["urn:sdx:port:tenet.ac.za:Tenet03:50", \
                                                           "urn:sdx:port:ampath.net:Ampath3:50"], str(data)
            
        # Change port_id
        payload = {
            "name": "New port_id in endpoints",
            "endpoints": [
                {
                    "port_id": "urn:sdx:port:tenet.ac.za:Tenet01:41",
                },
                {
                    "port_id": "urn:sdx:port:sax.net:Sax01:40",
                },
            ],
        }
        response = requests.patch(f"{api_url}/{key}", json=payload)
        assert response.status_code == 201, response.text

        response = requests.get(api_url + f'/{key}/archived')
        data = response.json()
        current_data = data[key] 
        assert current_data["current_path"][0]["port_id"] == "urn:sdx:port:tenet.ac.za:Tenet01:41", str(data)
        assert current_data["current_path"][-1]["port_id"] == "urn:sdx:port:sax.net:Sax01:40", str(data)

    def test_050_delete_l2vpn_successfully(self):
        """Test deleting all two L2VPNs successfully."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        data = response.json()
        assert len(data) == 2, str(data)

        # Delete all L2VPN
        for key in data:
            response = requests.delete(f"{api_url}/{key}")
            assert response.status_code == 200, response.text

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        # make sure the L2VPNs were deleted from SDX-Controller
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        data = response.json()
        assert len(data) == 0, str(data)
        # make sure OXPs also had their EVC deleted
        ## -> ampath
        response = requests.get("http://ampath:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 0, response.text
        ## -> sax
        response = requests.get("http://sax:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 0, response.text
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 0, response.text
    
    def test_060_link_convergency_with_l2vpn_with_alternative_paths(self):
        """
        Test a simple link convergency with L2VPNs that have alternative paths:
        - Create 3 L2VPN, 
        - test connectivity, 
        - set one link to down, 
        - wait a few seconds for convergency, 
        - test connectivity again
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {"name": "Text", "endpoints":
                   [{"port_id": "urn:sdx:port:ampath.net:Ampath1:50", "vlan": "100",},
                    {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100",},],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        h1, h8 = self.net.net.get('h1', 'h8')
        h1.cmd('ip link add link %s name vlan100 type vlan id 100' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan100')
        h1.cmd('ip addr add 10.1.1.1/24 dev vlan100')
        h8.cmd('ip link add link %s name vlan100 type vlan id 100' % (h8.intfNames()[0]))
        h8.cmd('ip link set up vlan100')
        h8.cmd('ip addr add 10.1.1.8/24 dev vlan100')

        payload = {"name": "Text", "endpoints":
                   [{"port_id": "urn:sdx:port:ampath.net:Ampath1:50", "vlan": "101",},
                    {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "101",},],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        h1.cmd('ip link add link %s name vlan101 type vlan id 101' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan101')
        h1.cmd('ip addr add 10.1.1.1/24 dev vlan101')
        h8.cmd('ip link add link %s name vlan100 type vlan id 101' % (h8.intfNames()[0]))
        h8.cmd('ip link set up vlan101')
        h8.cmd('ip addr add 10.1.1.8/24 dev vlan101')

        payload = {"name": "Text", "endpoints":
                   [{"port_id": "urn:sdx:port:ampath.net:Ampath1:50", "vlan": "102",},
                    {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "102",},],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        h1.cmd('ip link add link %s name vlan102 type vlan id 102' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan102')
        h1.cmd('ip addr add 10.1.1.1/24 dev vlan102')
        h8.cmd('ip link add link %s name vlan102 type vlan id 102' % (h8.intfNames()[0]))
        h8.cmd('ip link set up vlan102')
        h8.cmd('ip addr add 10.1.1.8/24 dev vlan102')

        result = h1.cmd('ping -c4 10.1.1.8')
        assert ', 0% packet loss,' in result

        # link down
        h1.cmd('ip link del vlan102')

        # wait a few seconds for convergency
        time.sleep(30)
        result = h1.cmd('ping -c4 10.1.1.8')
        assert ', 0% packet loss,' in result

        # link down
        h1.cmd('ip link del vlan101')

        # wait a few seconds for convergency
        time.sleep(30)
        result = h1.cmd('ping -c4 10.1.1.8')
        assert ', 0% packet loss,' in result

        # link down
        h1.cmd('ip link del vlan100')

        # wait a few seconds -> there are no links left
        time.sleep(30)
        result = h1.cmd('ping -c4 10.1.1.8')
        assert ', 100% packet loss,' in result
