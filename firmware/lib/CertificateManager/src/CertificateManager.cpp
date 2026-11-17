#include "CertificateManager.h"
#include "X509Parser.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef UNIT_TEST
#include "Arduino.h"
// Forward declaration for unit tests
class WiFiManager;
#else
#include "WiFiManager.h"
#endif

CertificateManager::CertificateManager(Preferences &prefs, IArduino *arduino)
    : _passkey(0), _latitude(0.0f), _longitude(0.0f), _prefs(prefs), _arduino(arduino), _wifiManager(nullptr),
      _clientCert(nullptr), _clientKey(nullptr), _caCert(nullptr) {
  _lastError[0] = '\0';
  _cn[0] = '\0';
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

  _arduino->logf("CertificateManager: Loaded identity, lat=%.6f, lon=%.6f", _latitude, _longitude);

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

// Validates and persists what the BLE transport received. On failure sets
// _lastError and returns false.
bool CertificateManager::applyProvisioning(const char *wifiSsid, const char *wifiPassword, float latitude,
                                           float longitude) {
  if (!wifiSsid || !wifiPassword || strlen(wifiSsid) == 0 || strlen(wifiPassword) == 0) {
    setError("WiFi SSID and password must not be empty");
    return false;
  }
  if (latitude < -90.0f || latitude > 90.0f) {
    setError("Invalid latitude: must be between -90 and 90");
    return false;
  }
  if (longitude < -180.0f || longitude > 180.0f) {
    setError("Invalid longitude: must be between -180 and 180");
    return false;
  }

  // Store location in NVS
  _latitude = latitude;
  _longitude = longitude;
  _prefs.putFloat("latitude", _latitude);
  _prefs.putFloat("longitude", _longitude);

#ifndef UNIT_TEST
  if (!_wifiManager || !_wifiManager->storeCredentials(wifiSsid, wifiPassword)) {
    setError("Failed to store WiFi credentials");
    return false;
  }
  _arduino->log("CertificateManager: WiFi credentials stored successfully");
#else
  if (!_wifiManager) {
    setError("WiFi manager not available");
    return false;
  }
  _arduino->log("CertificateManager: WiFi credentials stored successfully (mock)");
#endif

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
