#!/bin/bash
CONTAINER=$(docker compose ps sdx-controller -q)
IP=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $CONTAINER)

case $1 in
links)
	curl -s http://$IP:8080/SDX-Controller/topology | jq -r '(["ID","STATUS","STATE"] | (., map(length*"-"))), (.links[] | [.id, .status, .state]) | @tsv' | column -t
	;;
nodes)
	curl -s http://$IP:8080/SDX-Controller/topology | jq -r '(["ID","STATUS","STATE"] | (., map(length*"-"))), (.nodes[] | [.id, .status, .state]) | @tsv' | column -t
	;;
ports)
	curl -s http://$IP:8080/SDX-Controller/topology |  jq -r '(["ID","STATUS","STATE","L2VPN-VLAN-RANGE"] | (., map(length*"-"))), (.nodes[].ports[] | [.id, .status, .state, .services.l2vpn_ptp.vlan_range|tostring]) | @tsv' | column -t
	;;
l2vpn)
	if [ $# -eq 1 ]; then
		curl -s http://$IP:8080/SDX-Controller/l2vpn/1.0 | jq -r '(["ID", "STATUS", "ENDPOINT-1", "VLAN-1", "ENDPOINT-2", "VLAN-2"] | (., map(length*"-"))), (.[]|[.service_id, .status, .endpoints[0].port_id, .endpoints[0].vlan, .endpoints[1].port_id, .endpoints[1].vlan]) | @tsv' | column -t
	fi
	if [ $# -eq 2 ]; then
		curl -s http://$IP:8080/SDX-Controller/l2vpn/1.0/$2 | jq -r '(["ID", "STATUS", "ENDPOINT-1", "VLAN-1", "ENDPOINT-2", "VLAN-2"] | (., map(length*"-"))), (.[]|[.service_id, .status, .endpoints[0].port_id, .endpoints[0].vlan, .endpoints[1].port_id, .endpoints[1].vlan]) | @tsv' | column -t
		echo ""
		echo "Current Path:"
		echo "-------------"
		curl -s http://$IP:8080/SDX-Controller/l2vpn/1.0/$2 | jq -r '.[].current_path[]|.port_id + " " + .vlan' | column -t
	fi
	;;
*)
	echo "USAGE $0 nodes|ports|links"
	;;
esac
