#include "NetworkList.h"

#include <cstring>

// The 802.11 limit, like WiFiManager::MAX_SSID_BYTES.
static constexpr size_t MAX_SSID_BYTES = 32;

size_t encodeNetworks(ScannedNetwork *networks, size_t count, uint8_t *out, size_t capacity) {
  // Insertion sort, strongest first: a scan finds a few dozen access points at most.
  for (size_t i = 1; i < count; i++) {
    ScannedNetwork network = networks[i];
    size_t j = i;
    for (; j > 0 && networks[j - 1].rssi < network.rssi; j--) {
      networks[j] = networks[j - 1];
    }
    networks[j] = network;
  }

  size_t written = 0;
  for (size_t i = 0; i < count; i++) {
    size_t length = strlen(networks[i].ssid);
    if (length == 0 || length > MAX_SSID_BYTES) {
      continue;
    }
    // A mesh or a dual-band router shows one SSID from several access points; the first is the strongest.
    bool seen = false;
    for (size_t j = 0; j < i && !seen; j++) {
      seen = strcmp(networks[j].ssid, networks[i].ssid) == 0;
    }
    if (seen) {
      continue;
    }
    if (written + 2 + length > capacity) {
      break;
    }
    out[written++] = static_cast<uint8_t>(networks[i].rssi);
    out[written++] = static_cast<uint8_t>(length);
    memcpy(out + written, networks[i].ssid, length);
    written += length;
  }
  return written;
}
