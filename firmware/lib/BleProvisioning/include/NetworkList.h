#ifndef NETWORK_LIST_H
#define NETWORK_LIST_H

#include <cstddef>
#include <cstdint>

// The most a GATT value holds (BLE_ATT_ATTR_MAX_LEN), so the whole list goes in one read.
constexpr size_t NETWORKS_MAX_BYTES = 512;

// One access point a WiFi scan found; ssid is NUL-terminated, empty for a hidden network.
struct ScannedNetwork {
  const char *ssid;
  int8_t rssi;
};

// Encodes a scan for the Networks characteristic: entries of [int8 RSSI][uint8 length][SSID bytes],
// strongest first, one per SSID (its strongest access point), without hidden networks. Sorts networks
// in place. Stops at the last whole entry that fits capacity, and returns the bytes written.
size_t encodeNetworks(ScannedNetwork *networks, size_t count, uint8_t *out, size_t capacity);

#endif // NETWORK_LIST_H
