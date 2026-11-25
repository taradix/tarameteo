#ifndef I_BLE_PROVISIONER_H
#define I_BLE_PROVISIONER_H

#include <cstddef>
#include <cstdint>

// GATT contract shared with the mobile provisioning app. One custom 128-bit
// service, ten characteristics. All writes require an encrypted + authenticated
// link (static-passkey pairing), so the WiFi password never crosses in clear.
//
// Field characteristics are single-write (each fits one MTU); the client writes
// SSID/Password and optionally Location/Label and the backend settings
// (Server/Port/Interval: the MQTT server and seconds between readings), then writes
// BleCommit::PROVISION to Commit. Status then goes "provisioning" while the board
// joins the WiFi, and "ok" once it has joined and saved everything. An
// "error:<code>" saves nothing, and the client can fix the fields and commit again.
// Networks lists the WiFi the board found before it started advertising, for the
// client to offer.
//
// Writing BleCommit::RESET to Commit instead forgets everything provisioning saved
// (WiFi, location, label, server, interval), but not the factory identity. Status
// goes "reset", and the board then sleeps until it is power-cycled, which opens
// the window of a board that was never provisioned.
namespace BleProvisioningUUID {
constexpr const char *SERVICE = "6d5a0001-8b6e-4b3a-9c1d-2f7a5e0c1a01";
constexpr const char *SSID = "6d5a0002-8b6e-4b3a-9c1d-2f7a5e0c1a01";
constexpr const char *PASSWORD = "6d5a0003-8b6e-4b3a-9c1d-2f7a5e0c1a01";
constexpr const char *LOCATION = "6d5a0004-8b6e-4b3a-9c1d-2f7a5e0c1a01"; // 8 bytes: LE float32 lat, LE float32 lon
constexpr const char *COMMIT = "6d5a0005-8b6e-4b3a-9c1d-2f7a5e0c1a01";
constexpr const char *STATUS = "6d5a0006-8b6e-4b3a-9c1d-2f7a5e0c1a01"; // Read + Notify: "idle"/"provisioning"/"ok"/"reset"/"error:<code>", code being ssid/password/location/label/server/port/interval/wifi/storage/commit
constexpr const char *LABEL = "6d5a0007-8b6e-4b3a-9c1d-2f7a5e0c1a01";  // Read + Write: UTF-8, at most 32 bytes, empty for none
constexpr const char *NETWORKS = "6d5a0008-8b6e-4b3a-9c1d-2f7a5e0c1a01"; // Read: the networks it can join, encoded by encodeNetworks() (NetworkList.h)
constexpr const char *SERVER = "6d5a0009-8b6e-4b3a-9c1d-2f7a5e0c1a01";   // Read + Write: host name or IPv4 address, at most 253 bytes
constexpr const char *PORT = "6d5a000a-8b6e-4b3a-9c1d-2f7a5e0c1a01";     // Read + Write: LE uint16, 1 to 65535
constexpr const char *INTERVAL = "6d5a000b-8b6e-4b3a-9c1d-2f7a5e0c1a01"; // Read + Write: LE uint32 seconds between readings, 60 to 86400
} // namespace BleProvisioningUUID

// The one byte written to Commit: what the board does with the fields. Any other
// value gets "error:commit".
namespace BleCommit {
constexpr uint8_t PROVISION = 0x01;
constexpr uint8_t RESET = 0x02;
} // namespace BleCommit

// What a Commit write asks for, as poll() returns it; Unknown for a value that isn't a BleCommit.
enum class BleRequest : uint8_t { None, Provision, Reset, Unknown };

// Defined in WiFiManager.h and StationSettings.h; declarations need no more, which
// keeps this contract free of their dependencies.
struct WiFiCredentials;
struct Location;
struct MqttServer;

// Transport for BLE provisioning. NimBLE write callbacks run on their own task,
// so the adapter buffers a single payload and the main loop drains it via poll(),
// which keeps provisioning single-threaded.
class IBleProvisioner {
public:
  virtual ~IBleProvisioner() = default;

  // Start advertising under deviceName, requiring the static passkey to pair.
  // label, location, server and interval are the current ones: the client can
  // read the label, server and interval to prefill them, and a payload without
  // one of these fields keeps it. networks is what Networks reads, copied.
  // Returns false when the BLE stack or advertising fails to start.
  virtual bool begin(const char *deviceName, uint32_t passkey, const char *label, const Location &location,
                     const MqttServer &server, uint32_t interval, const uint8_t *networks, size_t networksLength) = 0;
  virtual void stop() = 0;

  // Returns what a Commit write asked for, once per write, else None. For
  // Provision, whatever the fields hold: the getters then return the last values
  // written (begin()'s for fields the client skipped), and apply() validates them.
  // A port or interval of the wrong length reads as 0, which apply() rejects.
  virtual BleRequest poll() = 0;
  virtual WiFiCredentials wifi() = 0;
  virtual Location location() = 0;
  virtual const char *label() = 0;
  virtual MqttServer mqttServer() = 0;
  virtual uint32_t interval() = 0;

  // Report result back to the client over the Status characteristic (notify).
  virtual void notifyStatus(const char *status) = 0;
};

#endif // I_BLE_PROVISIONER_H
