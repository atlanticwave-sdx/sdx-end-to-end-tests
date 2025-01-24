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

class TestE2EReturnCodesEditL2vpn:
    net = None

    @classmethod
    def setup_class(cls):
        cls.net = NetworkTest(["ampath", "sax", "tenet"])
        cls.net.wait_switches_connect()
        cls.net.run_setup_topo()
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        response_json = response.json()
        for l2vpn in response_json:
            response = requests.delete(api_url+f'/{l2vpn}')

    @classmethod
    def teardown_class(cls):
        cls.net.stop()
   
    @classmethod
    def setup_method(cls):
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        response_json = response.json()
        if len(response_json) == 0:
            # Create an L2VPN to edit later
            api_url = SDX_CONTROLLER + '/l2vpn/1.0'
            cls.payload = {
                "name": "Test L2VPN request",
                "endpoints": [
                    {"port_id": "urn:sdx:port:ampath.net:Ampath2:50","vlan": "50"},
                    {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "50"}
                ]
            }
            response = requests.post(api_url, json=cls.payload)
            assert response.status_code == 201, response.text

        response = requests.get(api_url)
        data = response.json()
        cls.key = list(data.keys())[0]

    def test_010_edit_l2vpn_vlan_code201(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Modified
        Edit vlan
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        self.payload['endpoints'][0]['vlan'] = "200"
        self.payload['endpoints'][1]['vlan'] = "200"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 201, response.text

    def test_011_edit_l2vpn_port_id_code201(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Modified
        Edit port_id
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        self.payload['endpoints'][0]['port_id'] = "urn:sdx:port:sax.net:Sax01:50"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 201, response.text

    def test_020_edit_l2vpn_with_vlan_integer_code400(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Wrong vlan: vlan is not a string
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        self.payload['endpoints'][0]['vlan'] = 300
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, response.text

    def test_021_edit_l2vpn_with_vlan_out_of_range_code400(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Wrong vlan: vlan is out of range 1-4095
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        self.payload['endpoints'][0]['vlan'] = 5000
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, response.text

    def test_022_edit_l2vpn_with_vlan_all_code400(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Wrong vlan: since one endpoint has the "all" option, all endpoints must have the same value
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        self.payload['endpoints'][0]['vlan'] = "all"
        self.payload['endpoints'][1]['vlan'] = "any"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, response.text

    def test_023_edit_l2vpn_with_body_incomplete_code400(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Body incomplete: vlan attribute is missing on an endpoint
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "300"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50"}
            ]
        }
        response = requests.patch(f"{api_url}/{self.key}", json=payload)
        assert response.status_code == 400, response.text
            
    def test_024_edit_l2vpn_with_body_incorrect_code400(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Body incorrect: port_id
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath","vlan": "300"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "300"}
            ]
        }
        response = requests.patch(f"{api_url}/{self.key}", json=payload)
        assert response.status_code == 400, response.text
        
    @pytest.mark.xfail(reason="return status 500 -> The server encountered an internal error --- No support for P2MP")
    def test_030_edit_l2vpn_with_p2mp_code402(self):
        """
        Test the return code for creating a SDX L2VPN
        402: Request not compatible (For instance, when a L2VPN P2MP is requested but only L2VPN P2P is supported)P2MP
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN ID 200 at AMPATH, TENET, at SAX", 
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "200"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "200"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "200"}
            ]
        }
        response = requests.patch(f"{api_url}/{self.key}", json=payload)
        assert response.status_code == 402, response.text

    def test_040_edit_l2vpn_not_found_id_code404(self):
        """
        Test the return code for creating a SDX L2VPN
        404: L2VPN Service ID not found
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        key = '11111111-1111-1111-1111-111111111111'
        response = requests.patch(f"{api_url}/{key}", json=self.payload)
        assert response.status_code == 404, response.text

    def test_050_edit_l2vpn_conflict_code409(self):
        """
        Test the return code for creating a SDX L2VPN
        409: Conflicts with a different L2VPN
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        # Create a new l2vpn with similar endpoints to the existing one. Only the vlan varies
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath2:50","vlan": "500"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "500"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        # edit the first l2pvn to match the newly created one
        self.payload['endpoints'][0]['vlan'] = "500"
        self.payload['endpoints'][1]['vlan'] = "500"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 409, response.text

    def test_060_edit_l2vpn_with_min_bw_out_of_range_code410(self):
        """
        Test the return code for creating a SDX L2VPN
        410: Can't fulfill the strict QoS requirements
        Case: min_bw out of range (value must be in [0-100])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        self.payload['qos_metrics'] = {'min_bw':{'value': 101}}
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, response.text

    def test_061_edit_l2vpn_with_max_delay_out_of_range_code410(self):
        """
        Test the return code for creating a SDX L2VPN
        410: Can't fulfill the strict QoS requirements
        Case: max_delay out of range (value must be in [0-1000])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        self.payload['qos_metrics'] = {'max_delay':{'value': 1001}}
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, response.text

    def test_062_edit_l2vpn_with_max_number_oxps_out_of_range_code410(self):
        """
        Test the return code for creating a SDX L2VPN
        410: Can't fulfill the strict QoS requirements
        Case: max_number_oxps out of range (value must be in [0-100])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        self.payload['qos_metrics'] = {'max_number_oxps':{'value': 101}}
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, response.text
    
    @pytest.mark.xfail(reason="return status 400 -> Error: Validation error: '<=' not supported between instances of 'int' and 'NoneType' ")
    def test_072_edit_l2vpn_with_impossible_scheduling_code411(self):
        """
        Test the return code for creating a SDX L2VPN
        411: Scheduling not possible
        end_time before current date
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        self.payload['scheduling'] = {'end_time': "2023-12-31T12:00:00Z"}
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 411, response.text
