"""Weather data."""

from datetime import datetime

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


class WeatherDataRequest(BaseModel):
    """Weather data model for API requests."""

    timestamp: datetime | int = Field(..., description="Timestamp of the measurement (datetime or Unix timestamp)")
    temperature: float = Field(..., description="Temperature in Celsius")
    humidity: float = Field(..., description="Relative humidity in percent")
    pressure: float = Field(..., description="Atmospheric pressure in hPa")
    altitude: float | None = Field(None, description="Altitude in meters")
    rssi: int | None = Field(None, description="WiFi signal strength in dBm")
    retry_count: int | None = Field(None, description="Number of retry attempts")

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        """Convert Unix timestamp to datetime if needed."""
        if isinstance(v, int):
            return datetime.fromtimestamp(v)
        return v

    def __str__(self):
        return (
            f"{self.timestamp} - "
            f"T: {self.temperature}°C, "
            f"H: {self.humidity}%, "
            f"P: {self.pressure} hPa, "
            f"Alt: {self.altitude}m, "
            f"RSSI: {self.rssi} dBm, "
            f"Retry: {self.retry_count}"
        )
