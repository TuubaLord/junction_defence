# ESP32 Mesh Network & Tactical Visualizer

A robust, spatially-aware mesh network implementation for ESP32 nodes using the ESP-NOW protocol, featuring real-time topology visualization and a logic-driven digital twin simulation.

## 🏗️ Project Architecture

### 1. Real-World Deployment (`esp_network/`)
*   **`src/main.cpp`**: Core C++ firmware. Implements a custom **Path-Vector Routing Protocol** on top of ESP-NOW. It handles discovery, multi-hop routing, and serial telemetry.
*   **`chat_client.py`**: A terminal-based interface connecting to the Master node via Serial. It manages network state, handles chat commands, and performs reliable file transfers.
*   **`visualizer.py`**: A Matplotlib-based real-time engine that renders the live mesh topology, using **NetworkX** for graph layout and animations.

### 2. Logic Simulation (`mesh_network/`)
*   **`network_sim.py`**: A pure-Python discrete-event simulation. It emulates radio signal propagation, node discovery, and distance-vector routing logic using 2D coordinate math.
*   **`network_visualization.py`**: A Matplotlib-driven visual interface for the simulation. It allows for interactive node disabling/enabling and visualizes routing pings and packet flow.

---

## 🚀 How It Works

### Custom Mesh Protocol
The system uses a decentralized routing protocol optimized for ESP-NOW's 250-byte packet limit.
1.  **Discovery & Handshaking**: Nodes broadcast their presence and routing tables every 2 seconds.
2.  **Shortest Path Selection**: The protocol identifies the path with the **least number of hops** to a destination.
3.  **Serial Telemetry**: The Master node outputs `[GRAPH]` serial strings that provide a complete "snapshot" of the mesh topology to the connected computer.

### Real-Time Visualization (`visualizer.py`)
The live visualizer processes the Master node's telemetry to create a tactical map:
*   **Graph Layout**: Uses the **Fruchterman-Reingold (Spring-Mass)** algorithm to arrange nodes.
*   **Coordinate Constraints**: Automatically shifts the view so the Master node acts as the origin `(0,0)`, with other nodes clustered logically around it.
*   **Packet Animation**: Intercepts `[SEND]` and `[RCV]` events to animate discrete "packets" traveling along the mesh edges.
*   **Targeting**: Highlights target nodes in **Red** and the local Master in **Green**.

### Simulation Logic (`network_sim.py`)
The simulation provides a sandbox for testing protocol changes:
*   **Signal Radius**: Models radio range as an expanding circle. Nodes only receive data if they are within the `max_ping_radius`.
*   **Interactive Faults**: In the visualization, you can click on any blue node to disable it, forcing the mesh to recalculate routes in real-time.

---

## 🛠️ Setup & Usage

### Running the Real Mesh
1.  **Flash Hardware**: Upload `src/main.cpp` to your ESP32 boards using PlatformIO.
2.  **Launch Chat Client**:
    ```bash
    pipenv run python esp_network/chat_client.py
    ```
3.  **Launch Live Visualizer**:
    ```bash
    pipenv run python esp_network/visualizer.py
    ```

### Running the Simulation
To test mesh logic without hardware:
```bash
pipenv run python mesh_network/network_visualization.py
```

---

## 📈 Technical Specs
*   **Layer 2**: ESP-NOW (Unicast for data, Broadcast for routing)
*   **Layout**: NetworkX Spring Layout
*   **Visuals**: Matplotlib Animation API
*   **Packet Header**: Custom 13-byte `RouteEntry` (6 Target, 6 Next-Hop, 1 Hops)
