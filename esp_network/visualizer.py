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

def update(frame):
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
        if now - last_seen > 2.0:
            node_colors.append("#333333") # Ghost node (Black/Dark Gray)
        else:
            node_colors.append("#00aaff") # Active node (Blue)
            
    if len(nodes) > 0:
        pos = nx.spring_layout(G, seed=42)
        nx.draw(G, pos, ax=ax, with_labels=True, 
                node_color=node_colors, 
                node_size=3000, 
                font_size=8, 
                font_weight="bold",
                font_color="white",
                edge_color="#555555",
                width=2,
                arrowsize=20)

ani = animation.FuncAnimation(fig, update, interval=500, cache_frame_data=False)
plt.show()
