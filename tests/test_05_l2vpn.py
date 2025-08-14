import json
import re
import time
from datetime import datetime, timedelta
import uuid
import random

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

    @classmethod
    def setup_method(cls):
        cls.net.config_all_links_up()

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
                }
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data.get("status") == "under provisioning", str(data)
        service_id = data.get("service_id")
        assert service_id != None, str(data)

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 1, str(data)
        assert service_id in data, str(data)
        assert data[service_id].get("status") == "up", str(data)

        # make sure OXPs have the new EVCs
        ## -> ampath
        response = requests.get("http://ampath:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        assert len(evcs) == 1, response.text
        found = 0
        for evc in evcs.values():
            if evc.get("uni_a", {}).get("tag", {}).get("value") == 300:
                found += 1
        assert found == 1, str(evcs)
        ## -> sax
        response = requests.get("http://sax:8181/api/kytos/mef_eline/v2/evc/")
        data = response.json()
        assert len(data) == 1, str(data)
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        assert len(evcs) == 1, response.text
        found = 0
        for evc in evcs.values():
            if evc.get("uni_z", {}).get("tag", {}).get("value") == 300:
                found += 1
        assert found == 1, str(evcs)

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
                }
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data.get("status") == "under provisioning", str(data)
        service_id = data.get("service_id")
        assert service_id != None, str(data)

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 2, str(data)
        assert service_id in data, str(data)
        assert data[service_id].get("status") == "up", str(data)

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
        assert found == 0, str(evcs)
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        found = 0
        for evc in evcs.values():
            if evc.get("uni_z", {}).get("tag", {}).get("value") == 100:
                found += 1
        assert found == 0, str(evcs)

        # wait a few seconds to allow status change from UNDER_PROVISIONG to UP
        time.sleep(5)

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
                }
            ]
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
        assert found == 1, str(evcs)
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        found = 0
        for evc in evcs.values():
            if evc.get("uni_z", {}).get("tag", {}).get("value") == 100:
                found += 1
        assert found == 1, str(evcs)

    def test_045_edit_port_l2vpn_successfully(self):
        """Test change the port_id of endpoints of an existing L2vpn connection."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        data = response.json()
        key = list(data.keys())[0]
        current_data = data[key]  
        assert current_data["endpoints"][0]["port_id"] == "urn:sdx:port:ampath.net:Ampath3:50", str(data)
        assert current_data["endpoints"][1]["port_id"] == "urn:sdx:port:tenet.ac.za:Tenet03:50", str(data)

        # Change port_id
        payload = {
            "name": "New port_id in endpoints",
            "endpoints": [
                {
                    "port_id": "urn:sdx:port:ampath.net:Ampath2:50",
                    "vlan": "100",
                },
                {
                    "port_id": "urn:sdx:port:sax.net:Sax02:50",
                    "vlan": "100",
                }
            ]
        }
        response = requests.patch(f"{api_url}/{key}", json=payload)
        assert response.status_code == 201, response.text

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        response = requests.get(f"{api_url}/{key}")
        data = response.json()[key]
        assert data["status"] == "up", str(data)
        assert len(data["endpoints"]) == 2, str(data)
        assert data["endpoints"][0]["port_id"] == "urn:sdx:port:ampath.net:Ampath2:50", str(data)
        assert data["endpoints"][1]["port_id"] == "urn:sdx:port:sax.net:Sax02:50", str(data)


        # make sure OXPs have the new EVCs
        ## -> ampath
        response = requests.get("http://ampath:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 2, response.text
        ## -> sax
        response = requests.get("http://sax:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 2, response.text
        ## -> tenet
        response = requests.get("http://tenet:8181/api/kytos/mef_eline/v2/evc/")
        assert len(response.json()) == 1, response.text

    def test_050_delete_l2vpn_successfully(self):
        """Test deleting all two L2VPNs successfully."""
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        data = response.json()
        assert len(data) == 2, str(data)

        # Delete all L2VPN
        for key in data:
            response = requests.delete(f"{api_url}/{key}")
            assert response.status_code == 200, f"{response.text=} previous_data={data}"

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
        
        payload = {"name": "Text",
                   "endpoints": [
                       {"port_id": "urn:sdx:port:ampath.net:Ampath1:50", "vlan": "100"},
                       {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
                    ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        h1, h8 = self.net.net.get('h1', 'h8')
        h1.cmd('ip link add link %s name vlan100 type vlan id 100' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan100')
        h1.cmd('ip addr add 10.1.1.1/24 dev vlan100')
        h8.cmd('ip link add link %s name vlan100 type vlan id 100' % (h8.intfNames()[0]))
        h8.cmd('ip link set up vlan100')
        h8.cmd('ip addr add 10.1.1.8/24 dev vlan100')

        payload = {"name": "Text",
                   "endpoints": [
                       {"port_id": "urn:sdx:port:ampath.net:Ampath1:50", "vlan": "101"},
                       {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "101"}
                    ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        h1.cmd('ip link add link %s name vlan101 type vlan id 101' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan101')
        h1.cmd('ip addr add 10.1.2.1/24 dev vlan101')
        h8.cmd('ip link add link %s name vlan101 type vlan id 101' % (h8.intfNames()[0]))
        h8.cmd('ip link set up vlan101')
        h8.cmd('ip addr add 10.1.2.8/24 dev vlan101')

        payload = {"name": "Text",
                   "endpoints": [
                       {"port_id": "urn:sdx:port:ampath.net:Ampath1:50", "vlan": "102"},
                       {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "102"}
                    ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        h1.cmd('ip link add link %s name vlan102 type vlan id 102' % (h1.intfNames()[0]))
        h1.cmd('ip link set up vlan102')
        h1.cmd('ip addr add 10.1.3.1/24 dev vlan102')
        h8.cmd('ip link add link %s name vlan102 type vlan id 102' % (h8.intfNames()[0]))
        h8.cmd('ip link set up vlan102')
        h8.cmd('ip addr add 10.1.3.8/24 dev vlan102')

        # wait a few seconds to allow OXPs to deploy the L2VPNs
        time.sleep(10)

        # test connectivity
        result_100 = h1.cmd('ping -c4 10.1.1.8')
        result_101 = h1.cmd('ping -c4 10.1.2.8')
        result_102 = h1.cmd('ping -c4 10.1.3.8')

        # set one link to down
        self.net.net.configLinkStatus('Ampath1', 'Sax01', 'down')

        # wait a few seconds for convergency
        time.sleep(15)

        # test connectivity again
        result_100_2 = h1.cmd('ping -c4 10.1.1.8')
        result_101_2 = h1.cmd('ping -c4 10.1.2.8')
        result_102_2 = h1.cmd('ping -c4 10.1.3.8')

        # clean up
        h1.cmd('ip link del vlan100')
        h1.cmd('ip link del vlan101')
        h1.cmd('ip link del vlan102')
        h8.cmd('ip link del vlan100')
        h8.cmd('ip link del vlan101')
        h8.cmd('ip link del vlan102')

        assert ', 0% packet loss,' in result_100
        assert ', 0% packet loss,' in result_101
        assert ', 0% packet loss,' in result_102

        assert ', 0% packet loss,' in result_100_2
        assert ', 0% packet loss,' in result_101_2
        assert ', 0% packet loss,' in result_102_2


    def test_070_multiple_l2vpn_with_bandwidth_qos_metric(self):
        """
        Test the creation of multiple L2VPNs with Bandwidth QoS Metrics
        in a way that will consume all possible residual bandwidth, then
        check if new L2VPNs with BW requirements wont be accepted, check if
        new L2VPNs without BW requirements will be acesspted and finally
        run connectivity tests on the provisioned L2VPNs
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        base_vlan = 300
        count = 0
        request_pairs = [
            ("ampath.net:Ampath3:50",  "tenet.ac.za:Tenet01:50"),
            ("ampath.net:Ampath3:50",  "tenet.ac.za:Tenet01:50"),
            ("ampath.net:Ampath1:50",  "ampath.net:Ampath2:50"),
            ("sax.net:Sax01:50",       "sax.net:Sax02:50"),
            ("tenet.ac.za:Tenet01:50", "tenet.ac.za:Tenet03:50"),
        ]
        uni2host = {
            "ampath.net:Ampath1:50": "h1",
            "ampath.net:Ampath2:50": "h2",
            "ampath.net:Ampath3:50": "h3",
            "sax.net:Sax01:50": "h4",
            "sax.net:Sax02:50": "h5",
            "tenet.ac.za:Tenet01:50": "h6",
            "tenet.ac.za:Tenet02:50": "h7",
            "tenet.ac.za:Tenet03:50": "h8",
        }
        # first of all: make sure we have a clean environment
        data = requests.get(api_url).json()
        for l2vpn in data.keys():
            requests.delete(f"{api_url}/{l2vpn}")

        # wait until all L2VPNs are removed
        for i in range(30):
            data = requests.get(api_url).json()
            if len(data) == 0:
                break
            time.sleep(2)
        else:
            assert False, f"Timeout waiting for L2VPN removal. {data=}"

        # give a few seconds so that SDX-Controller can update link properties
        time.sleep(10)

        # case 1: first we make requests that will consume 90% of the link capacity
        for unia, uniz in request_pairs:
            vlan_id = base_vlan + count
            payload = {"name": f"VLAN--{vlan_id}--{unia}--{uniz}",
                "endpoints": [
                    {"port_id": f"urn:sdx:port:{unia}", "vlan": str(vlan_id)},
                    {"port_id": f"urn:sdx:port:{uniz}", "vlan": str(vlan_id)}
                ],
                "qos_metrics": {"min_bw": {"value": 9}},
            }
            response = requests.post(api_url, json=payload)
            assert response.status_code == 201, f"{payload=} {response.text=}"
            count += 1

        # case 2: then we make requests that will consume the remaining 10% of the link BW
        for unia, uniz in request_pairs:
            vlan_id = base_vlan + count
            payload = {"name": f"VLAN--{vlan_id}--{unia}--{uniz}",
                "endpoints": [
                    {"port_id": f"urn:sdx:port:{unia}", "vlan": str(vlan_id)},
                    {"port_id": f"urn:sdx:port:{uniz}", "vlan": str(vlan_id)}
                ],
                "qos_metrics": {"min_bw": {"value": 1}},
            }
            response = requests.post(api_url, json=payload)
            assert response.status_code == 201, f"{payload=} {response.text=}"
            count += 1

        # case 3: now all requests, no matter how much BW we request, should fail
        for unia, uniz in request_pairs:
            vlan_id = base_vlan + count
            payload = {"name": f"VLAN--{vlan_id}--{unia}--{uniz}",
                "endpoints": [
                    {"port_id": f"urn:sdx:port:{unia}", "vlan": str(vlan_id)},
                    {"port_id": f"urn:sdx:port:{uniz}", "vlan": str(vlan_id)}
                ],
                "qos_metrics": {"min_bw": {"value": random.randint(1,10)}},
            }
            response = requests.post(api_url, json=payload)
            assert response.status_code == 410, f"{payload=} {response.text=}"

        # case 4: on the other hand, requests without BW requirements should be okay
        for unia, uniz in request_pairs:
            vlan_id = base_vlan + count
            payload = {"name": f"VLAN--{vlan_id}--{unia}--{uniz}",
                "endpoints": [
                    {"port_id": f"urn:sdx:port:{unia}", "vlan": str(vlan_id)},
                    {"port_id": f"urn:sdx:port:{uniz}", "vlan": str(vlan_id)}
                ],
            }
            response = requests.post(api_url, json=payload)
            assert response.status_code == 201, f"{payload=} {response.text=}"
            count += 1

        # wait for all L2VPNs to be UP
        for i in range(30):
            data = requests.get(api_url).json()
            if all([l2vpn["status"] == "up" for l2vpn in data.values()]):
                break
            time.sleep(3)
        else:
            assert False, f"Timeout waiting for L2VPN converge. {data=}"

        # wait a couple of seconds to SDX-Controller propagate changes
        time.sleep(10)

        vlan_inc = 0
        for unia, uniz in request_pairs:
            for i in range(3):  # 3 success cases to test
                vlan_id = base_vlan + vlan_inc + i*len(request_pairs)
                hostA, hostZ = self.net.net.get(uni2host[unia], uni2host[uniz])
                hostA.cmd(f"ip link add link {hostA.intfNames()[0]} name vlan{vlan_id} type vlan id {vlan_id}")
                hostA.cmd(f"ip link set up vlan{vlan_id}")
                hostA.cmd(f"ip addr add 2001:db8:ffff:{vlan_id}::1/64 dev vlan{vlan_id}")
                hostZ.cmd(f"ip link add link {hostZ.intfNames()[0]} name vlan{vlan_id} type vlan id {vlan_id}")
                hostZ.cmd(f"ip link set up vlan{vlan_id}")
                hostZ.cmd(f"ip addr add 2001:db8:ffff:{vlan_id}::2/64 dev vlan{vlan_id}")
                # run first ping just to learn mac
                hostA.cmd(f"ping6 -c1 2001:db8:ffff:{vlan_id}::2 2>&1 >/dev/null")
                # now run ping and collect results
                ping_result = hostA.cmd(f"ping6 -c4 -i0.2 2001:db8:ffff:{vlan_id}::2")
                assert ', 0% packet loss,' in ping_result, f"{vlan_id=} {dataA=} {dataZ=} {ping_result=}"
            vlan_inc += 1

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert len(data) == 15, str(data)

        # Delete all L2VPN
        for key in data:
            response = requests.delete(f"{api_url}/{key}")
            assert response.status_code == 200, response.text

        time.sleep(3)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        data = requests.get(api_url).json()
        assert len(data) == 0, str(data)
