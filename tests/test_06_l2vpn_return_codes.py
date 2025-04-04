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

    @classmethod
    def setup_method(cls):
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, f"Expected 200 OK when retrieving L2VPNs, got {response.status_code}. Response: {response.text}"
        response_json = response.json()
        for l2vpn in response_json:
            response = requests.delete(api_url+f'/{l2vpn}')
    
    def test_010_create_l2vpn(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with VLAN translation
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, f"Expected 201 Created, got {response.status_code}. Response: {response.text}"

    def test_011_create_l2vpn_vlan_translation(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with VLAN translation
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with VLAN translation",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "150"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, f"Expected 201 Created, got {response.status_code}. Response: {response.text}"

    def test_012_create_l2vpn_with_vlan_any(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with option 'any'
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with VLAN any",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "any"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, f"Expected 201 Created, got {response.status_code}. Response: {response.text}"

    def test_013_create_l2vpn_with_vlan_range(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with VLAN range
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with VLANs range",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100:999"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "100:999"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, f"Expected 201 Created, got {response.status_code}. Response: {response.text}"

    def test_014_create_l2vpn_with_vlan_untagged(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with 'untagged' and a VLAN ID
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with VLAN untagged",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "untagged"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, f"Expected 201 Created, got {response.status_code}. Response: {response.text}"

    def test_015_create_l2vpn_with_optional_attributes(self):
        """
        Test the return code for creating a SDX L2VPN
        422: Attribute not supported (scheduling not implemented)
        Example with optional attributes like description, scheduling, QoS, notifications
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with optional attributes",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ],
            "description": "Example to demonstrate a L2VPN with optional attributes",
            "scheduling": {
                "end_time": self._future_date()
            },
            "qos_metrics": {
                "min_bw": {"value": 5, "strict": False},
                "max_delay": {"value": 150, "strict": True},
                "max_number_oxps": {"value": 3}
            },
            "notifications": [
                {"email": "user@domain.com"},
                {"email": "user2@domain2.com"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 422, f"Expected 422 Unprocessable Entity due to unsupported attributes, got {response.status_code}. Response: {response.text}"

    def _future_date(self, isoformat_time=True):
        """
        Generate a future date, 3 months from now, for scheduling attributes.
        Returns ISO 8601 format with time unless specified to return only date.
        """
        current_time = datetime.now()
        year, month = current_time.year, current_time.month
        if month + 3 > 12:
            month = month - 9
            year += 1
        else:
            month += 3
        future_date = datetime(year, month, 1)
        return future_date.strftime('%Y-%m-%dT%H:%M:%SZ') if isoformat_time else future_date.date().isoformat()

    def test_020_create_l2vpn_with_invalid_vlan_type(self):
        """
        Test creating L2VPN with invalid VLAN type (int instead of string)
        400: Bad Request - Invalid type
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Invalid VLAN type",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": 100},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "200"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, f"Expected 400 Bad Request due to non-string VLAN, got {response.status_code}. Response: {response.text}"

    def test_021_create_l2vpn_with_vlan_out_of_range(self):
        """
        Test creating L2VPN with VLAN > 4095
        400: Bad Request - VLAN out of range
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN out of range",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "5000"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, f"Expected 400 Bad Request due to VLAN out of range, got {response.status_code}. Response: {response.text}"

    def test_022_create_l2vpn_with_vlan_negative(self):
        """
        Test creating L2VPN with negative VLAN value
        400: Bad Request - Negative VLAN invalid
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Negative VLAN",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "-100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, f"Expected 400 Bad Request due to negative VLAN, got {response.status_code}. Response: {response.text}"

    def test_023_create_l2vpn_with_vlan_all(self):
        """
        Test creating L2VPN where one endpoint uses 'all' VLAN and the other uses 'any'
        400: Bad Request - VLAN mismatch
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Mismatched VLANs: all vs any",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "all"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "any"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, f"Expected 400 Bad Request for VLAN mismatch, got {response.status_code}. Response: {response.text}"

    def test_024_create_l2vpn_with_missing_vlan(self):
        """
        Test creating L2VPN with missing VLAN key on one endpoint
        400: Bad Request - Incomplete payload
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Missing VLAN",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, f"Expected 400 Bad Request due to missing VLAN, got {response.status_code}. Response: {response.text}"

    def test_025_create_l2vpn_with_body_incorrect(self):
        """
        Test creating L2VPN with incorrect port_id value (malformed)
        400: Bad Request - Invalid port_id format
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Invalid port_id format",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, f"Expected 400 Bad Request due to malformed port_id, got {response.status_code}. Response: {response.text}"

    def test_026_create_l2vpn_with_missing_name(self):
        """
        Test creating L2VPN without a 'name' field
        400: Bad Request - Missing required field
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, f"Expected 400 Bad Request due to missing name, got {response.status_code}. Response: {response.text}"

    def test_027_create_l2vpn_with_non_existent_port(self):
        """
        Test creating L2VPN with a port that doesn't exist in SDX
        400: Bad Request - Port not found
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Non-existent port",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:InvalidPort:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, f"Expected 400 Bad Request for non-existent port, got {response.status_code}. Response: {response.text}"

    def test_028_create_l2vpn_with_invalid_port_id_format(self):
        """
        Test creating L2VPN with invalid URN format in port_id
        400: Bad Request - Malformed port_id
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Malformed port_id format",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:xyz", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, f"Expected 400 Bad Request for malformed port_id, got {response.status_code}. Response: {response.text}"

    def test_029_create_l2vpn_with_single_endpoint(self):
        """
        Test creating L2VPN with only one endpoint
        400: Bad Request - Must provide two endpoints
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Single endpoint only",
            "endpoints": [
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, f"Expected 400 Bad Request for single endpoint, got {response.status_code}. Response: {response.text}"

    def test_030_create_l2vpn_with_p2mp(self):
        """
        Test creating a L2VPN with more than two endpoints (P2MP not supported)
        402: Not Supported - Only P2P is supported
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "P2MP L2VPN test",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 402, f"Expected 402 Not Supported for P2MP request, got {response.status_code}. Response: {response.text}"

    def test_040_create_duplicate_l2vpn(self):
        """
        Test creating a duplicate L2VPN (same name and endpoints)
        First request should return 201, second should return 409
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Duplicate L2VPN",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }

        # First creation should succeed
        response1 = requests.post(api_url, json=payload)
        assert response1.status_code == 201, f"Expected 201 Created, got {response1.status_code}. Response: {response1.text}"

        # Duplicate creation should fail
        response2 = requests.post(api_url, json=payload)
        assert response2.status_code == 409, f"Expected 409 Conflict for duplicate L2VPN, got {response2.status_code}. Response: {response2.text}"

    def test_050_create_l2vpn_with_invalid_json(self):
        """
        Test creating L2VPN with invalid JSON payload
        Simulate by passing plain text instead of JSON
        400: Bad Request - Invalid JSON format
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        headers = {'Content-Type': 'application/json'}
        payload = "this is not a json"

        response = requests.post(api_url, data=payload, headers=headers)
        assert response.status_code == 400, f"Expected 400 Bad Request for invalid JSON body, got {response.status_code}. Response: {response.text}"

    def test_060_create_l2vpn_with_no_body(self):
        """
        Test creating L2VPN with no request body
        400: Bad Request - Missing body
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        headers = {'Content-Type': 'application/json'}

        response = requests.post(api_url, headers=headers)
        assert response.status_code == 400, f"Expected 400 Bad Request for missing body, got {response.status_code}. Response: {response.text}"

    def test_070_create_l2vpn_with_invalid_method(self):
        """
        Test sending a GET request to a POST-only endpoint
        405: Method Not Allowed
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url, data="irrelevant")
        assert response.status_code in [200, 405], f"Expected 405 or 200 depending on controller behavior, got {response.status_code}. Response: {response.text}"

    def test_071_create_l2vpn_with_extra_fields(self):
        """
        Test creating L2VPN with extra unexpected fields in the payload
        201: Should still succeed if extra fields are ignored
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Extra fields test",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "300"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "300"}
            ],
            "extra_field": "should be ignored",
            "another_one": {"nested": True}
        }

        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, f"Expected 201 Created even with extra fields, got {response.status_code}. Response: {response.text}"

