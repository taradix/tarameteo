#include "BME280Sensor.h"
#include <cmath>

BME280Sensor::BME280Sensor(uint8_t address, int8_t sda, int8_t scl, float seaLevelPressure)
    : _address(address), _sda(sda), _scl(scl), _seaLevelPressure(seaLevelPressure), _available(false) {
  _lastError[0] = '\0';
}

bool BME280Sensor::begin() {
  Wire.begin(_sda, _scl);

  if (!_bme.begin(_address)) {
    char found[64] = "none";
    char *p = found;
    bool any = false;
    for (uint8_t addr = 1; addr < 127; addr++) {
      Wire.beginTransmission(addr);
      if (Wire.endTransmission() == 0) {
        p += snprintf(p, found + sizeof(found) - p, any ? ", 0x%02X" : "0x%02X", addr);
        any = true;
      }
    }
    snprintf(_lastError, sizeof(_lastError),
             "Could not find BME280 at 0x%02X (SDA: %d, SCL: %d) — I2C devices found: %s",
             _address, _sda, _scl, found);
    return false;
  }

  if (!configureSensor()) {
    return false;
  }

  _available = true;
  return true;
}

bool BME280Sensor::configureSensor() {
  // Configure sensor for weather monitoring
  _bme.setSampling(Adafruit_BME280::MODE_NORMAL,     // Operating Mode
                   Adafruit_BME280::SAMPLING_X2,     // Temperature
                   Adafruit_BME280::SAMPLING_X16,    // Pressure
                   Adafruit_BME280::SAMPLING_X1,     // Humidity
                   Adafruit_BME280::FILTER_X16,      // Filtering
                   Adafruit_BME280::STANDBY_MS_500); // Standby time

  return true;
}

float BME280Sensor::getTemperature() const {
  if (!_available) {
    updateLastError("Sensor not available");
    return NAN;
  }
  return const_cast<Adafruit_BME280 &>(_bme).readTemperature();
}

float BME280Sensor::getPressure() const {
  if (!_available) {
    updateLastError("Sensor not available");
    return NAN;
  }
  return const_cast<Adafruit_BME280 &>(_bme).readPressure() / 100.0f; // Convert Pa to hPa
}

float BME280Sensor::getHumidity() const {
  if (!_available) {
    updateLastError("Sensor not available");
    return NAN;
  }
  return const_cast<Adafruit_BME280 &>(_bme).readHumidity();
}

float BME280Sensor::getAltitude() const {
  if (!_available) {
    updateLastError("Sensor not available");
    return NAN;
  }
  return const_cast<Adafruit_BME280 &>(_bme).readAltitude(_seaLevelPressure);
}

void BME280Sensor::updateLastError(const char *error) const {
  strncpy(_lastError, error, sizeof(_lastError) - 1);
  _lastError[sizeof(_lastError) - 1] = '\0';
}
