#include "WiFiManager.h"

#ifdef UNIT_TEST
#include "Arduino.h"
#include "WiFi.h"
#else
#include <Arduino.h>
#include <WiFi.h>
#endif

WiFiManager::WiFiManager(int connectTimeoutMs) : _connectTimeoutMs(connectTimeoutMs) {
  _lastError[0] = '\0';
  _ssid[0] = '\0';
  _password[0] = '\0';
}

WiFiManager::~WiFiManager() { _prefs.end(); }

bool WiFiManager::begin() {
  if (!loadFromNVS()) {
    setError("No WiFi credentials found in NVS");
    return false; // Don't set WiFi mode yet - might need provisioning
  }

  WiFi.mode(WIFI_STA);
  return true;
}

bool WiFiManager::connect() { return isConnected() || attemptConnection(_ssid, _password); }

bool WiFiManager::tryConnect(const char *ssid, const char *password) {
  WiFi.mode(WIFI_STA); // begin() skips it on a board with no credentials yet
  return attemptConnection(ssid, password);
}

bool WiFiManager::reconnect() {
  // Try to reconnect with exponential backoff
  for (int attempt = 0; attempt < MAX_RECONNECT_ATTEMPTS; attempt++) {
    if (isConnected() || attemptConnection(_ssid, _password)) {
      return true;
    }

    if (attempt < MAX_RECONNECT_ATTEMPTS - 1) {
      delay(RECONNECT_DELAY_MS * (1 << attempt)); // Exponential backoff
    }
  }

  snprintf(_lastError, sizeof(_lastError), "Failed to reconnect after %d attempts", MAX_RECONNECT_ATTEMPTS);
  return false;
}

bool WiFiManager::attemptConnection(const char *ssid, const char *password) {
  WiFi.disconnect();
  delay(100); // Short delay to ensure disconnect

  WiFi.begin(ssid, password);

  // Wait for connection with timeout
  unsigned long startTime = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - startTime > (unsigned long)_connectTimeoutMs) {
      setError("Connection timeout");
      return false;
    }
    delay(100);
  }

  // WL_CONNECTED means association succeeded but DHCP may still be in flight.
  // Wait until the stack has assigned a non-zero local IP before returning.
  while (WiFi.localIP() == IPAddress(0, 0, 0, 0)) {
    if (millis() - startTime > (unsigned long)_connectTimeoutMs) {
      setError("DHCP timeout");
      return false;
    }
    delay(100);
  }

  return true;
}

bool WiFiManager::isConnected() const { return WiFi.status() == WL_CONNECTED; }

int WiFiManager::getRSSI() const { return WiFi.RSSI(); }

const char *WiFiManager::getIP() const {
  static char ipStr[16];
  IPAddress ip = WiFi.localIP();
  snprintf(ipStr, sizeof(ipStr), "%d.%d.%d.%d", ip[0], ip[1], ip[2], ip[3]);
  return ipStr;
}

void WiFiManager::setError(const char *error) {
  strncpy(_lastError, error, sizeof(_lastError) - 1);
  _lastError[sizeof(_lastError) - 1] = '\0';
}

bool WiFiManager::isProvisioned() const { return (strlen(_ssid) > 0); }

bool WiFiManager::needsProvisioning() const { return !isProvisioned(); }

bool WiFiManager::loadFromNVS() {
  if (!_prefs.begin("tarameteo_wifi", true)) { // Read-only mode
    return false;
  }

  size_t ssidLen = _prefs.getString("ssid", _ssid, sizeof(_ssid));
  size_t passLen = _prefs.getString("password", _password, sizeof(_password));

  _prefs.end();

  if (ssidLen == 0 || passLen == 0) {
    _ssid[0] = '\0';
    _password[0] = '\0';
    return false;
  }

  Serial.printf("WiFiManager: Loaded WiFi credentials from NVS (SSID: %s)\n", _ssid);
  return true;
}

bool WiFiManager::saveToNVS() {
  if (!_prefs.begin("tarameteo_wifi", false)) { // Read-write mode
    setError("Failed to open NVS for writing");
    return false;
  }

  if (_prefs.putString("ssid", _ssid) == 0) {
    _prefs.end();
    setError("Failed to save SSID to NVS");
    return false;
  }

  if (_prefs.putString("password", _password) == 0) {
    _prefs.end();
    setError("Failed to save password to NVS");
    return false;
  }

  _prefs.end();
  Serial.printf("WiFiManager: Saved WiFi credentials to NVS (SSID: %s)\n", _ssid);
  return true;
}

bool WiFiManager::isValidSsid(const char *ssid) {
  return ssid && ssid[0] != '\0' && strlen(ssid) <= MAX_SSID_BYTES;
}

bool WiFiManager::isValidPassword(const char *password) {
  return password && password[0] != '\0' && strlen(password) <= MAX_PASSWORD_BYTES;
}

bool WiFiManager::storeCredentials(const char *ssid, const char *password) {
  // Guards the buffers below; applyProvisioning has already checked both.
  if (!isValidSsid(ssid) || !isValidPassword(password)) {
    setError("Invalid WiFi credentials");
    return false;
  }

  memcpy(_ssid, ssid, strlen(ssid) + 1);
  memcpy(_password, password, strlen(password) + 1);

  return saveToNVS();
}
