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
    fig.patch.set_facecolor('white'); ax.set_facecolor('white')
    ax.set_title("Mesh Network Routing Simulation & Jammer Mapping")
    ax.set_xlabel("X"); ax.set_ylabel("Y")
    ax.set_xlim(-5, 35); ax.set_ylim(-5, 35)
    ax.grid(True, linestyle='--', alpha=0.3)
    
    scatter_nodes = ax.scatter([], [], color='blue', marker='o', s=100, zorder=5, label='Nodes')
    scatter_disabled =ax.scatter([], [], color='black', marker='o', s=100, zorder=5, label='Disabled')
    scatter_masters = ax.scatter([], [], color='purple', marker='*', s=300, zorder=6, label='Masters')
    scatter_blue_pkts = ax.scatter([], [], color='blue', marker='o', s=50, edgecolors='white', zorder=7, label='Msg Packets')
    scatter_red_pkts = ax.scatter([], [], color='red', marker='o', s=50, edgecolors='white', zorder=7, label='Ack Packets')
    
    scatter_jammedness = ax.scatter([], [], c=[], cmap='YlOrRd', s=100, alpha=0.6, zorder=3, label='Jammedness Map')
    jammer_marker, = ax.plot([], [], 'rx', markersize=15, markeredgewidth=3, zorder=10, label='Actual Jammer')
    jammer_est_marker, = ax.plot([], [], 'go', markersize=15, fillstyle='none', markeredgewidth=2, zorder=10, label='Est. Jammer')
    
    # Physics-based Jammer Field Visualization (Heatmap)
    grid_res = 100
    gx = np.linspace(-5, 35, grid_res)
    gy = np.linspace(-5, 35, grid_res)
    G_X, G_Y = np.meshgrid(gx, gy)
    # Use a solid vmin/vmax for consistent glow appearance
    jammer_field_img = ax.imshow(np.zeros((grid_res, grid_res)), extent=[-5, 35, -5, 35], 
                                 origin='lower', cmap='Reds', alpha=0.4, zorder=1, 
                                 interpolation='bilinear', vmin=0, vmax=6)
    
    est_beam_lines = [ax.plot([], [], 'g--', alpha=0.5, zorder=2)[0] for _ in range(2)]
    est_beam_center = ax.plot([], [], 'g:', alpha=0.3, zorder=2)[0]

    ax.legend(loc='upper right', fontsize='small')
    plt.subplots_adjust(left=0.25)
    ax_toggles = plt.axes([0.02, 0.4, 0.18, 0.25])
    toggles = CheckButtons(ax_toggles, ('Packets', 'Msg Pings', 'Loc Pings', 'Jammedness', 'Est. Beam'), (True, True, True, True, True))
    visibility = {'Packets': True, 'Msg Pings': True, 'Loc Pings': True, 'Jammedness': True, 'Est. Beam': True}
    def toggle_visibility(label): visibility[label] = not visibility[label]
    toggles.on_clicked(toggle_visibility)
    
    lines, ping_circles, routing_texts = [], [], []
    time_text = ax.text(0.05, 0.95, '', transform=ax.transAxes, fontsize=12, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    jammer_text = ax.text(0.05, 0.85, '', transform=ax.transAxes, fontsize=10, verticalalignment='top', color='red', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    def on_click(event):
        if event.xdata is None or event.ydata is None: return
        closest = None, float('inf')
        for node in sim.nodes:
            if node.is_master: continue
            dist = math.hypot(node.x - event.xdata, node.y - event.ydata)
            if dist < closest[1]: closest = (node, dist)
        if closest[0] and closest[1] < 2.0:
            closest[0].is_disabled = not closest[0].is_disabled
            if closest[0].is_disabled:
                closest[0].is_active = False
                for n in sim.nodes:
                    if closest[0] in n.neighbors: n.neighbors.remove(closest[0])
                closest[0].neighbors = []

    fig.canvas.mpl_connect('button_press_event', on_click)

    def update(frame):
        sim.step(0.1)
        nonlocal lines, ping_circles, routing_texts
        for l in lines + ping_circles + routing_texts: l.remove()
        lines, ping_circles, routing_texts = [], [], []
        
        nodes_x, nodes_y, disabled_x, disabled_y, masters_x, masters_y = [], [], [], [], [], []
        msgs_blue_x, msgs_blue_y, msgs_red_x, msgs_red_y = [], [], [], []
        drawn_edges = set()

        for node in sim.nodes:
            if node.is_disabled:
                disabled_x.append(node.x); disabled_y.append(node.y); continue
            if not node.is_active: continue
            if node.is_master: masters_x.append(node.x); masters_y.append(node.y)
            else: nodes_x.append(node.x); nodes_y.append(node.y)
            for neighbor in node.neighbors:
                edge = frozenset([node.id, neighbor.id])
                if edge not in drawn_edges:
                    drawn_edges.add(edge)
                    jam = sim.edge_jammedness.get(edge, 0.0); norm_jam = min(1.0, jam / 20.0)
                    line, = ax.plot([node.x, neighbor.x], [node.y, neighbor.y], color=plt.get_cmap('YlOrRd')(norm_jam), alpha=0.3 + 0.5 * norm_jam, linewidth=1.0 + norm_jam * 4.0, zorder=1)
                    lines.append(line)
                    
        for p in sim.pings:
            radius = (sim.current_time - p['start_time']) * p['sender'].ping_speed
            if radius <= 0: continue
            is_msg, is_loc = p['type'] in ('blue_ping', 'red_ping'), p['type'] in ('discovery', 'reply')
            if (is_msg and visibility['Msg Pings']) or (is_loc and visibility['Loc Pings']):
                color = {'discovery':'green', 'reply':'orange', 'blue_ping':'blue', 'red_ping':'red'}.get(p['type'], 'gray')
                alpha = min(1.0, max(0, 1 - radius / p['sender'].max_ping_radius) + (0.3 if is_msg else 0))
                circle = plt.Circle((p['sender'].x, p['sender'].y), radius, color=color, fill=False, alpha=alpha, linewidth=2 if is_msg else 1, zorder=2)
                ax.add_patch(circle); ping_circles.append(circle)
            if is_msg and visibility['Packets']:
                for n in p['sender'].neighbors:
                    dist = p['sender'].distance_to(n)
                    if radius <= dist:
                        ratio = radius / dist
                        mx, my = p['sender'].x + ratio * (n.x - p['sender'].x), p['sender'].y + ratio * (n.y - p['sender'].y)
                        if p['type'] == 'blue_ping': msgs_blue_x.append(mx); msgs_blue_y.append(my)
                        else: msgs_red_x.append(mx); msgs_red_y.append(my)
                
        scatter_nodes.set_offsets(list(zip(nodes_x, nodes_y)) if nodes_x else np.empty((0, 2)))
        scatter_disabled.set_offsets(list(zip(disabled_x, disabled_y)) if disabled_x else np.empty((0, 2)))
        scatter_masters.set_offsets(list(zip(masters_x, masters_y)) if masters_x else np.empty((0, 2)))
        scatter_blue_pkts.set_offsets(list(zip(msgs_blue_x, msgs_blue_y)) if msgs_blue_x else np.empty((0, 2)))
        scatter_red_pkts.set_offsets(list(zip(msgs_red_x, msgs_red_y)) if msgs_red_x else np.empty((0, 2)))
        
        # 1. Update Physics-based Jammer Field Glow (Always visible if active)
        jammer_marker.set_data([sim.jammer.x], [sim.jammer.y]); jammer_marker.set_visible(True)
        dist_sq = (G_X - sim.jammer.x)**2 + (G_Y - sim.jammer.y)**2
        dist_sq = np.maximum(dist_sq, 0.5)
        field = sim.jammer.strength / dist_sq
        if sim.jammer.beam_angle is not None:
            angles = np.degrees(np.arctan2(G_Y - sim.jammer.y, G_X - sim.jammer.x))
            diffs = (angles - sim.jammer.beam_angle + 180) % 360 - 180
            falloff = np.exp(-0.5 * (diffs / (sim.jammer.beam_width / 4))**2)
            field = np.where(np.abs(diffs) <= sim.jammer.beam_width / 2, field * falloff, field * 0.05)
        
        jammer_field_img.set_data(np.log1p(field))
        jammer_field_img.set_visible(True)

        # 2. Update Jammedness Map (Drone-collected samples)
        if visibility['Jammedness'] and sim.jammedness_samples:
            sx, sy, sv = zip(*sim.jammedness_samples)
            scatter_jammedness.set_offsets(list(zip(sx, sy))); scatter_jammedness.set_array(np.array(sv))
            max_v = max(sv) if sv else 1.0; scatter_jammedness.set_sizes([40 + 200 * (v / max_v) for v in sv])
            scatter_jammedness.set_visible(True)
            
            jammer_est_marker.set_data([sim.est_jammer_pos[0]], [sim.est_jammer_pos[1]]); jammer_est_marker.set_visible(True)
            dist_err = math.hypot(sim.est_jammer_pos[0] - sim.jammer.x, sim.est_jammer_pos[1] - sim.jammer.y)
            jammer_text.set_text(f"Jammer Est Error: {dist_err:.2f}m\nEst Angle: {sim.est_beam_angle:.1f} deg\nEst Width: {sim.est_beam_width:.1f} deg")

            if visibility['Est. Beam']:
                for i, offset in enumerate([-sim.est_beam_width/2, sim.est_beam_width/2]):
                    angle = math.radians(sim.est_beam_angle + offset)
                    est_beam_lines[i].set_data([sim.est_jammer_pos[0], sim.est_jammer_pos[0] + 50 * math.cos(angle)], [sim.est_jammer_pos[1], sim.est_jammer_pos[1] + 50 * math.sin(angle)])
                    est_beam_lines[i].set_visible(True)
                est_beam_center.set_data([sim.est_jammer_pos[0], sim.est_jammer_pos[0] + 50 * math.cos(math.radians(sim.est_beam_angle))], [sim.est_jammer_pos[1], sim.est_jammer_pos[1] + 50 * math.sin(math.radians(sim.est_beam_angle))])
                est_beam_center.set_visible(True)
            else:
                for l in est_beam_lines: l.set_visible(False)
                est_beam_center.set_visible(False)
        else:
            scatter_jammedness.set_visible(False); jammer_est_marker.set_visible(False)
            for l in est_beam_lines: l.set_visible(False)
            est_beam_center.set_visible(False); jammer_text.set_text("")

        for node in sim.nodes:
            if node.is_disabled or not node.is_active or node.is_master: continue
            info = [f"{mid}, {rt['distance']:.1f}, {rt['hops']}" for mid, rt in node.routing_table.items() if mid in ['0', '1']]
            if info:
                t = ax.text(node.x, node.y - 1.5, "\n".join(info), fontsize=8, ha='center', va='top', color='black', zorder=10)
                routing_texts.append(t)
        time_text.set_text(f'Time: {sim.current_time:.1f}s')
        return [scatter_nodes, scatter_disabled, scatter_masters, scatter_blue_pkts, scatter_red_pkts, time_text, scatter_jammedness, jammer_marker, jammer_est_marker, jammer_text, jammer_field_img] + lines + ping_circles + routing_texts + est_beam_lines + [est_beam_center]

    ani = animation.FuncAnimation(fig, update, interval=100, blit=False, cache_frame_data=False)
    plt.show()

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    visualize_network(os.path.join(current_dir, "node_locations.txt"), os.path.join(current_dir, "master_locations.txt"))
