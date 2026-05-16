import math
import numpy as np
from scipy.interpolate import griddata

class Node:
    def __init__(self, id, x, y, init_time):
        self.id = id
        self.x = x
        self.y = y
        self.init_time = init_time
        self.is_active = False
        self.is_disabled = False
        self.jammedness = 0.0 # Local interference measurement
        
        # Distance Vector Routing Table
        self.routing_table = {}
            
        self.neighbors = []
        self.last_ping_time = -100
        self.ping_interval = 10.0
        self.check_interval = 2.0
        self.last_check_time = -100
        self.ping_speed = 5.0
        self.max_ping_radius = 15.0

    def distance_to(self, other_node):
        return math.hypot(self.x - other_node.x, self.y - other_node.y)
    
    def update_position(self, x, y):
        self.x = x
        self.y = y

class Jammer:
    def __init__(self, x, y, strength=200.0, beam_angle=180, beam_width=40):
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
                interference *= 0.05 # Even more attenuation outside beam
            else:
                interference *= math.exp(-0.5 * (angle_diff / (self.beam_width / 4))**2)
        return interference
    
    def update_params(self, x=None, y=None, angle=None):
        if x is not None: self.x = x
        if y is not None: self.y = y
        if angle is not None: self.beam_angle = angle % 360

class AdvancedNetworkSim:
    def __init__(self, node_locations_file):
        self.nodes = []
        self.current_time = 0.0
        self.pings = []
        self.active_transmissions = {}
        self.last_message_spawn_time = 0.0
        self.message_spawn_interval = 10.0
        
        self.jammer = Jammer(23, 17, strength=400, beam_angle=150, beam_width=40)
        self.edge_jammedness = {} 
        
        # Estimated parameters
        self.est_jammer_pos = (0, 0)
        self.est_beam_angle = 0.0
        self.est_beam_width = 0.0
        self.interference_grid = None # For contour mapping
        self.grid_coords = None

        self.load_nodes(node_locations_file)
        
    def load_nodes(self, filename):
        try:
            with open(filename, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    parts = line.split(',')
                    if len(parts) >= 3:
                        x, y, init_time = map(float, parts[:3])
                        nid = f"D_{len(self.nodes)}"
                        node = Node(nid, x, y, init_time)
                        self.nodes.append(node)
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

        # Message spawning disabled as command nodes are removed

        self._update_estimates()

    def _emit_ping(self, sender, ptype, target=None, payload=None):
        if ptype == 'discovery': sender.last_ping_time = self.current_time
        self.pings.append({
            'sender': sender, 'start_time': self.current_time, 'type': ptype, 'target': target, 'payload': payload,
            'handled_by': set(), 'routing_table': {k: {'distance': v['distance'], 'hops': v['hops']} for k, v in sender.routing_table.items()}
        })

    def _handle_ping_collision(self, ping, receiver):
        sender = ping['sender']
        dist_to_sender = receiver.distance_to(sender)
        
        jammer_interference = self.jammer.get_interference(receiver.x, receiver.y)
        noise_floor = 0.05
        signal_power = 10.0 / (dist_to_sender ** 2 if dist_to_sender > 0.1 else 0.01)
        
        sinr = signal_power / (jammer_interference + noise_floor)
        
        success_prob = 1.0 / (1.0 + math.exp(-2.0 * (sinr - 0.8)))
        if np.random.random() > success_prob:
            return 

        if sender not in receiver.neighbors:
            receiver.neighbors.append(sender)
            if receiver not in sender.neighbors: sender.neighbors.append(receiver)
        
        receiver.jammedness = (receiver.jammedness * 0.8) + (jammer_interference * 0.2)
        
        edge = frozenset([sender.id, receiver.id])
        self.edge_jammedness[edge] = jammer_interference / (signal_power + 0.01)

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

    def _check_neighbors(self, node):
        active_neighbors = [n for n in node.neighbors if n.is_active]
        node.neighbors = active_neighbors
        for mid in list(node.routing_table.keys()):
            if node.routing_table[mid]['next_hop'] not in active_neighbors: del node.routing_table[mid]

    def _update_estimates(self):
        nodes = [n for n in self.nodes if n.is_active and n.jammedness > 0.01]
        if not nodes: return
        
        total_j = sum(n.jammedness for n in nodes)
        self.est_jammer_pos = (sum(n.x * n.jammedness for n in nodes) / total_j,
                               sum(n.y * n.jammedness for n in nodes) / total_j)
        
        points = np.array([[n.x, n.y] for n in nodes])
        values = np.array([n.jammedness for n in nodes])
        
        grid_x, grid_y = np.mgrid[-5:35:50j, -5:35:50j]
        self.grid_coords = (grid_x, grid_y)
        
        try:
            self.interference_grid = griddata(points, values, (grid_x, grid_y), method='linear', fill_value=0)
        except:
            pass
        
        sin_sum, cos_sum = 0.0, 0.0
        for n in nodes:
            angle = math.atan2(n.y - self.est_jammer_pos[1], n.x - self.est_jammer_pos[0])
            sin_sum += n.jammedness * math.sin(angle)
            cos_sum += n.jammedness * math.cos(angle)
        
        self.est_beam_angle = math.degrees(math.atan2(sin_sum, cos_sum))
        
        angles = []
        for n in nodes:
            a = math.degrees(math.atan2(n.y - self.est_jammer_pos[1], n.x - self.est_jammer_pos[0]))
            diff = (a - self.est_beam_angle + 180) % 360 - 180
            angles.append((diff, n.jammedness))
        
        if len(angles) > 1:
            weighted_var = sum(j * (d**2) for d, j in angles) / total_j
            self.est_beam_width = max(10, math.sqrt(weighted_var) * 2.5)
