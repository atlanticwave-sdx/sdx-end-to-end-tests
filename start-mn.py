from tests.helpers import NetworkTest

with open("/tmp/status", "w") as f:
    f.write("starting")
print("* Creating network and instantiating nodes...")
net = NetworkTest(["ampath", "sax", "tenet"])
print("* Waiting switches to connect...")
net.wait_switches_connect()
print("* Running topology setup...")
net.run_setup_topo()
print("* All done!")
with open("/tmp/status", "w") as f:
    f.write("ready")
