import matplotlib.pyplot as plt
import matplotlib.animation as animation
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
    scatter_messages = ax.scatter([], [], color='yellow', marker='o', s=50, edgecolors='black', zorder=7, label='Messages')
    
    ax.legend(loc='upper left')
    
    lines = []
    ping_circles = []

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
        
        nonlocal lines, ping_circles
        for line in lines: line.remove()
        for circle in ping_circles: circle.remove()
        lines = []
        ping_circles = []
        
        nodes_x, nodes_y = [], []
        disabled_x, disabled_y = [], []
        masters_x, masters_y = [], []
        msgs_x, msgs_y = [], []
        
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
                color = 'green' if p['type'] == 'discovery' else 'orange'
                alpha_val = max(0, 1 - radius / p['sender'].max_ping_radius)
                circle = plt.Circle((p['sender'].x, p['sender'].y), radius, color=color, fill=False, alpha=alpha_val, zorder=2)
                ax.add_patch(circle)
                ping_circles.append(circle)
                
        for msg in sim.messages:
            if msg.edge_length > 0:
                ratio = min(1.0, msg.progress / msg.edge_length)
                mx = msg.current_node.x + ratio * (msg.next_node.x - msg.current_node.x)
                my = msg.current_node.y + ratio * (msg.next_node.y - msg.current_node.y)
                msgs_x.append(mx)
                msgs_y.append(my)
                
        scatter_nodes.set_offsets(list(zip(nodes_x, nodes_y)) if nodes_x else np.empty((0, 2)))
        scatter_disabled.set_offsets(list(zip(disabled_x, disabled_y)) if disabled_x else np.empty((0, 2)))
        scatter_masters.set_offsets(list(zip(masters_x, masters_y)) if masters_x else np.empty((0, 2)))
        scatter_messages.set_offsets(list(zip(msgs_x, msgs_y)) if msgs_x else np.empty((0, 2)))
        
        time_text.set_text(f'Time: {sim.current_time:.1f}s')
        
        return [scatter_nodes, scatter_disabled, scatter_masters, scatter_messages, time_text] + lines + ping_circles

    ani = animation.FuncAnimation(fig, update, interval=100, blit=False, cache_frame_data=False)
    plt.show()

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    locations_file = os.path.join(current_dir, "node_locations.txt")
    masters_file = os.path.join(current_dir, "master_locations.txt")
    visualize_network(locations_file, masters_file)
