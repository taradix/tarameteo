#include "CertificateManager.h"
#include "X509Parser.h"

#include <ArduinoJson.h>
#include <stdio.h>
#include <string.h>

#ifdef UNIT_TEST
#include "Arduino.h"
// Forward declaration for unit tests
class WiFiManager;
#else
#include "WiFiManager.h"
#endif

static const int SECONDS_PER_DAY = 24 * 60 * 60;

CertificateManager::CertificateManager(Preferences &prefs, IWiFi *wifi, IArduino *arduino)
    : _prefs(prefs), _wifi(wifi), _arduino(arduino), _expiresAt(0), _certVersion(0), _provisioningActive(false),
      _provisioningStartTime(0), _provisioningServer(nullptr), _wifiManager(nullptr), _clientCert(nullptr),
      _clientKey(nullptr), _caCert(nullptr), _latitude(0.0f), _longitude(0.0f) {
  _lastError[0] = '\0';
  _cn[0] = '\0';
}

CertificateManager::~CertificateManager() {
  stopProvisioningMode();
  if (_clientCert)
    free(_clientCert);
  if (_clientKey)
    free(_clientKey);
  if (_caCert)
    free(_caCert);
}

bool CertificateManager::begin() {
  _arduino->log("CertificateManager: Initializing...");

  // Initialize NVS
  if (!_prefs.begin("tarameteo_certs", false)) {
    setError("Failed to initialize NVS");
    return false;
  }

  // Try to load existing certificates
  if (loadFromNVS()) {
    _arduino->log("CertificateManager: Certificates loaded from NVS");

    // Validate loaded certificates
    if (validateCertificates()) {
      _arduino->log("CertificateManager: Certificates validated successfully");
      return true;
    } else {
      _arduino->log("CertificateManager: Certificate validation failed");
      // Don't return false - allow provisioning to proceed
    }
  }

  // No certificates found or invalid - will need provisioning
  // But don't start it here - let the main code handle it
  if (needsProvisioning()) {
    _arduino->log("CertificateManager: Certificates not found - provisioning needed");
    return false;
  }

  return true;
}

bool CertificateManager::isProvisioned() const { return (_clientCert != nullptr && _clientKey != nullptr); }

bool CertificateManager::needsProvisioning() const { return !isProvisioned(); }

bool CertificateManager::loadFromNVS() {
  if (!_prefs.isKey("cli_cert") || !_prefs.isKey("cli_key")) {
    setError("Certificates not found in NVS");
    return false;
  }

  _clientCert = (char *)malloc(MAX_CERT_SIZE);
  _clientKey = (char *)malloc(MAX_KEY_SIZE);
  if (!_clientCert || !_clientKey) {
    setError("Failed to allocate memory for certificates");
    return false;
  }

  size_t certLen = _prefs.getString("cli_cert", _clientCert, MAX_CERT_SIZE);
  if (certLen == 0) {
    setError("Failed to read client certificate from NVS");
    return false;
  }

  size_t keyLen = _prefs.getString("cli_key", _clientKey, MAX_KEY_SIZE);
  if (keyLen == 0) {
    setError("Failed to read client key from NVS");
    return false;
  }

  if (_prefs.isKey("ca_cert")) {
    _caCert = (char *)malloc(MAX_CERT_SIZE);
    if (_caCert) {
      size_t caLen = _prefs.getString("ca_cert", _caCert, MAX_CERT_SIZE);
      if (caLen == 0) {
        free(_caCert);
        _caCert = nullptr;
      }
    }
  }

  _prefs.getString("cert_cn", _cn, MAX_CN_LENGTH);
  _expiresAt = _prefs.getULong("cert_expires", 0);
  _certVersion = _prefs.getInt("cert_version", 0);
  _latitude = _prefs.getFloat("latitude", 0.0f);
  _longitude = _prefs.getFloat("longitude", 0.0f);

  _arduino->logf("CertificateManager: Loaded cert CN=%s, expires=%lu, version=%d, lat=%.6f, lon=%.6f",
                 _cn, _expiresAt, _certVersion, _latitude, _longitude);

  return true;
}

bool CertificateManager::saveToNVS(const char *certPem, const char *keyPem, const char *caCertPem) {
  _arduino->log("CertificateManager: Saving certificates to NVS");

  if (_prefs.putString("cli_cert", certPem) == 0) {
    setError("Failed to save client certificate");
    return false;
  }

  if (_prefs.putString("cli_key", keyPem) == 0) {
    setError("Failed to save client key");
    return false;
  }

  if (caCertPem && strlen(caCertPem) > 0) {
    _prefs.putString("ca_cert", caCertPem);
  }

  _prefs.putString("cert_cn", _cn);
  _prefs.putULong("cert_expires", _expiresAt);
  _prefs.putInt("cert_version", _certVersion);
  _prefs.putFloat("latitude", _latitude);
  _prefs.putFloat("longitude", _longitude);

  _arduino->log("CertificateManager: Certificates saved successfully");
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
    client.setInsecure();
    _arduino->log("CertificateManager: WARNING - No CA cert, skipping server certificate verification");
  }

  client.setCertificate(_clientCert);
  client.setPrivateKey(_clientKey);

  _arduino->logf("CertificateManager: Client certificate loaded (CN=%s)", _cn);
  return true;
}

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

  if (!extractExpirationFromCert(_clientCert)) {
    _arduino->log("CertificateManager: WARNING - Failed to extract expiration date");
  } else {
    // Check if certificate is expired or expiring soon
    unsigned long now = _arduino->millis() / 1000; // Current time in seconds (approximation)
    if (_expiresAt > 0 && _expiresAt < now) {
      setError("Certificate has expired");
      return false;
    } else if (_expiresAt > 0 && (_expiresAt - now) < (CERT_EXPIRY_WARNING_DAYS * SECONDS_PER_DAY)) {
      unsigned long daysLeft = (_expiresAt - now) / SECONDS_PER_DAY;
      _arduino->logf("CertificateManager: WARNING - Certificate expires in %lu days", daysLeft);
    }
  }

  #ifdef DEBUG_CERTS
  char certInfo[1024];
  if (X509Parser::getCertificateInfo(_clientCert, certInfo, sizeof(certInfo))) {
    _arduino->log("Certificate details:");
    _arduino->log(certInfo);
  }
  #endif

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

bool CertificateManager::extractExpirationFromCert(const char *certPem) {
  bool result = X509Parser::extractExpiration(certPem, &_expiresAt);

  if (!result) {
    _arduino->log("CertificateManager: WARNING - Failed to extract expiration date");
    // Set a default (10 years from now) as fallback
    _expiresAt = (_arduino->millis() / 1000) + (3650UL * 86400UL);
    return false;
  }

  // Log expiration date for debugging
  unsigned long now = _arduino->millis() / 1000;
  long daysUntilExpiry = (_expiresAt - now) / 86400;
  _arduino->logf("CertificateManager: Certificate expires in %ld days", daysUntilExpiry);

  return true;
}

bool CertificateManager::validateCertKeyPair(const char *certPem, const char *keyPem) {
  // First validate PEM format
  if (!validateCertificateFormat(certPem)) {
    _arduino->log("CertificateManager: Invalid certificate format");
    return false;
  }

  if (!validatePrivateKeyFormat(keyPem)) {
    _arduino->log("CertificateManager: Invalid private key format");
    return false;
  }

  // Then verify cryptographic match
  _arduino->log("CertificateManager: Validating certificate/key pair...");
  bool result = X509Parser::validateKeyPair(certPem, keyPem);

  if (!result) {
    _arduino->log("CertificateManager: ERROR - Certificate and private key do not match!");
    return false;
  }

  _arduino->log("CertificateManager: Certificate/key pair validated successfully");
  return true;
}

void CertificateManager::logCertificateInfo(const char* certPem) {
  char info[512];
  if (X509Parser::getCertificateInfo(certPem, info, sizeof(info))) {
    _arduino->log("Certificate Information:");
    _arduino->log(info);
  }
}

bool CertificateManager::storeCertificates(const char *certPem, const char *keyPem, const char *caCertPem) {
  _arduino->log("CertificateManager: Storing certificates");

  // Validate formats
  if (!validateCertificateFormat(certPem)) {
    setError("Invalid certificate format");
    return false;
  }

  if (!validatePrivateKeyFormat(keyPem)) {
    setError("Invalid private key format");
    return false;
  }

  if (!validateCertKeyPair(certPem, keyPem)) {
    setError("Certificate and key do not match");
    return false;
  }

  #ifdef DEBUG_CERTIFICATES
  logCertificateInfo(certPem);
  #endif

  // Allocate and store in memory
  if (_clientCert)
    free(_clientCert);
  if (_clientKey)
    free(_clientKey);
  if (_caCert)
    free(_caCert);

  _clientCert = (char *)malloc(strlen(certPem) + 1);
  _clientKey = (char *)malloc(strlen(keyPem) + 1);

  if (!_clientCert || !_clientKey) {
    setError("Failed to allocate memory");
    return false;
  }

  strcpy(_clientCert, certPem);
  strcpy(_clientKey, keyPem);

  if (caCertPem && strlen(caCertPem) > 0) {
    _caCert = (char *)malloc(strlen(caCertPem) + 1);
    if (_caCert) {
      strcpy(_caCert, caCertPem);
    }
  } else {
    _caCert = nullptr;
  }

  // Extract CN and set metadata
  if (!extractCNFromCert(certPem)) {
    setError("Failed to extract CN from certificate");
    return false;
  }

  if (X509Parser::extractSerial(certPem, _serialNumber, sizeof(_serialNumber))) {
    _arduino->logf("Certificate serial: %s", _serialNumber);
  }

  extractExpirationFromCert(certPem);
  _certVersion++;

  // Save to NVS
  if (!saveToNVS(certPem, keyPem, caCertPem)) {
    return false;
  }

  _arduino->log("CertificateManager: Certificates stored successfully");
  return true;
}

bool CertificateManager::clearCertificates() {
  _arduino->log("CertificateManager: Clearing certificates");

  _prefs.clear();

  if (_clientCert) {
    free(_clientCert);
    _clientCert = nullptr;
  }
  if (_clientKey) {
    free(_clientKey);
    _clientKey = nullptr;
  }
  if (_caCert) {
    free(_caCert);
    _caCert = nullptr;
  }

  _cn[0] = '\0';
  _expiresAt = 0;
  _certVersion = 0;
  _latitude = 0.0f;
  _longitude = 0.0f;

  return true;
}

bool CertificateManager::startProvisioningMode(IWebServer *webServer) {
  _arduino->log("CertificateManager: Starting provisioning mode");

  if (!webServer) {
    setError("Web server not provided");
    return false;
  }

  _provisioningServer = webServer;

  // Disconnect any existing WiFi connections
  _wifi->disconnect();
  _arduino->delay(100);

  // Start WiFi in AP mode with explicit IP configuration
  char macStr[64];
  snprintf(macStr, sizeof(macStr), "TaraMeteoProv-%s", getLastMACOctet());

  _wifi->mode(2); // WIFI_AP

  // Configure AP with explicit IP address
  // Note: IPAddress is provided by Arduino.h in ESP32 builds
  // In unit tests, it's provided by test/mocks/Arduino.h
  IPAddress local_IP(192, 168, 4, 1);
  IPAddress gateway(192, 168, 4, 1);
  IPAddress subnet(255, 255, 255, 0);

  if (!_wifi->softAPConfig(local_IP, gateway, subnet)) {
    _arduino->log("CertificateManager: Failed to configure AP IP");
    setError("Failed to configure AP");
    return false;
  }

  if (!_wifi->softAP(macStr)) {
    _arduino->log("CertificateManager: Failed to start AP");
    setError("Failed to start AP");
    return false;
  }

  _arduino->delay(500); // Give AP time to start

  auto IP = _wifi->softAPIP();
  _arduino->log("===========================================");
  _arduino->logf("AP SSID: %s", macStr);
  // Note: IP.toString() might not work with mocks, so we format manually
  _arduino->log("AP IP: 192.168.4.1");
  _arduino->log("AP Password: (none - open network)");
  _arduino->log("Visit: http://192.168.4.1");
  _arduino->log("===========================================");

  setupProvisioningServer();

  _provisioningActive = true;
  _provisioningStartTime = _arduino->millis();

  _arduino->log("CertificateManager: HTTP server started and ready for requests");
  return true;
}

void CertificateManager::stopProvisioningMode() {
  if (_provisioningServer) {
    _provisioningServer->stop();
    _provisioningServer = nullptr;
  }
  _provisioningActive = false;
  _arduino->log("CertificateManager: Provisioning mode stopped");
}

void CertificateManager::handleProvisioningLoop() {
  if (_provisioningServer && _provisioningActive) {
    _provisioningServer->handleClient();

    // Check for timeout every 30 seconds
    static unsigned long lastCheck = 0;
    unsigned long now = _arduino->millis();
    if (now - lastCheck > 30000) {
      unsigned long elapsed = (now - _provisioningStartTime) / 1000;
      _arduino->logf("Provisioning active for %lu seconds, waiting for connection...", elapsed);

      // Show number of connected clients
      int clients = _wifi->softAPgetStationNum();
      _arduino->logf("Connected clients to AP: %d", clients);

      lastCheck = now;
    }
  }
}

void CertificateManager::setupProvisioningServer() {
  _provisioningServer->on("/", [this]() {
    _arduino->log("CertificateManager: Received GET request for /");
    handleRootRequest();
  });

  _provisioningServer->onPost("/provision", [this]() {
    _arduino->log("CertificateManager: Received POST request for /provision");
    handleProvisionRequest();
  });

  _provisioningServer->onNotFound([this]() {
    _arduino->logf("CertificateManager: 404 - Not found: %s", _provisioningServer->uri());
    _provisioningServer->send(404, "text/plain", "Not found");
  });

  _provisioningServer->begin();
  _arduino->log("CertificateManager: HTTP server started on port 80");
}

void CertificateManager::handleRootRequest() {
  const char *html = R"html(
<!DOCTYPE html>
<html>
<head>
    <title>TaraMeteo Certificate Provisioning</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial; margin: 40px; background: #f0f0f0; }
        .container { background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto; }
        h1 { color: #2196F3; }
        textarea { width: 100%; height: 150px; margin: 10px 0; font-family: monospace; }
        button { background: #2196F3; color: white; padding: 15px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { background: #0b7dda; }
        .info { background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>TaraMeteo Provisioning</h1>
        <div class="info">
            <strong>Flash Once, Provision Many</strong><br>
            <p>Provision both WiFi credentials and mTLS certificates through this interface.
            The sensor name will be derived from the certificate CN.</p>
        </div>
        <form method="POST" action="/provision">
            <h2>WiFi Configuration</h2>
            <label><strong>WiFi SSID:</strong></label>
            <input type="text" name="wifi_ssid" placeholder="your-wifi-network" style="width: 100%; padding: 10px; margin: 10px 0; font-size: 14px;">

            <label><strong>WiFi Password:</strong></label>
            <input type="password" name="wifi_password" placeholder="your-wifi-password" style="width: 100%; padding: 10px; margin: 10px 0; font-size: 14px;">

            <h2>Location</h2>
            <label><strong>Latitude:</strong></label>
            <input type="number" name="latitude" required step="0.000001" min="-90" max="90" placeholder="45.504" style="width: 100%; padding: 10px; margin: 10px 0; font-size: 14px;">

            <label><strong>Longitude:</strong></label>
            <input type="number" name="longitude" required step="0.000001" min="-180" max="180" placeholder="-73.617" style="width: 100%; padding: 10px; margin: 10px 0; font-size: 14px;">

            <h2>mTLS Certificates</h2>
            <label><strong>Client Certificate (PEM):</strong></label>
            <textarea name="cert" required placeholder="-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----"></textarea>

            <label><strong>Private Key (PEM):</strong></label>
            <textarea name="key" required placeholder="-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----"></textarea>

            <label><strong>CA Certificate (PEM, optional):</strong></label>
            <textarea name="ca_cert" placeholder="-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----"></textarea>

            <button type="submit">Provision Device</button>
        </form>
    </div>
</body>
</html>
)html";

  _provisioningServer->send(200, "text/html", html);
}

void CertificateManager::handleProvisionRequest() {
  _arduino->log("CertificateManager: Received provisioning request");

  // Check if we have the required fields
  if (!_provisioningServer->hasArg("cert") || !_provisioningServer->hasArg("key")) {
    sendResponse(400, "Missing required fields: cert and key");
    return;
  }

  if (!_provisioningServer->hasArg("latitude") || !_provisioningServer->hasArg("longitude")) {
    sendResponse(400, "Missing required fields: latitude and longitude");
    return;
  }

  float latitude = atof(_provisioningServer->arg("latitude"));
  float longitude = atof(_provisioningServer->arg("longitude"));

  if (latitude < -90.0f || latitude > 90.0f) {
    sendResponse(400, "Invalid latitude: must be between -90 and 90");
    return;
  }
  if (longitude < -180.0f || longitude > 180.0f) {
    sendResponse(400, "Invalid longitude: must be between -180 and 180");
    return;
  }

  _latitude = latitude;
  _longitude = longitude;

  const char *cert = _provisioningServer->arg("cert");
  const char *key = _provisioningServer->arg("key");
  const char *caCert = _provisioningServer->arg("ca_cert");

  // Handle WiFi credentials if provided
  bool wifiProvisioned = false;
  if (_wifiManager && _provisioningServer->hasArg("wifi_ssid") && _provisioningServer->hasArg("wifi_password")) {
    const char *wifiSsid = _provisioningServer->arg("wifi_ssid");
    const char *wifiPassword = _provisioningServer->arg("wifi_password");

    if (strlen(wifiSsid) > 0 && strlen(wifiPassword) > 0) {
#ifndef UNIT_TEST
      if (_wifiManager->storeCredentials(wifiSsid, wifiPassword)) {
        _arduino->log("CertificateManager: WiFi credentials stored successfully");
        wifiProvisioned = true;
      } else {
        sendResponse(400, "Failed to store WiFi credentials");
        return;
      }
#else
      // In unit tests, just mark as provisioned
      _arduino->log("CertificateManager: WiFi credentials stored successfully (mock)");
      wifiProvisioned = true;
#endif
    }
  }

  // Validate and store certificates
  const char *caCertArg = (strlen(caCert) > 0) ? caCert : nullptr;
  if (storeCertificates(cert, key, caCertArg)) {
    char message[256];
    if (wifiProvisioned) {
      snprintf(message, sizeof(message),
               "Provisioned successfully! WiFi and certificates stored. Rebooting in 3 seconds...");
    } else {
      snprintf(message, sizeof(message), "Provisioned successfully! Certificates stored. Rebooting in 3 seconds...");
    }
    sendResponse(200, message);

    // Stop provisioning and reboot
    _arduino->delay(3000);
    stopProvisioningMode();
    _arduino->restart();
  } else {
    sendResponse(400, _lastError);
  }
}

void CertificateManager::sendResponse(int code, const char *message) {
  StaticJsonDocument<256> doc;
  doc["status"] = (code == 200) ? "success" : "error";
  doc["message"] = message;
  if (code == 200) {
    doc["cn"] = _cn;
  }

  char response[512];
  serializeJson(doc, response, sizeof(response));

  _provisioningServer->send(code, "application/json", response);
}

const char *CertificateManager::getLastMACOctet() {
  static char macStr[5];
  uint8_t mac[6];
  _wifi->macAddress(mac);
  snprintf(macStr, sizeof(macStr), "%02X%02X", mac[4], mac[5]);
  return macStr;
}

void CertificateManager::setError(const char *error) {
  strncpy(_lastError, error, sizeof(_lastError) - 1);
  _lastError[sizeof(_lastError) - 1] = '\0';
  _arduino->logf("CertificateManager: ERROR - %s", _lastError);
}
