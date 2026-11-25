#ifndef NIMBLE_PROVISIONER_ADAPTER_H
#define NIMBLE_PROVISIONER_ADAPTER_H

#include "FieldCodec.h"
#include "IBleProvisioner.h"

#ifndef UNIT_TEST
#include "StationSettings.h"
#include "WiFiManager.h"
#include <NimBLEDevice.h>
#include <atomic>
#include <cstring>

// Real BLE provisioning transport backed by NimBLE-Arduino v2.
//
// Threading: NimBLE runs its own host task; characteristic write callbacks fire
// on it. They only copy the payload into member buffers and set _request.
// The main loop calls poll() to consume it. Single writer (BLE task) / single
// reader (main loop): the release store / acquire load on _request makes the
// buffer writes before Commit visible to poll() — no locks needed.
class NimBLEProvisionerAdapter : public IBleProvisioner {
public:
  NimBLEProvisionerAdapter() : _request(BleRequest::None), _location{0.0f, 0.0f}, _port(0), _interval(0), _statusChar(nullptr) {
    _ssid[0] = '\0';
    _password[0] = '\0';
    _label[0] = '\0';
    _mqttHost[0] = '\0';
  }

  bool begin(const char *deviceName, uint32_t passkey, const char *label, const Location &location,
             const MqttServer &server, uint32_t interval, const uint8_t *networks, size_t networksLength) override {
    // A client that never writes Label, Location, Server, Port or Interval keeps the current ones.
    copyString(_label, reinterpret_cast<const uint8_t *>(label), strlen(label));
    _location = location;
    copyString(_mqttHost, reinterpret_cast<const uint8_t *>(server.host), strlen(server.host));
    _port = server.port;
    _interval = interval;

    if (!NimBLEDevice::init(deviceName)) {
      return false;
    }

    // Static passkey pairing: bonding + MITM protection + LE Secure Connections.
    // The device has no display, so it only supplies a fixed passkey the app enters.
    NimBLEDevice::setSecurityAuth(true, true, true);
    NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);
    NimBLEDevice::setSecurityPasskey(passkey);

    _gattServer = NimBLEDevice::createServer();
    // NimBLE stops advertising once a client connects and, by default, doesn't start again when it
    // leaves: a session that failed or was abandoned would hide the board for the rest of its window.
    _gattServer->advertiseOnDisconnect(true);
    NimBLEService *service = _gattServer->createService(BleProvisioningUUID::SERVICE);

    // Field writes require an encrypted + authenticated link.
    const uint32_t writeSecure = NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_ENC | NIMBLE_PROPERTY::WRITE_AUTHEN;

    _ssidChar = service->createCharacteristic(BleProvisioningUUID::SSID, writeSecure);
    _ssidChar->setCallbacks(new FieldCallback(this, Field::Ssid));

    _passwordChar = service->createCharacteristic(BleProvisioningUUID::PASSWORD, writeSecure);
    _passwordChar->setCallbacks(new FieldCallback(this, Field::Password));

    _locationChar = service->createCharacteristic(BleProvisioningUUID::LOCATION, writeSecure);
    _locationChar->setCallbacks(new FieldCallback(this, Field::Location));

    _labelChar = service->createCharacteristic(
        BleProvisioningUUID::LABEL,
        writeSecure | NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::READ_ENC | NIMBLE_PROPERTY::READ_AUTHEN);
    _labelChar->setValue(_label);
    _labelChar->setCallbacks(new FieldCallback(this, Field::Label));

    // Readable like Label, so the client can show the current values.
    const uint32_t readWriteSecure =
        writeSecure | NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::READ_ENC | NIMBLE_PROPERTY::READ_AUTHEN;
    _serverChar = service->createCharacteristic(BleProvisioningUUID::SERVER, readWriteSecure);
    _serverChar->setValue(_mqttHost);
    _serverChar->setCallbacks(new FieldCallback(this, Field::Server));

    _portChar = service->createCharacteristic(BleProvisioningUUID::PORT, readWriteSecure);
    uint8_t portBytes[2];
    encodePort(_port, portBytes);
    _portChar->setValue(portBytes, sizeof(portBytes));
    _portChar->setCallbacks(new FieldCallback(this, Field::Port));

    _intervalChar = service->createCharacteristic(BleProvisioningUUID::INTERVAL, readWriteSecure);
    uint8_t intervalBytes[4];
    encodeInterval(_interval, intervalBytes);
    _intervalChar->setValue(intervalBytes, sizeof(intervalBytes));
    _intervalChar->setCallbacks(new FieldCallback(this, Field::Interval));

    _commitChar = service->createCharacteristic(BleProvisioningUUID::COMMIT, writeSecure);
    _commitChar->setCallbacks(new FieldCallback(this, Field::Commit));

    // Read only: the client never writes it, so it has no callback.
    NimBLECharacteristic *networksChar = service->createCharacteristic(
        BleProvisioningUUID::NETWORKS, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::READ_ENC | NIMBLE_PROPERTY::READ_AUTHEN);
    networksChar->setValue(networks, networksLength);

    _statusChar = service->createCharacteristic(BleProvisioningUUID::STATUS,
                                                NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
    _statusChar->setValue("idle");

    // No service->start() (deprecated in NimBLE 2): advertising starts the GATT server.
    NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
    adv->addServiceUUID(BleProvisioningUUID::SERVICE);
    // Flags + the 128-bit UUID take 21 of the 31 advertising bytes, too few
    // for the name, so it goes in the scan response.
    NimBLEAdvertisementData scanResponse;
    scanResponse.setName(deviceName);
    adv->setScanResponseData(scanResponse);
    adv->enableScanResponse(true);
    return NimBLEDevice::startAdvertising();
  }

  void stop() override { NimBLEDevice::deinit(true); }

  BleRequest poll() override { return _request.exchange(BleRequest::None, std::memory_order_acquire); }

  WiFiCredentials wifi() override { return {_ssid, _password}; }
  Location location() override { return _location; }
  const char *label() override { return _label; }
  MqttServer mqttServer() override { return {_mqttHost, _port}; }
  uint32_t interval() override { return _interval; }

  void notifyStatus(const char *status) override {
    if (_statusChar) {
      _statusChar->setValue(status);
      _statusChar->notify();
    }
  }

private:
  enum class Field { Ssid, Password, Location, Label, Server, Port, Interval, Commit };

  // Copies a written field into the matching buffer. On Commit, sets the request
  // poll() watches. The string buffers hold one byte more than allowed, so an
  // over-long value reaches applyProvisioning and fails there instead of being cut.
  void onFieldWrite(Field field, const uint8_t *data, size_t len) {
    switch (field) {
    case Field::Ssid:
      copyString(_ssid, data, len);
      break;
    case Field::Password:
      copyString(_password, data, len);
      break;
    case Field::Location:
      decodeLocation(data, len, _location.latitude, _location.longitude);
      break;
    case Field::Label:
      copyString(_label, data, len);
      break;
    case Field::Server:
      copyString(_mqttHost, data, len);
      break;
    case Field::Port:
      _port = decodePort(data, len);
      break;
    case Field::Interval:
      _interval = decodeInterval(data, len);
      break;
    case Field::Commit:
      _request.store(decodeCommit(data, len), std::memory_order_release);
      break;
    }
  }

  class FieldCallback : public NimBLECharacteristicCallbacks {
  public:
    FieldCallback(NimBLEProvisionerAdapter *owner, Field field) : _owner(owner), _field(field) {}
    void onWrite(NimBLECharacteristic *characteristic, NimBLEConnInfo &connInfo) override {
      NimBLEAttValue value = characteristic->getValue();
      _owner->onFieldWrite(_field, value.data(), value.length());
    }

  private:
    NimBLEProvisionerAdapter *_owner;
    Field _field;
  };

  NimBLEServer *_gattServer;
  NimBLECharacteristic *_ssidChar;
  NimBLECharacteristic *_passwordChar;
  NimBLECharacteristic *_locationChar;
  NimBLECharacteristic *_labelChar;
  NimBLECharacteristic *_serverChar;
  NimBLECharacteristic *_portChar;
  NimBLECharacteristic *_intervalChar;
  NimBLECharacteristic *_commitChar;
  NimBLECharacteristic *_statusChar;

  char _ssid[WiFiManager::MAX_SSID_BYTES + 2];
  char _password[WiFiManager::MAX_PASSWORD_BYTES + 2];
  char _label[StationSettings::MAX_LABEL_BYTES + 2];
  char _mqttHost[StationSettings::MAX_HOST_BYTES + 2];
  std::atomic<BleRequest> _request;
  Location _location;
  uint16_t _port;
  uint32_t _interval;
};

#endif // UNIT_TEST
#endif // NIMBLE_PROVISIONER_ADAPTER_H
