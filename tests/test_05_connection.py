import json
import re
import time
from datetime import datetime, timedelta
import uuid

import pytest
from random import randrange
import requests

from tests.helpers import NetworkTest

SDX_CONTROLLER = 'http://sdx-controller:8080/SDX-Controller/1.0.0'

class TestE2EConnection:
    net = None

    @classmethod
    def setup_class(cls):
        cls.net = NetworkTest(["amlight", "sax", "tenet"])
        cls.net.wait_switches_connect()
        cls.net.run_setup_topo()

    @classmethod
    def teardown_class(cls):
        cls.net.stop()

    def test_010_list_connections_empty(self):
        """Test if list connections return empty."""
        api_url = SDX_CONTROLLER + '/connections'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        assert response.json() == {}

    def test_020_create_connection_successfully(self):
        """Test creating a connection successfully."""
        api_url = SDX_CONTROLLER + '/connection'
        payload = {
            "id": "1",
            #"id": uuid.uuid4(),
            "name": "Test connection request 1",
            "start_time": "2000-01-23T04:56:07.000Z",
            "end_time": "2000-01-23T04:56:07.000Z",
            "bandwidth_required": 10,
            "latency_required": 300,
            "egress_port": {
                "id": "urn:sdx:port:tenet.ac.za:Tenet03:50",
                "name": "Tenet03:50",
                "node": "urn:sdx:port:tenet.ac.za:Tenet03",
                "status": "up"
            },
            "ingress_port": {
                "id": "urn:sdx:port:ampath.net:Ampath3:50",
                "name": "Ampath3:50",
                "node": "urn:sdx:port:ampath.net:Ampath3",
                "status": "up"
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 200, response.text
        response_json = response.json()
        assert response_json.get("status") == "OK", response_json
        assert response_json.get("connection_id") == "1", response_json

        api_url = SDX_CONTROLLER + '/connections'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        response_json = response.json()
        assert len(response_json) == 1, response_json
        assert "1" in response_json, response_json

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        # make sure OXPs have the new connection
        ## -> amlight
        response = requests.get("http://amlight:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 1, response.json()
        ## -> sax
        response = requests.get("http://sax:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 1, response.json()
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 1, response.json()

    def test_030_create_connection_with_vlan(self):
        """Test creating a connection successfully."""
        api_url = SDX_CONTROLLER + '/connection'
        payload = {
            "id": "2",
            #"id": uuid.uuid4(),
            "name": "Test connection request 2",
            "start_time": "2000-01-23T04:56:07.000Z",
            "end_time": "2000-01-23T04:56:07.000Z",
            "bandwidth_required": 10,
            "latency_required": 300,
            "ingress_port": {
                "id": "urn:sdx:port:ampath.net:Ampath3:50",
                "name": "Ampath3:50",
                "node": "urn:sdx:port:ampath.net:Ampath3",
                "status": "up",
                "vlan_range": 77
            },
            "egress_port": {
                "id": "urn:sdx:port:tenet.ac.za:Tenet03:50",
                "name": "Tenet03:50",
                "node": "urn:sdx:port:tenet.ac.za:Tenet03",
                "status": "up",
                "vlan_range": 66
            },
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 200, response.text
        response_json = response.json()
        assert response_json.get("status") == "OK", response_json
        assert response_json.get("connection_id") == "2", response_json

        api_url = SDX_CONTROLLER + '/connections'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        response_json = response.json()
        assert len(response_json) == 2, response_json
        assert "2" in response_json, response_json

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        # make sure OXPs have the new connection
        ## -> amlight
        response = requests.get("http://amlight:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        assert len(evcs) == 2, evcs
        found = 0
        for evc in evcs.values():
            if evc.get("uni_a", {}).get("tag", {}).get("value") == 77:
                found += 1
            if evc.get("uni_z", {}).get("tag", {}).get("value") == 77:
                found += 1
        assert found == 1, evcs
        ## -> sax
        response = requests.get("http://sax:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 2, response.json()
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        assert len(evcs) == 2, evcs
        found = 0
        for evc in evcs.values():
            if evc.get("uni_a", {}).get("tag", {}).get("value") == 66:
                found += 1
            if evc.get("uni_z", {}).get("tag", {}).get("value") == 66:
                found += 1
        assert found == 1, evcs

    @pytest.mark.xfail
    def test_030_delete_connection_successfully(self):
        """Test deleting a connection successfully."""
        api_url = SDX_CONTROLLER + '/connection/1'
        api_url_connections = SDX_CONTROLLER + '/connections'

        # make sure the connection exists
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        response_json = response.json()
        assert response_json.get("id") == "1", response_json

        # Delete the connection
        response = requests.delete(api_url)
        assert response.status_code == 200, response.text

        # give time to SDX Controller to propagate connection removal to OXPs
        time.sleep(10)

        # Check if the connection was deleted from SDX-Controller
        response = requests.get(api_url)
        assert response.status_code == 404, response.text
        response = requests.get(api_url_connections)
        assert response.status_code == 200, response.text
        assert len(response.json()) == 1

        # make sure OXPs had their connection deleted
        ## -> amlight
        response = requests.get("http://amlight:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 1, response.json()
        ## -> sax
        response = requests.get("http://sax:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 1, response.json()
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 1, response.json()
