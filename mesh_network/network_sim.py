import math

class Node:
    def __init__(self, id, x, y, init_time, is_master=False):
        self.id = id
        self.x = x
        self.y = y
        self.init_time = init_time
        self.is_master = is_master
        self.is_active = False
        self.is_disabled = False
        
        # Distance Vector Routing Table
        # Map of master_node_id -> { 'distance': float, 'hops': int, 'next_hop': Node }
        self.routing_table = {}
        if self.is_master:
            self.routing_table[self.id] = {'distance': 0.0, 'hops': 0, 'next_hop': self}
            
        self.neighbors = [] # All nodes within ping range
        self.last_ping_time = -100
        self.ping_interval = 10.0
        self.check_interval = 2.0
        self.last_check_time = -100
        self.ping_speed = 5.0
        self.max_ping_radius = 15.0

    def distance_to(self, other_node):
        return math.hypot(self.x - other_node.x, self.y - other_node.y)

class NetworkSim:
    def __init__(self, node_locations_file, master_locations_file):
        self.nodes = []
        self.masters = []
        self.current_time = 0.0
        self.pings = []
        self.active_transmissions = {} # msg_id -> {'start_time', 'timeout', 'target'}
        self.last_message_spawn_time = 0.0
        self.message_spawn_interval = 10.0 # <-- Edit this value (in seconds) to change how often Master 0 sends messages
        
        self.load_nodes(node_locations_file, is_master=False)
        self.load_nodes(master_locations_file, is_master=True)
        
    def load_nodes(self, filename, is_master):
        try:
            with open(filename, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    parts = line.split(',')
                    if len(parts) >= 3:
                        x = float(parts[0])
                        y = float(parts[1])
                        init_time = float(parts[2])
                        nid = f"{len(self.masters)}" if is_master else f"N_{len(self.nodes)}"
                        node = Node(nid, x, y, init_time, is_master)
                        self.nodes.append(node)
                        if is_master:
                            self.masters.append(node)
        except FileNotFoundError:
            print(f"Error: {filename} not found.")

    def step(self, dt):
        self.current_time += dt
        
        # 1. Activate nodes based on init_time
        for node in self.nodes:
            if node.is_disabled: continue
            if not node.is_active and self.current_time >= node.init_time:
                node.is_active = True
                self._emit_ping(node, 'discovery')
                
        # 2. Update active nodes
        for node in self.nodes:
            if node.is_disabled: continue
            if not node.is_active: continue
            
            # Periodic pings to share routing tables
            if (self.current_time - node.last_ping_time) >= node.ping_interval:
                self._emit_ping(node, 'discovery')
                
            # Periodic connection and route cleanup
            if (self.current_time - node.last_check_time) >= node.check_interval:
                node.last_check_time = self.current_time
                self._check_neighbors(node)

        # 3. Update pings (signal propagation)
        active_pings = []
        for p in self.pings:
            radius = (self.current_time - p['start_time']) * p['sender'].ping_speed
            if radius > p['sender'].max_ping_radius:
                continue # ping dissipated
                
            active_pings.append(p)
            for target_node in self.nodes:
                if target_node == p['sender'] or not target_node.is_active: continue
                if target_node in p['handled_by']: continue
                
                # Check distance
                if p['sender'].distance_to(target_node) <= radius:
                    p['handled_by'].add(target_node)
                    self._handle_ping_collision(p, target_node)
                    
        self.pings = active_pings

        # 4. Spawning Messages from Masters
        if self.current_time - self.last_message_spawn_time >= self.message_spawn_interval:
            self.last_message_spawn_time = self.current_time
            if len(self.masters) >= 2:
                sender = self.masters[0]
                target = self.masters[1]
                
                # Check if route exists to determine timeout
                if target.id in sender.routing_table:
                    hops = sender.routing_table[target.id]['hops']
                    next_hop_id = sender.routing_table[target.id]['next_hop'].id
                    timeout = max(1.5, hops * 1.5) # Minimum 1.5s
                    
                    msg_id = f"msg_{int(self.current_time * 100)}"
                    self.active_transmissions[msg_id] = {
                        'start_time': self.current_time,
                        'timeout': timeout,
                        'target': target
                    }
                    self._emit_ping(sender, 'blue_ping', payload={'msg_id': msg_id, 'target': target.id, 'visited': [sender.id], 'next_hop': next_hop_id})

        # 5. Check for timeouts and retries
        for msg_id, t_info in list(self.active_transmissions.items()):
            if self.current_time - t_info['start_time'] > t_info['timeout']:
                # Timeout occurred, retry
                self.active_transmissions[msg_id]['start_time'] = self.current_time
                target_id = t_info['target'].id
                sender = self.masters[0]
                if target_id in sender.routing_table:
                    next_hop_id = sender.routing_table[target_id]['next_hop'].id
                    self._emit_ping(sender, 'blue_ping', payload={'msg_id': msg_id, 'target': target_id, 'visited': [sender.id], 'next_hop': next_hop_id})

    def _emit_ping(self, sender, ptype, target=None, payload=None):
        if ptype == 'discovery':
            sender.last_ping_time = self.current_time
            
        self.pings.append({
            'sender': sender,
            'start_time': self.current_time,
            'type': ptype,
            'target': target,
            'payload': payload,
            'handled_by': set(),
            # Piggyback routing table on the ping
            'routing_table': {k: {'distance': v['distance'], 'hops': v['hops']} for k, v in sender.routing_table.items()}
        })

    def _handle_ping_collision(self, ping, receiver):
        sender = ping['sender']
        
        # Add bidirectional edge
        if sender not in receiver.neighbors:
            receiver.neighbors.append(sender)
            if receiver not in sender.neighbors:
                sender.neighbors.append(receiver)
                
        # Handle Routing Updates (Distance Vector)
        dist_to_sender = receiver.distance_to(sender)
        
        for master_id, advertised in ping['routing_table'].items():
            new_dist = advertised['distance'] + dist_to_sender
            new_hops = advertised['hops'] + 1
            
            if master_id not in receiver.routing_table:
                receiver.routing_table[master_id] = {'distance': new_dist, 'hops': new_hops, 'next_hop': sender}
            else:
                current_dist = receiver.routing_table[master_id]['distance']
                if new_dist < current_dist - 0.1: # Small epsilon to prevent loops
                    receiver.routing_table[master_id] = {'distance': new_dist, 'hops': new_hops, 'next_hop': sender}
                # If path through same next_hop worsened, update it
                elif receiver.routing_table[master_id]['next_hop'] == sender and abs(new_dist - current_dist) > 0.1:
                    receiver.routing_table[master_id]['distance'] = new_dist
                    receiver.routing_table[master_id]['hops'] = new_hops
                    
        # Always reply to discovery so the sender can discover us
        if ping['type'] == 'discovery':
            self._emit_ping(receiver, 'reply', target=sender)
            
        # Handle Broadcast Routing (Blue/Red Pings)
        if ping['type'] == 'blue_ping':
            msg_id = ping['payload']['msg_id']
            visited = ping['payload'].get('visited', [])
            expected_next_hop = ping['payload'].get('next_hop')
            
            if expected_next_hop is not None and expected_next_hop != receiver.id:
                return # Only the designated shortest path node should relay this!
            
            if receiver.id not in visited:
                new_visited = visited + [receiver.id]
                target_id = ping['payload']['target']
                
                if receiver.id == target_id:
                    # Target reached! Send red_ping back to Master 0
                    if '0' in receiver.routing_table:
                        next_hop_id = receiver.routing_table['0']['next_hop'].id
                        self._emit_ping(receiver, 'red_ping', payload={'msg_id': msg_id, 'target': '0', 'visited': [receiver.id], 'next_hop': next_hop_id})
                else:
                    # Look up next hop for the target
                    if target_id in receiver.routing_table:
                        next_hop_id = receiver.routing_table[target_id]['next_hop'].id
                        new_payload = dict(ping['payload'])
                        new_payload['visited'] = new_visited
                        new_payload['next_hop'] = next_hop_id
                        self._emit_ping(receiver, 'blue_ping', payload=new_payload)
                        
        elif ping['type'] == 'red_ping':
            msg_id = ping['payload']['msg_id']
            visited = ping['payload'].get('visited', [])
            expected_next_hop = ping['payload'].get('next_hop')
            
            if expected_next_hop is not None and expected_next_hop != receiver.id:
                return # Only the designated shortest path node should relay this!
            
            if receiver.id not in visited:
                new_visited = visited + [receiver.id]
                target_id = ping['payload']['target']
                
                if receiver.id == target_id:
                    # ACK reached Master 0! Remove from active transmissions
                    if msg_id in self.active_transmissions:
                        del self.active_transmissions[msg_id]
                else:
                    # Look up next hop for Master 0
                    if target_id in receiver.routing_table:
                        next_hop_id = receiver.routing_table[target_id]['next_hop'].id
                        new_payload = dict(ping['payload'])
                        new_payload['visited'] = new_visited
                        new_payload['next_hop'] = next_hop_id
                        self._emit_ping(receiver, 'red_ping', payload=new_payload)

    def _check_neighbors(self, node):
        active_neighbors = [n for n in node.neighbors if n.is_active]
        node.neighbors = active_neighbors
        
        # Purge dead routes (if neighbor died)
        for mid in list(node.routing_table.keys()):
            if mid == node.id and node.is_master: continue
            next_hop = node.routing_table[mid]['next_hop']
            if next_hop not in active_neighbors:
                del node.routing_table[mid]
