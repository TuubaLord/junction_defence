import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import json
import time
import os

state_file = "graph_state.json"

fig, ax = plt.subplots(figsize=(10, 8))
fig.patch.set_facecolor('#1e1e1e')
ax.set_facecolor('#1e1e1e')

global_pos = {}

def update(frame):
    global global_pos
    ax.clear()
    ax.set_title("Live ESP32 Mesh Topology", color='white', pad=20, fontsize=14)
    ax.set_facecolor('#1e1e1e')
    
    if not os.path.exists(state_file):
        ax.text(0.5, 0.5, "Waiting for ESP32 Routing Broadcasts...", 
                color='gray', ha='center', va='center', transform=ax.transAxes)
        return
        
    try:
        with open(state_file, "r") as f:
            data = json.load(f)
    except Exception:
        return
        
    G = nx.DiGraph()
    now = time.time()
    
    for edge in data.get("edges", []):
        G.add_edge(edge[0], edge[1])
        
    nodes = list(G.nodes())
    node_colors = []
    
    for n in nodes:
        last_seen = data.get("last_seen", {}).get(n, 0)
        if now - last_seen > 5.0:
            node_colors.append("#333333") # Ghost node (Black/Dark Gray)
        else:
            node_colors.append("#00aaff") # Active node (Blue)
            
    if len(nodes) > 0:
        new_pos = nx.spring_layout(G, seed=42)
        
        # Smooth organic interpolation
        for n in G.nodes():
            if n not in global_pos:
                global_pos[n] = new_pos[n]
            else:
                global_pos[n] = [
                    global_pos[n][0] * 0.8 + new_pos[n][0] * 0.2,
                    global_pos[n][1] * 0.8 + new_pos[n][1] * 0.2
                ]
                
        # Clean up removed nodes from global pos
        global_pos = {n: p for n, p in global_pos.items() if n in G.nodes()}
        
        nx.draw(G, global_pos, ax=ax, with_labels=True, 
                node_color=node_colors, 
                node_size=3000, 
                font_size=8, 
                font_weight="bold",
                font_color="white",
                edge_color="#555555",
                width=2,
                arrowsize=20)
                
        # --- ANIMATE PACKETS ---
        packet_speed = 1.5 # nodes per second
        for pkt in data.get("packets", []):
            path = pkt.get("path", [])
            total_edges = len(path) - 1
            if total_edges < 1: continue
            
            elapsed = now - pkt.get("start_time", 0)
            current_progress = elapsed * packet_speed
            
            if current_progress < total_edges:
                edge_idx = int(current_progress)
                edge_progress = current_progress - edge_idx
                
                node_a = path[edge_idx]
                node_b = path[edge_idx + 1]
                
                if node_a in global_pos and node_b in global_pos:
                    pos_a = global_pos[node_a]
                    pos_b = global_pos[node_b]
                    x = pos_a[0] + (pos_b[0] - pos_a[0]) * edge_progress
                    y = pos_a[1] + (pos_b[1] - pos_a[1]) * edge_progress
                    
                    ax.plot(x, y, marker='o', markersize=15, color=pkt.get("color", "white"), zorder=5, 
                            markeredgecolor='white', markeredgewidth=2)

ani = animation.FuncAnimation(fig, update, interval=100, cache_frame_data=False)
plt.show()
