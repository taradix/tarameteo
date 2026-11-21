#include "CertificateManager.h"
#include "X509Parser.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef UNIT_TEST
#include "Arduino.h"
#include "../../WiFiManager/WiFiManager.h"
#else
#include "WiFiManager.h"
#endif

const char *const CertificateManager::SETTING_KEYS[] = {"latitude",    "longitude", "label",
                                                        "mqtt_server", "mqtt_port", "interval"};

CertificateManager::CertificateManager(Preferences &prefs, IArduino *arduino)
    : _mqttPort(0), _interval(0), _provisioningStatus("idle"), _passkey(0), _location{0.0f, 0.0f}, _prefs(prefs),
      _arduino(arduino), _wifiManager(nullptr), _clientCert(nullptr), _clientKey(nullptr), _caCert(nullptr) {
  _lastError[0] = '\0';
  _cn[0] = '\0';
  _label[0] = '\0';
  _mqttHost[0] = '\0';
}

CertificateManager::~CertificateManager() {
  clearClientCredentials();
  clearCACertificate();
}

bool CertificateManager::begin(const MqttServer &defaultServer, uint32_t defaultInterval) {
  _arduino->log("CertificateManager: Initializing...");

  // Initialize NVS
  if (!_prefs.begin("tarameteo_certs", false)) {
    setError("Failed to initialize NVS");
    return false;
  }

  if (!loadFromNVS(defaultServer, defaultInterval)) {
    _arduino->log("CertificateManager: No factory identity in NVS - run scripts/factory.py");
    return false;
  }

  // Never clear NVS here: the identity cannot be re-created on the device.
  if (!validateCertificates()) {
    clearClientCredentials();
    clearCACertificate();
    return false;
  }

  if (_passkey == 0 || _passkey > MAX_PASSKEY) {
    setError("BLE passkey missing from NVS");
    return false;
  }

  _arduino->log("CertificateManager: Certificates validated successfully");
  return true;
}

bool CertificateManager::isProvisioned() const { return (_clientCert != nullptr && _clientKey != nullptr); }

bool CertificateManager::needsProvisioning() const { return !isProvisioned(); }

bool CertificateManager::loadFromNVS(const MqttServer &defaultServer, uint32_t defaultInterval) {
  if (!_prefs.isKey("cli_cert") || !_prefs.isKey("cli_key")) {
    setError("Certificates not found in NVS");
    return false;
  }

  if (!_clientCert) {
    _clientCert = (char *)malloc(MAX_CERT_SIZE);
  }
  if (!_clientKey) {
    _clientKey = (char *)malloc(MAX_KEY_SIZE);
  }
  if (!_clientCert || !_clientKey) {
    clearClientCredentials();
    setError("Failed to allocate memory for certificates");
    return false;
  }

  size_t certLen = _prefs.getString("cli_cert", _clientCert, MAX_CERT_SIZE);
  if (certLen == 0) {
    clearClientCredentials();
    setError("Failed to read client certificate from NVS");
    return false;
  }

  size_t keyLen = _prefs.getString("cli_key", _clientKey, MAX_KEY_SIZE);
  if (keyLen == 0) {
    clearClientCredentials();
    setError("Failed to read client key from NVS");
    return false;
  }

  if (_prefs.isKey("ca_cert")) {
    clearCACertificate();
    _caCert = (char *)malloc(MAX_CERT_SIZE);
    if (_caCert) {
      size_t caLen = _prefs.getString("ca_cert", _caCert, MAX_CERT_SIZE);
      if (caLen == 0) {
        clearCACertificate();
      }
    }
  }

  _passkey = _prefs.getULong("passkey", 0);
  _location = {_prefs.getFloat("latitude", 0.0f), _prefs.getFloat("longitude", 0.0f)};
  _label[0] = '\0';
  if (_prefs.isKey("label")) {
    _prefs.getString("label", _label, sizeof(_label));
  }

  // Provisioned backend settings, else the defaults; applyProvisioning validated the stored ones.
  if (_prefs.isKey("mqtt_server")) {
    _prefs.getString("mqtt_server", _mqttHost, sizeof(_mqttHost));
  } else {
    strncpy(_mqttHost, defaultServer.host, sizeof(_mqttHost) - 1);
    _mqttHost[sizeof(_mqttHost) - 1] = '\0';
  }
  _mqttPort = (uint16_t)_prefs.getULong("mqtt_port", defaultServer.port);
  _interval = (uint32_t)_prefs.getULong("interval", defaultInterval);

  _arduino->logf("CertificateManager: Loaded identity, lat=%.6f, lon=%.6f, label=%s", _location.latitude,
                 _location.longitude, _label);
  _arduino->logf("CertificateManager: MQTT server %s:%u, a reading every %lu s", _mqttHost, (unsigned)_mqttPort,
                 (unsigned long)_interval);

  return true;
}

bool CertificateManager::loadCertificates(IWiFiClient &client) {
  if (!isProvisioned()) {
    setError("Certificates not provisioned");
    return false;
  }

  if (_caCert) {
    client.setCACert(_caCert);
    _arduino->log("CertificateManager: CA certificate loaded");
  } else {
    setError("CA certificate is required for TLS server verification");
    return false;
  }

  client.setCertificate(_clientCert);
  client.setPrivateKey(_clientKey);

  _arduino->logf("CertificateManager: Client certificate loaded (CN=%s)", _cn);
  return true;
}

// Format and CN only: expiry is the MQTT server's call, and board certs never
// expire anyway (backend pki.NO_EXPIRY).
bool CertificateManager::validateCertificates() {
  if (!isProvisioned()) {
    setError("Certificates not provisioned");
    return false;
  }

  if (!validateCertificateFormat(_clientCert)) {
    setError("Invalid certificate format");
    return false;
  }

  if (!validatePrivateKeyFormat(_clientKey)) {
    setError("Invalid private key format");
    return false;
  }

  if (!extractCNFromCert(_clientCert)) {
    setError("Failed to extract CN from certificate");
    return false;
  }

  return true;
}

bool CertificateManager::validateCertificateFormat(const char *certPem) {
  if (!certPem || strlen(certPem) == 0) {
    return false;
  }

  if (strstr(certPem, "-----BEGIN CERTIFICATE-----") == nullptr) {
    return false;
  }
  if (strstr(certPem, "-----END CERTIFICATE-----") == nullptr) {
    return false;
  }

  return true;
}

bool CertificateManager::validatePrivateKeyFormat(const char *keyPem) {
  if (!keyPem || strlen(keyPem) == 0) {
    return false;
  }

  bool hasBegin = (strstr(keyPem, "-----BEGIN PRIVATE KEY-----") != nullptr) ||
                  (strstr(keyPem, "-----BEGIN RSA PRIVATE KEY-----") != nullptr) ||
                  (strstr(keyPem, "-----BEGIN EC PRIVATE KEY-----") != nullptr);

  bool hasEnd = (strstr(keyPem, "-----END PRIVATE KEY-----") != nullptr) ||
                (strstr(keyPem, "-----END RSA PRIVATE KEY-----") != nullptr) ||
                (strstr(keyPem, "-----END EC PRIVATE KEY-----") != nullptr);

  return (hasBegin && hasEnd);
}

bool CertificateManager::extractCNFromCert(const char *certPem) {
  bool result = X509Parser::extractCN(certPem, _cn, MAX_CN_LENGTH);

  if (!result) {
    _arduino->log("CertificateManager: Failed to extract CN from certificate");
    return false;
  }

  _arduino->logf("CertificateManager: Extracted CN: %s", _cn);
  return true;
}

// Validates what the BLE transport received, joins the WiFi with it, then
// persists it. On failure sets _lastError and _provisioningStatus and returns false.
bool CertificateManager::applyProvisioning(const WiFiCredentials &wifi, const Location &location, const char *label,
                                           const MqttServer &server, uint32_t interval) {
  if (!WiFiManager::isValidSsid(wifi.ssid)) {
    return rejectProvisioning("error:ssid", "Invalid WiFi SSID: 1 to 32 bytes");
  }
  if (!WiFiManager::isValidPassword(wifi.password)) {
    return rejectProvisioning("error:password", "Invalid WiFi password: 1 to 64 bytes");
  }
  // Written so NaN fails too
  if (!(location.latitude >= -90.0f && location.latitude <= 90.0f)) {
    return rejectProvisioning("error:location", "Invalid latitude: must be between -90 and 90");
  }
  if (!(location.longitude >= -180.0f && location.longitude <= 180.0f)) {
    return rejectProvisioning("error:location", "Invalid longitude: must be between -180 and 180");
  }
  if (!isValidLabel(label)) {
    return rejectProvisioning("error:label", "Invalid label: at most 32 bytes of UTF-8, no control characters");
  }
  if (!isValidHost(server.host)) {
    return rejectProvisioning("error:server", "Invalid MQTT server: a host name or IPv4 address, at most 253 bytes");
  }
  if (server.port == 0) {
    return rejectProvisioning("error:port", "Invalid MQTT port: 1 to 65535");
  }
  if (!isValidInterval(interval)) {
    return rejectProvisioning("error:interval", "Invalid interval: 60 to 86400 seconds");
  }
  if (!_wifiManager) {
    return rejectProvisioning("error:wifi", "WiFi manager not available");
  }

  // Join before saving anything, so a typo in the password can't lock the board out.
  if (!_wifiManager->tryConnect(wifi)) {
    return rejectProvisioning("error:wifi", _wifiManager->getLastError());
  }

  // A failed write puts back what NVS held, so a rejected payload changes nothing
  // there either; memory still holds the old settings until the end.
  bool existed[SETTING_COUNT];
  for (size_t i = 0; i < SETTING_COUNT; i++) {
    existed[i] = _prefs.isKey(SETTING_KEYS[i]);
  }
  if (!putSettings(location, label, server, interval)) {
    restoreSettings(existed);
    _provisioningStatus = "error:storage"; // putSettings set the error
    return false;
  }
  // Credentials last: they end the provisioning window on the next boot.
  if (!_wifiManager->storeCredentials(wifi)) {
    restoreSettings(existed);
    return rejectProvisioning("error:storage", _wifiManager->getLastError());
  }
  _location = location;
  memcpy(_label, label, strlen(label) + 1);                // isValidLabel checked it fits
  memcpy(_mqttHost, server.host, strlen(server.host) + 1); // isValidHost checked it fits
  _mqttPort = server.port;
  _interval = interval;

  _arduino->log("CertificateManager: Provisioning saved");
  _provisioningStatus = "ok";
  return true;
}

// Writes every setting; false, with the error set, at the first that fails.
bool CertificateManager::putSettings(const Location &location, const char *label, const MqttServer &server,
                                     uint32_t interval) {
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
void CertificateManager::restoreSettings(const bool (&existed)[SETTING_COUNT]) {
  static_assert(sizeof(SETTING_KEYS) / sizeof(SETTING_KEYS[0]) == SETTING_COUNT,
                "SETTING_COUNT must match SETTING_KEYS");
  char error[sizeof(_lastError)];
  memcpy(error, _lastError, sizeof(error)); // Keep the failure that caused this, not a restore's
  if (!putSettings(_location, _label, getMqttServer(), _interval)) {
    _arduino->log("CertificateManager: Could not restore every setting in NVS");
  }
  for (size_t i = 0; i < SETTING_COUNT; i++) {
    if (!existed[i]) {
      _prefs.remove(SETTING_KEYS[i]);
    }
  }
  memcpy(_lastError, error, sizeof(error));
}

bool CertificateManager::rejectProvisioning(const char *status, const char *error) {
  _provisioningStatus = status;
  setError(error);
  return false;
}

// The backend drops a whole reading whose label isn't well-formed UTF-8 or has
// control characters (labels reach email subjects), so reject it up front.
bool CertificateManager::isValidLabel(const char *label) {
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
bool CertificateManager::isValidHost(const char *host) {
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

void CertificateManager::setError(const char *error) {
  strncpy(_lastError, error, sizeof(_lastError) - 1);
  _lastError[sizeof(_lastError) - 1] = '\0';
  _arduino->logf("CertificateManager: ERROR - %s", _lastError);
}

void CertificateManager::clearClientCredentials() {
  free(_clientCert);
  free(_clientKey);
  _clientCert = nullptr;
  _clientKey = nullptr;
}

void CertificateManager::clearCACertificate() {
  free(_caCert);
  _caCert = nullptr;
}
