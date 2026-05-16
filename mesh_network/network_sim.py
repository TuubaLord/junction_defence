import math
import numpy as np

class Node:
    def __init__(self, id, x, y, init_time, is_master=False):
        self.id = id
        self.x = x
        self.y = y
        self.init_time = init_time
        self.is_master = is_master
        self.is_active = False
        self.is_disabled = False
        self.jammedness = 0.0 # Local jammedness at node
        
        # Distance Vector Routing Table
        self.routing_table = {}
        if self.is_master:
            self.routing_table[self.id] = {'distance': 0.0, 'hops': 0, 'next_hop': self}
            
        self.neighbors = []
        self.last_ping_time = -100
        self.ping_interval = 10.0
        self.check_interval = 2.0
        self.last_check_time = -100
        self.ping_speed = 5.0
        self.max_ping_radius = 15.0

    def distance_to(self, other_node):
        return math.hypot(self.x - other_node.x, self.y - other_node.y)

class Jammer:
    def __init__(self, x, y, strength=50.0, beam_angle=135, beam_width=40):
        self.x = x
        self.y = y
        self.strength = strength
        self.beam_angle = beam_angle  # in degrees
        self.beam_width = beam_width  # in degrees

    def get_interference(self, target_x, target_y):
        dist = math.hypot(target_x - self.x, target_y - self.y)
        if dist < 0.1: dist = 0.1
        interference = self.strength / (dist ** 2)
        
        if self.beam_angle is not None:
            angle_to_target = math.degrees(math.atan2(target_y - self.y, target_x - self.x))
            angle_diff = (angle_to_target - self.beam_angle + 180) % 360 - 180
            if abs(angle_diff) > self.beam_width / 2:
                interference *= 0.1
            else:
                interference *= math.exp(-0.5 * (angle_diff / (self.beam_width / 4))**2)
        return interference

class NetworkSim:
    def __init__(self, node_locations_file, master_locations_file):
        self.nodes = []
        self.masters = []
        self.current_time = 0.0
        self.pings = []
        self.active_transmissions = {}
        self.last_message_spawn_time = 0.0
        self.message_spawn_interval = 10.0
        
        self.jammer = Jammer(30, 15, strength=200, beam_angle=180, beam_width=40)
        self.jammedness_samples = []
        self.edge_jammedness = {} 
        
        # Estimated parameters
        self.est_jammer_pos = (0, 0)
        self.est_beam_angle = 0.0
        self.est_beam_width = 0.0

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
                        x, y, init_time = map(float, parts[:3])
                        nid = f"{len(self.masters)}" if is_master else f"N_{len(self.nodes)}"
                        node = Node(nid, x, y, init_time, is_master)
                        self.nodes.append(node)
                        if is_master: self.masters.append(node)
        except FileNotFoundError:
            print(f"Error: {filename} not found.")

    def step(self, dt):
        self.current_time += dt
        for node in self.nodes:
            if node.is_disabled: continue
            if not node.is_active and self.current_time >= node.init_time:
                node.is_active = True
                self._emit_ping(node, 'discovery')
            
            if node.is_active:
                if (self.current_time - node.last_ping_time) >= node.ping_interval:
                    self._emit_ping(node, 'discovery')
                if (self.current_time - node.last_check_time) >= node.check_interval:
                    node.last_check_time = self.current_time
                    self._check_neighbors(node)

        active_pings = []
        for p in self.pings:
            radius = (self.current_time - p['start_time']) * p['sender'].ping_speed
            if radius > p['sender'].max_ping_radius: continue
            active_pings.append(p)
            for target_node in self.nodes:
                if target_node == p['sender'] or not target_node.is_active: continue
                if target_node in p['handled_by']: continue
                if p['sender'].distance_to(target_node) <= radius:
                    p['handled_by'].add(target_node)
                    self._handle_ping_collision(p, target_node)
        self.pings = active_pings

        if self.current_time - self.last_message_spawn_time >= self.message_spawn_interval:
            self.last_message_spawn_time = self.current_time
            if len(self.masters) >= 2:
                sender, target = self.masters[0], self.masters[1]
                if target.id in sender.routing_table:
                    hops = sender.routing_table[target.id]['hops']
                    next_hop_id = sender.routing_table[target.id]['next_hop'].id
                    timeout = max(1.5, hops * 1.5)
                    msg_id = f"msg_{int(self.current_time * 100)}"
                    self.active_transmissions[msg_id] = {'start_time': self.current_time, 'timeout': timeout, 'target': target}
                    self._emit_ping(sender, 'blue_ping', payload={'msg_id': msg_id, 'target': target.id, 'visited': [sender.id], 'next_hop': next_hop_id})

        for msg_id, t_info in list(self.active_transmissions.items()):
            if self.current_time - t_info['start_time'] > t_info['timeout']:
                self.active_transmissions[msg_id]['start_time'] = self.current_time
                target_id = t_info['target'].id
                sender = self.masters[0]
                if target_id in sender.routing_table:
                    next_hop_id = sender.routing_table[target_id]['next_hop'].id
                    self._emit_ping(sender, 'blue_ping', payload={'msg_id': msg_id, 'target': target_id, 'visited': [sender.id], 'next_hop': next_hop_id})

        self._estimate_beam_field()

    def _emit_ping(self, sender, ptype, target=None, payload=None):
        if ptype == 'discovery': sender.last_ping_time = self.current_time
        self.pings.append({
            'sender': sender, 'start_time': self.current_time, 'type': ptype, 'target': target, 'payload': payload,
            'handled_by': set(), 'routing_table': {k: {'distance': v['distance'], 'hops': v['hops']} for k, v in sender.routing_table.items()}
        })

    def _handle_ping_collision(self, ping, receiver):
        sender = ping['sender']
        if sender not in receiver.neighbors:
            receiver.neighbors.append(sender)
            if receiver not in sender.neighbors: sender.neighbors.append(receiver)
                
        dist_to_sender = receiver.distance_to(sender)
        
        # Jammedness Calculation
        interference = self.jammer.get_interference(receiver.x, receiver.y)
        signal = 1.0 / (dist_to_sender ** 2 if dist_to_sender > 0.1 else 0.01)
        jammedness = interference / (signal + 0.01)
        
        receiver.jammedness = (receiver.jammedness * 0.9) + (jammedness * 0.1)
        edge = frozenset([sender.id, receiver.id])
        self.edge_jammedness[edge] = jammedness
        self.jammedness_samples.append(((sender.x + receiver.x) / 2, (sender.y + receiver.y) / 2, jammedness))
        if len(self.jammedness_samples) > 200: self.jammedness_samples.pop(0)

        for master_id, advertised in ping['routing_table'].items():
            new_dist, new_hops = advertised['distance'] + dist_to_sender, advertised['hops'] + 1
            if master_id not in receiver.routing_table:
                receiver.routing_table[master_id] = {'distance': new_dist, 'hops': new_hops, 'next_hop': sender}
            else:
                current_dist = receiver.routing_table[master_id]['distance']
                if new_dist < current_dist - 0.1:
                    receiver.routing_table[master_id] = {'distance': new_dist, 'hops': new_hops, 'next_hop': sender}
                elif receiver.routing_table[master_id]['next_hop'] == sender and abs(new_dist - current_dist) > 0.1:
                    receiver.routing_table[master_id]['distance'], receiver.routing_table[master_id]['hops'] = new_dist, new_hops
                    
        if ping['type'] == 'discovery': self._emit_ping(receiver, 'reply', target=sender)
        if ping['type'] == 'blue_ping':
            msg_id, visited, expected_next_hop = ping['payload']['msg_id'], ping['payload'].get('visited', []), ping['payload'].get('next_hop')
            if expected_next_hop and expected_next_hop != receiver.id: return
            if receiver.id not in visited:
                new_visited, target_id = visited + [receiver.id], ping['payload']['target']
                if receiver.id == target_id:
                    if '0' in receiver.routing_table:
                        next_hop_id = receiver.routing_table['0']['next_hop'].id
                        self._emit_ping(receiver, 'red_ping', payload={'msg_id': msg_id, 'target': '0', 'visited': [receiver.id], 'next_hop': next_hop_id})
                elif target_id in receiver.routing_table:
                    next_hop_id = receiver.routing_table[target_id]['next_hop'].id
                    new_payload = dict(ping['payload']); new_payload['visited'], new_payload['next_hop'] = new_visited, next_hop_id
                    self._emit_ping(receiver, 'blue_ping', payload=new_payload)
                        
        elif ping['type'] == 'red_ping':
            msg_id, visited, expected_next_hop = ping['payload']['msg_id'], ping['payload'].get('visited', []), ping['payload'].get('next_hop')
            if expected_next_hop and expected_next_hop != receiver.id: return
            if receiver.id not in visited:
                new_visited, target_id = visited + [receiver.id], ping['payload']['target']
                if receiver.id == target_id:
                    if msg_id in self.active_transmissions: del self.active_transmissions[msg_id]
                elif target_id in receiver.routing_table:
                    next_hop_id = receiver.routing_table[target_id]['next_hop'].id
                    new_payload = dict(ping['payload']); new_payload['visited'], new_payload['next_hop'] = new_visited, next_hop_id
                    self._emit_ping(receiver, 'red_ping', payload=new_payload)

    def _check_neighbors(self, node):
        active_neighbors = [n for n in node.neighbors if n.is_active]
        node.neighbors = active_neighbors
        for mid in list(node.routing_table.keys()):
            if mid == node.id and node.is_master: continue
            if node.routing_table[mid]['next_hop'] not in active_neighbors: del node.routing_table[mid]

    def _estimate_beam_field(self):
        # 1. Estimate Jammer Position (Weighted centroid of nodes by jammedness)
        nodes = [n for n in self.nodes if n.is_active and n.jammedness > 0.1]
        if not nodes: return
        
        total_j = sum(n.jammedness for n in nodes)
        self.est_jammer_pos = (sum(n.x * n.jammedness for n in nodes) / total_j,
                               sum(n.y * n.jammedness for n in nodes) / total_j)
        
        # 2. Estimate Beam Angle (Weighted circular mean)
        sin_sum, cos_sum = 0.0, 0.0
        for n in nodes:
            angle = math.atan2(n.y - self.est_jammer_pos[1], n.x - self.est_jammer_pos[0])
            sin_sum += n.jammedness * math.sin(angle)
            cos_sum += n.jammedness * math.cos(angle)
        
        self.est_beam_angle = math.degrees(math.atan2(sin_sum, cos_sum))
        
        # 3. Estimate Beam Width (Weighted standard deviation of angles)
        angles = []
        for n in nodes:
            a = math.degrees(math.atan2(n.y - self.est_jammer_pos[1], n.x - self.est_jammer_pos[0]))
            diff = (a - self.est_beam_angle + 180) % 360 - 180
            angles.append((diff, n.jammedness))
        
        if len(angles) > 1:
            weighted_var = sum(j * (d**2) for d, j in angles) / total_j
            self.est_beam_width = max(10, math.sqrt(weighted_var) * 2.5) # Scale factor for visualization
