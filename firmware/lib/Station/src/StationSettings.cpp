#include "StationSettings.h"

#include <stdio.h>
#include <string.h>

#ifdef UNIT_TEST
#include "../../WiFiManager/WiFiManager.h"
#include "Arduino.h"
#else
#include "WiFiManager.h"
#endif

const char *const StationSettings::KEYS[] = {"latitude", "longitude", "label", "mqtt_server", "mqtt_port", "interval"};

StationSettings::StationSettings(Preferences &prefs, IArduino *arduino, WiFiManager &wifiManager)
    : _status("idle"), _location{0.0f, 0.0f}, _mqttPort(0), _interval(0), _defaultServer{"", 0}, _defaultInterval(0),
      _prefs(prefs), _arduino(arduino),
      _wifiManager(wifiManager) {
  _lastError[0] = '\0';
  _label[0] = '\0';
  _mqttHost[0] = '\0';
}

bool StationSettings::begin(const MqttServer &defaultServer, uint32_t defaultInterval) {
  if (!_prefs.begin("tarameteo_certs", false)) {
    setError("Failed to initialize NVS");
    return false;
  }
  _defaultServer = defaultServer;
  _defaultInterval = defaultInterval;
  load();
  return true;
}

// The stored settings, else the defaults.
void StationSettings::load() {
  _location = {_prefs.getFloat("latitude", 0.0f), _prefs.getFloat("longitude", 0.0f)};
  _label[0] = '\0';
  if (_prefs.isKey("label")) {
    _prefs.getString("label", _label, sizeof(_label));
  }
  // Provisioned, else the defaults; apply() validated the stored ones.
  if (_prefs.isKey("mqtt_server")) {
    _prefs.getString("mqtt_server", _mqttHost, sizeof(_mqttHost));
  } else {
    strncpy(_mqttHost, _defaultServer.host, sizeof(_mqttHost) - 1);
    _mqttHost[sizeof(_mqttHost) - 1] = '\0';
  }
  _mqttPort = (uint16_t)_prefs.getULong("mqtt_port", _defaultServer.port);
  _interval = (uint32_t)_prefs.getULong("interval", _defaultInterval);

  _arduino->logf("StationSettings: lat=%.6f, lon=%.6f, label=%s", _location.latitude, _location.longitude, _label);
  _arduino->logf("StationSettings: MQTT server %s:%u, a reading every %lu s", _mqttHost, (unsigned)_mqttPort,
                 (unsigned long)_interval);
}

bool StationSettings::reset() {
  // The WiFi first: without it the board stops sending readings, whatever else stays.
  if (!_wifiManager.clearCredentials()) {
    return reject("error:storage", _wifiManager.getLastError());
  }
  // Key by key: FactoryIdentity's keys share the namespace. remove() fails on a missing key.
  for (const char *key : KEYS) {
    if (_prefs.isKey(key) && !_prefs.remove(key)) {
      load(); // What is left
      return reject("error:storage", "Failed to erase settings from NVS");
    }
  }
  load(); // The defaults now
  _arduino->log("StationSettings: Reset to factory settings");
  _status = "reset";
  return true;
}

// Validates what the BLE transport received, joins the WiFi with it, then
// persists it. On failure sets _lastError and _status and returns false.
bool StationSettings::apply(const WiFiCredentials &wifi, const Location &location, const char *label,
                            const MqttServer &server, uint32_t interval) {
  if (!WiFiManager::isValidSsid(wifi.ssid)) {
    return reject("error:ssid", "Invalid WiFi SSID: 1 to 32 bytes");
  }
  if (!WiFiManager::isValidPassword(wifi.password)) {
    return reject("error:password", "Invalid WiFi password: 1 to 64 bytes");
  }
  // Written so NaN fails too
  if (!(location.latitude >= -90.0f && location.latitude <= 90.0f)) {
    return reject("error:location", "Invalid latitude: must be between -90 and 90");
  }
  if (!(location.longitude >= -180.0f && location.longitude <= 180.0f)) {
    return reject("error:location", "Invalid longitude: must be between -180 and 180");
  }
  if (!isValidLabel(label)) {
    return reject("error:label", "Invalid label: at most 32 bytes of UTF-8, no control characters");
  }
  if (!isValidHost(server.host)) {
    return reject("error:server", "Invalid MQTT server: a host name or IPv4 address, at most 253 bytes");
  }
  if (server.port == 0) {
    return reject("error:port", "Invalid MQTT port: 1 to 65535");
  }
  if (!isValidInterval(interval)) {
    return reject("error:interval", "Invalid interval: 60 to 86400 seconds");
  }
  // Join before saving anything, so a typo in the password can't lock the board out.
  if (!_wifiManager.tryConnect(wifi)) {
    return reject("error:wifi", _wifiManager.getLastError());
  }

  // A failed write puts back what NVS held, so a rejected payload changes nothing
  // there either; memory still holds the old settings until the end.
  bool existed[KEY_COUNT];
  for (size_t i = 0; i < KEY_COUNT; i++) {
    existed[i] = _prefs.isKey(KEYS[i]);
  }
  if (!put(location, label, server, interval)) {
    restore(existed);
    _status = "error:storage"; // put() set the error
    return false;
  }
  // Credentials last: they end the provisioning window on the next boot.
  if (!_wifiManager.storeCredentials(wifi)) {
    restore(existed);
    return reject("error:storage", _wifiManager.getLastError());
  }
  _location = location;
  memcpy(_label, label, strlen(label) + 1);                // isValidLabel checked it fits
  memcpy(_mqttHost, server.host, strlen(server.host) + 1); // isValidHost checked it fits
  _mqttPort = server.port;
  _interval = interval;

  _arduino->log("StationSettings: Provisioning saved");
  _status = "ok";
  return true;
}

// Writes every setting; false, with the error set, at the first that fails.
bool StationSettings::put(const Location &location, const char *label, const MqttServer &server, uint32_t interval) {
  // put* returns 0 bytes written on failure.
  if (_prefs.putFloat("latitude", location.latitude) == 0 || _prefs.putFloat("longitude", location.longitude) == 0) {
    setError("Failed to store location in NVS");
    return false;
  }
  // NOTE: putString also returns 0 for an empty label, so that write can't be
  // checked; a failed clear keeps the previous label until reprovisioning.
  if (_prefs.putString("label", label) == 0 && label[0] != '\0') {
    setError("Failed to store label in NVS");
    return false;
  }
  if (_prefs.putString("mqtt_server", server.host) == 0 || _prefs.putULong("mqtt_port", server.port) == 0) {
    setError("Failed to store MQTT server in NVS");
    return false;
  }
  if (_prefs.putULong("interval", interval) == 0) {
    setError("Failed to store interval in NVS");
    return false;
  }
  return true;
}

// Puts NVS back as it was before a failed save: the settings memory holds, which are
// the stored ones or the defaults, without the keys that weren't there. Best effort:
// a write that failed once may fail again.
void StationSettings::restore(const bool (&existed)[KEY_COUNT]) {
  static_assert(sizeof(KEYS) / sizeof(KEYS[0]) == KEY_COUNT, "KEY_COUNT must match KEYS");
  char error[sizeof(_lastError)];
  memcpy(error, _lastError, sizeof(error)); // Keep the failure that caused this, not a restore's
  if (!put(_location, _label, getMqttServer(), _interval)) {
    _arduino->log("StationSettings: Could not restore every setting in NVS");
  }
  for (size_t i = 0; i < KEY_COUNT; i++) {
    if (!existed[i]) {
      _prefs.remove(KEYS[i]);
    }
  }
  memcpy(_lastError, error, sizeof(error));
}

bool StationSettings::reject(const char *status, const char *error) {
  _status = status;
  setError(error);
  return false;
}

// The backend drops a whole reading whose label isn't well-formed UTF-8 or has
// control characters (labels reach email subjects), so reject it up front.
bool StationSettings::isValidLabel(const char *label) {
  if (!label || strlen(label) > MAX_LABEL_BYTES) {
    return false;
  }
  const unsigned char *s = reinterpret_cast<const unsigned char *>(label);
  while (*s) {
    unsigned char c = *s++;
    if (c < 0x20 || c == 0x7f) {
      return false;
    }
    if (c < 0x80) {
      continue;
    }
    // Lead byte: how many continuation bytes follow, and the first one's range (Unicode table 3-7).
    int more;
    unsigned char lo = 0x80;
    unsigned char hi = 0xbf;
    if (c >= 0xc2 && c <= 0xdf) {
      more = 1;
    } else if (c >= 0xe0 && c <= 0xef) {
      more = 2;
      lo = (c == 0xe0) ? 0xa0 : lo; // overlong
      hi = (c == 0xed) ? 0x9f : hi; // surrogates
    } else if (c >= 0xf0 && c <= 0xf4) {
      more = 3;
      lo = (c == 0xf0) ? 0x90 : lo; // overlong
      hi = (c == 0xf4) ? 0x8f : hi; // past U+10FFFF
    } else {
      return false;
    }
    for (; more > 0; more--, lo = 0x80, hi = 0xbf) {
      if (*s < lo || *s > hi) { // also stops at the terminating NUL
        return false;
      }
      s++;
    }
  }
  return true;
}

// Letters, digits, dots and hyphens: what a DNS name or an IPv4 address holds.
// The rest (labels starting with a hyphen, empty labels) is DNS's to reject.
bool StationSettings::isValidHost(const char *host) {
  if (!host || host[0] == '\0' || strlen(host) > MAX_HOST_BYTES) {
    return false;
  }
  for (const char *c = host; *c; c++) {
    bool ok =
        (*c >= 'a' && *c <= 'z') || (*c >= 'A' && *c <= 'Z') || (*c >= '0' && *c <= '9') || *c == '.' || *c == '-';
    if (!ok) {
      return false;
    }
  }
  return true;
}

void StationSettings::setError(const char *error) {
  strncpy(_lastError, error, sizeof(_lastError) - 1);
  _lastError[sizeof(_lastError) - 1] = '\0';
  _arduino->logf("StationSettings: ERROR - %s", _lastError);
}
