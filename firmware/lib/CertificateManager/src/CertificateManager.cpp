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

CertificateManager::CertificateManager(Preferences &prefs, IArduino *arduino)
    : _provisioningStatus("idle"), _passkey(0), _latitude(0.0f), _longitude(0.0f), _prefs(prefs), _arduino(arduino),
      _wifiManager(nullptr), _clientCert(nullptr), _clientKey(nullptr), _caCert(nullptr) {
  _lastError[0] = '\0';
  _cn[0] = '\0';
  _label[0] = '\0';
}

CertificateManager::~CertificateManager() {
  clearClientCredentials();
  clearCACertificate();
}

bool CertificateManager::begin() {
  _arduino->log("CertificateManager: Initializing...");

  // Initialize NVS
  if (!_prefs.begin("tarameteo_certs", false)) {
    setError("Failed to initialize NVS");
    return false;
  }

  if (!loadFromNVS()) {
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

bool CertificateManager::loadFromNVS() {
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
  _latitude = _prefs.getFloat("latitude", 0.0f);
  _longitude = _prefs.getFloat("longitude", 0.0f);
  _label[0] = '\0';
  if (_prefs.isKey("label")) {
    _prefs.getString("label", _label, sizeof(_label));
  }

  _arduino->logf("CertificateManager: Loaded identity, lat=%.6f, lon=%.6f, label=%s", _latitude, _longitude, _label);

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

// Format and CN only: expiry is the broker's call, and board certs never
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
bool CertificateManager::applyProvisioning(const char *wifiSsid, const char *wifiPassword, float latitude,
                                           float longitude, const char *label) {
  if (!WiFiManager::isValidSsid(wifiSsid)) {
    return rejectProvisioning("error:ssid", "Invalid WiFi SSID: 1 to 32 bytes");
  }
  if (!WiFiManager::isValidPassword(wifiPassword)) {
    return rejectProvisioning("error:password", "Invalid WiFi password: 1 to 64 bytes");
  }
  // Written so NaN fails too
  if (!(latitude >= -90.0f && latitude <= 90.0f)) {
    return rejectProvisioning("error:location", "Invalid latitude: must be between -90 and 90");
  }
  if (!(longitude >= -180.0f && longitude <= 180.0f)) {
    return rejectProvisioning("error:location", "Invalid longitude: must be between -180 and 180");
  }
  if (!isValidLabel(label)) {
    return rejectProvisioning("error:label", "Invalid label: at most 32 bytes of UTF-8, no control characters");
  }
  if (!_wifiManager) {
    return rejectProvisioning("error:wifi", "WiFi manager not available");
  }

  // Join before saving anything, so a typo in the password can't lock the board out.
  if (!_wifiManager->tryConnect(wifiSsid, wifiPassword)) {
    return rejectProvisioning("error:wifi", _wifiManager->getLastError());
  }

  // Store location and label in NVS; put* returns 0 bytes written on failure.
  // NOTE: putString also returns 0 for an empty label, so that write can't be
  // checked; a failed clear keeps the previous label until reprovisioning.
  if (_prefs.putFloat("latitude", latitude) == 0 || _prefs.putFloat("longitude", longitude) == 0) {
    return rejectProvisioning("error:storage", "Failed to store location in NVS");
  }
  if (_prefs.putString("label", label) == 0 && label[0] != '\0') {
    return rejectProvisioning("error:storage", "Failed to store label in NVS");
  }
  // Credentials last: they end the provisioning window on the next boot.
  if (!_wifiManager->storeCredentials(wifiSsid, wifiPassword)) {
    return rejectProvisioning("error:storage", _wifiManager->getLastError());
  }
  _latitude = latitude;
  _longitude = longitude;
  memcpy(_label, label, strlen(label) + 1); // isValidLabel checked it fits

  _arduino->log("CertificateManager: Provisioning saved");
  _provisioningStatus = "ok";
  return true;
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
