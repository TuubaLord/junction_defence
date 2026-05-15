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
        # Map of master_node_id -> { 'distance': float, 'next_hop': Node }
        self.routing_table = {}
        if self.is_master:
            self.routing_table[self.id] = {'distance': 0.0, 'next_hop': self}
            
        self.neighbors = [] # All nodes within ping range
        self.last_ping_time = -100
        self.ping_interval = 10.0
        self.check_interval = 2.0
        self.last_check_time = -100
        self.ping_speed = 15.0
        self.max_ping_radius = 15.0

    def distance_to(self, other_node):
        return math.hypot(self.x - other_node.x, self.y - other_node.y)

class Message:
    def __init__(self, sender_master, target_master, start_node, next_node):
        self.sender = sender_master
        self.target = target_master
        self.current_node = start_node
        self.next_node = next_node
        self.progress = 0.0 # Distance traveled from current_node towards next_node
        self.speed = 3.0 # physical travel speed units/sec
        self.edge_length = start_node.distance_to(next_node) if next_node else 0

class NetworkSim:
    def __init__(self, node_locations_file, master_locations_file):
        self.nodes = []
        self.masters = []
        self.current_time = 0.0
        self.pings = []
        self.messages = []
        self.last_message_spawn_time = 0.0
        
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
                        nid = f"M_{len(self.masters)}" if is_master else f"N_{len(self.nodes)}"
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
        if self.current_time - self.last_message_spawn_time >= 2.0:
            self.last_message_spawn_time = self.current_time
            if len(self.masters) >= 2:
                # Spawn a message from Master 0 -> 1
                self._spawn_message(self.masters[0], self.masters[1])
                # Spawn a message from Master 1 -> 0
                self._spawn_message(self.masters[1], self.masters[0])

        # 5. Move Messages Physically
        active_messages = []
        for msg in self.messages:
            if msg.next_node is None or not msg.next_node.is_active: 
                continue # Dropped if no route or node died
                
            msg.progress += msg.speed * dt
            
            if msg.progress >= msg.edge_length:
                # Arrived at next_node
                msg.current_node = msg.next_node
                if msg.current_node == msg.target:
                    # Message delivered successfully!
                    continue
                    
                # Look up next hop in routing table
                target_id = msg.target.id
                if target_id in msg.current_node.routing_table:
                    next_hop = msg.current_node.routing_table[target_id]['next_hop']
                    if next_hop and next_hop.is_active:
                        msg.next_node = next_hop
                        msg.edge_length = msg.current_node.distance_to(next_hop)
                        msg.progress = 0.0
                        active_messages.append(msg)
                # Else message is dropped
            else:
                active_messages.append(msg)
                
        self.messages = active_messages

    def _spawn_message(self, sender, target):
        if not sender.is_active: return
        target_id = target.id
        if target_id in sender.routing_table:
            next_hop = sender.routing_table[target_id]['next_hop']
            if next_hop != sender and next_hop is not None:
                msg = Message(sender, target, sender, next_hop)
                self.messages.append(msg)

    def _emit_ping(self, sender, ptype, target=None):
        if ptype == 'discovery':
            sender.last_ping_time = self.current_time
            
        self.pings.append({
            'sender': sender,
            'start_time': self.current_time,
            'type': ptype,
            'target': target,
            'handled_by': set(),
            # Piggyback routing table on the ping
            'routing_table': {k: v['distance'] for k, v in sender.routing_table.items()}
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
        
        for master_id, advertised_dist in ping['routing_table'].items():
            new_dist = advertised_dist + dist_to_sender
            
            if master_id not in receiver.routing_table:
                receiver.routing_table[master_id] = {'distance': new_dist, 'next_hop': sender}
            else:
                current_dist = receiver.routing_table[master_id]['distance']
                if new_dist < current_dist - 0.1: # Small epsilon to prevent loops
                    receiver.routing_table[master_id] = {'distance': new_dist, 'next_hop': sender}
                # If path through same next_hop worsened, update it
                elif receiver.routing_table[master_id]['next_hop'] == sender and abs(new_dist - current_dist) > 0.1:
                    receiver.routing_table[master_id]['distance'] = new_dist
                    
        # Always reply to discovery so the sender can discover us
        if ping['type'] == 'discovery':
            self._emit_ping(receiver, 'reply', target=sender)

    def _check_neighbors(self, node):
        active_neighbors = [n for n in node.neighbors if n.is_active]
        node.neighbors = active_neighbors
        
        # Purge dead routes (if neighbor died)
        for mid in list(node.routing_table.keys()):
            if mid == node.id and node.is_master: continue
            next_hop = node.routing_table[mid]['next_hop']
            if next_hop not in active_neighbors:
                del node.routing_table[mid]
