export interface WeatherLocation {
  key: string;
  name: string;
  latitude: number;
  longitude: number;
}

export interface WeatherHour {
  time: string;
  temperature: number;
  apparentTemperature: number;
  precipitationProbability: number;
  weatherCode: number;
  windSpeed: number;
}

export interface WeatherDay {
  date: string;
  weatherCode: number;
  temperatureMax: number;
  temperatureMin: number;
  precipitationProbabilityMax: number;
  sunrise: string;
  sunset: string;
}

export interface WeatherForecast {
  location: WeatherLocation;
  timezone: string;
  hours: WeatherHour[];
  days: WeatherDay[];
  fetchedAt: string | null;
  lastAttemptAt: string;
  errorMessage: string | null;
  stale: boolean;
}
