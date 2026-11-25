#include "WiFiManager.h"

#ifdef UNIT_TEST
#include "Arduino.h"
#include "WiFi.h"
#else
#include <Arduino.h>
#include <WiFi.h>
#endif

WiFiManager::WiFiManager(Preferences &prefs, int connectTimeoutMs)
    : _prefs(prefs), _connectTimeoutMs(connectTimeoutMs) {
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

bool WiFiManager::connect() { return isConnected() || attemptConnection({_ssid, _password}); }

bool WiFiManager::tryConnect(const WiFiCredentials &credentials) {
  WiFi.mode(WIFI_STA); // begin() skips it on a board with no credentials yet
  return attemptConnection(credentials);
}

bool WiFiManager::reconnect() {
  // Try to reconnect with exponential backoff
  for (int attempt = 0; attempt < MAX_RECONNECT_ATTEMPTS; attempt++) {
    if (isConnected() || attemptConnection({_ssid, _password})) {
      return true;
    }

    if (attempt < MAX_RECONNECT_ATTEMPTS - 1) {
      delay(RECONNECT_DELAY_MS * (1 << attempt)); // Exponential backoff
    }
  }

  snprintf(_lastError, sizeof(_lastError), "Failed to reconnect after %d attempts", MAX_RECONNECT_ATTEMPTS);
  return false;
}

bool WiFiManager::attemptConnection(const WiFiCredentials &credentials) {
  WiFi.disconnect();
  delay(100); // Short delay to ensure disconnect

  WiFi.begin(credentials.ssid, credentials.password);

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

// Writes both keys. When one fails, puts back the pair memory holds (the stored one),
// or removes both when there was none, so NVS never pairs one SSID with another's password.
bool WiFiManager::saveToNVS(const WiFiCredentials &credentials) {
  if (!_prefs.begin("tarameteo_wifi", false)) { // Read-write mode
    setError("Failed to open NVS for writing");
    return false;
  }

  const char *failure = nullptr;
  if (_prefs.putString("ssid", credentials.ssid) == 0) {
    failure = "Failed to save SSID to NVS";
  } else if (_prefs.putString("password", credentials.password) == 0) {
    failure = "Failed to save password to NVS";
  }
  if (failure != nullptr) {
    if (isProvisioned()) {
      _prefs.putString("ssid", _ssid);
      _prefs.putString("password", _password);
    } else {
      _prefs.remove("ssid");
      _prefs.remove("password");
    }
    _prefs.end();
    setError(failure);
    return false;
  }

  _prefs.end();
  Serial.printf("WiFiManager: Saved WiFi credentials to NVS (SSID: %s)\n", credentials.ssid);
  return true;
}

bool WiFiManager::isValidSsid(const char *ssid) {
  return ssid && ssid[0] != '\0' && strlen(ssid) <= MAX_SSID_BYTES;
}

bool WiFiManager::isValidPassword(const char *password) {
  return password && password[0] != '\0' && strlen(password) <= MAX_PASSWORD_BYTES;
}

bool WiFiManager::storeCredentials(const WiFiCredentials &credentials) {
  // Guards the buffers below; applyProvisioning has already checked both.
  if (!isValidSsid(credentials.ssid) || !isValidPassword(credentials.password)) {
    setError("Invalid WiFi credentials");
    return false;
  }

  if (!saveToNVS(credentials)) {
    return false;
  }
  memcpy(_ssid, credentials.ssid, strlen(credentials.ssid) + 1);
  memcpy(_password, credentials.password, strlen(credentials.password) + 1);
  return true;
}

bool WiFiManager::clearCredentials() {
  // The namespace holds the pair alone, so clearing it all leaves nothing else out.
  if (!_prefs.begin("tarameteo_wifi", false) || !_prefs.clear()) {
    _prefs.end();
    setError("Failed to erase WiFi credentials from NVS");
    return false;
  }
  _prefs.end();
  _ssid[0] = '\0';
  _password[0] = '\0';
  return true;
}
