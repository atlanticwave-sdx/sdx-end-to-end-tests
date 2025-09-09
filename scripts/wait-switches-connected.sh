#!/bin/bash
while true; do
	# _uuid,connection_mode,controller_burst_limit,controller_queue_size,controller_rate_limit,enable_async_messages,external_ids,inactivity_probe,is_connected,local_gateway,local_ip,local_netmask,max_backoff,other_config,role,status,target,type
	STATUS=$(docker compose exec -it mininet ovs-vsctl -f json list  Controller | jq -r '.data[]|.[0][1] + " " + (.[8]|tostring) + " " + .[16]' | grep -v ptcp:)
	OK=$(echo "$STATUS" | grep -c true)
	PEND=$(echo "$STATUS" | grep -c false)
	if [ $OK -gt 0 -a $PEND -eq 0 ]; then
		break
	fi
	echo -n "."
	sleep 1
done

# wait start-mn.py finishes
while true; do
	STATUS=$(docker compose exec -i mininet cat /tmp/status 2>/dev/null)
	if [ "$STATUS" = "ready" ]; then
		break
	fi
	echo -n "."
	sleep 1
done
echo "switches connected"
