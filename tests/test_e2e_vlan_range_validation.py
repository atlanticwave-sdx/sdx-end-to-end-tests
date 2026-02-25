import time
import pytest
import requests

from tests.helpers import NetworkTest

# Base URLs
SDX_CONTROLLER = "http://sdx-controller:8080/SDX-Controller"
KYTOS_API = "http://%s:8181/api/kytos"
KYTOS_SDX_API = KYTOS_API + "/sdx"
KYTOS_TOPO_API = KYTOS_API + "/topology/v3"
MEF_ELINE_API = KYTOS_API + "/mef_eline/v2/evc/"


def _parse_vlan_range(vlan_range_list):
    """
    Parse a list of VLAN range strings.
    into a flat set of individual VLAN IDs.
    """
    vlans = set()
    for entry in vlan_range_list:
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            start, end = int(entry[0]), int(entry[1])
            vlans.update(range(start, end + 1))
        elif isinstance(entry, str) and "-" in entry:
            start, end = entry.split("-")
            vlans.update(range(int(start), int(end) + 1))
        else:
            vlans.add(int(entry))
    return vlans

class TestE2EVlanRangeValidation:
    """
    kytos-sdx must validate (and subtract already-reserved VLANs from) the
    port vlan_range BEFORE exporting the topology to SDX-LC. If a VLAN is
    already in use by an active EVC on a port, that VLAN must NOT appear in
    the vlan_range advertised to SDX-LC/SDX-Controller.

    Failure to do this causes the SDX-Controller and PCE to believe a VLAN
    is available when it is not, leading to provisioning failures.

    All tests follow the same pattern:
      1. Create one or more L2VPNs to occupy specific VLANs on a port.
      2. Force kytos-sdx to re-export the topology.
      3. Verify that the occupied VLANs are absent from the port's vlan_range
         in both the kytos-sdx topology export and the SDX-Controller topology.
      4. Verify that the remaining vlan_range is still valid and contiguous.
    """

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
        """Delete all existing L2VPNs before each test."""
        api_url = SDX_CONTROLLER + "/l2vpn/1.0"
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        for l2vpn_id in response.json():
            del_resp = requests.delete(f"{api_url}/{l2vpn_id}")
            assert del_resp.status_code == 200, del_resp.text
        time.sleep(2)

    def _force_topology_export(self, oxp):
        """Trigger kytos-sdx to re-export the topology to SDX-LC."""
        sdx_api = KYTOS_SDX_API % oxp
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, (
            f"Failed to trigger topology export on {oxp}: {response.text}"
        )
        time.sleep(5)

    def _get_kytos_sdx_port(self, oxp, port_name):
        """
        Return the port dict from kytos-sdx topology export for the given
        port name.
        """
        sdx_api = KYTOS_SDX_API % oxp
        response = requests.get(f"{sdx_api}/topology/2.0.0")
        assert response.status_code == 200, response.text
        topo = response.json()
        for node in topo.get("nodes", []):
            for port in node.get("ports", []):
                if port.get("name") == port_name:
                    return port
        return None

    def _get_sdx_controller_port(self, port_id):
        """
        Return the port dict from SDX-Controller topology for the given
        port.
        """
        response = requests.get(SDX_CONTROLLER + "/topology")
        assert response.status_code == 200, response.text
        topo = response.json()
        for node in topo.get("nodes", []):
            for port in node.get("ports", []):
                if port.get("id") == port_id:
                    return port
        return None

    @pytest.mark.xfail(strict=True)
    def test_010_vlan_range_excludes_used_vlan_after_l2vpn_creation(self):
        """
        After creating an L2VPN that uses VLAN 100 on Ampath3:50, the
        kytos-sdx topology export must NOT include VLAN 100 in the
        vlan_range of that port.
        """
        l2vpn_api = SDX_CONTROLLER + "/l2vpn/1.0"
        vlan = "100"
        port_name = "Ampath3-eth50"
        port_id = "urn:sdx:port:ampath.net:Ampath3:50"
        oxp = "ampath"

        # Create L2VPN to occupy VLAN 100 on Ampath3:50
        payload = {
            "name": "Test vlan_range validation after L2VPN creation",
            "endpoints": [
                {"port_id": port_id, "vlan": vlan},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": vlan},
            ],
        }
        response = requests.post(l2vpn_api, json=payload)
        assert response.status_code == 201, response.text
        service_id = response.json()["service_id"]

        time.sleep(5)

        # Confirm L2VPN is up
        response = requests.get(f"{l2vpn_api}/{service_id}")
        assert response.status_code == 200, response.text
        assert response.json()[service_id]["status"] == "up"

        # Force re-export of the topology from the ampath OXP
        self._force_topology_export(oxp)

        # --- Check kytos-sdx topology export ---
        port = self._get_kytos_sdx_port(oxp, port_name)
        assert port is not None, (
            f"Port {port_name} not found in kytos-sdx topology export for {oxp}"
        )
        services = port.get("services", {})
        l2vpn_ptp = services.get("l2vpn-ptp", {})
        vlan_range_raw = l2vpn_ptp.get("vlan_range", [])
        assert vlan_range_raw, (
            f"vlan_range is empty or missing for {port_name} in kytos-sdx export"
        )
        available_vlans = _parse_vlan_range(vlan_range_raw)
        assert int(vlan) not in available_vlans, (
            f"VLAN {vlan} is in use by an active EVC on {port_name} but is still "
            f"present in the kytos-sdx vlan_range export: {vlan_range_raw}. "
            f"This is the bug described in kytos-sdx issue #93."
        )

        # --- Check SDX-Controller topology ---
        sdx_port = self._get_sdx_controller_port(port_id)
        assert sdx_port is not None, (
            f"Port {port_id} not found in SDX-Controller topology"
        )
        sdx_services = sdx_port.get("services", {})
        sdx_vlan_range_raw = sdx_services.get("l2vpn-ptp", {}).get("vlan_range", [])
        if sdx_vlan_range_raw:
            sdx_available_vlans = _parse_vlan_range(sdx_vlan_range_raw)
            assert int(vlan) not in sdx_available_vlans, (
                f"VLAN {vlan} is in use on {port_id} but still appears in the "
                f"SDX-Controller topology vlan_range: {sdx_vlan_range_raw}. "
                f"kytos-sdx must exclude it before exporting (issue #93)."
            )

    @pytest.mark.xfail(strict=True)
    def test_011_vlan_range_restored_after_l2vpn_deletion(self):
        """
        After deleting an L2VPN that was using VLAN 200 on Ampath3:50,
        the port's vlan_range must include VLAN 200 again in the next
        topology export.
        """
        l2vpn_api = SDX_CONTROLLER + "/l2vpn/1.0"
        vlan = "200"
        port_name = "Ampath3-eth50"
        port_id = "urn:sdx:port:ampath.net:Ampath3:50"
        oxp = "ampath"

        # Create L2VPN
        payload = {
            "name": "Test vlan_range restored after L2VPN deletion",
            "endpoints": [
                {"port_id": port_id, "vlan": vlan},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": vlan},
            ],
        }
        response = requests.post(l2vpn_api, json=payload)
        assert response.status_code == 201, response.text
        service_id = response.json()["service_id"]
        time.sleep(5)

        # Force export and confirm VLAN 200 is absent
        self._force_topology_export(oxp)
        port = self._get_kytos_sdx_port(oxp, port_name)
        assert port is not None
        vlan_range_raw = port["services"]["l2vpn-ptp"].get("vlan_range", [])
        available_vlans = _parse_vlan_range(vlan_range_raw)
        assert int(vlan) not in available_vlans, (
            f"VLAN {vlan} should be absent from vlan_range while L2VPN is active"
        )

        # Delete the L2VPN
        response = requests.delete(f"{l2vpn_api}/{service_id}")
        assert response.status_code == 200, response.text
        time.sleep(5)

        # Force export and confirm VLAN 200 is now back in the range
        self._force_topology_export(oxp)
        port = self._get_kytos_sdx_port(oxp, port_name)
        assert port is not None
        vlan_range_raw = port["services"]["l2vpn-ptp"].get("vlan_range", [])
        available_vlans = _parse_vlan_range(vlan_range_raw)
        assert int(vlan) in available_vlans, (
            f"VLAN {vlan} should be back in vlan_range after L2VPN deletion, "
            f"but it is still absent. vlan_range: {vlan_range_raw}"
        )

    @pytest.mark.xfail(strict=True)
    def test_012_vlan_range_excludes_multiple_used_vlans(self):
        """
        Create two L2VPNs using different VLANs on the same port and verify
        that both VLANs are excluded from the kytos-sdx topology export.
        """
        l2vpn_api = SDX_CONTROLLER + "/l2vpn/1.0"
        vlan_a = "300"
        vlan_b = "400"
        port_name = "Tenet03-eth50"
        port_id = "urn:sdx:port:tenet.ac.za:Tenet03:50"
        oxp = "tenet"

        for vlan in (vlan_a, vlan_b):
            payload = {
                "name": f"Test vlan_range multiple VLANs ({vlan})",
                "endpoints": [
                    {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": vlan},
                    {"port_id": port_id, "vlan": vlan},
                ],
            }
            response = requests.post(l2vpn_api, json=payload)
            assert response.status_code == 201, (
                f"Failed to create L2VPN with VLAN {vlan}: {response.text}"
            )
            time.sleep(5)

        # Force re-export
        self._force_topology_export(oxp)

        port = self._get_kytos_sdx_port(oxp, port_name)
        assert port is not None, (
            f"Port {port_name} not found in kytos-sdx topology for {oxp}"
        )
        vlan_range_raw = port["services"]["l2vpn-ptp"].get("vlan_range", [])
        available_vlans = _parse_vlan_range(vlan_range_raw)

        for vlan in (vlan_a, vlan_b):
            assert int(vlan) not in available_vlans, (
                f"VLAN {vlan} is in use on {port_name} but still present in "
                f"kytos-sdx vlan_range export: {vlan_range_raw} (issue #93)"
            )

    def test_013_vlan_range_export_consistent_between_kytos_sdx_and_sdx_controller(self):
        """
        After creating an L2VPN and forcing a topology re-export, the
        vlan_range reported by kytos-sdx and the one propagated to the
        SDX-Controller must be consistent: any VLAN excluded at the
        kytos-sdx level must also be excluded at the SDX-Controller level.
        """
        l2vpn_api = SDX_CONTROLLER + "/l2vpn/1.0"
        vlan = "500"
        port_name = "Ampath1-eth50"
        port_id = "urn:sdx:port:ampath.net:Ampath1:50"
        oxp = "ampath"

        payload = {
            "name": "Test vlan_range consistency kytos-sdx vs SDX-Controller",
            "endpoints": [
                {"port_id": port_id, "vlan": vlan},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": vlan},
            ],
        }
        response = requests.post(l2vpn_api, json=payload)
        assert response.status_code == 201, response.text
        service_id = response.json()["service_id"]
        time.sleep(5)

        # Confirm L2VPN is up
        response = requests.get(f"{l2vpn_api}/{service_id}")
        assert response.status_code == 200, response.text
        assert response.json()[service_id]["status"] == "up"

        self._force_topology_export(oxp)

        # vlan_range from kytos-sdx
        port_kytos = self._get_kytos_sdx_port(oxp, port_name)
        assert port_kytos is not None
        kytos_vlan_range_raw = port_kytos["services"]["l2vpn-ptp"].get("vlan_range", [])
        kytos_vlans = _parse_vlan_range(kytos_vlan_range_raw)

        # vlan_range from SDX-Controller
        port_sdx = self._get_sdx_controller_port(port_id)
        assert port_sdx is not None, (
            f"Port {port_id} not found in SDX-Controller topology"
        )
        sdx_vlan_range_raw = port_sdx.get("services", {}).get("l2vpn-ptp", {}).get("vlan_range", [])

        if sdx_vlan_range_raw:
            sdx_vlans = _parse_vlan_range(sdx_vlan_range_raw)

            # Both must agree that VLAN 500 is NOT available
            assert int(vlan) not in kytos_vlans, (
                f"VLAN {vlan} should be excluded in kytos-sdx export (issue #93). "
                f"vlan_range: {kytos_vlan_range_raw}"
            )
            assert int(vlan) not in sdx_vlans, (
                f"VLAN {vlan} should be excluded in SDX-Controller topology. "
                f"vlan_range: {sdx_vlan_range_raw}"
            )

            extra_in_sdx = sdx_vlans - kytos_vlans
            assert not extra_in_sdx, (
                f"SDX-Controller vlan_range contains VLANs not present in the "
                f"kytos-sdx export: {extra_in_sdx}. This indicates kytos-sdx is "
                f"not properly filtering before export (issue #93)."
            )

    @pytest.mark.xfail(strict=True)
    def test_014_vlan_range_valid_bounds_after_l2vpn_creation(self):
        """
        After creating an L2VPN and forcing a topology export, every range
        entry in vlan_range must satisfy:
          - start >= 1 and end <= 4094
          - start <= end (no inverted ranges)
          - No VLAN IDs from active EVCs appear in any range entry
        """
        l2vpn_api = SDX_CONTROLLER + "/l2vpn/1.0"
        vlan = "810"
        port_name = "Tenet01-eth50"
        port_id = "urn:sdx:port:tenet.ac.za:Tenet01:50"
        oxp = "tenet"

        payload = {
            "name": "Test vlan_range valid bounds",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath1:50", "vlan": vlan},
                {"port_id": port_id, "vlan": vlan},
            ],
        }
        response = requests.post(l2vpn_api, json=payload)
        assert response.status_code == 201, response.text
        service_id = response.json()["service_id"]
        time.sleep(5)

        response = requests.get(f"{l2vpn_api}/{service_id}")
        assert response.status_code == 200, response.text
        l2vpn_data = response.json()[service_id]
        assert l2vpn_data["status"] == "up", (
            f"L2VPN with VLAN {vlan} on {port_name} should be 'up' but is "
            f"'{l2vpn_data['status']}'. This is the symptom from issue #110 "
            f"caused by invalid vlan_range export (issue #93)."
        )

        self._force_topology_export(oxp)

        port = self._get_kytos_sdx_port(oxp, port_name)
        assert port is not None
        vlan_range_raw = port["services"]["l2vpn-ptp"].get("vlan_range", [])
        assert vlan_range_raw, (
            f"vlan_range is empty for {port_name} after L2VPN creation"
        )

        for entry in vlan_range_raw:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                start, end = int(entry[0]), int(entry[1])
            elif isinstance(entry, str) and "-" in entry:
                start, end = int(entry.split("-")[0]), int(entry.split("-")[1])
            else:
                start = end = int(entry)

            assert 1 <= start <= end <= 4094, (
                f"Invalid vlan_range entry '{entry}' for {port_name}: "
                f"start={start}, end={end} must satisfy 1 <= start <= end <= 4094"
            )
            assert int(vlan) not in range(start, end + 1), (
                f"Active VLAN {vlan} is still covered by range entry "
                f"'{entry}' in {port_name} vlan_range (issue #93)"
            )
