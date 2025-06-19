import mininet.clean
import time
import os
import requests
import importlib
import socket

class NetworkTest:
    def __init__(
        self,
        controllers,
        topo_name="simple3oxps",
    ):
        self.controllers_ip = []
        for ctl in controllers:
            self.controllers_ip.append(socket.gethostbyname(ctl))
        mininet.clean.cleanup()
        try:
            module = importlib.import_module(f"tests.topologies.{topo_name}")
            create_topo = getattr(module, "create_topo")
            setup_topo = getattr(module, "setup_topo")
            get_converted_topologies = getattr(module, "get_converted_topologies")
        except (ImportError, AttributeError):
            raise ValueError(
                f"Invalid topology: {topo_name}. Check test/topologies/"
            )
        self.net = create_topo(*self.controllers_ip)
        self.setup_topo = setup_topo
        self.get_converted_topologies = get_converted_topologies

    def run_setup_topo(self):
        try:
            self.setup_topo(*self.controllers_ip)
        except Exception as exc:
            self.stop()
            mininet.clean.cleanup()
            raise Exception(exc)

    def wait_switches_connect(self):
        for i in range(300):
            if all(sw.connected() for sw in self.net.switches):
                break
            time.sleep(1)
        else:
            status = [(sw.name, sw.connected()) for sw in self.net.switches]
            raise Exception('Timeout waiting switches connect: %s' % status)

    def config_all_links_up(self):
        for link in self.net.links:
            self.net.configLinkStatus(
                link.intf1.node.name,
                link.intf2.node.name,
                "up"
            )

    def stop(self):
        self.net.stop()
        #mininet.clean.cleanup()

    def change_node_status(self, status, target='tcp:127.0.0.1:6654'):
        node = self.net.get('Ampath1')
        config = node.cmd('ovs-vsctl get-controller', node.name).split()
        if status == 'down':
            node.cmd(f"ovs-vsctl set-controller {node.name} {target}")
            node.cmd(f"ovs-vsctl get-controller {node.name}") 
        else:
            node.cmd(f"ovs-vsctl set-controller {node.name} {target}")
            node.cmd(f"ovs-vsctl get-controller {node.name}")
            
        return " ".join(config)