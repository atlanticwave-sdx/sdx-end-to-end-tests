import logging
import threading
from itertools import chain
from typing import List, Optional

import networkx as nx
from networkx.algorithms import approximation as approx
from sdx_datamodel.models.port import Port
from sdx_datamodel.parsing.connectionhandler import ConnectionHandler

from sdx_pce.models import (
    ConnectionPath,
    ConnectionRequest,
    ConnectionSolution,
    TrafficMatrix,
    VlanTag,
    VlanTaggedBreakdown,
    VlanTaggedBreakdowns,
    VlanTaggedPort,
)
from sdx_pce.topology.manager import TopologyManager
from sdx_pce.utils.exceptions import ValidationError

UNUSED_VLAN = None


class TEManager:
    """
    TE Manager for connection - topology operations.

    Functions of this class are:

        - generate inputs to the PCE solver

        - converter the solver output.

        - VLAN reservation and unreservation.
    """

    def __init__(self, topology_data):
        self.topology_manager = TopologyManager()

        # A lock to safely perform topology operations.
        self._topology_lock = threading.Lock()

        self._logger = logging.getLogger(__name__)

        # A {domain, {port, {vlan, in_use}}} mapping.
        self._vlan_tags_table = {}

        # Making topology_data optional while investigating
        # https://github.com/atlanticwave-sdx/sdx-controller/issues/145.
        #
        # TODO: a nicer thing to do would be to keep less state around.
        # https://github.com/atlanticwave-sdx/pce/issues/122
        if topology_data:
            self.topology_manager.add_topology(topology_data)
            self.graph = self.generate_graph_te()
            self._update_vlan_tags_table(
                domain_name=topology_data.get("id"),
                port_map=self.topology_manager.get_port_map(),
            )
        else:
            self.graph = None

    def add_topology(self, topology_data: dict):
        """
        Add a new topology to TEManager.

        :param topology_data: a dictionary that represents a topology.
        """
        self.topology_manager.add_topology(topology_data)

        # Ports appear in two places in the combined topology
        # maintained by TopologyManager: attached to each of the
        # nodes, and attached to links.  Here we are using the ports
        # attached to links.
        self._update_vlan_tags_table(
            domain_name=topology_data.get("id"),
            port_map=self.topology_manager.get_port_map(),
        )

    def update_topology(self, topology_data: dict):
        """
        Update an existing topology in TEManager.

        :param topology_data: a dictionary that represents a topology.
        """
        self.topology_manager.update_topology(topology_data)

        # Update vlan_tags_table in a non-disruptive way. Previous concerned
        # still applies:
        # TODO: careful here when updating VLAN tags table -- what do
        # we do when an in use VLAN tag becomes invalid in the update?
        # See https://github.com/atlanticwave-sdx/pce/issues/123
        self._update_vlan_tags_table(
            domain_name=topology_data.get("id"),
            port_map=self.topology_manager.get_port_map(),
        )

    def get_topology_map(self) -> dict:
        """
        Get {topology_id: topology, ..} map.
        """
        return self.topology_manager.get_topology_map()

    def get_port_obj_services_label_range(self, port: Port) -> List[str]:
        vlan_range = None
        services = port.services
        if services and services.l2vpn_ptp:
            vlan_range = services.l2vpn_ptp.get("vlan_range")
        return vlan_range

    def get_failed_links(self) -> List[dict]:
        """Get failed links on the topology (ie., Links not up and enabled)."""
        return self.topology_manager.get_failed_links()

    def _update_vlan_tags_table(self, domain_name: str, port_map: dict):
        """
        Update VLAN tags table in a non-disruptive way, meaning: only add new
        VLANs to the table. Removed VLANs will need further discussion (see
        https://github.com/atlanticwave-sdx/pce/issues/123)
        """
        self._vlan_tags_table.setdefault(domain_name, {})

        for port_id, port in port_map.items():
            # Get the label range for this port: either from the
            # port itself (v1), or from the services attached to it (v2).
            label_range = self.get_port_obj_services_label_range(port)
            if label_range is None:
                label_range = port.vlan_range

            # TODO: why is label_range sometimes None, and what to
            # do when that happens?
            if label_range is None:
                self._logger.info(f"label_range on {port.id} is None")
                continue

            # label_range is of the form ['100-200', '1000']; let
            # us expand it.  Would have been ideal if this was
            # already in some parsed form, but it is not, so this
            # is a work-around.
            all_labels = self._expand_label_range(label_range)

            self._vlan_tags_table[domain_name].setdefault(port_id, {})
            for label in all_labels:
                self._vlan_tags_table[domain_name][port_id].setdefault(
                    label, UNUSED_VLAN
                )

    def _expand_label_range(self, label_range: []) -> List[int]:
        """
        Expand the label range to a list of numbers.
        """
        labels = [self._expand_label(label) for label in label_range]
        # flatten result and return it.
        return list(chain.from_iterable(labels))

    def _expand_label(self, label) -> List[int]:

        start = stop = 0
        """
        Expand items in label range to a list of numbers.

        Items in label ranges can be of the form "100-200" or "100".
        For the first case, we return [100,101,...200]; for the second
        case, we return [100].
        """
        if isinstance(label, str):
            parts = label.split("-")
            start = int(parts[0])
            stop = int(parts[-1]) + 1

        if isinstance(label, int):
            start = label
            stop = label + 1
        """
        Items in label ranges can be of the form [100, 200].
        For the first case, we return [100,101,...200].
        """
        if isinstance(label, list):
            start = label[0]
            stop = label[1] + 1

        """
        Items in label ranges can not be of the tuple form (100, 200), per JSON schema.
        """

        if start == 0 or stop == 0 or start > stop:
            raise ValidationError(f"Invalid label range: {label}")

        return list(range(start, stop))

    def generate_traffic_matrix(self, connection_request: dict) -> TrafficMatrix:
        """
        Generate a Traffic Matrix from the connection request we have.

        A connection request specifies an ingress port, an egress
        port, and some other properties.  The ports may belong to
        different domains.  We need to break that request down into a
        set of requests, each of them specific to a domain.  We call
        such a domain-wise set of requests a traffic matrix.
        """
        self._logger.info(
            f"generate_traffic_matrix: connection_request: {connection_request}"
        )

        request = ConnectionHandler().import_connection_data(connection_request)

        self._logger.info(f"generate_traffic_matrix: decoded request: {request}")

        ingress_port = request.ingress_port
        egress_port = request.egress_port

        self._logger.info(
            f"generate_traffic_matrix, ports: "
            f"ingress_port.id: {ingress_port.id}, "
            f"egress_port.id: {egress_port.id}"
        )

        topology = self.topology_manager.get_topology()

        ingress_node = topology.get_node_by_port(ingress_port.id)
        egress_node = topology.get_node_by_port(egress_port.id)

        if ingress_node is None:
            self._logger.warning(
                f"No ingress node was found for ingress port ID '{ingress_port.id}'"
            )
            return None

        if egress_node is None:
            self._logger.warning(
                f"No egress node is found for egress port ID '{egress_port.id}'"
            )
            return None

        ingress_nodes = [
            x for x, y in self.graph.nodes(data=True) if y["id"] == ingress_node.id
        ]

        egress_nodes = [
            x for x, y in self.graph.nodes(data=True) if y["id"] == egress_node.id
        ]

        if len(ingress_nodes) <= 0:
            self._logger.warning(
                f"No ingress node '{ingress_node.id}' found in the graph"
            )
            return None

        if len(egress_nodes) <= 0:
            self._logger.warning(
                f"No egress node '{egress_node.id}' found in the graph"
            )
            return None

        required_bandwidth = request.bandwidth_required or 0
        required_latency = request.latency_required or float("inf")
        request_id = request.id

        self._logger.info(
            f"Setting required_latency: {required_latency}, "
            f"required_bandwidth: {required_bandwidth}"
        )

        request = ConnectionRequest(
            source=ingress_nodes[0],
            destination=egress_nodes[0],
            required_bandwidth=required_bandwidth,
            required_latency=required_latency,
        )

        return TrafficMatrix(connection_requests=[request], request_id=request_id)

    def generate_graph_te(self) -> Optional[nx.Graph]:
        """
        Return the topology graph that we have.
        """
        graph = self.topology_manager.generate_graph()

        if graph is None:
            self._logger.warning("No graph could be generated")
            return None

        graph = nx.convert_node_labels_to_integers(graph, label_attribute="id")

        # TODO: why is this needed?
        self.graph = graph
        # print(list(graph.nodes(data=True)))

        return graph

    def graph_node_connectivity(self, source=None, dest=None):
        """
        Check that a source and destination node have connectivity.
        """
        # TODO: is this method really needed?
        return approx.node_connectivity(self.graph, source, dest)

    def requests_connectivity(self, tm: TrafficMatrix) -> bool:
        """
        Check that connectivity is possible.
        """
        # TODO: consider using filter() and reduce(), maybe?
        # TODO: write some tests for this method.
        for request in tm.connection_requests:
            conn = self.graph_node_connectivity(request.source, request.destination)
            self._logger.info(
                f"Request connectivity: source {request.source}, "
                f"destination: {request.destination} = {conn}"
            )
            if conn is False:
                return False

        return True

    def get_links_on_path(self, solution: ConnectionSolution) -> list:
        """
        Return all the links on a connection solution.

        The result will be a list of dicts, like so:

        .. code-block::

           [{'source': 'urn:ogf:network:sdx:port:zaoxi:A1:1',
              'destination': 'urn:ogf:network:sdx:port:zaoxi:B1:3'},
            {'source': 'urn:ogf:network:sdx:port:zaoxi:B1:1',
             'destination': 'urn:ogf:network:sdx:port:sax:B3:1'},
            {'source': 'urn:ogf:network:sdx:port:sax:B3:3',
             'destination': 'urn:ogf:network:sdx:port:sax:B1:4'},
            {'source': 'urn:ogf:network:sdx:port:sax:B1:1',
             'destination': 'urn:sdx:port:amlight:B1:1'},
            {'source': 'urn:sdx:port:amlight.net:B1:3',
             'destination': 'urn:sdx:port:amlight.net:A1:1'}]

        """
        if solution is None or solution.connection_map is None:
            self._logger.warning(f"Can't find paths for {solution}")
            return None

        result = []

        for domain, links in solution.connection_map.items():
            for link in links:
                assert isinstance(link, ConnectionPath)

                src_node = self.graph.nodes.get(link.source)
                assert src_node is not None

                dst_node = self.graph.nodes.get(link.destination)
                assert dst_node is not None

                ports = self._get_ports_by_link(link)

                self._logger.info(
                    f"get_links_on_path: src_node: {src_node} (#{link.source}), "
                    f"dst_node: {dst_node} (#{link.destination}), "
                    f"ports: {ports}"
                )

                if ports:
                    p1, p2 = ports
                    result.append({"source": p1["id"], "destination": p2["id"]})

        return result

    def add_breakdowns_to_connection(self, connection_request: dict, breakdowns: dict):
        """
        add breakdowns to connection request for the sdx-controller to process.
        """
        connection_request["breakdowns"] = breakdowns

        return connection_request

    def generate_connection_breakdown(
        self, solution: ConnectionSolution, connection_request: dict
    ) -> dict:
        """
        Take a connection solution and generate a breakdown.
        """
        if solution is None or solution.connection_map is None:
            self._logger.warning(f"Can't find a breakdown for {solution}")
            return None

        breakdown = {}
        paths = solution.connection_map  # p2p for now

        for domain, links in paths.items():
            self._logger.info(f"domain: {domain}, links: {links}")

            current_link_set = []

            for count, link in enumerate(links):
                self._logger.info(f"count: {count}, link: {link}")

                assert isinstance(link, ConnectionPath)

                src_node = self.graph.nodes.get(link.source)
                assert src_node is not None

                dst_node = self.graph.nodes.get(link.destination)
                assert dst_node is not None

                self._logger.info(
                    f"source node: {src_node}, destination node: {dst_node}"
                )

                src_domain = self.topology_manager.get_domain_name(src_node["id"])
                dst_domain = self.topology_manager.get_domain_name(dst_node["id"])

                # TODO: what do we do when a domain can't be
                # determined? Can a domain be `None`?
                self._logger.info(
                    f"source domain: {src_domain}, destination domain: {dst_domain}"
                )

                current_link_set.append(link)
                current_domain = src_domain
                if src_domain == dst_domain:
                    # current_domain = domain_1
                    if count == len(links) - 1:
                        breakdown[current_domain] = current_link_set.copy()
                else:
                    breakdown[current_domain] = current_link_set.copy()
                    current_domain = None
                    current_link_set = []

        self._logger.info(f"[intermediate] breakdown: {breakdown}")

        # now starting with the ingress_port
        first = True
        i = 0
        domain_breakdown = {}

        # TODO: using dict to represent a breakdown is dubious, and
        # may lead to incorrect results.  Dicts are lexically ordered,
        # and that may break some assumptions about the order in which
        # we form and traverse the breakdown.

        # Note:Extra flag to indicate if the connection request is in the format of TrafficMatrix or not
        # If the connection request is in the format of TrafficMatrix, then the ingress_port and egress_port
        # are not present in the connection_request
        request_format_is_tm = isinstance(connection_request, list)
        self._logger.info(
            f"connection_requst: {connection_request}; type:{type(request_format_is_tm)}"
        )
        same_domain_port_flag = False
        if not request_format_is_tm:
            connection_request = (
                ConnectionHandler().import_connection_data(connection_request).to_dict()
            )
            self._logger.info(
                f'connection_requst ingress_port: {connection_request["ingress_port"]["id"]}'
            )
            self._logger.info(
                f'connection_requst egress_port: {connection_request["egress_port"]["id"]}'
            )
            # flag to indicate if the request ingress and egress ports belong to the same domain
            same_domain_port_flag = self.topology_manager.are_two_ports_same_domain(
                connection_request["ingress_port"]["id"],
                connection_request["egress_port"]["id"],
            )
            self._logger.info(f"same_domain_user_port_flag: {same_domain_port_flag}")

        # Now generate the breakdown with potential user specified tags
        ingress_user_port = None
        egress_user_port = None
        for domain, links in breakdown.items():
            self._logger.debug(
                f"Creating domain_breakdown: domain: {domain}, links: {links}"
            )
            segment = {}

            if first:
                first = False
                # ingress port for this domain is on the first link.
                if (
                    not request_format_is_tm
                    and connection_request["ingress_port"]["id"]
                    not in self.topology_manager.get_port_link_map()
                ):
                    self._logger.warning(
                        f"Port {connection_request['ingress_port']['id']} not found in port map, it's a user port"
                    )
                    ingress_port_id = connection_request["ingress_port"]["id"]
                    ingress_user_port = connection_request["ingress_port"]
                    ingress_port = self.topology_manager.get_port_by_id(ingress_port_id)
                else:
                    if request_format_is_tm:
                        ingress_port, _ = self._get_ports_by_link(links[0])
                    else:
                        ingress_port = self.topology_manager.get_port_by_id(
                            connection_request["ingress_port"]["id"]
                        )

                # egress port for this domain is on the last link.
                if (
                    not request_format_is_tm
                    and same_domain_port_flag
                    and connection_request["egress_port"]["id"]
                    not in self.topology_manager.get_port_link_map()
                ):
                    self._logger.warning(
                        f"Port {connection_request['egress_port']['id']} not found in port map, it's a user port"
                    )
                    egress_port_id = connection_request["egress_port"]["id"]
                    egress_user_port = connection_request["egress_port"]
                    egress_port = self.topology_manager.get_port_by_id(egress_port_id)
                    _, next_ingress_port = self._get_ports_by_link(links[-1])
                else:
                    egress_port, next_ingress_port = self._get_ports_by_link(links[-1])
                    if same_domain_port_flag:
                        egress_port = next_ingress_port
                self._logger.info(
                    f"ingress_port:{ingress_port}, egress_port:{egress_port}, next_ingress_port:{next_ingress_port}"
                )
            elif i == len(breakdown) - 1:
                ingress_port = next_ingress_port
                if (
                    not request_format_is_tm
                    and connection_request["egress_port"]["id"]
                    not in self.topology_manager.get_port_link_map()
                ):
                    self._logger.warning(
                        f"Port {connection_request['egress_port']['id']} not found in port map, it's a user port"
                    )
                    egress_port_id = connection_request["egress_port"]["id"]
                    egress_user_port = connection_request["egress_port"]
                    egress_port = self.topology_manager.get_port_by_id(egress_port_id)
                else:
                    _, egress_port = self._get_ports_by_link(links[-1])

                self._logger.info(f"links[-1]: {links[-1]}")
                self._logger.info(
                    f"ingress_port:{ingress_port}, egress_port:{egress_port}"
                )
            else:
                ingress_port = next_ingress_port
                egress_port, next_ingress_port = self._get_ports_by_link(links[-1])

            segment = {}
            segment["ingress_port"] = ingress_port
            segment["egress_port"] = egress_port

            self._logger.info(f"segment for {domain}: {segment}")

            domain_breakdown[domain] = segment.copy()
            i = i + 1

        self._logger.info(
            f"generate_connection_breakdown(): domain_breakdown: {domain_breakdown}"
        )

        tagged_breakdown = self._reserve_vlan_breakdown(
            domain_breakdown=domain_breakdown,
            request_id=solution.request_id,
            ingress_user_port=ingress_user_port,
            egress_user_port=egress_user_port,
        )
        self._logger.info(
            f"generate_connection_breakdown(): tagged_breakdown: {tagged_breakdown}"
        )

        # Make tests pass, temporarily.
        if tagged_breakdown is None:
            return None

        assert isinstance(tagged_breakdown, VlanTaggedBreakdowns)

        # Return a dict containing VLAN-tagged breakdown in the
        # expected format.
        return tagged_breakdown.to_dict().get("breakdowns")

    def _get_ports_by_link(self, link: ConnectionPath):
        """
        Given a link, find the ports associated with it.

        Returns a (Port, Port) tuple.
        """
        assert isinstance(link, ConnectionPath)

        node1 = self.graph.nodes[link.source]["id"]
        node2 = self.graph.nodes[link.destination]["id"]

        ports = self.topology_manager.get_topology().get_port_by_link(node1, node2)

        # Avoid some possible crashes.
        if ports is None:
            return None, None

        n1, p1, n2, p2 = ports

        assert n1 == node1
        assert n2 == node2

        return p1, p2

    """
    functions for vlan reservation.

    Operations are:

        - obtain the available vlan lists

        - find the vlan continuity on a path if possible.

        - find the vlan translation on the multi-domain path if
          continuity not possible

        - reserve the vlan on all the ports on the path

        - unreserve the vlan when the path is removed
    """

    def _reserve_vlan_breakdown(
        self,
        domain_breakdown: dict,
        request_id: str,
        ingress_user_port=None,
        egress_user_port=None,
    ) -> Optional[VlanTaggedBreakdowns]:
        """
        Upate domain breakdown with VLAN reservation information.

        This is the top-level function, to be called after
        _generate_connection_breakdown_tm(), and should be a private
        implementation detail.  It should be always called, meaning,
        the VLAN tags should be present in the final breakdown,
        regardless of whether the connection request explicitly asked
        for it or not.

        For this to work, TEManager should maintain a table of VLAN
        allocation from each of the domains.  The ones that are not in
        use can be reserved, and the ones that are not in use anymore
        should be returned to the pool by calling unreserve().

        :param domain_breakdown: per port available vlan range is
            pased in datamodel._parse_available_vlans(self, vlan_str)

        :return: Updated domain_breakdown with the VLAN assigned to
                 each port along a path, or None if failure.
        """

        # # Check if there exist a path of vlan continuity.  This is
        # # disabled for now, until the simple case is handled.
        # selected_vlan = self.find_vlan_on_path(domain_breakdown)
        # if selected_vlan is not None:
        #     return self._reserve_vlan_on_path(domain_breakdown, selected_vlan)

        # if not, assuming vlan translation on the domain border port

        self._logger.info(
            f"reserve_vlan_breakdown: domain_breakdown: {domain_breakdown}"
        )

        breakdowns = {}

        # upstream_o_vlan = ""
        for domain, segment in domain_breakdown.items():
            # These are topology ports
            ingress_port = segment.get("ingress_port")
            egress_port = segment.get("egress_port")

            self._logger.debug(
                f"VLAN reservation: domain: {domain}, "
                f"ingress_port: {ingress_port}, egress_port: {egress_port}"
            )

            if ingress_port is None or egress_port is None:
                return None

            ingress_user_port_tag = None
            egress_user_port_tag = None
            if (
                ingress_user_port is not None
                and ingress_port["id"] == ingress_user_port["id"]
            ):
                ingress_user_port_tag = ingress_user_port.get("vlan_range")
            if (
                egress_user_port is not None
                and egress_port["id"] == egress_user_port["id"]
            ):
                egress_user_port_tag = egress_user_port.get("vlan_range")

            ingress_vlan = self._reserve_vlan(
                domain, ingress_port, request_id, ingress_user_port_tag
            )
            egress_vlan = self._reserve_vlan(
                domain, egress_port, request_id, egress_user_port_tag
            )

            ingress_port_id = ingress_port["id"]
            egress_port_id = egress_port["id"]

            # TODO: what to do when a port is not in the port map which only has all the ports on links?
            # User facing ports need clarification from the custermers.
            # For now, we are assuming that the user facing port either (1) provides the vlan
            # or (2) uses the OXP vlan if (2.1) not provided or provided (2.2) is not in the vlan range in the topology port.
            # And we do't allow user specified vlan on a OXP port.
            if (
                ingress_port_id not in self.topology_manager.get_port_link_map()
                and ingress_vlan is None
            ):
                self._logger.warning(
                    f"Port {ingress_port_id} not found in port map, it's a user port, by default uses the OXP vlan"
                )
                ingress_vlan = egress_vlan

            if (
                egress_port_id not in self.topology_manager.get_port_link_map()
                and egress_vlan is None
            ):
                self._logger.warning(
                    f"Port {egress_port_id} not found in port map, it's a user port, by default uses the OXP vlan"
                )
                egress_vlan = ingress_vlan

            self._logger.info(
                f"VLAN reservation: domain: {domain}, "
                f"ingress_vlan: {ingress_vlan}, egress_vlan: {egress_vlan}"
            )

            # if one has empty vlan range, first resume reserved vlans
            # in the previous domain, then return false.
            if ingress_vlan is None:
                self._unreserve_vlan(domain, ingress_port, ingress_vlan)
                return None

            if egress_vlan is None:
                self._unreserve_vlan(domain, egress_port, egress_vlan)
                return None

            # # vlan translation from upstream_o_vlan to i_vlan
            # segment["ingress_upstream_vlan"] = upstream_o_vlan
            # segment["ingress_vlan"] = ingress_vlan
            # segment["egress_vlan"] = egress_vlan
            # upstream_o_vlan = egress_vlan

            port_a = VlanTaggedPort(
                VlanTag(value=ingress_vlan, tag_type=1), port_id=ingress_port_id
            )
            port_z = VlanTaggedPort(
                VlanTag(value=egress_vlan, tag_type=1), port_id=egress_port_id
            )

            # Names look like "AMLIGHT_vlan_201_202_Ampath_Tenet".  We
            # can form the initial part, but where did the
            # `Ampath_Tenet` at the end come from?
            domain_name = domain.split(":")[-1].split(".")[0].upper()
            name = f"{domain_name}_vlan_{ingress_vlan}_{egress_vlan}"

            breakdowns[domain] = VlanTaggedBreakdown(
                name=name,
                dynamic_backup_path=True,
                uni_a=port_a,
                uni_z=port_z,
            )

        return VlanTaggedBreakdowns(breakdowns=breakdowns)

    def _find_vlan_on_path(self, path):
        """
        Find an unused available VLAN on path.

        Finds a VLAN that's not being used at the moment on a provided
        path.  Returns an available VLAN if possible, None if none are
        available on the submitted path.

        output: vlan_tag string or None
        """

        # TODO: implement this
        # https://github.com/atlanticwave-sdx/pce/issues/126

        assert False, "Not implemented"

    def _reserve_vlan_on_path(self, domain_breakdown, selected_vlan):
        # TODO: what is the difference between reserve_vlan and
        # reserve_vlan_on_path?

        # TODO: implement this
        # https://github.com/atlanticwave-sdx/pce/issues/126

        # return domain_breakdown
        assert False, "Not implemented"

    def _reserve_vlan(self, domain: str, port: dict, request_id: str, tag=None):
        # with self._topology_lock:
        #     pass

        port_id = port["id"]
        self._logger.debug(f"reserve_vlan domain: {domain} port_id: {port_id}")

        if port_id is None:
            return None

        # Look up available VLAN tags by domain and port ID.
        # self._logger.debug(f"vlan tags table: {self._vlan_tags_table}")
        domain_table = self._vlan_tags_table.get(domain)
        # self._logger.debug(f"domain vlan table: {domain} domain_table: {domain_table}")

        if domain_table is None:
            self._logger.warning(f"reserve_vlan domain: {domain} entry: {domain_table}")
            return None

        vlan_table = domain_table.get(port_id)

        self._logger.debug(f"reserve_vlan domain: {domain} vlan_table: {vlan_table}")

        # TODO: figure out when vlan_table can be None
        if vlan_table is None:
            self._logger.warning(
                f"Can't find a mapping for domain:{domain} port:{port_id}"
            )
            return None

        available_tag = None

        if tag is None:
            # Find the first available VLAN tag from the table.
            for vlan_tag, vlan_usage in vlan_table.items():
                if vlan_usage is UNUSED_VLAN:
                    available_tag = vlan_tag
        else:
            if tag in vlan_table and vlan_table[tag] is UNUSED_VLAN:
                available_tag = tag
            else:
                return None

        # mark the tag as in-use.
        vlan_table[available_tag] = request_id

        self._logger.debug(
            f"reserve_vlan domain {domain}, after reservation: "
            f"vlan_table: {vlan_table}, available_tag: {available_tag}"
        )

        return available_tag

    def unreserve_vlan(self, request_id: str):
        """
        Return previously reserved VLANs back to the pool.
        """
        for domain, port_table in self._vlan_tags_table.items():
            for port, vlan_table in port_table.items():
                for vlan, assignment in vlan_table.items():
                    if assignment == request_id:
                        vlan_table[vlan] = UNUSED_VLAN

    # to be called by delete_connection()
    def _unreserve_vlan_breakdown(self, break_down):
        # TODO: implement this.
        # https://github.com/atlanticwave-sdx/pce/issues/127
        # with self._topology_lock:
        #     pass
        assert False, "Not implemented"

    def _unreserve_vlan(self, domain: str, port: dict, tag=None):
        """
        Mark a VLAN tag as not in use.
        """
        # TODO: implement this.
        # https://github.com/atlanticwave-sdx/pce/issues/127

        # with self._topology_lock:
        #     pass
        assert False, "Not implemented"

    def _print_vlan_tags_table(self):
        import pprint

        self._logger.info("------ VLAN TAGS TABLE -------")
        self._logger.info(pprint.pformat(self._vlan_tags_table))
        self._logger.info("------------------------------")
