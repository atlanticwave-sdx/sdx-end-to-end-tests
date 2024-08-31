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
        assert response.status_code == 200, response.text
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
                    "port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50",
                    "vlan": "any",
                },
                {
                    "port_id": "urn:sdx:port:ampath.net:Ampath3:50",
                    "vlan": "any",
                },
            ],
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 200, response.text
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

    def test_030_delete_l2vpn_successfully(self):
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
