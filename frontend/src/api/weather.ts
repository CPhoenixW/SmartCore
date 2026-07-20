import { apiRequest } from "./client";
import type { WeatherForecast } from "@/types/weather";

export const weatherApi = {
  latest: () => apiRequest<WeatherForecast | null>("/api/weather"),
};
