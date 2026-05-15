import serial
import serial.tools.list_ports
import threading
import sys
import time
import os
import base64

def print_help():
    print("\n--- Mesh Chat Commands ---")
    print("  /routes         - View current network topology")
    print("  /target <MAC>   - Set the destination MAC address")
    print("  /file <path>    - Send a file to the target MAC")
    print("  /quit           - Exit the chat client")
    print("  <any text>      - Send text to the current target MAC")
    print("--------------------------\n")

last_routes_str = ""
current_routes = []
incoming_files = {}
ack_received = threading.Event()
is_sending_file = False

def read_from_port(ser):
    global last_routes_str, current_routes, incoming_files, is_sending_file
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
                    
                    if line.startswith("[ACK]"):
                        ack_received.set()
                        if is_sending_file:
                            continue # Hide spammy ACKs during file upload
                    
                    # Intercept File Transfer Packets
                    if line.startswith("[RCV]"):
                        parts = line.split(" says: ", 1)
                        if len(parts) == 2:
                            sender_mac = parts[0].replace("[RCV] ", "").strip()
                            payload = parts[1].strip()
                            
                            if payload.startswith("[F_START]"):
                                f_parts = payload.split(" ", 2)
                                if len(f_parts) == 3:
                                    filename = f_parts[1]
                                    total_chunks = int(f_parts[2])
                                    incoming_files[sender_mac] = {'filename': filename, 'chunks': total_chunks, 'data': {}}
                                    sys.stdout.write("\r\033[K")
                                    print(f"\033[96m[FILE] Incoming file '{filename}' ({total_chunks} chunks) from {sender_mac}...\033[0m")
                                    sys.stdout.write("\033[96m> \033[0m")
                                    sys.stdout.flush()
                                continue
                                
                            elif payload.startswith("[F_DATA]"):
                                if sender_mac in incoming_files:
                                    f_parts = payload.split(" ", 2)
                                    if len(f_parts) == 3:
                                        c_idx = int(f_parts[1])
                                        c_data = f_parts[2]
                                        incoming_files[sender_mac]['data'][c_idx] = c_data
                                        
                                        pct = int((len(incoming_files[sender_mac]['data']) / incoming_files[sender_mac]['chunks']) * 100)
                                        sys.stdout.write("\r\033[K")
                                        sys.stdout.write(f"\033[96m[FILE] Receiving '{incoming_files[sender_mac]['filename']}'... {pct}%\033[0m")
                                        sys.stdout.flush()
                                continue
                                
                            elif payload.startswith("[F_END]"):
                                if sender_mac in incoming_files:
                                    finfo = incoming_files[sender_mac]
                                    full_b64 = ""
                                    for i in range(finfo['chunks']):
                                        full_b64 += finfo['data'].get(i, "")
                                    
                                    sys.stdout.write("\r\033[K")
                                    try:
                                        file_bytes = base64.b64decode(full_b64)
                                        with open("recv_" + finfo['filename'], "wb") as f:
                                            f.write(file_bytes)
                                        print(f"\n\033[92m[FILE] Successfully saved 'recv_{finfo['filename']}'!\033[0m")
                                    except Exception as e:
                                        print(f"\n\033[91m[FILE] Error decoding file: {e}\033[0m")
                                    
                                    del incoming_files[sender_mac]
                                    sys.stdout.write("\033[96m> \033[0m")
                                    sys.stdout.flush()
                                continue
                    
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
            elif user_input.startswith("/file"):
                global is_sending_file
                if target_mac is None:
                    print("\033[91mError: Target MAC not set. Use /target <MAC>\033[0m")
                    continue
                    
                parts = user_input.split(" ", 1)
                if len(parts) < 2:
                    print("Usage: /file <filename>")
                    continue
                    
                filename = parts[1].strip()
                if not os.path.exists(filename):
                    print(f"\033[91mFile not found: {filename}\033[0m")
                    continue
                
                is_sending_file = True
                try:
                    with open(filename, "rb") as f:
                        file_data = f.read()
                    
                    b64_data = base64.b64encode(file_data).decode('utf-8')
                    chunk_size = 110 # Max payload is 127, [F_DATA] NNN takes ~15
                    chunks = [b64_data[i:i+chunk_size] for i in range(0, len(b64_data), chunk_size)]
                    total_chunks = len(chunks)
                    
                    print(f"\033[96m[FILE] Sending '{filename}' in {total_chunks} chunks...\033[0m")
                    
                    def send_reliable(payload_str):
                        retries = 3
                        while retries > 0:
                            ack_received.clear()
                            ser.write(f"SEND {target_mac} {payload_str}\n".encode('utf-8'))
                            if ack_received.wait(3.0): # Wait 3 seconds for physical RTT ACK
                                return True
                            retries -= 1
                            sys.stdout.write(f"\r\033[K\033[93m[FILE] Chunk timeout. Retrying...\033[0m\n")
                            sys.stdout.write("\033[96m> \033[0m")
                            sys.stdout.flush()
                        return False
                    
                    # 1. Send start
                    if not send_reliable(f"[F_START] {os.path.basename(filename)} {total_chunks}"):
                        print("\033[91m[FILE] Failed to initiate transfer.\033[0m")
                    else:
                        # 2. Send chunks
                        success = True
                        for i, chunk in enumerate(chunks):
                            if not send_reliable(f"[F_DATA] {i} {chunk}"):
                                print(f"\n\033[91m[FILE] Transfer failed at chunk {i}.\033[0m")
                                success = False
                                break
                            
                            pct = int(((i+1)/total_chunks)*100)
                            sys.stdout.write(f"\r\033[K\033[96m[FILE] Uploading... {pct}%\033[0m")
                            sys.stdout.flush()
                            
                        # 3. Send end
                        if success:
                            print()
                            send_reliable("[F_END]")
                            print("\033[92m[FILE] Transfer complete!\033[0m")
                            
                except Exception as e:
                    print(f"\033[91mError reading file: {e}\033[0m")
                is_sending_file = False
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
