TESTS=tests/
#TESTS=tests/test_20_use_case_topology.py
#TESTS=tests/test_99_topology_big_changes.py::TestE2ETopologyBigChanges::test_050_del_intra_link_check_topology

REP=$1

test -z "$REP" && REP=1

for i in $(seq 1 $REP); do
	docker compose down -v 2>/dev/null; docker compose up -d 2>/dev/null;
	
	#for oxp in ampath tenet sax; do 
	#	docker compose exec -it $oxp bash -c "apt-get update && apt-get install -y tcpdump; nohup tcpdump -i eth0 -w /captura.pcap & true"
	#done
	
	./wait-mininet-ready.sh
	docker compose exec -it mininet python3 -m pytest $TESTS | result-e2e.log
	
	for oxp in ampath tenet sax; do
		docker compose cp $oxp:/var/log/syslog /tmp/$i--$oxp.log; 
		#docker compose cp $oxp:/captura.pcap /tmp/$i--$oxp-captura.pcap; 
	done
	cp result-e2e.log /tmp/$i--result-e2e.log
done
