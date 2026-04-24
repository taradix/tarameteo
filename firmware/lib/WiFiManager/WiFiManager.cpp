#include "WiFiManager.h"

#ifdef UNIT_TEST
#include "Arduino.h"
#include "WiFi.h"
#else
#include <Arduino.h>
#include <WiFi.h>
#endif

WiFiManager::WiFiManager(const char *ssid, const char *password, int connectTimeoutMs) : _reconnectAttempts(0), _connectTimeoutMs(connectTimeoutMs) {
  _lastError[0] = '\0';
  _ssid[0] = '\0';
  _password[0] = '\0';

  // If credentials provided, use them (backward compatibility)
  if (ssid && password) {
    strncpy(_ssid, ssid, sizeof(_ssid) - 1);
    _ssid[sizeof(_ssid) - 1] = '\0';
    strncpy(_password, password, sizeof(_password) - 1);
    _password[sizeof(_password) - 1] = '\0';
    Serial.println("WiFiManager: Using credentials from constructor");
  }
  // Otherwise, they will be loaded from NVS in begin()
}

WiFiManager::~WiFiManager() { _prefs.end(); }

bool WiFiManager::begin() {
  // If no credentials were provided in constructor, try to load from NVS
  if (strlen(_ssid) == 0) {
    if (!loadFromNVS()) {
      updateLastError("No WiFi credentials found in NVS or constructor");
      return false; // Don't set WiFi mode yet - might need provisioning
    }
    Serial.println("WiFiManager: Loaded credentials from NVS");
  }

  // Only set to STA mode if we have credentials
  if (strlen(_ssid) > 0) {
    WiFi.mode(WIFI_STA);
  }

  return true;
}

bool WiFiManager::connect() { return attemptConnection(); }

bool WiFiManager::reconnect() {
  if (_reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    updateLastError("Maximum reconnection attempts reached");
    return false;
  }

  _reconnectAttempts++;

  // Try to reconnect with exponential backoff
  for (int attempt = 0; attempt < MAX_RECONNECT_ATTEMPTS; attempt++) {
    if (attemptConnection()) {
      _reconnectAttempts = 0; // Reset counter on successful connection
      return true;
    }

    if (attempt < MAX_RECONNECT_ATTEMPTS - 1) {
      delay(RECONNECT_DELAY_MS * (1 << attempt)); // Exponential backoff
    }
  }

  snprintf(_lastError, sizeof(_lastError), "Failed to reconnect after %d attempts", _reconnectAttempts);
  return false;
}

bool WiFiManager::attemptConnection() {
  if (WiFi.status() == WL_CONNECTED) {
    return true; // Already connected
  }

  WiFi.disconnect();
  delay(100); // Short delay to ensure disconnect

  WiFi.begin(_ssid, _password);

  // Wait for connection with timeout
  unsigned long startTime = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - startTime > (unsigned long)_connectTimeoutMs) {
      updateLastError("Connection timeout");
      return false;
    }
    delay(100);
  }

  // WL_CONNECTED means association succeeded but DHCP may still be in flight.
  // Wait until the stack has assigned a non-zero local IP before returning.
  while (WiFi.localIP() == IPAddress(0, 0, 0, 0)) {
    if (millis() - startTime > (unsigned long)_connectTimeoutMs) {
      updateLastError("DHCP timeout");
      return false;
    }
    delay(100);
  }

  return true;
}

void WiFiManager::disconnect() {
  WiFi.disconnect();
  _reconnectAttempts = 0;
}

bool WiFiManager::isConnected() const { return WiFi.status() == WL_CONNECTED; }

int WiFiManager::getRSSI() const { return WiFi.RSSI(); }

const char *WiFiManager::getIP() const {
  static char ipStr[16];
  IPAddress ip = WiFi.localIP();
  snprintf(ipStr, sizeof(ipStr), "%d.%d.%d.%d", ip[0], ip[1], ip[2], ip[3]);
  return ipStr;
}

void WiFiManager::updateLastError(const char *error) {
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
    updateLastError("Failed to open NVS for writing");
    return false;
  }

  if (_prefs.putString("ssid", _ssid) == 0) {
    _prefs.end();
    updateLastError("Failed to save SSID to NVS");
    return false;
  }

  if (_prefs.putString("password", _password) == 0) {
    _prefs.end();
    updateLastError("Failed to save password to NVS");
    return false;
  }

  _prefs.end();
  Serial.printf("WiFiManager: Saved WiFi credentials to NVS (SSID: %s)\n", _ssid);
  return true;
}

bool WiFiManager::storeCredentials(const char *ssid, const char *password) {
  if (!ssid || !password || strlen(ssid) == 0 || strlen(password) == 0) {
    updateLastError("Invalid WiFi credentials");
    return false;
  }

  strncpy(_ssid, ssid, sizeof(_ssid) - 1);
  _ssid[sizeof(_ssid) - 1] = '\0';
  strncpy(_password, password, sizeof(_password) - 1);
  _password[sizeof(_password) - 1] = '\0';

  return saveToNVS();
}

bool WiFiManager::clearCredentials() {
  if (!_prefs.begin("tarameteo_wifi", false)) {
    return false;
  }

  _prefs.clear();
  _prefs.end();

  _ssid[0] = '\0';
  _password[0] = '\0';

  Serial.println("WiFiManager: Cleared WiFi credentials from NVS");
  return true;
}