import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import CheckButtons
import os
import numpy as np
import math
from advanced_sim import AdvancedNetworkSim

def visualize_tactical_hud(locations_file):
    sim = AdvancedNetworkSim(locations_file)
    
    # Dark Theme HUD
    plt.style.use('dark_background')
    
    # Disable default Matplotlib keybinds
    plt.rcParams['keymap.save'] = ''
    plt.rcParams['keymap.fullscreen'] = ''
    plt.rcParams['keymap.home'] = ''
    plt.rcParams['keymap.back'] = ''
    plt.rcParams['keymap.forward'] = ''
    plt.rcParams['keymap.pan'] = ''
    plt.rcParams['keymap.zoom'] = ''
    
    fig, ax = plt.subplots(figsize=(12, 10))
    fig.canvas.manager.set_window_title('Tactical Swarm HUD - Pure Mesh EW Demo')
    
    ax.set_xlim(-5, 35)
    ax.set_ylim(-5, 35)
    ax.set_aspect('equal')
    ax.grid(True, linestyle=':', alpha=0.2, color='cyan')
    
    # Custom HUD Elements
    scatter_nodes = ax.scatter([], [], color='#00f2ff', marker='o', s=120, edgecolors='white', zorder=5, label='Drone Swarm')
    scatter_disabled = ax.scatter([], [], color='#444444', marker='x', s=100, zorder=5, label='Disabled')
    
    # Physics Glow (Heatmap)
    grid_res = 80
    gx = np.linspace(-5, 35, grid_res)
    gy = np.linspace(-5, 35, grid_res)
    G_X, G_Y = np.meshgrid(gx, gy)
    jammer_field_img = ax.imshow(np.zeros((grid_res, grid_res)), extent=[-5, 35, -5, 35], 
                                 origin='lower', cmap='hot', alpha=0.3, zorder=1, 
                                 interpolation='bilinear', vmin=0, vmax=5)
    
    jammer_marker, = ax.plot([], [], 'rx', markersize=20, markeredgewidth=3, zorder=10, label='Target Jammer')
    jammer_est_marker, = ax.plot([], [], 'go', markersize=15, fillstyle='none', markeredgewidth=2, zorder=10, label='Estimated jammer location')

    ax.legend(loc='upper right', fontsize='small', framealpha=0.5)

    # Layer Toggles
    plt.subplots_adjust(left=0.2)
    ax_toggles = plt.axes([0.02, 0.4, 0.15, 0.15])
    toggles = CheckButtons(ax_toggles, 
                           ('Pings', 'Mesh Links', 'Jammer Glow'), 
                           (True, True, True))
    
    visibility = {
        'Pings': True, 'Mesh Links': True, 
        'Jammer Glow': True
    }
    
    def toggle_visibility(label):
        visibility[label] = not visibility[label]
        
    toggles.on_clicked(toggle_visibility)
    
    # HUD Text
    info_text = ax.text(0.02, 0.98, '', transform=ax.transAxes, fontsize=10, 
                        verticalalignment='top', family='monospace', color='#00f2ff',
                        bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.7, edgecolor='#00f2ff'))
    
    controls_help = ax.text(0.02, 0.02, 'WASD: Move Jammer | Q/E: Rotate Beam | DRAG: Move Drones', 
                            transform=ax.transAxes, fontsize=9, color='yellow', alpha=0.8)

    # Interaction State
    drag_node = None
    
    def on_key(event):
        step = 0.5
        if event.key == 'w': sim.jammer.update_params(y=sim.jammer.y + step)
        elif event.key == 's': sim.jammer.update_params(y=sim.jammer.y - step)
        elif event.key == 'a': sim.jammer.update_params(x=sim.jammer.x - step)
        elif event.key == 'd': sim.jammer.update_params(x=sim.jammer.x + step)
        elif event.key == 'q': sim.jammer.update_params(angle=sim.jammer.beam_angle + 5)
        elif event.key == 'e': sim.jammer.update_params(angle=sim.jammer.beam_angle - 5)

    def on_press(event):
        nonlocal drag_node
        if event.xdata is None or event.ydata is None: return
        for node in sim.nodes:
            if math.hypot(node.x - event.xdata, node.y - event.ydata) < 1.5:
                drag_node = node
                break

    def on_release(event):
        nonlocal drag_node
        drag_node = None

    def on_motion(event):
        if drag_node and event.xdata is not None and event.ydata is not None:
            drag_node.update_position(event.xdata, event.ydata)

    fig.canvas.mpl_connect('key_press_event', on_key)
    fig.canvas.mpl_connect('button_press_event', on_press)
    fig.canvas.mpl_connect('button_release_event', on_release)
    fig.canvas.mpl_connect('motion_notify_event', on_motion)

    lines = []
    ping_circles = []

    def update(frame):
        sim.step(0.1)
        nonlocal lines, ping_circles
        for l in lines + ping_circles: l.remove()
        lines, ping_circles = [], []
        
        nodes_x, nodes_y, disabled_x, disabled_y = [], [], [], []
        
        drawn_edges = set()
        
        # Draw Mesh Links
        if visibility['Mesh Links']:
            for node in sim.nodes:
                if node.is_disabled:
                    disabled_x.append(node.x); disabled_y.append(node.y); continue
                if not node.is_active: continue
                nodes_x.append(node.x); nodes_y.append(node.y)
                
                for neighbor in node.neighbors:
                    edge = frozenset([node.id, neighbor.id])
                    if edge not in drawn_edges:
                        drawn_edges.add(edge)
                        jam = sim.edge_jammedness.get(edge, 0.0)
                        norm_jam = min(1.0, jam / 10.0)
                        color = (0.2 + 0.8*norm_jam, 0.8*(1-norm_jam), 0.9*(1-norm_jam))
                        line, = ax.plot([node.x, neighbor.x], [node.y, neighbor.y], 
                                        color=color, alpha=0.4 + 0.4*norm_jam, 
                                        linewidth=1.0 + norm_jam*3, zorder=1)
                        lines.append(line)
        else:
            for node in sim.nodes:
                if node.is_disabled:
                    disabled_x.append(node.x); disabled_y.append(node.y); continue
                if not node.is_active: continue
                nodes_x.append(node.x); nodes_y.append(node.y)
        
        # Update Node Sprites
        scatter_nodes.set_offsets(list(zip(nodes_x, nodes_y)) if nodes_x else np.empty((0, 2)))
        scatter_disabled.set_offsets(list(zip(disabled_x, disabled_y)) if disabled_x else np.empty((0, 2)))
        
        # Update True Jammer Glow
        dist_sq = (G_X - sim.jammer.x)**2 + (G_Y - sim.jammer.y)**2
        dist_sq = np.maximum(dist_sq, 0.5)
        field = sim.jammer.strength / dist_sq
        if sim.jammer.beam_angle is not None:
            angles = np.degrees(np.arctan2(G_Y - sim.jammer.y, G_X - sim.jammer.x))
            diffs = (angles - sim.jammer.beam_angle + 180) % 360 - 180
            falloff = np.exp(-0.5 * (diffs / (sim.jammer.beam_width / 4))**2)
            field = np.where(np.abs(diffs) <= sim.jammer.beam_width / 2, field * falloff, field * 0.05)
        
        if visibility['Jammer Glow']:
            jammer_field_img.set_data(np.log1p(field))
            jammer_field_img.set_visible(True)
        else:
            jammer_field_img.set_visible(False)
            
        jammer_marker.set_data([sim.jammer.x], [sim.jammer.y])
        
        jammer_est_marker.set_data([sim.est_jammer_pos[0]], [sim.est_jammer_pos[1]])
        
        # Stats Update
        err = math.hypot(sim.est_jammer_pos[0] - sim.jammer.x, sim.est_jammer_pos[1] - sim.jammer.y)
        info_text.set_text(f"--- TACTICAL SWARM DATA ---\n"
                           f"TIME: {sim.current_time:.1f}s\n"
                           f"JAMMER LOCATION ERROR: {err:.2f}m\n"
                           f"EST BEAM: {sim.est_beam_angle:.1f}°\n"
                           f"EST WIDTH: {sim.est_beam_width:.1f}°\n"
                           f"SWARM SIZE: {len(nodes_x)}")
        
        # Pings
        for p in sim.pings:
            radius = (sim.current_time - p['start_time']) * p['sender'].ping_speed
            if radius <= 0: continue
            
            if visibility['Pings']:
                color = {'discovery':'#00ff9d', 'reply':'#ffaa00'}.get(p['type'], 'gray')
                circle = plt.Circle((p['sender'].x, p['sender'].y), radius, color=color, fill=False, 
                                    alpha=max(0, 1 - radius / p['sender'].max_ping_radius), 
                                    linewidth=1, zorder=2)
                ax.add_patch(circle)
                ping_circles.append(circle)

        return [scatter_nodes, scatter_disabled, jammer_field_img, jammer_marker, jammer_est_marker, info_text] + lines + ping_circles

    ani = animation.FuncAnimation(fig, update, interval=50, blit=False, cache_frame_data=False)
    plt.show()

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    visualize_tactical_hud(os.path.join(current_dir, "node_locations_20.txt"))
