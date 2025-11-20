import threading
import logging
import time

class NodeMonitor:
    """
    Monitors the status of nodes in the distributed system
    """
    def __init__(self, nodes: list, check_interval: int = 5, timeout: int = 15):
        """
        Initialize the NodeMonitor

        Args:
            nodes: List of nodes to monitor (e.g., [(host, port), ...])
            check_interval: Time interval (in seconds) between health checks
            timeout: Time (in seconds) to consider a node as failed
        """
        self.nodes = nodes
        self.check_interval = check_interval
        self.timeout = timeout
        self.node_status = {node: {'last_seen': time.time(), 'active': True} for node in nodes}
        self.logger = logging.getLogger(__name__)
        self.lock = threading.Lock()

    def start_monitoring(self):
        """
        Start monitoring nodes in a separate thread
        """
        threading.Thread(target=self._monitor_nodes, daemon=True).start()
        self.logger.info("Node monitoring started")

    def _monitor_nodes(self):
        """
        Periodically check the status of nodes
        """
        while True:
            time.sleep(self.check_interval)
            with self.lock:
                for node, status in self.node_status.items():
                    if time.time() - status['last_seen'] > self.timeout:
                        if status['active']:
                            self.logger.warning(f"Node {node} is unresponsive. Marking as failed.")
                            status['active'] = False
                            self._reassign_tasks(node)

    def update_heartbeat(self, node):
        """
        Update the heartbeat for a node

        Args:
            node: The node that sent a heartbeat
        """
        with self.lock:
            if node in self.node_status:
                self.node_status[node]['last_seen'] = time.time()
                if not self.node_status[node]['active']:
                    self.logger.info(f"Node {node} is back online.")
                    self.node_status[node]['active'] = True

    def _reassign_tasks(self, failed_node):
        """
        Reassign tasks from a failed node to other nodes

        Args:
            failed_node: The node that failed
        """
        self.logger.info(f"Reassigning tasks from failed node {failed_node}.")
        # Implement task reassignment logic here
        # For example, consult logs or a central task queue

