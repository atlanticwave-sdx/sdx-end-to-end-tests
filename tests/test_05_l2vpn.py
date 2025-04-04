import json
import time
from datetime import datetime, timedelta
import uuid

import pytest
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
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"
        assert response.json() == {}, f"Expected empty dict, got: {response.json()}"

    def test_020_create_l2vpn_successfully(self):
        """Test creating a L2VPN successfully."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request 1",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "300"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "300"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, f"L2VPN creation failed: {response.text}"
        response_json = response.json()
        assert response_json.get("status") == "OK", f"Unexpected status: {response_json}"
        service_id = response_json.get("service_id")
        assert service_id is not None, f"Missing service_id: {response_json}"

        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        response_json = response.json()
        assert len(response_json) == 1, f"Expected 1 L2VPN, got {len(response_json)}: {response_json}"
        assert service_id in response_json, f"Service ID {service_id} not found: {response_json}"

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        # make sure OXPs have the new EVCs
        for oxp in ["ampath", "sax", "tenet"]:
            response = requests.get(f"http://{oxp}:8181/api/kytos/mef_eline/v2/evc/")
            evcs = response.json()
            assert len(evcs) == 1, f"{oxp} expected 1 EVC, got {len(evcs)}: {evcs}"

        evcs = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/").json()
        found = sum(1 for evc in evcs.values() if evc.get("uni_z", {}).get("tag", {}).get("value") == 300)
        assert found == 1, f"Expected one EVC with vlan=300 on uni_z: {evcs}"

    def test_030_create_l2vpn_with_any_vlan(self):
        """Test creating a L2VPN successfully."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request 2",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "any"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "any"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, f"Failed to create L2VPN with vlan=any: {response.text}"
        response_json = response.json()
        assert response_json.get("status") == "OK", f"Unexpected status: {response_json}"
        service_id = response_json.get("service_id")
        assert service_id is not None, f"No service_id in response: {response_json}"

        response = requests.get(api_url)
        response_json = response.json()
        assert len(response_json) == 2, f"Expected 2 L2VPNs, got {len(response_json)}: {response_json}"
        assert service_id in response_json, f"Service ID {service_id} not found in list"

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        for oxp in ["ampath", "sax", "tenet"]:
            evcs = requests.get(f"http://{oxp}:8181/api/kytos/mef_eline/v2/evc/").json()
            assert len(evcs) == 2, f"{oxp} expected 2 EVCs, got {len(evcs)}: {evcs}"

    def test_040_edit_vlan_l2vpn_successfully(self):
        """Test change the vlan of endpoints of an existing L2vpn connection."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        key = list(data.keys())[0]
        current = data[key]

        payload = {
            "name": "New vlan in endpoints",
            "endpoints": [
                {"port_id": current["endpoints"][0]["port_id"], "vlan": "100"},
                {"port_id": current["endpoints"][1]["port_id"], "vlan": "100"}
            ]
        }
        response = requests.patch(f"{api_url}/{key}", json=payload)
        assert response.status_code == 201, f"Patch failed: {response.text}"

        updated = requests.get(api_url).json()[key]
        assert updated["name"] == "New vlan in endpoints", str(updated)
        assert updated["endpoints"][0]["vlan"] == "100", str(updated)
        assert updated["endpoints"][1]["vlan"] == "100", str(updated)

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        # make sure OXPs have the new EVCs
        for oxp, field in [("ampath", "uni_a"), ("tenet", "uni_z")]:
            evcs = requests.get(f"http://{oxp}:8181/api/kytos/mef_eline/v2/evc/").json()
            found = sum(1 for evc in evcs.values() if evc.get(field, {}).get("tag", {}).get("value") == 100)
            assert found == 1, f"{oxp} expected 1 EVC with vlan=100: {evcs}"

    def test_045_edit_port_l2vpn_successfully(self):
        """Test change the port_id of endpoints of an existing L2vpn connection."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        key = list(data.keys())[0]
        current = data[key]

        for i in range(2):
            assert current["endpoints"][i]["port_id"] in [
                "urn:sdx:port:tenet.ac.za:Tenet03:50",
                "urn:sdx:port:ampath.net:Ampath3:50"
            ], f"Unexpected port: {current['endpoints'][i]}"

        payload = {
            "name": "New port_id in endpoints",
            "endpoints": [
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet01:41", "vlan": "100"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:40", "vlan": "100"}
            ]
        }
        response = requests.patch(f"{api_url}/{key}", json=payload)
        assert response.status_code == 201, f"Port patch failed: {response.text}"

        archived = requests.get(api_url + f'/{key}/archived').json()[key]
        assert archived["current_path"][0]["port_id"] == "urn:sdx:port:tenet.ac.za:Tenet01:41", str(archived)
        assert archived["current_path"][-1]["port_id"] == "urn:sdx:port:sax.net:Sax01:40", str(archived)

    def test_050_delete_l2vpn_successfully(self):
        """Test deleting all two L2VPNs successfully."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert len(data) == 2, f"Expected 2 services before delete, got {len(data)}"

        for key in data:
            response = requests.delete(f"{api_url}/{key}")
            assert response.status_code == 200, f"Delete failed for {key}: {response.text}"

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        response = requests.get(api_url)
        assert len(response.json()) == 0, f"L2VPNs not cleared: {response.json()}"

        # make sure OXPs also had their EVC deleted
        for oxp in ["ampath", "sax", "tenet"]:
            evcs = requests.get(f"http://{oxp}:8181/api/kytos/mef_eline/v2/evc/").json()
            assert len(evcs) == 0, f"{oxp} still has EVCs: {evcs}"

    @pytest.mark.xfail(reason="AssertionError: assert ', 0% packet loss, ... 100% packet loss,...'")
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
        h1, h8 = self.net.net.get('h1', 'h8')

        def setup_vlan(vlan, ip1, ip8):
            payload = {
                "name": f"VLAN {vlan}",
                "endpoints": [
                    {"port_id": "urn:sdx:port:ampath.net:Ampath1:50", "vlan": str(vlan)},
                    {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": str(vlan)}
                ]
            }
            response = requests.post(api_url, json=payload)
            assert response.status_code == 201, f"L2VPN setup failed: {response.text}"
            h1.cmd(f"ip link add link {h1.intfNames()[0]} name vlan{vlan} type vlan id {vlan}")
            h1.cmd(f"ip link set up vlan{vlan}")
            h1.cmd(f"ip addr add {ip1}/24 dev vlan{vlan}")
            h8.cmd(f"ip link add link {h8.intfNames()[0]} name vlan{vlan} type vlan id {vlan}")
            h8.cmd(f"ip link set up vlan{vlan}")
            h8.cmd(f"ip addr add {ip8}/24 dev vlan{vlan}")

        setup_vlan(100, "10.1.1.1", "10.1.1.8")
        setup_vlan(101, "10.1.2.1", "10.1.2.8")
        setup_vlan(102, "10.1.3.1", "10.1.3.8")

        def ping(ip): return h1.cmd(f'ping -c4 {ip}')
        result_100 = ping("10.1.1.8")
        result_101 = ping("10.1.2.8")
        result_102 = ping("10.1.3.8")

        self.net.net.configLinkStatus('Ampath1', 'Sax01', 'down')
        time.sleep(15)

        result_100_2 = ping("10.1.1.8")
        result_101_2 = ping("10.1.2.8")
        result_102_2 = ping("10.1.3.8")

        for vlan in [100, 101, 102]:
            h1.cmd(f"ip link del vlan{vlan}")
            h8.cmd(f"ip link del vlan{vlan}")

        assert ', 0% packet loss,' in result_100
        assert ', 0% packet loss,' in result_101
        assert ', 0% packet loss,' in result_102
        assert ', 0% packet loss,' in result_100_2
        # expected fail: result_101_2 and result_102_2

