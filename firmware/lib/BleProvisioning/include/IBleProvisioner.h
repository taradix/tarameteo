#ifndef I_BLE_PROVISIONER_H
#define I_BLE_PROVISIONER_H

#include <cstdint>

// GATT contract shared with the mobile provisioning app. One custom 128-bit
// service, five characteristics. All writes require an encrypted + authenticated
// link (static-passkey pairing), so the WiFi password never crosses in clear.
//
// Field characteristics are single-write (each fits one MTU); the client writes
// SSID/Password/Location, then writes Commit to signal a complete payload.
namespace BleProvisioningUUID {
constexpr const char *SERVICE = "6d5a0001-8b6e-4b3a-9c1d-2f7a5e0c1a01";
constexpr const char *SSID = "6d5a0002-8b6e-4b3a-9c1d-2f7a5e0c1a01";
constexpr const char *PASSWORD = "6d5a0003-8b6e-4b3a-9c1d-2f7a5e0c1a01";
constexpr const char *LOCATION = "6d5a0004-8b6e-4b3a-9c1d-2f7a5e0c1a01"; // 8 bytes: LE float32 lat, LE float32 lon
constexpr const char *COMMIT = "6d5a0005-8b6e-4b3a-9c1d-2f7a5e0c1a01";
constexpr const char *STATUS = "6d5a0006-8b6e-4b3a-9c1d-2f7a5e0c1a01"; // Read + Notify: "idle"/"provisioning"/"ok"/"error:<reason>"
} // namespace BleProvisioningUUID

// Transport for BLE provisioning. NimBLE write callbacks run on their own task,
// so the adapter buffers a single payload and the main loop drains it via poll()
// — keeps provisioning single-threaded, matching the old HTTP flow.
class IBleProvisioner {
public:
  virtual ~IBleProvisioner() = default;

  // Start advertising under deviceName, requiring the static passkey to pair.
  virtual bool begin(const char *deviceName, uint32_t passkey) = 0;
  virtual void stop() = 0;

  // Returns true once Commit has been received with a full payload. The
  // ssid()/password()/latitude()/longitude() getters are valid after that.
  virtual bool poll() = 0;
  virtual const char *ssid() = 0;
  virtual const char *password() = 0;
  virtual float latitude() = 0;
  virtual float longitude() = 0;

  // Report result back to the client over the Status characteristic (notify).
  virtual void notifyStatus(const char *status) = 0;
};

#endif // I_BLE_PROVISIONER_H
