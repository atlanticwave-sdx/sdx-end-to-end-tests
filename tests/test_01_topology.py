import json
import re
import time
from datetime import datetime, timedelta

import pytest
from random import randrange
import requests

from tests.helpers import NetworkTest

SDX_CONTROLLER = 'http://sdx-controller:8080/SDX-Controller/1.0.0'

class TestE2ETopology:
    net = None

    @classmethod
    def setup_class(cls):
        cls.net = NetworkTest(["amlight", "sax", "tenet"])

    @classmethod
    def teardown_class(cls):
        cls.net.stop()

    def test_010_list_topology(self):
        """Test if the topology was loaded correctly."""
        api_url = SDX_CONTROLLER + '/topology'

        # initially the topology is empty, since no OXP was enabled
        response = requests.get(api_url)
        assert response.status_code == 204, response.text

        # then we enable the OXPs and topology should be available
        self.net.wait_switches_connect()
        self.net.run_setup_topo()
        
        # give time so that messages are exchanged between components
        time.sleep(15)

        ## make sure OXPs sent the topology to SDX-LC
        ## -> amlight
        #response = requests.get("http://amlight:8181/api/kytos/sdx_topology/v1/version/control")
        #assert response.ok
        #assert response.json() != {}, response.json()
        ## -> sax
        #response = requests.get("http://sax:8181/api/kytos/sdx_topology/v1/version/control")
        #assert response.ok
        #assert response.json() != {}, response.json()
        ## -> tenet
        #response = requests.get("http://tenet:8181/api/kytos/sdx_topology/v1/version/control")
        #assert response.ok
        #assert response.json() != {}, response.json()

        response = requests.get(api_url)
        assert response.status_code == 200, response.text
        assert response.json() != {}

        # TODO: other checks

    @pytest.mark.xfail
    def test_015_check_topology_follows_model_2_0_0(self):
        assert False

    @pytest.mark.xfail
    def test_020_set_intra_link_down_check_topology(self):
        assert False
