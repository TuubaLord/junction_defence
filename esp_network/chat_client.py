import serial
import serial.tools.list_ports
import threading
import sys
import time

def print_help():
    print("\n--- Mesh Chat Commands ---")
    print("  /routes         - View current network topology")
    print("  /target <MAC>   - Set the destination MAC address")
    print("  /quit           - Exit the chat client")
    print("  <any text>      - Send text to the current target MAC")
    print("--------------------------\n")

last_routes_str = ""
current_routes = []

def read_from_port(ser):
    global last_routes_str, current_routes
    in_route_block = False
    
    while True:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line:
                    continue
                    
                # Handle routing table sync block
                if line == "[ROUTE_START]":
                    in_route_block = True
                    current_routes = []
                    continue
                elif line == "[ROUTE_END]":
                    in_route_block = False
                    # Format route summary
                    if current_routes:
                        r_str = ", ".join([f"{mac} ({hops} hops)" for mac, hops in current_routes])
                    else:
                        r_str = "No active nodes found."
                        
                    # Only alert if topology changed
                    if r_str != last_routes_str:
                        last_routes_str = r_str
                        sys.stdout.write("\r\033[K")
                        print(f"\033[95m[NET] Topology Change! Active Nodes: {r_str}\033[0m")
                        sys.stdout.write("\033[96m> \033[0m")
                        sys.stdout.flush()
                    continue
                elif line.startswith("[ROUTE] "):
                    parts = line.split()
                    if len(parts) == 3:
                        current_routes.append((parts[1], parts[2]))
                    continue
                    
                # Filter out raw routing noise, only show chat relevant info
                if (line.startswith("[RCV]") or 
                    line.startswith("[ACK]") or 
                    line.startswith("[ERR]") or 
                    line.startswith("ESP32 MESH") or 
                    "Node MAC:" in line):
                    
                    # Clear current line to prevent input overwrite artifacts
                    sys.stdout.write("\r\033[K")
                    
                    # Add color to incoming messages for better UX
                    if line.startswith("[RCV]"):
                        print(f"\033[92m{line}\033[0m") # Green
                    elif line.startswith("[ACK]"):
                        print(f"\033[94m{line}\033[0m") # Blue
                    elif line.startswith("[ERR]"):
                        print(f"\033[91m{line}\033[0m") # Red
                    else:
                        print(f"\033[93m{line}\033[0m") # Yellow for system
                        
                    # Reprint prompt
                    sys.stdout.write("\033[96m> \033[0m")
                    sys.stdout.flush()
        except Exception as e:
            print(f"\nSerial read error: {e}")
            break

def main():
    print("\n=== ESP32 Tactical Mesh Chat Client ===")
    ports = serial.tools.list_ports.comports()
    
    if not ports:
        print("No serial ports found! Is your ESP32 plugged in?")
        return

    print("Available ports:")
    for i, port in enumerate(ports):
        print(f"[{i}] {port.device} - {port.description}")
        
    try:
        idx = int(input("\nSelect port index: "))
        selected_port = ports[idx].device
    except (ValueError, IndexError):
        print("Invalid selection.")
        return
        
    baud_rate = 115200
    try:
        ser = serial.Serial(selected_port, baud_rate, timeout=1)
        print(f"\nConnected to {selected_port} at {baud_rate} baud.")
    except Exception as e:
        print(f"Failed to connect to {selected_port}: {e}")
        return
        
    # Start read thread
    thread = threading.Thread(target=read_from_port, args=(ser,), daemon=True)
    thread.start()
    
    target_mac = None
    print_help()
    
    try:
        while True:
            # We want a nice prompt
            sys.stdout.write("\033[96m> \033[0m")
            sys.stdout.flush()
            user_input = input().strip()
            
            if not user_input:
                continue
                
            if user_input.startswith("/quit"):
                break
            elif user_input.startswith("/routes"):
                if current_routes:
                    print("\n\033[95m--- Current Routing Table ---\033[0m")
                    for mac, hops in current_routes:
                        print(f"\033[95mNode {mac}  ->  Distance: {hops} hops\033[0m")
                    print("\033[95m-----------------------------\033[0m\n")
                else:
                    print("\033[95mCurrent Topology: No active nodes found.\033[0m")
            elif user_input.startswith("/target"):
                parts = user_input.split(" ", 1)
                if len(parts) > 1:
                    target_mac = parts[1].strip().upper()
                    print(f"Target MAC locked to: \033[93m{target_mac}\033[0m")
                else:
                    print("Usage: /target AA:BB:CC:DD:EE:FF")
            else:
                if target_mac is None:
                    print("\033[91mError: Target MAC not set. Use /target <MAC>\033[0m")
                else:
                    # Format as the ESP32 expects
                    command = f"SEND {target_mac} {user_input}\n"
                    ser.write(command.encode('utf-8'))
                    
                    # Print local echo
                    sys.stdout.write("\r\033[K")
                    print(f"\033[90m[YOU -> {target_mac}] {user_input}\033[0m")
                    
    except KeyboardInterrupt:
        pass
    finally:
        print("\nClosing connection...")
        ser.close()

if __name__ == "__main__":
    main()
