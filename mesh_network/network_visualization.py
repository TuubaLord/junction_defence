import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import CheckButtons
import os
import numpy as np
import math
from network_sim import NetworkSim

def visualize_network(locations_file, masters_file):
    sim = NetworkSim(locations_file, masters_file)
    
    fig, ax = plt.subplots(figsize=(10, 10))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_title("Mesh Network Routing Simulation")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    
    ax.set_xlim(-5, 35)
    ax.set_ylim(-5, 35)
    ax.grid(True, linestyle='--', alpha=0.3)
    
    scatter_nodes = ax.scatter([], [], color='blue', marker='o', s=100, zorder=5, label='Nodes')
    scatter_disabled = ax.scatter([], [], color='black', marker='o', s=100, zorder=5, label='Disabled')
    scatter_masters = ax.scatter([], [], color='purple', marker='*', s=300, zorder=6, label='Masters')
    scatter_blue_pkts = ax.scatter([], [], color='blue', marker='o', s=50, edgecolors='white', zorder=7, label='Msg Packets')
    scatter_red_pkts = ax.scatter([], [], color='red', marker='o', s=50, edgecolors='white', zorder=7, label='Ack Packets')
    
    ax.legend(loc='upper right')
    
    # Make room for toggle buttons
    plt.subplots_adjust(left=0.25)
    ax_toggles = plt.axes([0.02, 0.4, 0.18, 0.15])
    toggles = CheckButtons(ax_toggles, ('Packets', 'Message Pings', 'Location Pings'), (True, True, True))
    
    visibility = {'Packets': True, 'Message Pings': True, 'Location Pings': True}
    
    def toggle_visibility(label):
        visibility[label] = not visibility[label]
        
    toggles.on_clicked(toggle_visibility)
    
    lines = []
    ping_circles = []
    routing_texts = []

    time_text = ax.text(0.05, 0.95, '', transform=ax.transAxes, fontsize=12,
                        verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    def on_click(event):
        if event.xdata is None or event.ydata is None:
            return
            
        click_x, click_y = event.xdata, event.ydata
        closest_node = None
        min_dist = float('inf')
        
        for node in sim.nodes:
            if node.is_master:
                continue
                
            dist = math.hypot(node.x - click_x, node.y - click_y)
            if dist < min_dist:
                min_dist = dist
                closest_node = node
                
        if closest_node and min_dist < 2.0:
            closest_node.is_disabled = not closest_node.is_disabled
            
            if closest_node.is_disabled:
                closest_node.is_active = False
                print(f"Disabled node {closest_node.id} at ({closest_node.x}, {closest_node.y})")
                # Immediately severe connections for visualization
                for n in sim.nodes:
                    if closest_node in n.neighbors:
                        n.neighbors.remove(closest_node)
                closest_node.neighbors = []
            else:
                print(f"Re-enabled node {closest_node.id} at ({closest_node.x}, {closest_node.y})")
                # Let simulation activate it naturally if time >= init_time

    fig.canvas.mpl_connect('button_press_event', on_click)

    def update(frame):
        dt = 0.1 
        sim.step(dt)
        
        nonlocal lines, ping_circles, routing_texts
        for line in lines: line.remove()
        for circle in ping_circles: circle.remove()
        for text in routing_texts: text.remove()
        lines = []
        ping_circles = []
        routing_texts = []
        
        nodes_x, nodes_y = [], []
        disabled_x, disabled_y = [], []
        masters_x, masters_y = [], []
        msgs_blue_x, msgs_blue_y = [], []
        msgs_red_x, msgs_red_y = [], []
        
        drawn_edges = set()
        
        for node in sim.nodes:
            if node.is_disabled:
                disabled_x.append(node.x)
                disabled_y.append(node.y)
                continue
                
            if not node.is_active: continue
            
            if node.is_master:
                masters_x.append(node.x)
                masters_y.append(node.y)
            else:
                nodes_x.append(node.x)
                nodes_y.append(node.y)
                
            for neighbor in node.neighbors:
                edge = frozenset([node, neighbor])
                if edge not in drawn_edges:
                    drawn_edges.add(edge)
                    line, = ax.plot([node.x, neighbor.x], [node.y, neighbor.y], color='gray', alpha=0.3, linewidth=1, zorder=1)
                    lines.append(line)
                    
        for p in sim.pings:
            radius = (sim.current_time - p['start_time']) * p['sender'].ping_speed
            if radius > 0:
                is_message_ping = p['type'] in ('blue_ping', 'red_ping')
                is_location_ping = p['type'] in ('discovery', 'reply')
                
                # Render expanding circles based on toggles
                if (is_message_ping and visibility['Message Pings']) or (is_location_ping and visibility['Location Pings']):
                    if p['type'] == 'discovery': color = 'green'
                    elif p['type'] == 'reply': color = 'orange'
                    elif p['type'] == 'blue_ping': color = 'blue'
                    elif p['type'] == 'red_ping': color = 'red'
                    else: color = 'gray'
                    
                    alpha_val = max(0, 1 - radius / p['sender'].max_ping_radius)
                    linewidth = 2 if is_message_ping else 1
                    if is_message_ping:
                        alpha_val = min(1.0, alpha_val + 0.3)
                        
                    circle = plt.Circle((p['sender'].x, p['sender'].y), radius, color=color, fill=False, alpha=alpha_val, linewidth=linewidth, zorder=2)
                    ax.add_patch(circle)
                    ping_circles.append(circle)
                    
                # Calculate yellow dots on the edge of message pings
                if is_message_ping and visibility['Packets']:
                    for neighbor in p['sender'].neighbors:
                        dist = p['sender'].distance_to(neighbor)
                        if radius <= dist:
                            ratio = radius / dist
                            mx = p['sender'].x + ratio * (neighbor.x - p['sender'].x)
                            my = p['sender'].y + ratio * (neighbor.y - p['sender'].y)
                            if p['type'] == 'blue_ping':
                                msgs_blue_x.append(mx)
                                msgs_blue_y.append(my)
                            elif p['type'] == 'red_ping':
                                msgs_red_x.append(mx)
                                msgs_red_y.append(my)
                
        scatter_nodes.set_offsets(list(zip(nodes_x, nodes_y)) if nodes_x else np.empty((0, 2)))
        scatter_disabled.set_offsets(list(zip(disabled_x, disabled_y)) if disabled_x else np.empty((0, 2)))
        scatter_masters.set_offsets(list(zip(masters_x, masters_y)) if masters_x else np.empty((0, 2)))
        scatter_blue_pkts.set_offsets(list(zip(msgs_blue_x, msgs_blue_y)) if msgs_blue_x else np.empty((0, 2)))
        scatter_red_pkts.set_offsets(list(zip(msgs_red_x, msgs_red_y)) if msgs_red_x else np.empty((0, 2)))
        
        # Add routing texts for active non-master nodes
        for node in sim.nodes:
            if node.is_disabled or not node.is_active or node.is_master: continue
            info_lines = []
            for mid in ['0', '1']:
                if mid in node.routing_table:
                    rt = node.routing_table[mid]
                    info_lines.append(f"{mid}, {rt['distance']:.1f}, {rt['hops']}")
            
            if info_lines:
                t = ax.text(node.x, node.y - 1.5, "\n".join(info_lines), fontsize=8, ha='center', va='top', color='black', zorder=10)
                routing_texts.append(t)
        
        time_text.set_text(f'Time: {sim.current_time:.1f}s')
        
        return [scatter_nodes, scatter_disabled, scatter_masters, scatter_blue_pkts, scatter_red_pkts, time_text] + lines + ping_circles + routing_texts

    ani = animation.FuncAnimation(fig, update, interval=100, blit=False, cache_frame_data=False)
    plt.show()

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    locations_file = os.path.join(current_dir, "node_locations.txt")
    masters_file = os.path.join(current_dir, "master_locations.txt")
    visualize_network(locations_file, masters_file)
