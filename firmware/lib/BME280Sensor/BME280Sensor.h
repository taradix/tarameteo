/*
 * BME280Sensor.h
 * Wrapper library for the BME280 sensor using Adafruit's BME280 library
 */

#ifndef BME280_SENSOR_H
#define BME280_SENSOR_H

#include <Wire.h>
#include <Adafruit_BME280.h>

class BME280Sensor {
public:
    static constexpr uint8_t DEFAULT_ADDRESS = 0x77;
    static constexpr int8_t DEFAULT_SDA = 6;
    static constexpr int8_t DEFAULT_SCL = 7;

    // Constructor takes I2C configuration and sea level pressure
    BME280Sensor(uint8_t address = DEFAULT_ADDRESS,
                 int8_t sda = DEFAULT_SDA,
                 int8_t scl = DEFAULT_SCL,
                 float seaLevelPressure = 1013.25f);

    bool begin();
    float getTemperature() const;
    float getPressure() const;
    float getHumidity() const;
    float getAltitude() const;
    const char* getLastError() const { return _lastError; }

private:
    Adafruit_BME280 _bme;
    uint8_t _address;
    int8_t _sda;
    int8_t _scl;
    float _seaLevelPressure;
    bool _available;
    mutable char _lastError[128];  // Allow modification in const methods

    void setError(const char* error) const;
    void configureSensor();
};

#endif // BME280_SENSOR_H
