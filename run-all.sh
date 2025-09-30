#!/bin/bash

SCRIPT_NAME=$0
TESTS=tests/
#TESTS=tests/test_20_use_case_topology.py
#TESTS=tests/test_99_topology_big_changes.py::TestE2ETopologyBigChanges::test_050_del_intra_link_check_topology
REP=1
PULL=y

function action_help(){
  test -n "$1" && echo "ERROR: $1"
  echo "USAGE: $SCRIPT_NAME [OPTIONS]"
  echo ""
  echo "  -r|--repeat NUMBER    Number of repetitions to be executed. Default: 1"
  echo "  -t|--tests TEST       Test cases to be executed. Default: tests/"
  echo "  --no-pull             Do NOT pull docker images"
  echo "  -h|--help             Show this help message and exit"
  exit 0
}

#######
## Main
#######

while [[ $# -gt 0 ]]; do
  case $1 in
    -r|--repeat)
      test -z "$2" && action_help "missing argument for $1"
      REP=$2
      shift
      shift
      ;;
    -t|--tests)
      test -z "$2" && action_help "missing argument for $1"
      TESTS=$2
      shift
      shift
      ;;
    --no-pull)
      PULL=n
      shift
      ;;
    -h|--help)
      action_help
      exit 0
      ;;
    *)
      action_help "Unknown option provided $1"
      exit 0
      #ORIG_ARGS+=("$1")
      #shift # past argument
      ;;
  esac
done


# additional args: ${ORIG_ARGS[@]}

if [ "$PULL" = "y" ]; then
	docker compose pull
fi

for i in $(seq 1 $REP); do
	docker compose down -v 2>/dev/null
	docker compose up --pull never -d 2>/dev/null
	
	#for oxp in ampath tenet sax; do 
	#	docker compose exec -it $oxp bash -c "apt-get update && apt-get install -y tcpdump; nohup tcpdump -i eth0 -w /captura.pcap & true"
	#done
	
	./wait-mininet-ready.sh
	docker compose exec -it mininet python3 -m pytest $TESTS | tee result-e2e.log
	
	for oxp in ampath tenet sax; do
		docker compose cp $oxp:/var/log/syslog /tmp/$i--$oxp.log
		docker compose logs $oxp-lc -t  > /tmp/$i--$oxp-lc.log
		#docker compose cp $oxp:/captura.pcap /tmp/$i--$oxp-captura.pcap; 
	done
	docker compose logs sdx-controller -t  > /tmp/$i--sdx-controller.log
	cp result-e2e.log /tmp/$i--result-e2e.log
done
