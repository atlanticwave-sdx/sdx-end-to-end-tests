import json
import time
import uuid
import pytest
import requests

from tests.helpers import NetworkTest

SDX_CONTROLLER = 'http://sdx-controller:8080/SDX-Controller'

class TestE2EReturnCodesDeleteL2vpn:
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
        # Cleanup any existing L2VPNs
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, f"Failed to list L2VPNs before test. Response: {response.text}"
        for key in response.json():
            response = requests.delete(f"{api_url}/{key}")
            assert response.status_code in [200, 404], f"Failed to delete L2VPN {key}. Response: {response.text}"
        # Create a baseline L2VPN to use for deletion tests
        cls.payload = {
            "name": "L2VPN-to-delete",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=cls.payload)
        assert response.status_code == 201, f"Failed to create L2VPN for deletion tests. Response: {response.text}"
        cls.l2vpn_id = list(requests.get(api_url).json().keys())[0]

    def test_010_delete_existing_l2vpn(self):
        """ Test deleting an existing L2VPN (200 OK) """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0/{self.l2vpn_id}"
        response = requests.delete(api_url)
        assert response.status_code == 200, f"Expected 200 OK when deleting existing L2VPN, got {response.status_code}: {response.text}"

    def test_020_delete_nonexistent_l2vpn(self):
        """ Test deleting a non-existent L2VPN (404 Not Found) """
        fake_id = str(uuid.uuid4())
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0/{fake_id}"
        response = requests.delete(api_url)
        assert response.status_code == 404, (
            f"Expected 404 Not Found when deleting non-existent L2VPN, got {response.status_code}: {response.text}"
        )

    def test_030_delete_l2vpn_twice(self):
        """ Test deleting the same L2VPN twice (second should return 404) """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0/{self.l2vpn_id}"
        # First delete should succeed
        response = requests.delete(api_url)
        assert response.status_code == 200, (
            f"First delete failed, expected 200 OK, got {response.status_code}: {response.text}"
        )
        # Second delete should fail with 404
        response = requests.delete(api_url)
        assert response.status_code == 404, (
            f"Second delete should return 404 Not Found, got {response.status_code}: {response.text}"
        )

    def test_040_delete_with_invalid_id_format(self):
        """ Test deleting with invalid UUID format (400 Bad Request expected if validated) """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0/not-a-valid-uuid"
        response = requests.delete(api_url)
        assert response.status_code in [400, 404], (
            f"Expected 400 or 404 for invalid UUID format, got {response.status_code}: {response.text}"
        )

    def test_050_delete_l2vpn_conflict_resolution(self):
        """
        Create two L2VPNs and delete one to ensure the other is unaffected.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        payload1 = {
            "name": "Delete Conflict Test A",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath2:50", "vlan": "300"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50", "vlan": "300"}
            ]
        }
        payload2 = {
            "name": "Delete Conflict Test B",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "301"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "301"}
            ]
        }

        response_a = requests.post(api_url, json=payload1)
        assert response_a.status_code == 201, (
            f"Expected 201 when creating L2VPN A, got {response_a.status_code}: {response_a.text}"
        )
        l2vpn_id_a = list(requests.get(api_url).json().keys())[0]

        response_b = requests.post(api_url, json=payload2)
        assert response_b.status_code == 201, (
            f"Expected 201 when creating L2VPN B, got {response_b.status_code}: {response_b.text}"
        )
        l2vpn_id_b = list(requests.get(api_url).json().keys())[1]

        # Delete only L2VPN A
        del_response = requests.delete(f"{api_url}/{l2vpn_id_a}")
        assert del_response.status_code == 200, (
            f"Expected 200 when deleting L2VPN A, got {del_response.status_code}: {del_response.text}"
        )

        # Ensure L2VPN B still exists
        get_response = requests.get(f"{api_url}/{l2vpn_id_b}")
        assert get_response.status_code == 200, (
            f"Expected 200 for L2VPN B after deleting A, got {get_response.status_code}: {get_response.text}"
        )

        # Clean up L2VPN B
        cleanup = requests.delete(f"{api_url}/{l2vpn_id_b}")
        assert cleanup.status_code == 200, (
            f"Expected 200 when cleaning up L2VPN B, got {cleanup.status_code}: {cleanup.text}"
        )

    def test_060_delete_l2vpn_twice(self):
        """
        Try deleting the same L2VPN twice.
        First should return 200, second should return 404.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        payload = {
            "name": "Delete Twice Test",
            "endpoints": [
                {"port_id": "urn:sdx:port:sax.net:Sax01:50", "vlan": "350"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "350"}
            ]
        }

        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, (
            f"Expected 201 when creating L2VPN, got {response.status_code}: {response.text}"
        )
        l2vpn_id = list(requests.get(api_url).json().keys())[0]

        # First deletion
        del_response_1 = requests.delete(f"{api_url}/{l2vpn_id}")
        assert del_response_1.status_code == 200, (
            f"Expected 200 on first deletion, got {del_response_1.status_code}: {del_response_1.text}"
        )

        # Second deletion
        del_response_2 = requests.delete(f"{api_url}/{l2vpn_id}")
        assert del_response_2.status_code == 404, (
            f"Expected 404 on second deletion, got {del_response_2.status_code}: {del_response_2.text}"
        )

    def test_070_delete_l2vpn_after_edit(self):
        """
        Edit an existing L2VPN and then delete it.
        Ensure both operations succeed.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        payload = {
            "name": "Edit then Delete Test",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "400"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50", "vlan": "400"}
            ]
        }

        create_resp = requests.post(api_url, json=payload)
        assert create_resp.status_code == 201, (
            f"Expected 201 when creating L2VPN, got {create_resp.status_code}: {create_resp.text}"
        )
        l2vpn_id = list(requests.get(api_url).json().keys())[0]

        # Edit it
        payload["endpoints"][0]["vlan"] = "401"
        edit_resp = requests.patch(f"{api_url}/{l2vpn_id}", json=payload)
        assert edit_resp.status_code == 201, (
            f"Expected 201 when editing L2VPN, got {edit_resp.status_code}: {edit_resp.text}"
        )

        # Delete it
        delete_resp = requests.delete(f"{api_url}/{l2vpn_id}")
        assert delete_resp.status_code == 200, (
            f"Expected 200 when deleting edited L2VPN, got {delete_resp.status_code}: {delete_resp.text}"
        )

    def test_080_delete_all_l2vpns(self):
        """
        Create multiple L2VPNs, then delete them all and confirm none remain.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"

        # Create multiple L2VPNs
        for i in range(3):
            payload = {
                "name": f"Bulk Delete Test {i}",
                "endpoints": [
                    {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": f"{300 + i}"},
                    {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": f"{300 + i}"}
                ]
            }
            resp = requests.post(api_url, json=payload)
            assert resp.status_code == 201, (
                f"Expected 201 when creating L2VPN #{i}, got {resp.status_code}: {resp.text}"
            )

        # Fetch and delete all
        response = requests.get(api_url)
        assert response.status_code == 200, (
            f"Expected 200 when listing L2VPNs, got {response.status_code}: {response.text}"
        )

        l2vpns = response.json()
        for l2vpn_id in l2vpns:
            del_resp = requests.delete(f"{api_url}/{l2vpn_id}")
            assert del_resp.status_code == 200, (
                f"Expected 200 when deleting L2VPN {l2vpn_id}, got {del_resp.status_code}: {del_resp.text}"
            )

        # Confirm all are deleted
        final_resp = requests.get(api_url)
        assert final_resp.status_code == 200, (
            f"Expected 200 after deletions, got {final_resp.status_code}: {final_resp.text}"
        )
        assert final_resp.json() == {}, "Expected all L2VPNs deleted, but some remain."

    @classmethod
    def teardown_method(cls):
        """
        Ensure no L2VPNs remain after each test to avoid cross-test contamination.
        """
        api_url = f"{SDX_CONTROLLER}/l2vpn/1.0"
        response = requests.get(api_url)
        if response.status_code == 200:
            for l2vpn_id in response.json():
                requests.delete(f"{api_url}/{l2vpn_id}")

