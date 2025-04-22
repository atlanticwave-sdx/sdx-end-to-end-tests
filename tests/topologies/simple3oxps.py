import json
import time
import requests
from pathlib import Path
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch

KYTOS_TOPO_API = "http://%s:8181/api/kytos/topology/v3"
KYTOS_SDX_API = "http://%s:8181/api/kytos/sdx"

def create_topo(ampath_ctrl, sax_ctrl, tenet_ctrl):
    """Create a simple topology with three OXPs."""
    net = Mininet(topo=None, build=False, controller=RemoteController, switch=OVSSwitch)

    # ********************************************** TENET OXP - Start ************************************************
    TenetController = net.addController('tenet_ctrl', controller=RemoteController, ip=tenet_ctrl, port=6653)
    TenetController.start()

    tenet_sw1 = net.addSwitch('Tenet01', listenPort=6701, dpid='cc00000000000006')
    tenet_sw2 = net.addSwitch('Tenet02', listenPort=6702, dpid='cc00000000000007')
    tenet_sw3 = net.addSwitch('Tenet03', listenPort=6703, dpid='cc00000000000008')

    net.addLink(tenet_sw1, tenet_sw2, port1=1, port2=1)
    net.addLink(tenet_sw1, tenet_sw3, port1=2, port2=2)

    h6 = net.addHost('h6', mac='00:00:00:00:00:06')
    h7 = net.addHost('h7', mac='00:00:00:00:00:07')
    h8 = net.addHost('h8', mac='00:00:00:00:00:08')

    net.addLink(h6, tenet_sw1, port1=1, port2=50)
    net.addLink(h7, tenet_sw2, port1=1, port2=50)
    net.addLink(h8, tenet_sw3, port1=1, port2=50)

    # ************************************************ TENET OXP - End ************************************************

    # ************************************************ SAX OXP - Start ************************************************
    SaxController = net.addController('sax_ctrl', controller=RemoteController, ip=sax_ctrl, port=6653)
    SaxController.start()

    sax_sw1 = net.addSwitch('Sax01', listenPort=6801, dpid='dd00000000000004')
    sax_sw2 = net.addSwitch('Sax02', listenPort=6802, dpid='dd00000000000005')

    net.addLink(sax_sw1, sax_sw2, port1=1, port2=1)

    h4 = net.addHost('h4', mac='00:00:00:00:00:04')
    h5 = net.addHost('h5', mac='00:00:00:00:00:05')

    net.addLink(h4, sax_sw1, port1=1, port2=50)
    net.addLink(h5, sax_sw2, port1=1, port2=50)

    # ************************************************ SAX OXP - End ************************************************

    # ******************************************** Ampath OXP - Start **********************************************
    AmpathController = net.addController('ampath_ctrl', controller=RemoteController, ip=ampath_ctrl, port=6653)
    AmpathController.start()

    Ampath1 = net.addSwitch('Ampath1', listenPort=6601, dpid='aa00000000000001')
    Ampath2 = net.addSwitch('Ampath2', listenPort=6602, dpid='aa00000000000002')
    Ampath3 = net.addSwitch('Ampath3', listenPort=6603, dpid='aa00000000000003')

    net.addLink(Ampath1, Ampath2, port1=1, port2=1)
    net.addLink(Ampath1, Ampath3, port1=2, port2=2)
    net.addLink(Ampath2, Ampath3, port1=3, port2=3)

    h1 = net.addHost('h1', mac='00:00:00:00:00:01')
    h2 = net.addHost('h2', mac='00:00:00:00:00:02')
    h3 = net.addHost('h3', mac='00:00:00:00:00:03')

    net.addLink(h1, Ampath1, port1=1, port2=50)
    net.addLink(h2, Ampath2, port1=1, port2=50)
    net.addLink(h3, Ampath3, port1=1, port2=50)

    # ********************************************* Ampath OXP - End ************************************************

    # ********************************************** Inter-OXP links ***********************************************

    net.addLink(Ampath1, sax_sw1, port1=40, port2=40)
    net.addLink(Ampath2, sax_sw2, port1=40, port2=40)

    net.addLink(tenet_sw1, sax_sw1, port1=41, port2=41)
    net.addLink(tenet_sw2, sax_sw2, port1=41, port2=41)

    # Connect Ampath switches to Ampath controller
    Ampath1.start([AmpathController])
    Ampath2.start([AmpathController])
    Ampath3.start([AmpathController])

    sax_sw1.start([SaxController])
    sax_sw2.start([SaxController])

    tenet_sw1.start([TenetController])
    tenet_sw2.start([TenetController])
    tenet_sw3.start([TenetController])

    net.build()

    return net

def setup_topo(ampath_ctrl, sax_ctrl, tenet_ctrl):
    """Does all necessary setup for this test"""
    ampath_topo_api = KYTOS_TOPO_API % ampath_ctrl
    sax_topo_api = KYTOS_TOPO_API % sax_ctrl
    tenet_topo_api = KYTOS_TOPO_API % tenet_ctrl

    response = requests.get(f"{ampath_topo_api}/switches")
    assert response.status_code == 200
    ampath_switches = response.json()["switches"]
    assert len(ampath_switches) == 3

    response = requests.get(f"{sax_topo_api}/switches")
    assert response.status_code == 200
    sax_switches = response.json()["switches"]
    assert len(sax_switches) == 2

    response = requests.get(f"{tenet_topo_api}/switches")
    assert response.status_code == 200
    tenet_switches = response.json()["switches"]
    assert len(tenet_switches) == 3

    for sw_id in ampath_switches:
        response = requests.post(f"{ampath_topo_api}/switches/{sw_id}/enable")
        assert response.status_code == 201, response.text
        response = requests.post(f"{ampath_topo_api}/interfaces/switch/{sw_id}/enable")
        assert response.status_code == 200, response.text

    for sw_id in sax_switches:
        response = requests.post(f"{sax_topo_api}/switches/{sw_id}/enable")
        assert response.status_code == 201, response.text
        response = requests.post(f"{sax_topo_api}/interfaces/switch/{sw_id}/enable")
        assert response.status_code == 200, response.text

    for sw_id in tenet_switches:
        response = requests.post(f"{tenet_topo_api}/switches/{sw_id}/enable")
        assert response.status_code == 201, response.text
        response = requests.post(f"{tenet_topo_api}/interfaces/switch/{sw_id}/enable")
        assert response.status_code == 200, response.text

    # give a few seconds for link discovery (LLDP)
    time.sleep(10)

    response = requests.get(f"{ampath_topo_api}/links")
    assert response.status_code == 200
    ampath_links = response.json()["links"]
    assert len(ampath_links) == 3
    for link_id in ampath_links:
        response = requests.post(f"{ampath_topo_api}/links/{link_id}/enable")
        assert response.status_code == 201

    response = requests.get(f"{sax_topo_api}/links")
    assert response.status_code == 200
    sax_links = response.json()["links"]
    assert len(sax_links) == 1
    for link_id in sax_links:
        response = requests.post(f"{sax_topo_api}/links/{link_id}/enable")
        assert response.status_code == 201

    response = requests.get(f"{tenet_topo_api}/links")
    assert response.status_code == 200
    tenet_links = response.json()["links"]
    assert len(tenet_links) == 2
    for link_id in tenet_links:
        response = requests.post(f"{tenet_topo_api}/links/{link_id}/enable")
        assert response.status_code == 201

    metadata = {
        ampath_topo_api: {
            "switches/aa:00:00:00:00:00:00:01": {"lat": "25.77", "lng": "-80.19", "address": "Miami", "iso3166_2_lvl4": "US-FL"},
            "switches/aa:00:00:00:00:00:00:02": {"lat": "26.38", "lng": "-80.11", "address": "BocaRaton", "iso3166_2_lvl4": "US-FL"},
            "switches/aa:00:00:00:00:00:00:03": {"lat": "30.27", "lng": "-81.68", "address": "Jacksonville", "iso3166_2_lvl4": "US-FL"},
            "interfaces/aa:00:00:00:00:00:00:01:40": {"sdx_nni": "sax.net:Sax01:40"},
            "interfaces/aa:00:00:00:00:00:00:02:40": {"sdx_nni": "sax.net:Sax02:40"},
        },
        sax_topo_api: {
            "switches/dd:00:00:00:00:00:00:04": {"lat": "-3", "lng": "-40", "address": "Fortaleza", "iso3166_2_lvl4": "BR-CE"},
            "switches/dd:00:00:00:00:00:00:05": {"lat": "-3", "lng": "-20", "address": "Fortaleza", "iso3166_2_lvl4": "BR-CE"},
            "interfaces/dd:00:00:00:00:00:00:04:40": {"sdx_nni": "ampath.net:Ampath1:40"},
            "interfaces/dd:00:00:00:00:00:00:04:41": {"sdx_nni": "tenet.ac.za:Tenet01:41"},
            "interfaces/dd:00:00:00:00:00:00:05:40": {"sdx_nni": "ampath.net:Ampath2:40"},
            "interfaces/dd:00:00:00:00:00:00:05:41": {"sdx_nni": "tenet.ac.za:Tenet02:41"},
        },
        tenet_topo_api: {
            "switches/cc:00:00:00:00:00:00:06": {"lat": "-33", "lng": "18", "address": "CapeTown", "iso3166_2_lvl4": "ZA-WC"},
            "switches/cc:00:00:00:00:00:00:07": {"lat": "-26", "lng": "28", "address": "Johanesburgo", "iso3166_2_lvl4": "ZA-GP"},
            "switches/cc:00:00:00:00:00:00:08": {"lat": "-33", "lng": "27", "address": "EastLondon", "iso3166_2_lvl4": "ZA-EC"},
            "interfaces/cc:00:00:00:00:00:00:06:41": {"sdx_nni": "sax.net:Sax01:41"},
            "interfaces/cc:00:00:00:00:00:00:07:41": {"sdx_nni": "sax.net:Sax02:41"},
        },
    }

    for oxp in metadata:
        for item in metadata[oxp]:
            response = requests.post(f"{oxp}/{item}/metadata", json=metadata[oxp][item])
            assert 200 <= response.status_code < 300, response.text

    # give enough time for Kytos to process topology events
    time.sleep(10)

    # send topology to SDX-LC
    for oxp_ctrl in [ampath_ctrl, sax_ctrl, tenet_ctrl]:
        sdx_api = KYTOS_SDX_API % oxp_ctrl
        response = requests.post(f"{sdx_api}/topology/2.0.0")
        assert response.ok, response.text

    # give enough time for SDX-Controller to process topology events
    time.sleep(5)

    return True

def get_converted_topologies():
    topologies = ["simple3oxps_converted_ampath.json", "simple3oxps_converted_sax.json", "simple3oxps_converted_tenet.json"]
    return [json.loads((Path(__file__).parent / topo).read_text()) for topo in topologies]
