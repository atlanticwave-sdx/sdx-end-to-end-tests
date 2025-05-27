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
        assert response.status_code == 200, response.text
        response_json = response.json()
        for l2vpn in response_json:
            response = requests.delete(api_url+f'/{l2vpn}')

        # wait for L2VPN to be actually deleted
        time.sleep(2)

    
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
        assert response.status_code == 201, response.text
    
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
        assert response.status_code == 201, response.text

    def test_012_create_l2vpn_with_vlan_any(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with option "any"
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
        assert response.status_code == 201, response.text
    
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
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "500:999"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "500:999"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data.get("status") == "under provisioning", data
        service_id = data.get("service_id")
        assert service_id != None, data

        # give enough time to SDX-Controller to propagate change to OXPs
        time.sleep(10)

        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 1, data
        assert service_id in data, data
        assert data[service_id].get("status") == "up", data

        #
        # make sure OXPs have the new EVCs
        ## -> ampath
        response = requests.get("http://ampath:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        assert len(evcs) == 1, response.text
        found = 0
        for evc in evcs.values():
            if evc.get("uni_a", {}).get("tag", {}).get("value") == [[500, 999]]:
                found += 1
        assert found == 1, evcs
        ## -> sax
        response = requests.get("http://sax:8181/api/kytos/mef_eline/v2/evc/")
        evcs = response.json()
        assert len(evcs) == 1, response.text
        found = 0
        for evc in evcs.values():
            if evc.get("uni_z", {}).get("tag", {}).get("value") == [[500, 999]]:
                found += 1
        assert found == 1, evcs

    def test_014_create_l2vpn_with_vlan_untagged(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        P2P with "untagged" and a VLAN ID
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
        assert response.status_code == 201, response.text

    def _future_date(self, isoformat_time=True):
        # Get the current time
        current_time = datetime.now()

        # Get the current year and month
        year = current_time.year
        month = current_time.month

        if month + 3 > 12:
            month = month - 9
            year += 1
        else:
            month += 3
        day = 1

        future_date = datetime(year, month, day)
        if not isoformat_time:
            return future_date.date().isoformat()
        return future_date.strftime('%Y-%m-%dT%H:%M:%SZ')

    def test_015_create_l2vpn_with_optional_attributes(self):
        """
        Test the return code for creating a SDX L2VPN
        201: L2VPN Service Created
        Example with optional attributes
        Note: This test should return code 201 when the schedule is supported.
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with optional attributes",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "description": "Example to demonstrate a L2VPN with optional attributes",
            "scheduling": {
                "end_time": self._future_date()},
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
        assert response.status_code == 422, response.text

    def test_020_create_l2vpn_with_invalid_vlan_type(self):
        """
        Test the return code for creating a SDX L2VPN with an invalid VLAN type
        400: Invalid JSON or incorrect body (VLAN should be a string)
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN with invalid VLAN type",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": 100}, 
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "200"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_021_create_l2vpn_with_vlan_out_of_range(self):
        """
        Test the return code for creating a SDX L2VPN with an out-of-range VLAN
        400: Invalid VLAN value (greater than 4095)
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN with out of range VLAN",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "5000"}, 
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_022_create_l2vpn_with_vlan_negative(self):
        """
        Test the return code for creating a SDX L2VPN with a negative VLAN
        400: Invalid VLAN value (negative)
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN with negative VLAN",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "-100"}, 
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_023_create_l2vpn_with_vlan_all(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Wrong vlan: since one endpoint has the "all" option, all endpoints must have the same value
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with vlan all",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "all"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "any"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text
    
    def test_024_create_l2vpn_with_missing_vlan(self):
        """
        Test the return code for creating a SDX L2VPN with a missing VLAN value
        400: Invalid JSON or incomplete body (missing VLAN on one endpoint)
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN with missing VLAN",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_025_create_l2vpn_with_body_incorrect(self):
        """
        Test the return code for creating a SDX L2VPN
        400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Body incorrect: port_id
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with body incorrect",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_026_create_l2vpn_with_missing_name(self):
        """
        Test the return code for creating a SDX L2VPN with a missing 'name' field
        400: Invalid JSON or incomplete body 
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_027_create_l2vpn_with_non_existent_port(self):
        """
        Test return code for creating L2VPN with a non-existent port ID
        400: Invalid JSON or incomplete body 
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with non-existent port",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:InvalidPort:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_028_create_l2vpn_with_invalid_port_id_format(self):
        """
        Test return code for creating L2VPN with invalid port ID format (incorrect URN format)
        400: Invalid JSON or incomplete body 
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with invalid port ID format",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:xyz", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_029_create_l2vpn_with_single_endpoint(self):
        """
        Test return code for creating L2VPN with with a single endpoint
        400: Invalid JSON or incomplete body 
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with a single endpoint",
            "endpoints": [
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_030_create_l2vpn_with_p2mp(self):
        """
        Test the return code for creating a SDX L2VPN
        402: Request not compatible (For instance, when a L2VPN P2MP is requested but only L2VPN P2P is supported)
        P2MP
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test P2MP L2VPN creation", 
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 402, response.text
            
    def test_040_create_l2vpn_existing(self):
        """
        Test the return code for creating a SDX L2VPN
        409: L2VPN Service already exists
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test creation of L2VPN existing", 
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        time.sleep(30)

        response = requests.post(api_url, json=payload)
        assert response.status_code == 409, response.text

    def test_050_create_l2vpn_with_valid_bw(self):
        """
        Test the return code for creating a SDX L2VPN
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with valid bw",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "min_bw": {
                    "value": 10
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    def test_051_create_l2vpn_with_min_bw_out_of_range(self):
        """
        Test the return code for creating a SDX L2VPN
        Case: min_bw out of range (value must be in [0-100])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with min_bw out of range",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "min_bw": {
                    "value": 101
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_052_create_l2vpn_with_min_bw_negative(self):
        """
        Test the return code for creating a SDX L2VPN
        Case: min_bw negative (value must be in [0-100])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with min_bw negative",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "min_bw": {
                    "value": -10
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_053_create_l2vpn_with_no_available_bw(self):
        """
        Test the return code for creating a SDX L2VPN
        410: Can't fulfill the strict QoS requirements
        """
        ### first let's make sure the topology is consistent
        api_url_topology = SDX_CONTROLLER + '/topology'
        topology = requests.get(api_url_topology).json()
        for link in topology["links"]:
            assert int(link["residual_bandwidth"]) == 100, str(link)

        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "min_bw": {
                    "value": 9
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        payload = {
            "name": "Test L2VPN creation available bw",
            "endpoints": [
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet01:50","vlan": "200"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "200"}
            ],
            "qos_metrics": {
                "min_bw": {
                    "value": 2
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 410, response.text

    def test_054_create_l2vpn_with_available_bw(self):
        """
        Test the return code for creating a SDX L2VPN
        410: Can't fulfill the strict QoS requirements
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "min_bw": {
                    "value": 10
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        payload = {
            "name": "Test L2VPN creation no available bw",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath2:50","vlan": "200"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "200"}
            ],
            "qos_metrics": {
                "min_bw": {
                    "value": 3
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    def test_055_create_l2vpn_with_valid_max_delay(self):
        """
        Test the return code for creating a SDX L2VPN
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with valid max_delay",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "max_delay": {
                    "value": 50
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    def test_056_create_l2vpn_with_max_delay_out_of_range(self):
        """
        Test the return code for creating a SDX L2VPN
        Case: max_delay out of range (value must be in [0-1000])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with max_delay out of range",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "max_delay": {
                    "value": 1001
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_057_create_l2vpn_with_max_delay_negative(self):
        """
        Test the return code for creating a SDX L2VPN
        Case: max_delay negative (value must be in [0-1000])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with max_delay negative",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "max_delay": {
                    "value": -10
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_058_create_l2vpn_with_valid_max_number_oxps(self):
        """
        Test the return code for creating a SDX L2VPN
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with valid max_number_oxps",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "max_number_oxps": {
                    "value": 50
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    def test_059_create_l2vpn_with_max_number_oxps_out_of_range(self):
        """
        Test the return code for creating a SDX L2VPN
        Case: max_number_oxps out of range (value must be in [0-100])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with max_number_oxps out of range",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "max_number_oxps": {
                    "value": 101
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text
         
    def test_060_create_l2vpn_with_max_number_oxps_negative(self):
        """
        Test the return code for creating a SDX L2VPN
        Case: max_number_oxps negative (value must be in [0-100])
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with max_number_oxps negative",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "max_number_oxps": {
                    "value": -10
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text
    
    def test_061_create_l2vpn_with_no_available_oxps(self):
        """
        Creating a L2VPN from Ampath03 to Tenet03 (it means that the path will contain 3 OXP) 
        This tests requests a L2VPN and then set max_number_oxps = 2.
        This way the PCE/SDX-Controller should return 410
        
        410: Can't fulfill the strict QoS requirements
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        payload = {
            "name": "Test L2VPN creation",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "200"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "200"}
            ],
            'qos_metrics': {
                "max_number_oxps": {
                    "value": 2
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 410, response.text

    def test_062_create_l2vpn_with_all_available_oxps(self):
        """
        Test the return code for creating a SDX L2VPN
        410: Can't fulfill the strict QoS requirements
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "qos_metrics": {
                "max_number_oxps": {
                    "value": 10
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        payload = {
            "name": "Test L2VPN creation no available oxps",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath2:50","vlan": "200"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "200"}
            ],
            "qos_metrics": {
                "max_number_oxps": {
                    "value": 90
                }
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    def test_070_create_l2vpn_with_impossible_scheduling(self):
        """
        Test the return code for creating a SDX L2VPN
        411: Scheduling not possible
        end_time before current date
        Note: This test should return code 411 when the schedule is supported.
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with scheduling not possible",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "scheduling": {
                "end_time": "2023-12-30T12:00:00Z"
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 422, response.text

    def test_071_create_l2vpn_with_formatting_issue(self):
        """
        Test the return code for creating a SDX L2VPN
        Format YYYY-MM-DD, should be YYYY-MM-DDTHH:MM:SSZ
        422: Attribute not supported
        Note: This test should return code 400 (No valid format) when the schedule is supported.
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN creation with formatting issue",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ],
            "scheduling": {
                "end_time": self._future_date(False)
            }
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 422, response.text

    def test_080_create_l2vpn_with_no_path_available_between_endpoints(self):
        """
        Test the return code for creating a SDX L2VPN
        412: No path available between endpoints
        """

        # set one link to down
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'down')

        # wait a few seconds
        time.sleep(15)

        api_url_topology = SDX_CONTROLLER + '/topology'
        response = requests.get(api_url_topology)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        link1 = "urn:sdx:link:tenet.ac.za:Tenet01/2_Tenet03/2"
        assert links[link1]["status"] == "down", str(links[link1])
        
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {"name": "Text",
                   "endpoints": [
                       {"port_id": "urn:sdx:port:ampath.net:Ampath1:50", "vlan": "100"},
                       {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "100"}
                    ]
        }
        response = requests.post(api_url, json=payload)
        assert response.status_code == 412, response.text

        # set one link to up
        self.net.net.configLinkStatus('Tenet01', 'Tenet03', 'up')

        # wait a few seconds
        time.sleep(15)

        response = requests.get(api_url_topology)
        data = response.json()
        links = {link["id"]: link for link in data["links"]}
        assert links[link1]["status"] == "up", str(links[link1])

