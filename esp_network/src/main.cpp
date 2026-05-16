#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <map>

// --- Configuration ---
const unsigned long ROUTING_BCAST_INTERVAL = 2000; // ms

// --- Types & Structs ---
enum MsgType : uint8_t { DISCOVERY=0, ROUTING=1, BLUE_PING=2, RED_PING=3 };

#pragma pack(push, 1)

struct BaseMsg {
    MsgType type;
};

// Routing Table Entry advertised to neighbors
struct RouteEntry {
    uint8_t target[6];
    uint8_t next_hop[6]; // Added for Path-Vector full-graph visualization
    uint8_t hops;
};

// Periodic Routing Update Broadcast
struct RoutingMsg {
    MsgType type; // ROUTING
    uint8_t num_entries;
    RouteEntry entries[15]; // Max 15 entries to fit in 250 byte ESP-NOW limit
};

// Message passing (Blue and Red Pings)
struct DataMsg {
    MsgType type; // BLUE_PING or RED_PING
    uint32_t msg_id;
    uint8_t target[6];
    uint8_t next_hop[6]; // Designated relay node
    uint8_t visited_count;
    uint8_t visited[10][6]; // Prevent loops, track path (max 10 hops)
    char payload[128]; // Text message
};

#pragma pack(pop)

// --- Thread-Safe Queue for Relaying ---
#define MSG_QUEUE_SIZE 10
DataMsg relay_queue[MSG_QUEUE_SIZE];
volatile int queue_head = 0;
volatile int queue_tail = 0;
portMUX_TYPE queueMutex = portMUX_INITIALIZER_UNLOCKED;

void enqueueMsg(const DataMsg& m) {
    portENTER_CRITICAL(&queueMutex);
    int next = (queue_head + 1) % MSG_QUEUE_SIZE;
    if (next != queue_tail) { // If not full
        memcpy(&relay_queue[queue_head], &m, sizeof(DataMsg));
        queue_head = next;
    }
    portEXIT_CRITICAL(&queueMutex);
}

bool dequeueMsg(DataMsg& m) {
    bool has_msg = false;
    portENTER_CRITICAL(&queueMutex);
    if (queue_head != queue_tail) {
        memcpy(&m, &relay_queue[queue_tail], sizeof(DataMsg));
        queue_tail = (queue_tail + 1) % MSG_QUEUE_SIZE;
        has_msg = true;
    }
    portEXIT_CRITICAL(&queueMutex);
    return has_msg;
}

// --- Global State ---
struct RouteInfo {
    uint8_t hops;
    uint8_t next_hop[6];
    unsigned long last_updated;
};

std::map<uint64_t, RouteInfo> routing_table;
uint8_t broadcastAddress[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
uint8_t myMac[6];
esp_now_peer_info_t peerInfo;
unsigned long last_routing_bcast = 0;

// --- Helpers ---
uint64_t macToU64(const uint8_t* mac) {
    uint64_t val = 0;
    for(int i=0; i<6; i++) val = (val << 8) | mac[i];
    return val;
}

void u64ToMac(uint64_t val, uint8_t* mac) {
    for(int i=5; i>=0; i--) {
        mac[i] = val & 0xFF;
        val >>= 8;
    }
}

void printMac(const uint8_t* mac) {
    Serial.printf("%02X:%02X:%02X:%02X:%02X:%02X", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

// --- Logic ---
void broadcastRoutingTable() {
    RoutingMsg msg;
    msg.type = ROUTING;
    msg.num_entries = 0;
    
    // Clean up stale routes and register 1-hop neighbors as Unicast peers!
    unsigned long now = millis();
    for (auto it = routing_table.begin(); it != routing_table.end();) {
        if (it->second.hops > 0 && (now - it->second.last_updated > 10000)) { // 10s timeout
            it = routing_table.erase(it);
        } else {
        } else {
            // --- DYNAMICALLY ADD UNICAST PEERS ---
            if (it->second.hops == 1) {
                uint8_t m[6];
                u64ToMac(it->first, m);
                if (!esp_now_is_peer_exist(m)) {
                    esp_now_peer_info_t peer = {};
                    memcpy(peer.peer_addr, m, 6);
                    peer.channel = 0;
                    peer.encrypt = false;
                    esp_now_add_peer(&peer);
                }
            }
            if (msg.num_entries < 15) {
                u64ToMac(it->first, msg.entries[msg.num_entries].target);
                memcpy(msg.entries[msg.num_entries].next_hop, it->second.next_hop, 6);
                msg.entries[msg.num_entries].hops = it->second.hops;
                msg.num_entries++;
            }
            ++it;
        }
    }
    
    // Print our own edges so Python visualizer knows our local Master MAC!
    for (int i = 0; i < msg.num_entries; i++) {
        Serial.printf("[GRAPH] %02X:%02X:%02X:%02X:%02X:%02X -> %02X:%02X:%02X:%02X:%02X:%02X VIA %02X:%02X:%02X:%02X:%02X:%02X\n",
            myMac[0], myMac[1], myMac[2], myMac[3], myMac[4], myMac[5], // Sender (Us)
            msg.entries[i].target[0], msg.entries[i].target[1], msg.entries[i].target[2], 
            msg.entries[i].target[3], msg.entries[i].target[4], msg.entries[i].target[5], // Target
            msg.entries[i].next_hop[0], msg.entries[i].next_hop[1], msg.entries[i].next_hop[2],
            msg.entries[i].next_hop[3], msg.entries[i].next_hop[4], msg.entries[i].next_hop[5]); // Next Hop
    }
    
    if (msg.num_entries > 0) {
        esp_now_send(broadcastAddress, (uint8_t*)&msg, sizeof(BaseMsg) + 1 + (msg.num_entries * sizeof(RouteEntry)));
    }
}

void OnDataRecv(const uint8_t * mac, const uint8_t *incomingData, int len) {
    if (len < sizeof(BaseMsg)) return;
    BaseMsg* base = (BaseMsg*)incomingData;
    
    if (base->type == ROUTING) {
        RoutingMsg* msg = (RoutingMsg*)incomingData;
        uint64_t senderU64 = macToU64(mac);

        // Print raw routing data for Python full-graph visualization!
        for (int i = 0; i < msg->num_entries; i++) {
            Serial.printf("[GRAPH] %02X:%02X:%02X:%02X:%02X:%02X -> %02X:%02X:%02X:%02X:%02X:%02X VIA %02X:%02X:%02X:%02X:%02X:%02X\n",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], // Sender
                msg->entries[i].target[0], msg->entries[i].target[1], msg->entries[i].target[2], 
                msg->entries[i].target[3], msg->entries[i].target[4], msg->entries[i].target[5], // Target
                msg->entries[i].next_hop[0], msg->entries[i].next_hop[1], msg->entries[i].next_hop[2],
                msg->entries[i].next_hop[3], msg->entries[i].next_hop[4], msg->entries[i].next_hop[5]); // Next Hop
        }
        
        // Sender is distance 1 from us
        if (routing_table.find(senderU64) == routing_table.end() || routing_table[senderU64].hops > 1) {
            RouteInfo ri;
            ri.hops = 1;
            memcpy(ri.next_hop, mac, 6);
            ri.last_updated = millis();
            routing_table[senderU64] = ri;
        } else {
            routing_table[senderU64].last_updated = millis();
        }
        
        for (int i=0; i<msg->num_entries; i++) {
            uint64_t targetU64 = macToU64(msg->entries[i].target);
            if (targetU64 == macToU64(myMac)) continue; // ignore paths back to ourselves
            
            uint8_t proposedHops = msg->entries[i].hops + 1;
            
            if (routing_table.find(targetU64) == routing_table.end()) {
                RouteInfo ri;
                ri.hops = proposedHops;
                memcpy(ri.next_hop, mac, 6);
                ri.last_updated = millis();
                routing_table[targetU64] = ri;
            } else {
                RouteInfo& current = routing_table[targetU64];
                if (proposedHops < current.hops) {
                    current.hops = proposedHops;
                    memcpy(current.next_hop, mac, 6);
                    current.last_updated = millis();
                } else if (memcmp(current.next_hop, mac, 6) == 0) {
                    // Update hops if our current path changed length
                    current.hops = proposedHops;
                    current.last_updated = millis();
                }
            }
        }
    } else if (base->type == BLUE_PING || base->type == RED_PING) {
        DataMsg msg;
        memcpy(&msg, incomingData, sizeof(DataMsg)); // MUST copy out of const driver buffer!
        
        // 1. Check if we are designated next hop
        if (memcmp(msg.next_hop, myMac, 6) != 0) return; // Discard!
        
        // 2. Check visited to prevent loops
        for(int i=0; i<msg.visited_count; i++) {
            if (memcmp(msg.visited[i], myMac, 6) == 0) return;
        }
        
        // Add ourselves to visited
        if (msg.visited_count < 10) {
            memcpy(msg.visited[msg.visited_count], myMac, 6);
            msg.visited_count++;
        }
        
        uint64_t targetU64 = macToU64(msg.target);
        
        if (targetU64 == macToU64(myMac)) {
            // Reached destination!
            if (msg.type == BLUE_PING) {
                Serial.printf("\n[RCV] ");
                printMac(msg.visited[0]);
                Serial.printf(" says: %s\n", msg.payload);
                
                // Send RED_PING ack back to originator
                if (msg.visited_count > 0) {
                    DataMsg ack;
                    memset(&ack, 0, sizeof(DataMsg)); // Fully initialize to prevent garbage memory bugs
                    ack.type = RED_PING;
                    ack.msg_id = msg.msg_id;
                    memcpy(ack.target, msg.visited[0], 6); // originator
                    uint64_t origU64 = macToU64(ack.target);
                    if (routing_table.find(origU64) != routing_table.end()) {
                        memcpy(ack.next_hop, routing_table[origU64].next_hop, 6);
                        ack.visited_count = 1;
                        memcpy(ack.visited[0], myMac, 6);
                        enqueueMsg(ack);
                    }
                }
            } else {
                Serial.printf("\n[ACK] Message %u successfully delivered!\n", msg.msg_id);
            }
        } else {
            // Relay!
            if (routing_table.find(targetU64) != routing_table.end()) {
                memcpy(msg.next_hop, routing_table[targetU64].next_hop, 6);
                enqueueMsg(msg);
                Serial.printf("\n[RELAY] Queued msg %u for next hop.\n", msg.msg_id);
            } else {
                Serial.printf("\n[DROP] Dead end reached for msg %u.\n", msg.msg_id);
            }
        }
    }
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  
  // --- TX POWER CONFIGURATION ---
  // Lower the power to artificially shrink the range so you can test mesh routing on a single desk!
  // Max power: WIFI_POWER_19_5dBm (default, ~100+ meters)
  // Min power: WIFI_POWER_MINUS_1dBm (very weak, ~1-2 meters)
  WiFi.setTxPower(WIFI_POWER_MINUS_1dBm);
  // ------------------------------
  
  esp_read_mac(myMac, ESP_MAC_WIFI_STA);
  
  if (esp_now_init() != ESP_OK) {
    Serial.println("Error initializing ESP-NOW");
    return;
  }
  
  // Register broadcast peer
  memcpy(peerInfo.peer_addr, broadcastAddress, 6);
  peerInfo.channel = 0;  
  peerInfo.encrypt = false;
  esp_now_add_peer(&peerInfo);
  
  esp_now_register_recv_cb(OnDataRecv);
  
  // Add self to routing table
  RouteInfo selfRoute = {0, {0,0,0,0,0,0}, millis()};
  memcpy(selfRoute.next_hop, myMac, 6);
  routing_table[macToU64(myMac)] = selfRoute;
  
  Serial.println("\n-----------------------------------------");
  Serial.print("ESP32 MESH NODE BOOTED. MAC: ");
  printMac(myMac);
  Serial.println("\nType 'SEND <MAC> <Message>' to transmit.");
  Serial.println("-----------------------------------------");
}

void loop() {
  // 1. Periodic routing broadcasts
  if (millis() - last_routing_bcast > ROUTING_BCAST_INTERVAL) {
      last_routing_bcast = millis();
      broadcastRoutingTable();
      
      Serial.println("[ROUTE_START]");
      for (auto it = routing_table.begin(); it != routing_table.end(); ++it) {
          if (it->second.hops > 0) {
              uint8_t m[6];
              u64ToMac(it->first, m);
              Serial.printf("[ROUTE] %02X:%02X:%02X:%02X:%02X:%02X %d\n", m[0], m[1], m[2], m[3], m[4], m[5], it->second.hops);
          }
      }
      Serial.println("[ROUTE_END]");
  }
  
  // 2. Handle Serial Input
  if (Serial.available()) {
      String input = Serial.readStringUntil('\n');
      input.trim();
      if (input.startsWith("SEND ")) {
          unsigned int t[6];
          int parsed = sscanf(input.c_str(), "SEND %x:%x:%x:%x:%x:%x", 
                &t[0], &t[1], &t[2], &t[3], &t[4], &t[5]);
                
          if (parsed == 6) {
              uint8_t tgt[6] = {(uint8_t)t[0], (uint8_t)t[1], (uint8_t)t[2], (uint8_t)t[3], (uint8_t)t[4], (uint8_t)t[5]};
              int txtIdx = input.indexOf(' ', 6); // Find space after MAC
              if (txtIdx > 0) {
                  String text = input.substring(txtIdx + 1);
                  uint64_t tgtU64 = macToU64(tgt);
                  
                  if (routing_table.find(tgtU64) != routing_table.end()) {
                      DataMsg dmsg;
                      dmsg.type = BLUE_PING;
                      dmsg.msg_id = millis();
                      memcpy(dmsg.target, tgt, 6);
                      memcpy(dmsg.next_hop, routing_table[tgtU64].next_hop, 6);
                      dmsg.visited_count = 1;
                      memcpy(dmsg.visited[0], myMac, 6);
                      strncpy(dmsg.payload, text.c_str(), 127);
                      dmsg.payload[127] = 0; // null terminate
                      
                      enqueueMsg(dmsg);
                      Serial.printf("[SND] Blue Ping dispatched! ID: %u\n", dmsg.msg_id);
                  } else {
                      Serial.println("[ERR] Target MAC not in routing table! Unreachable.");
                  }
              } else {
                  Serial.println("[ERR] Missing message text.");
              }
          } else if (input.startsWith("SEND_VIA ")) {
              // Format: SEND_VIA TARGET_MAC RELAY_MAC Text...
              unsigned int t[6], r[6];
              int parsed = sscanf(input.c_str(), "SEND_VIA %x:%x:%x:%x:%x:%x %x:%x:%x:%x:%x:%x", 
                    &t[0], &t[1], &t[2], &t[3], &t[4], &t[5],
                    &r[0], &r[1], &r[2], &r[3], &r[4], &r[5]);
                    
              if (parsed == 12) {
                  uint8_t tgt[6] = {(uint8_t)t[0], (uint8_t)t[1], (uint8_t)t[2], (uint8_t)t[3], (uint8_t)t[4], (uint8_t)t[5]};
                  uint8_t relay[6] = {(uint8_t)r[0], (uint8_t)r[1], (uint8_t)r[2], (uint8_t)r[3], (uint8_t)r[4], (uint8_t)r[5]};
                  int txtIdx = input.indexOf(' ', 36); // Space after second MAC
                  if (txtIdx > 0) {
                      String text = input.substring(txtIdx + 1);
                      DataMsg dmsg;
                      dmsg.type = BLUE_PING;
                      dmsg.msg_id = millis();
                      memcpy(dmsg.target, tgt, 6);
                      memcpy(dmsg.next_hop, relay, 6); // FORCE BACKUP ROUTE
                      dmsg.visited_count = 1;
                      memcpy(dmsg.visited[0], myMac, 6);
                      strncpy(dmsg.payload, text.c_str(), 127);
                      dmsg.payload[127] = 0;
                      
                      enqueueMsg(dmsg);
                      Serial.printf("[SND] Backup Route Ping dispatched via %02X:%02X:%02X:%02X:%02X:%02X! ID: %u\n", 
                                    relay[0], relay[1], relay[2], relay[3], relay[4], relay[5], dmsg.msg_id);
                  } else {
                      Serial.println("[ERR] Missing message text.");
                  }
              } else {
                  Serial.println("[ERR] Invalid SEND_VIA format.");
              }
          } else {
              Serial.println("[ERR] Invalid command format.");
          }
      }
  }
  
  // 3. Process queued transmissions safely in the main loop
  DataMsg queuedMsg;
  if (dequeueMsg(queuedMsg)) {
      // Just-In-Time Peer Registration
      if (!esp_now_is_peer_exist(queuedMsg.next_hop)) {
          esp_now_peer_info_t peer = {};
          memcpy(peer.peer_addr, queuedMsg.next_hop, 6);
          peer.channel = 0;
          peer.encrypt = false;
          peer.ifidx = WIFI_IF_STA; // Explicitly assign to STA interface
          esp_now_add_peer(&peer);
      }
      
      // Send directly to next_hop via UNICAST! This forces the ESP32 Wi-Fi hardware to automatically retry!
      esp_now_send(queuedMsg.next_hop, (uint8_t*)&queuedMsg, sizeof(DataMsg));
      delay(5); // Give WiFi hardware a tiny bit of breathing room
  }
}
