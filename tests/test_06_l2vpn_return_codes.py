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

class TestE2EReturnCodes:
    net = None

    @classmethod
    def setup_class(cls):
        cls.net = NetworkTest(["ampath", "sax", "tenet"])
        cls.net.wait_switches_connect()
        cls.net.run_setup_topo()

    @classmethod
    def teardown_class(cls):
        cls.net.stop()
    
    def test_010_create_l2vpn_with_vlan_id_code201(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with VLAN translation
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/100 and TENET/150",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "150"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
    
    def test_011_create_l2vpn_with_vlan_any_code201(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with option "any"
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/300 and TENET/any",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "300"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "any"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
    
    def test_012_create_l2vpn_with_vlan_range_code201(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with VLAN range
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLANs 10-99 between AMPATH and SAX",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "10:99"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "10:99"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    @pytest.mark.xfail(reason="return status 410 -> PCE error: Can't find a vlan assignment")
    def test_013_create_l2vpn_with_vlan_untagged_code201(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with "untagged" and a VLAN ID
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/400 and TENET/untagged",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "400"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "untagged"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    def test_014_create_l2vpn_with_optional_attributes_code201(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        Example with optional attributes
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/700 and TENET/700",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "700"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "700"}
            ],
            "description": "Example to demonstrate a L2VPN with optional attributes",
            "scheduling": {
                "start_time": "2025-12-31"},
            "qos_metrics": {
                "min_bw": {"value": 5,"strict": False},
                "max_delay": {"value": 150,"strict": True},
                "max_number_oxps": {"value": 3}},
            "notifications": [
                {"email": "user@domain.com"}, 
                {"email": "user2@domain2.com"} 
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    def test_020_create_l2vpn_with_vlan_integer_code400(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Wrong vlan: vlan is not a string
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": 100},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "any"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    @pytest.mark.xfail(reason="return status 410 -> PCE error: Can't find a vlan assignment")
    def test_021_create_l2vpn_with_vlan_out_of_range_code400(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Wrong vlan: vlan is out of range 1-4095
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "5000"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "any"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    @pytest.mark.xfail(reason="return status 410 -> PCE error: Can't find a vlan assignment")
    def test_022_create_l2vpn_with_vlan_all_code400(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Wrong vlan: since one endpoint has the "all" option, all endpoints must have the same value
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "all"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "any"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text
    
    @pytest.mark.xfail(reason="return status 201 -> Connection published")
    def test_023_create_l2vpn_with_body_incomplete_code400(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Body incomplete: vlan attribute is missing on an endpoint
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "500"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_024_create_l2vpn_with_body_incorrect_code400(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Body incorrect: port_id
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath","vlan": "600"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "600"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    @pytest.mark.xfail(reason="return status 500 -> The server encountered an internal error --- No support for P2MP")
    def test_030_create_l2vpn_with_p2mp_code402(self):
        """
        Test the return code for creating a SDX L2VPN
        402: Request not compatible (For instance, when a L2VPN P2MP is requested but only L2VPN P2P is supported)
        P2MP
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
        response = requests.post(api_url, json=payload)
        assert response.status_code == 402, response.text
            
    @pytest.mark.xfail(reason="return status 410 -> PCE error: Can't find a vlan assignment")
    def test_040_create_l2vpn_existing_code409(self):
        """
        Test the return code for creating a SDX L2VPN
        409: L2VPN Service already exists
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between TENET/1000 and SAX/1000", 
            "endpoints": [
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "1000"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "1000"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        time.sleep(30)

        response = requests.post(api_url, json=payload)
        assert response.status_code == 409, response.text

    @pytest.mark.xfail(reason="return status 400 -> Validation error: Strict QoS requirements: 101 min_bw must be between 0 and 1000 -> (0-100?)")
    def test_050_create_l2vpn_with_min_bw_out_of_range_code410(self):
        """
        Test the return code for creating a SDX L2VPN
        410: Can't fulfill the strict QoS requirements
        Case: min_bw out of range (value must be in [0-100])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/2000 and TENET/2000",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "2000"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "2000"}
            ],
            "qos_metrics": {
                "min_bw": {
                    "value": 101
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 410, response.text

    @pytest.mark.xfail(reason="return status 400 -> Validation error: Strict QoS requirements: 1001 max_delay must be between 0 and 1000")
    def test_051_create_l2vpn_with_max_delay_out_of_range_code410(self):
        """
        Test the return code for creating a SDX L2VPN
        410: Can't fulfill the strict QoS requirements
        Case: max_delay out of range (value must be in [0-1000])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/2010 and TENET/2010",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "2010"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "2010"}
            ],
            "qos_metrics": {
                "max_delay": {
                    "value": 1001
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 410, response.text

    @pytest.mark.xfail(reason="return status 400 -> Error: Validation error: '<=' not supported between instances of 'int' and 'NoneType' ")
    def test_052_create_l2vpn_with_max_number_oxps_out_of_range_code410(self):
        """
        Test the return code for creating a SDX L2VPN
        410: Can't fulfill the strict QoS requirements
        Case: max_number_oxps out of range (value must be in [0-100])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/2020 and TENET/2020",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "2020"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "2020"}
            ],
            "qos_metrics": {
                "max_number_oxps": {
                    "value": 101
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 410, response.text

    @pytest.mark.xfail(reason="return status 400 -> Error: Validation error: Scheduling not possible: 2025-01-17 16:01:10.443861+00:00 start_time cannot be before the current time")
    def test_060_create_l2vpn_with_impossible_scheduling_code411(self):
        """
        Test the return code for creating a SDX L2VPN
        411: Scheduling not possible
        end_time before current date
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/2030 and TENET/2030",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "2030"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "2030"}
            ],
            "scheduling": {
                "end_time": "2023-12-30"
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 411, response.text
