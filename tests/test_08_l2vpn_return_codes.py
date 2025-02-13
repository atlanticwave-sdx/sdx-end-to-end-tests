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

class TestE2EReturnCodesListL2vpn:
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
        # Create an L2VPN to list later
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        cls.payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "100"}
            ]
        }
        response = requests.post(api_url, json=cls.payload)
        assert response.status_code == 201, response.text

        response = requests.get(api_url)
        data = response.json()
        cls.key = list(data.keys())[0]

    def _add_l2vpn(self, n = 2):
        '''Auxiliar function'''
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        for i in range(n):
            payload = {
                "name": "Test L2VPN request",
                "endpoints": [
                    {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": str(i+1)},
                    {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": str(i+1)}
                ]
            }
            response = requests.post(api_url, json=payload)
            assert response.status_code == 201, response.text

    def test_010_list_one_l2vpn(self):
        """
        Test the return code for listing one SDX L2VPN
        200: Ok
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(f"{api_url}/{self.key}")
        assert response.status_code == 200, response.text
        data = response.json()
        key = next(iter(data))
        assert key == self.key
    
    def test_020_list_one_l2vpn_not_found(self):
        """
        Test the return code for listing a non-existing SDX L2VPN
        404: Service ID not found
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        key = [-1]*32
        response = requests.get(f"{api_url}/{key}")
        assert response.status_code == 404, response.text
  
    def test_030_list_multiple_l2vpn(self):
        """
        Test the return code for listing multiple SDX L2VPN
        200: Ok
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(f"{api_url}")
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 1

    def test_031_list_multiple_l2vpn_multiple_existing(self):
        """
        Test the return code for listing multiple SDX L2VPN
        200: Ok
        """
        self._add_l2vpn()
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 3

    def test_040_delete_one_l2vpn(self):
        """
        Test the return code for listing one SDX L2VPN
        201: L2VPN Deleted
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        response = requests.delete(f"{api_url}/{self.key}")
        assert response.status_code == 200, response.text

        response = requests.get(f"{api_url}/{self.key}")
        assert response.status_code == 404, response.text
    
    def test_050_delete_one_l2vpn_not_found(self):
        """
        Test the return code for listing a non-existing SDX L2VPN
        404: L2VPN Service ID provided does not exist.
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        key = [-1]*32
        response = requests.get(f"{api_url}/{key}")
        assert response.status_code == 404, response.text
