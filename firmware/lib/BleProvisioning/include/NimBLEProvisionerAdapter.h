#ifndef NIMBLE_PROVISIONER_ADAPTER_H
#define NIMBLE_PROVISIONER_ADAPTER_H

#include "IBleProvisioner.h"

#ifndef UNIT_TEST
#include <NimBLEDevice.h>
#include <cstring>

// Real BLE provisioning transport backed by NimBLE-Arduino v2.
//
// Threading: NimBLE runs its own host task; characteristic write callbacks fire
// on it. They only copy the payload into member buffers and raise _committed.
// The main loop calls poll() to consume it. Single writer (BLE task) / single
// reader (main loop) with a volatile flag — no locks needed.
class NimBLEProvisionerAdapter : public IBleProvisioner {
public:
  NimBLEProvisionerAdapter() : _committed(false), _lat(0.0f), _lon(0.0f), _statusChar(nullptr) {
    _ssid[0] = '\0';
    _password[0] = '\0';
  }

  bool begin(const char *deviceName, uint32_t passkey) override {
    NimBLEDevice::init(deviceName);

    // Static passkey pairing: bonding + MITM protection + LE Secure Connections.
    // The device has no display, so it only supplies a fixed passkey the app enters.
    NimBLEDevice::setSecurityAuth(true, true, true);
    NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);
    NimBLEDevice::setSecurityPasskey(passkey);

    _server = NimBLEDevice::createServer();
    NimBLEService *service = _server->createService(BleProvisioningUUID::SERVICE);

    // Field writes require an encrypted + authenticated link.
    const uint32_t writeSecure = NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_ENC | NIMBLE_PROPERTY::WRITE_AUTHEN;

    _ssidChar = service->createCharacteristic(BleProvisioningUUID::SSID, writeSecure);
    _ssidChar->setCallbacks(new FieldCallback(this, Field::Ssid));

    _passwordChar = service->createCharacteristic(BleProvisioningUUID::PASSWORD, writeSecure);
    _passwordChar->setCallbacks(new FieldCallback(this, Field::Password));

    _locationChar = service->createCharacteristic(BleProvisioningUUID::LOCATION, writeSecure);
    _locationChar->setCallbacks(new FieldCallback(this, Field::Location));

    _commitChar = service->createCharacteristic(BleProvisioningUUID::COMMIT, writeSecure);
    _commitChar->setCallbacks(new FieldCallback(this, Field::Commit));

    _statusChar = service->createCharacteristic(BleProvisioningUUID::STATUS,
                                                NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
    _statusChar->setValue("idle");

    service->start();

    NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
    adv->addServiceUUID(BleProvisioningUUID::SERVICE);
    adv->setName(deviceName);
    NimBLEDevice::startAdvertising();
    return true;
  }

  void stop() override { NimBLEDevice::deinit(true); }

  bool poll() override {
    if (!_committed) {
      return false;
    }
    _committed = false;
    return true;
  }

  const char *ssid() override { return _ssid; }
  const char *password() override { return _password; }
  float latitude() override { return _lat; }
  float longitude() override { return _lon; }

  void notifyStatus(const char *status) override {
    if (_statusChar) {
      _statusChar->setValue(status);
      _statusChar->notify();
    }
  }

private:
  enum class Field { Ssid, Password, Location, Commit };

  // Copies a written field into the matching buffer. On Commit, raises the flag
  // poll() watches. Bounds are enforced against the fixed buffers.
  void onFieldWrite(Field field, const uint8_t *data, size_t len) {
    switch (field) {
    case Field::Ssid:
      copyString(_ssid, sizeof(_ssid), data, len);
      break;
    case Field::Password:
      copyString(_password, sizeof(_password), data, len);
      break;
    case Field::Location:
      if (len == 8) { // two little-endian float32: lat, lon
        memcpy(&_lat, data, 4);
        memcpy(&_lon, data + 4, 4);
      }
      break;
    case Field::Commit:
      _committed = true;
      break;
    }
  }

  static void copyString(char *dst, size_t dstSize, const uint8_t *data, size_t len) {
    size_t n = (len < dstSize - 1) ? len : dstSize - 1;
    memcpy(dst, data, n);
    dst[n] = '\0';
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

  NimBLEServer *_server;
  NimBLECharacteristic *_ssidChar;
  NimBLECharacteristic *_passwordChar;
  NimBLECharacteristic *_locationChar;
  NimBLECharacteristic *_commitChar;
  NimBLECharacteristic *_statusChar;

  char _ssid[32];
  char _password[64];
  volatile bool _committed;
  float _lat;
  float _lon;
};

#endif // UNIT_TEST
#endif // NIMBLE_PROVISIONER_ADAPTER_H
