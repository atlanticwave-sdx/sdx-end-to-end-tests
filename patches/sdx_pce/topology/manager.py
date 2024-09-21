import copy
import datetime
import logging
from typing import Mapping

import networkx as nx
from sdx_datamodel.models.link import Link
from sdx_datamodel.models.topology import (
    TOPOLOGY_INITIAL_VERSION,
    SDX_TOPOLOGY_ID_prefix,
)
from sdx_datamodel.parsing.topologyhandler import TopologyHandler

from .grenmlconverter import GrenmlConverter


class TopologyManager:
    """
    Manager for topology operations.

    Operations are:

        - Merge multiple topologies.

        - Convert to grenml (XML).
    """

    def __init__(self):
        # The merged "super" topology of topologies of different
        # domains, with inter-domain links between them computed.
        self._topology = None

        # Mapping from topology ID to topology.
        self._topology_map = {}

        # Mapping from port ID to port.
        self._port_map = {}

        # Mapping from port ID to link.
        self._port_link_map = {}

        # Number of interdomain links we computed.
        self._num_interdomain_link = 0

        self._logger = logging.getLogger(__name__)

        # mapping attributes for interdomain links
        self.status_map = {
            ("up", "up"): "up",
            ("up", "error"): "error",
            ("error", "up"): "error",
            ("error", "error"): "error",
            # defaults to down
        }
        self.state_map = {
            ("enabled", "enabled"): "enabled",
            ("maintenance", "maintenance"): "maintenance",
            ("maintenance", "enabled"): "maintenance",
            ("maintenance", "disabled"): "maintenance",
            ("enabled", "maintenance"): "maintenance",
            ("disabled", "maintenance"): "maintenance",
            # defults to disabled
        }
        # bandwidth: the bandwidth attribute will be created based on both port
        # speeds (the minimum of them). Port speed is stored on Port.type and
        # can be 100FE, 1GE, 10GE, 25GE, 40GE, 50GE, 100GE, 400GE, and Other
        # When the value Other is chosen, no bandwidth guaranteed services will
        # be supported, so that we map that value to bandwidth=0
        self.bandwidth_map = {
            "100FE": 0.1,
            "1GE": 1,
            "10GE": 10,
            "25GE": 25,
            "40GE": 40,
            "100GE": 100,
            "400GE": 400,
            "Other": 0,
        }

    def get_handler(self):
        return self.topology_handler

    def topology_id(self, id):
        self._topology._id(id)

    def set_topology(self, topology):
        self._topology = topology

    def get_topology(self):
        return self._topology

    def get_topology_map(self) -> dict:
        return self._topology_map

    def get_port_link_map(self) -> Mapping[str, dict]:
        """
        Return a mapping between port IDs and links.
        """
        return self._port_link_map

    def get_port_map(self) -> Mapping[str, dict]:
        """
        Return a mapping between port IDs and ports.
        """
        return self._port_map

    def clear_topology(self):
        self._topology = None
        self._topology_map = {}
        self._port_link_map = {}

    def add_topology(self, data):
        topology = TopologyHandler().import_topology_data(data)
        self._topology_map[topology.id] = topology

        if self._topology is None:
            self._topology = copy.deepcopy(topology)
            interdomain_ports = []

            # Generate a new topology id
            self.generate_id()

            # Addding to the port list
            # links = topology.links
            # for link in links:
            #    for port in link.ports:
            #        self._port_link_map[port["id"]] = link
        else:
            # check the inter-domain links first.
            interdomain_ports = self.inter_domain_check(topology)
            self._num_interdomain_link += len(interdomain_ports)
            if self._num_interdomain_link == 0:
                self._logger.debug(
                    f"Warning: no interdomain links detected in {topology.id}!"
                )

            # Nodes
            nodes = topology.nodes
            self._topology.add_nodes(nodes)

            # links
            links = topology.links
            self._topology.add_links(links)

            # version
            self.update_version(False)

        # Addding to the port list
        links = topology.links
        for link in links:
            for port in link.ports:
                port_id = port if isinstance(port, str) else port["id"]
                self._port_link_map[port_id] = link

        # Addding to the port node
        nodes = topology.nodes
        for node in nodes:
            for port in node.ports:
                self._port_map[port.id] = port

        # inter-domain links
        self.add_inter_domain_links(topology, interdomain_ports)

        self.update_timestamp()

    def get_domain_name(self, node_id):
        """
        Find the topology ID associated with the given node ID.

        A topology ID is expected to be of the format
        "urn:sdx:topology:amlight.net", and from this, we
        can find the domain name associated with the topology.

        TODO: This function name may be a misnomer?
        """
        domain_id = None
        # print(f"len of topology_list: {len(self._topology_map)}")
        for topology_id, topology in self._topology_map.items():
            if topology.has_node_by_id(node_id):
                domain_id = topology_id
                break

        return domain_id

    def generate_id(self):
        self._topology.id = SDX_TOPOLOGY_ID_prefix
        self._topology.version = TOPOLOGY_INITIAL_VERSION
        return id

    def remove_topology(self, topology_id):
        self._topology_map.pop(topology_id, None)
        self.update_version(False)
        self.update_timestamp()

    def is_link_interdomain(self, link, topology):
        """
        Check if a link is an interdomain link.
        """
        for port in link.ports:
            port_id = port if isinstance(port, str) else port["id"]
            if port_id not in self._port_link_map:
                return True
        return False

    def is_interdomain_port(self, port_id, topology_id):
        """
        Check if a Port ID is interdomain
        """
        # Sanity checks
        if (
            not isinstance(port_id, str)
            or not port_id.startswith("urn:sdx:port:")
            or not isinstance(topology_id, str)
            or not topology_id.startswith("urn:sdx:topology:")
        ):
            return False
        return port_id.split(":")[3] != topology_id.split(":")[3]

    def update_topology(self, data):
        # likely adding new inter-domain links
        update_handler = TopologyHandler()
        topology = update_handler.import_topology_data(data)
        self._topology_map[topology.id] = topology

        # Nodes.
        nodes = topology.nodes
        for node in nodes:
            self._topology.remove_node(node.id)

        # Links.
        links = topology.links
        for link in links:
            if not self.is_link_interdomain(link, topology):
                # print(link.id+";......."+str(link.nni))
                self._topology.remove_link(link.id)
                for port in link.ports:
                    port_id = port if isinstance(port, str) else port["id"]
                    self._port_link_map.pop(port_id)

        # Check the inter-domain links first.
        interdomain_ports = self.inter_domain_check(topology)
        if len(interdomain_ports) == 0:
            self._logger.warning("Warning: no interdomain links detected!")

        # Nodes.
        nodes = topology.nodes
        self._topology.add_nodes(nodes)

        # Links.
        links = topology.links
        self._topology.add_links(links)

        # inter-domain links
        self.add_inter_domain_links(topology, interdomain_ports)

        # Update the port node map
        for node in topology.nodes:
            for port in node.ports:
                self._port_map[port.id] = port

        self.update_version(True)
        self.update_timestamp()

    def update_version(self, sub: bool):
        try:
            [ver, sub_ver] = self._topology.version.split(".")
        except ValueError:
            ver = self._topology.version
            sub_ver = "0"

        self._topology.version = self.new_version(ver, sub_ver, sub)

        return self._topology.version

    def new_version(self, ver, sub_ver, sub: bool):
        if not sub:
            ver = str(int(ver) + 1)
            sub_ver = "0"
        else:
            sub_ver = str(int(sub_ver) + 1)

        return ver + "." + sub_ver

    def update_timestamp(self):
        ct = datetime.datetime.now().isoformat()
        self._topology.timestamp = ct

        return ct

    def inter_domain_check(self, topology):
        interdomain_port_dict = {}
        interdomain_ports = []
        interdomain_port_ids = []
        links = topology.links
        link_dict = {}
        for link in links:
            link_dict[link.id] = link
            for port in link.ports:
                port_id = port if isinstance(port, str) else port["id"]
                interdomain_port_dict[port_id] = link

        # match any ports in the existing topology
        for port_id in interdomain_port_dict:
            # print("interdomain_port:")
            # print(port_id)
            for existing_port, existing_link in self._port_link_map.items():
                # print(existing_port)
                if port_id == existing_port:
                    # print("Interdomain port:" + port_id)
                    # remove redundant link between two domains
                    self._topology.remove_link(existing_link.id)
                    interdomain_port_ids.append(port_id)
            self._port_link_map[port_id] = interdomain_port_dict[port_id]

        # count for inter-domain links according to topo spec 2.0.x
        for node in topology.nodes:
            for port in node.ports:
                # interdomain ports based on previous methodology
                if port.id in interdomain_port_ids:
                    interdomain_ports.append(port)
                # interdomain ports based on new methodology (spec 2.0)
                if self.is_interdomain_port(port.nni, topology.id):
                    interdomain_ports.append(port)

        return interdomain_ports

    def create_update_interdomain_link(self, port1, port2):
        """Create or update an interdomain link from two ports."""
        if port2.id < port1.id:
            port1, port2 = port2, port1

        port1_id = port1.id.replace("urn:sdx:port:", "", 1)
        port2_id = port2.id.replace("urn:sdx:port:", "", 1)
        link_id = f"urn:sdx:link:interdomain:{port1_id}:{port2_id}"

        for link in self._topology.links:
            if link_id == link.id:
                break
        else:
            link = Link(
                id=link_id,
                name=f"{port1.name}--{port2.name}",
                ports=[port1.id, port2.id],
                bandwidth=min(
                    self.bandwidth_map.get(port1.type, 100),
                    self.bandwidth_map.get(port2.type, 100),
                ),
                residual_bandwidth=100,
                latency=0,
                packet_loss=0,
                availability=100,
            )
            self._topology.add_links([link])

        link.status = self.status_map.get((port1.status, port2.status), "down")
        link.state = self.state_map.get((port1.state, port2.state), "disabled")

    def add_inter_domain_links(self, topology, interdomain_ports):
        """Add inter-domain links (whenever possible)."""
        for port in interdomain_ports:
            other_port = self._port_map.get(port.nni)
            if not other_port or other_port.nni != port.id:
                self._logger.warning(
                    "Interdomain link not added now - didnt find other port:"
                    f" port={port.id} other_port={port.nni} ({other_port})"
                )
                continue
            self.create_update_interdomain_link(port, other_port)

    def get_failed_links(self) -> dict:
        """Get failed links on the topology (ie., Links not up and enabled)."""
        failed_links = []
        for link in self._topology.links:
            if link.status in ("up", None) and link.state in ("enabled", None):
                continue
            failed_links.append({"id": link.id, "ports": link.ports})
        return failed_links

    # adjacent matrix of the graph, in jason?
    def generate_graph(self):
        graph = nx.Graph()

        if self._topology is None:
            self._logger.warning("We do not have a topology yet")
            return None

        links = self._topology.links
        for link in links:
            inter_domain_link = False
            if link.status not in ("up", None) or link.state not in ("enabled", None):
                continue
            ports = link.ports
            end_nodes = []
            for port in ports:
                port_id = port if isinstance(port, str) else port["id"]
                node = self._topology.get_node_by_port(port_id)
                if node is None:
                    self._logger.warning(
                        f"This port (id: {port_id}) does not belong to "
                        f"any node in the topology, likely a Non-SDX port!"
                    )
                    inter_domain_link = True
                    break
                else:
                    end_nodes.append(node)
                    # print("graph node:"+node.id)
            if not inter_domain_link:
                graph.add_edge(end_nodes[0].id, end_nodes[1].id)
                edge = graph.edges[end_nodes[0].id, end_nodes[1].id]
                edge["id"] = link.id
                edge["latency"] = link.latency
                edge["bandwidth"] = link.bandwidth
                edge["residual_bandwidth"] = link.residual_bandwidth
                edge["weight"] = 1000.0 * (1.0 / link.residual_bandwidth)
                edge["packet_loss"] = link.packet_loss
                edge["availability"] = link.availability

        return graph

    def generate_grenml(self):
        self.converter = GrenmlConverter(self._topology)

        return self.converter.read_topology()

    def add_domain_service(self):
        pass

    # may need to read from a configuration file.
    def update_private_properties(self):
        pass

    # on performance properties for now
    def update_link_property(self, link_id, property, value):
        # 1. update the individual topology
        for id, topology in self._topology_map.items():
            links = topology.links
            for link in links:
                self._logger.info(f"link.id={link.id}; id={id}")
                if link.id == link_id:
                    setattr(link, property, value)
                    self._logger.info("updated the link.")
                    # 1.2 need to change the sub_ver of the topology?

        # 2. check on the inter-domain link?
        # 3. update the interdomain topology
        links = self._topology.links
        for link in links:
            if link.id == link_id:
                setattr(link, property, value)
                self._logger.info("updated the link.")
                # 2.2 need to change the sub_ver of the topology?

        self.update_version(True)
        self.update_timestamp()
        # 4. Signal update the (networkx) graph

        # 5. signal Reoptimization of TE?

    def update_element_property_json(self, data, element, element_id, property, value):
        elements = data[element]
        for element in elements:
            if element["id"] == element_id:
                element[property] = value

        try:
            [ver, sub_ver] = data["version"].split(".")
        except ValueError:
            ver = "0"
            sub_ver = "0"

        data["version"] = self.new_version(ver, sub_ver, True)
        data["timestamp"] = datetime.datetime.now().isoformat()

    def get_port_by_id(self, port_id: str):
        """
        Given port id, returns a Port.
        """
        for node in self.get_topology().nodes:
            for port in node.ports:
                if port.id == port_id:
                    return port.to_dict()
        return None

    def are_two_ports_same_domain(self, port1_id: str, port2_id: str):
        """
        Check if two ports are in the same domain.
        """
        node1 = self.get_topology().get_node_by_port(port1_id)
        node2 = self.get_topology().get_node_by_port(port2_id)
        if node1 is None or node2 is None:
            return False

        domain1 = self.get_domain_name(node1.id)
        domain2 = self.get_domain_name(node2.id)
        return domain1 == domain2

    def update_node_property(self):
        pass

    def update_port_property(self):
        pass
