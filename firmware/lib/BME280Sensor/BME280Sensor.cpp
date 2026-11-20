#include "BME280Sensor.h"
#include <I2CAddressList.h>
#include <cmath>

BME280Sensor::BME280Sensor(uint8_t address, int8_t sda, int8_t scl, float seaLevelPressure)
    : _address(address), _sda(sda), _scl(scl), _seaLevelPressure(seaLevelPressure), _available(false) {
  _lastError[0] = '\0';
}

bool BME280Sensor::begin() {
  Wire.begin(_sda, _scl);

  if (!_bme.begin(_address)) {
    uint8_t found[126];
    size_t count = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
      Wire.beginTransmission(addr);
      if (Wire.endTransmission() == 0) {
        found[count++] = addr;
      }
    }
    snprintf(_lastError, sizeof(_lastError), "Could not find BME280 at 0x%02X (SDA: %d, SCL: %d) — I2C devices found: ",
             _address, _sda, _scl);
    appendI2CAddresses(_lastError, sizeof(_lastError), found, count);
    return false;
  }

  configureSensor();
  _available = true;
  return true;
}

void BME280Sensor::configureSensor() {
  // Configure sensor for weather monitoring
  _bme.setSampling(Adafruit_BME280::MODE_NORMAL,     // Operating Mode
                   Adafruit_BME280::SAMPLING_X2,     // Temperature
                   Adafruit_BME280::SAMPLING_X16,    // Pressure
                   Adafruit_BME280::SAMPLING_X1,     // Humidity
                   Adafruit_BME280::FILTER_X16,      // Filtering
                   Adafruit_BME280::STANDBY_MS_500); // Standby time
}

float BME280Sensor::getTemperature() const {
  if (!_available) {
    setError("Sensor not available");
    return NAN;
  }
  return const_cast<Adafruit_BME280 &>(_bme).readTemperature();
}

float BME280Sensor::getPressure() const {
  if (!_available) {
    setError("Sensor not available");
    return NAN;
  }
  return const_cast<Adafruit_BME280 &>(_bme).readPressure() / 100.0f; // Convert Pa to hPa
}

float BME280Sensor::getHumidity() const {
  if (!_available) {
    setError("Sensor not available");
    return NAN;
  }
  return const_cast<Adafruit_BME280 &>(_bme).readHumidity();
}

float BME280Sensor::getAltitude() const {
  if (!_available) {
    setError("Sensor not available");
    return NAN;
  }
  return const_cast<Adafruit_BME280 &>(_bme).readAltitude(_seaLevelPressure);
}

void BME280Sensor::setError(const char *error) const {
  strncpy(_lastError, error, sizeof(_lastError) - 1);
  _lastError[sizeof(_lastError) - 1] = '\0';
}
