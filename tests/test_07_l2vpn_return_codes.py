import json
import time
from datetime import datetime
import pytest
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
        # Ensure no leftover L2VPNs
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        response = requests.get(api_url)
        assert response.status_code == 200, f"Failed to get L2VPN list: {response.text}"
        for l2vpn_id in response.json():
            del_response = requests.delete(f"{api_url}/{l2vpn_id}")
            assert del_response.status_code in [200, 204], f"Failed to delete L2VPN {l2vpn_id}: {del_response.text}"

    @classmethod
    def teardown_class(cls):
        cls.net.stop()

    @classmethod
    def setup_method(cls):
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        response = requests.get(api_url)
        assert response.status_code == 200, f"Failed to list L2VPNs before setup: {response.text}"
        for l2vpn_id in response.json():
            requests.delete(f"{api_url}/{l2vpn_id}")

        cls.payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        create_response = requests.post(api_url, json=cls.payload)
        assert create_response.status_code == 201, f"L2VPN creation failed: {create_response.text}"

        get_response = requests.get(api_url)
        assert get_response.status_code == 200, f"Failed to retrieve L2VPN after creation: {get_response.text}"
        cls.key = list(get_response.json().keys())[0]

    def test_010_edit_l2vpn_vlan(self):
        """Edit VLAN on both endpoints - expect 201 Created."""
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload['endpoints'][0]['vlan'] = "200"
        self.payload['endpoints'][1]['vlan'] = "200"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 201, f"Expected 201 for VLAN edit, got {response.status_code}: {response.text}"

    def test_011_edit_l2vpn_port_id(self):
        """Edit port_id on one endpoint - expect 201 Created."""
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload['endpoints'][0]['port_id'] = "urn:sdx:port:sax.net:Sax01:50"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 201, f"Expected 201 for port_id edit, got {response.status_code}: {response.text}"

    def test_020_edit_l2vpn_with_vlan_integer(self):
        """Set VLAN as an integer instead of a string - expect 400 Bad Request."""
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload['endpoints'][0]['vlan'] = 300
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, f"Expected 400 for invalid VLAN type, got {response.status_code}: {response.text}"

    def test_021_edit_l2vpn_with_vlan_out_of_range(self):
        """Set VLAN above 4095 - expect 400 Bad Request."""
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload['endpoints'][0]['vlan'] = 5000
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, f"Expected 400 for VLAN out of range, got {response.status_code}: {response.text}"

    def test_022_edit_l2vpn_with_vlan_all(self):
        """
        One endpoint has 'all' VLAN and the other has 'any' — should fail.
        Expect 400: VLAN mismatch when 'all' is used.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload['endpoints'][0]['vlan'] = "all"
        self.payload['endpoints'][1]['vlan'] = "any"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, (
            f"Expected 400 for invalid 'all/any' VLAN combination, got {response.status_code}: {response.text}"
        )

    def test_023_edit_l2vpn_with_missing_vlan(self):
        """
        Missing VLAN on one endpoint — should return 400.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        payload = {
            "name": "Edit L2VPN missing VLAN",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "300"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50"}  # Missing VLAN
            ]
        }
        response = requests.patch(f"{api_url}/{self.key}", json=payload)
        assert response.status_code == 400, (
            f"Expected 400 for missing VLAN on endpoint, got {response.status_code}: {response.text}"
        )

    def test_024_edit_l2vpn_with_body_incorrect(self):
        """
        Incorrect port_id format — should return 400.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        payload = {
            "name": "Edit L2VPN incorrect port_id",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath", "vlan": "300"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "300"}
            ]
        }
        response = requests.patch(f"{api_url}/{self.key}", json=payload)
        assert response.status_code == 400, (
            f"Expected 400 for incorrect port_id format, got {response.status_code}: {response.text}"
        )

    def test_025_edit_l2vpn_with_vlan_negative(self):
        """
        Negative VLAN ID — should return 400.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload['endpoints'][0]['vlan'] = "-100"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, (
            f"Expected 400 for negative VLAN ID, got {response.status_code}: {response.text}"
        )

    def test_026_edit_l2vpn_with_missing_name(self):
        """
        Missing 'name' field — should return 400.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        payload = {
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "500"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "500"}
            ]
        }
        response = requests.patch(f"{api_url}/{self.key}", json=payload)
        assert response.status_code == 400, (
            f"Expected 400 for missing 'name' field, got {response.status_code}: {response.text}"
        )

    def test_027_edit_l2vpn_with_non_existent_port(self):
        """
        Port ID does not exist — should return 400.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload['endpoints'][0]['port_id'] = "urn:sdx:port:ampath.net:InvalidPort:50"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, (
            f"Expected 400 for non-existent port ID, got {response.status_code}: {response.text}"
        )

    def test_028_edit_l2vpn_with_invalid_port_id_format(self):
        """
        Invalid URN format for port ID — should return 400.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload['endpoints'][0]['port_id'] = "urn:sdx:port:ampath.net:Ampath3:xyz"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, (
            f"Expected 400 for invalid port ID format, got {response.status_code}: {response.text}"
        )

    def test_029_edit_l2vpn_with_with_single_endpoint(self):
        """
        Only one endpoint provided — should return 400.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        payload = {
            "name": "Edit L2VPN with single endpoint",
            "endpoints": [
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.patch(f"{api_url}/{self.key}", json=payload)
        assert response.status_code == 400, (
            f"Expected 400 for single endpoint in edit request, got {response.status_code}: {response.text}"
        )

    def test_030_edit_l2vpn_with_p2mp(self):
        """
        Add a third endpoint to make it P2MP — should return 402.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        payload = {
            "name": "Edit L2VPN to P2MP",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "200"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "200"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50", "vlan": "200"}
            ]
        }
        response = requests.patch(f"{api_url}/{self.key}", json=payload)
        assert response.status_code == 402, (
            f"Expected 402 for P2MP request on L2VPN edit, got {response.status_code}: {response.text}"
        )

    def test_040_edit_l2vpn_not_found_id_code404(self):
        """
        Use a nonexistent L2VPN ID — should return 404.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        invalid_key = '11111111-1111-1111-1111-111111111111'
        response = requests.patch(f"{api_url}/{invalid_key}", json=self.payload)
        assert response.status_code == 404, (
            f"Expected 404 for nonexistent L2VPN ID, got {response.status_code}: {response.text}"
        )

    def test_050_edit_l2vpn_conflict(self):
        """
        Create a second L2VPN with different VLAN, then edit the first one to match it — should return 409.
        Conflict due to overlapping services.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"

        # Create a new L2VPN that will cause a conflict
        conflicting_payload = {
            "name": "Conflicting L2VPN",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "500"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "500"}
            ]
        }
        create_response = requests.post(api_url, json=conflicting_payload)
        assert create_response.status_code == 201, (
            f"Expected 201 when creating conflicting L2VPN, got {create_response.status_code}: {create_response.text}"
        )

        # Edit the existing one to match the conflict
        self.payload['endpoints'][0]['vlan'] = "500"
        self.payload['endpoints'][1]['vlan'] = "500"
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 409, (
            f"Expected 409 due to conflict with existing L2VPN, got {response.status_code}: {response.text}"
        )
    @pytest.mark.xfail(reason="return status 410 -> Could not solve the request")
    def test_060_edit_l2vpn_with_min_bw(self):
        """
        Test editing L2VPN with QoS min_bw within allowed range.
        Should return 201 when valid. May fail if value > 10.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        payload = {
            "name": "Edit L2VPN with valid min_bw",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "300"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "300"}
            ],
            "qos_metrics": {"min_bw": {"value": 11}}
        }
        response = requests.patch(f"{api_url}/{self.key}", json=payload)
        assert response.status_code == 201, (
            f"Expected 201 for valid min_bw, got {response.status_code}: {response.text}"
        )

    def test_061_edit_l2vpn_with_max_delay(self):
        """
        Edit max_delay to a valid number in [0-1000].
        Should return 201.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload["qos_metrics"] = {"max_delay": {"value": 10}}
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 201, (
            f"Expected 201 for valid max_delay=10, got {response.status_code}: {response.text}"
        )

    def test_062_edit_l2vpn_with_max_number_oxps(self):
        """
        Edit max_number_oxps with a valid value in [0–100].
        Should return 201.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload["qos_metrics"] = {"max_number_oxps": {"value": 10}}
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 201, (
            f"Expected 201 for valid max_number_oxps=10, got {response.status_code}: {response.text}"
        )

    def test_063_edit_l2vpn_with_min_bw_out_of_range(self):
        """
        Edit min_bw to a value out of range [0-100] → should return 400.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload["qos_metrics"] = {"min_bw": {"value": 101}}
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, (
            f"Expected 400 for min_bw=101 out of range, got {response.status_code}: {response.text}"
        )

    def test_064_edit_l2vpn_with_max_delay_out_of_range(self):
        """
        Edit max_delay to a value > 1000 → should return 400.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload["qos_metrics"] = {"max_delay": {"value": 1001}}
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, (
            f"Expected 400 for max_delay=1001 out of range, got {response.status_code}: {response.text}"
        )

    def test_065_edit_l2vpn_with_max_number_oxps_out_of_range(self):
        """
        Edit max_number_oxps to a value > 100 → should return 400.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload["qos_metrics"] = {"max_number_oxps": {"value": 101}}
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 400, (
            f"Expected 400 for max_number_oxps=101 out of range, got {response.status_code}: {response.text}"
        )

    @pytest.mark.xfail(reason="return status 402 - Error: Validation error: Scheduling advanced reservation is not supported")
    def test_070_edit_l2vpn_with_impossible_scheduling(self):
        """
        Attempt to edit an L2VPN with a scheduling 'end_time' in the past.
        Expected: 411 (or 422 if scheduling is not yet supported).
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        self.payload['scheduling'] = {'end_time': "2023-12-31T12:00:00Z"}
        response = requests.patch(f"{api_url}/{self.key}", json=self.payload)
        assert response.status_code == 422, (
            f"Expected 422 for unsupported scheduling, got {response.status_code}: {response.text}"
        )

