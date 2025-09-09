#!/usr/bin/python3

import sys
from sdx_datamodel.constants import Constants, MongoCollections
from sdx_controller.utils.db_utils import DbUtils
db_instance = DbUtils()
db_instance.initialize_db()

from sdx_datamodel.models.topology import SDX_TOPOLOGY_ID_prefix

domains = db_instance.get_value_from_db(MongoCollections.DOMAINS, Constants.DOMAIN_LIST)

from sdx_pce.topology.temanager import TEManager
te_manager = TEManager(topology_data=None)

for domain in domains:
    print(f"Loading {domain}")
    topology = db_instance.get_value_from_db(MongoCollections.TOPOLOGIES, SDX_TOPOLOGY_ID_prefix + domain)
    te_manager.add_topology(topology)

from sdx_controller.handlers.connection_handler import (
    ConnectionHandler,
    connection_state_machine,
    get_connection_status,
    parse_conn_status,
    topology_db_update,
)

connection_handler = ConnectionHandler(db_instance)

service_id = sys.argv[1]
body = db_instance.get_value_from_db(MongoCollections.CONNECTIONS, f"{service_id}")
endpoints = {ep["port_id"]: ep["vlan"] for ep in body["endpoints"]}
print(body)

print("-> checking TEManager vlan allocation table")
resp = input("Press ENTER to continue or CTRL+C to abort...")

UNUSED_VLAN = None
changed_vlan_table = False
has_found = False
for domain, port_table in te_manager._vlan_tags_table.items():
    for port, vlan_table in port_table.items():
        for vlan, assignment in vlan_table.items():
            if port in endpoints and vlan == int(endpoints[port]):
                print("missing assignment", port, vlan, " --> fixing!")
                vlan_table[vlan] = service_id
                changed_vlan_table = True
            if assignment == service_id:
                has_found = True
                print(vlan_table[vlan])


if not has_found:
    resp = input("Connection request not found! want to fix this ? [yN] ")
    if resp == "y":
        for endpoint in endpoints:
            domain = "urn:sdx:topology:" + endpoint.split(":")[3]
            vlan = int(endpoints[endpoint])   ## TODO: vlan range
            te_manager._vlan_tags_table[domain][endpoint][vlan] = service_id
            print("updated vlans for port ", port, vlan)
        te_manager.update_available_vlans(te_manager._vlan_tags_table)

if changed_vlan_table:
    resp = input("Changed VLAN table! Do you want to save? [yN] ")
    if resp == "y":
        te_manager.update_available_vlans(te_manager._vlan_tags_table)
        topology_db_update(db_instance, te_manager)
        print("saved!")
    else:
        print("ok! ignoring changes to vlan table...")


print("-> removing connection")
resp = input("Press ENTER to continue or CTRL+C to abort...")
remove_conn_reason, remove_conn_code = connection_handler.remove_connection(te_manager, service_id)
te_manager.update_available_vlans(te_manager._vlan_tags_table)
topology_db_update(db_instance, te_manager)

print("-> Place new connection")
resp = input("Press ENTER to continue or CTRL+C to abort...")
body["status"] = "UNDER_PROVISIONING"
db_instance.add_key_value_pair_to_db(MongoCollections.CONNECTIONS, service_id, body)
reason, code = connection_handler.place_connection(te_manager, body)
print(reason, code)
