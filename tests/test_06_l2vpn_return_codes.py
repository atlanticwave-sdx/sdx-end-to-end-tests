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
    
    def test_010_code201(self):
        """
        Test the return code 201: L2VPN Service Created
        P2P with VLAN translation
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/100 and TENET/150",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "100",},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "150",},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
    
    def test_011_code201(self):
        """
        Test the return code 201: L2VPN Service Created
        P2P with option "any"
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/300 and TENET/any",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "300",},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "any",},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text
    
    @pytest.mark.xfail(reason="return status 400: PCE error: Can't find a valid vlan breakdown solution")
    def test_012_code201(self):
        """
        Test the return code 201: L2VPN Service Created
        P2P with VLAN range
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLANs 10-99 between AMPATH and SAX",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "10-99",},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "10-99",},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    @pytest.mark.xfail(reason="return status 400: PCE error: Can't find a valid vlan breakdown solution")
    def test_013_code201(self):
        """
        Test the return code 201: L2VPN Service Created
        P2P with "untagged" and a VLAN ID
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/400 and SAX/untagged",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "400",},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "untagged",},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    def test_014_code201(self):
        """
        Test the return code 201: L2VPN Service Created
        Example with optional attributes
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between AMPATH/700 and TENET/700",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "700",},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "700",},
            ],
            "description": "Example to demonstrate a L2VPN with optional attributes",
            "scheduling": {
                "end_time": "2025-12-31T12:00:00Z"},
            "qos_metrics": {
                "min_bw": {"value": 5,"strict": False},
                "max_delay": {"value": 150,"strict": True},
                "max_number_oxps": {"value": 3}},
            "notifications": [
                {"email": "user@domain.com"}, 
                {"email": "user2@domain2.com"} 
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

    def test_020_code400(self):
        """
        Test the return code 400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Wrong vlan: vlan is not a string
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": 100,},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "any",},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_021_code400(self):
        """
        Test the return code 400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Wrong vlan: vlan is out of range 1-4095
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "5000",},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "any",},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    def test_022_code400(self):
        """
        Test the return code 400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Wrong vlan: since one endpoint has the "all" option, all endpoints must have the same value
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "all",},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "any",},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text
    
    @pytest.mark.xfail(reason="return status 200: Connection published -- same behavior as vlan = 'any'")
    def test_023_code400(self):
        """
        Test the return code 400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Body incomplete: vlan attribute is missing on an endpoint
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50","vlan": "500",},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50"},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    @pytest.mark.xfail(reason="return status 402: Could not generate a traffic matrix")
    def test_024_code400(self):
        """
        Test the return code 400: Request does not have a valid JSON or body is incomplete/incorrect
        -> Body incorrect: port_id
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "Test L2VPN request",
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath","vlan": "600",},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50","vlan": "600",},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 400, response.text

    @pytest.mark.xfail(reason="return status 500: Internal Server Error")
    def test_030_code402(self):
        """
        Test the return code 402: Request not compatible (For instance, when a L2VPN P2MP is requested but only L2VPN P2P is supported)
        P2MP
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN ID 200 at AMPATH, TENET, at SAX", 
            "endpoints": [
                {"port_id": "urn:sdx:port:ampath.net:Ampath3:50", "vlan": "200"},
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "200"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "200",},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 402, response.text
            
    @pytest.mark.xfail(reason="return status 400: PCE error: Can't find a valid vlan breakdown solution")
    def test_040_code409(self):
        """
        Test the return code 409: L2VPN Service already exists
        """
        api_url = SDX_CONTROLLER + '/l2vpn/1.0'
        payload = {
            "name": "VLAN between TENET/1000 and SAX/1000", 
            "endpoints": [
                {"port_id": "urn:sdx:port:tenet.ac.za:Tenet03:50", "vlan": "1000"},
                {"port_id": "urn:sdx:port:sax.net:Sax01:50","vlan": "1000",},
            ],}
        response = requests.post(api_url, json=payload)
        assert response.status_code == 201, response.text

        time.sleep(30)

        response = requests.post(api_url, json=payload)
        assert response.status_code == 409, response.text

    def test_050_code409(self):
        """
        Test the return code 410: Can't fulfill the strict QoS requirements
        """

    def test_060_code409(self):
        """
        Test the return code 411: Scheduling not possible
        """

    def test_070_code409(self):
        """
        Test the return code 422: Attribute not supported by the SDX-LC/OXPO
        """
