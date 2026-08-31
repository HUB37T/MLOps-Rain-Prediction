import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const currentPredictionResponse = {
  server_time: "2026-08-30T07:05:00Z",
  primary_location: {
    id: "filkom-ub",
    name: "FILKOM Universitas Brawijaya",
    requested_coordinate: { latitude: -7.9666, longitude: 112.6326 },
    resolved_grid: { latitude: -7.9666, longitude: 112.6326 },
  },
  status: "available",
  active_configuration: {
    decision_threshold: 0.5,
    risk_configuration_version: "risk-v1",
  },
  prediction: {
    prediction_record_id: "pred-2026-08-30T07:00:00Z",
    official_prediction_time: "2026-08-30T07:00:00Z",
    actual_generation_time: "2026-08-30T07:05:00Z",
    prediction_horizon: {
      start: "2026-08-30T08:00:00Z",
      end: "2026-08-30T11:00:00Z",
    },
    rain_probability: 0.499,
    predicted_class: "no_rain",
    decision_threshold: 0.5,
    near_threshold: true,
    risk_level: "moderate",
    risk_boundaries: { low_to_moderate: 0.3, moderate_to_high: 0.7 },
    risk_configuration_version: "risk-v1",
    preparation_action: "Bawa perlindungan hujan dan periksa kesiapan lokasi cadangan.",
    preparation_copy_version: "prep-v1",
    feature_timestamp: "2026-08-30T07:00:00Z",
    data_freshness_seconds: 300,
    freshness_status: "fresh",
    model: {
      name: "baseline",
      version: "baseline-v1",
      status: "experimental",
      latest_validation_date: "2026-08-29",
    },
  },
  warnings: [],
};

type WeatherResponseFixture = {
  server_time: string;
  primary_location: { id: string; name: string };
  status: "complete" | "partial" | "unavailable";
  current_weather_timestamp: string;
  variables: Record<
    string,
    {
      value: number | null;
      unit: string;
      timestamp: string;
      freshness_status: string;
      status: string;
    }
  >;
  warnings: { code: string; message: string }[];
  provider: { name: string; attribution: string };
};

const currentWeatherResponse: WeatherResponseFixture = {
  server_time: "2026-08-30T07:05:00Z",
  primary_location: {
    id: "filkom-ub",
    name: "FILKOM Universitas Brawijaya",
  },
  status: "complete",
  current_weather_timestamp: "2026-08-30T07:00:00Z",
  variables: {
    temperature_2m: { value: 27.3, unit: "degC", timestamp: "2026-08-30T07:00:00Z", freshness_status: "fresh", status: "available" },
    relative_humidity_2m: { value: 82, unit: "percent", timestamp: "2026-08-30T07:00:00Z", freshness_status: "fresh", status: "available" },
    precipitation_1h: { value: 0.2, unit: "mm", timestamp: "2026-08-30T07:00:00Z", freshness_status: "fresh", status: "available" },
    cloud_cover: { value: 75, unit: "percent", timestamp: "2026-08-30T07:00:00Z", freshness_status: "fresh", status: "available" },
    wind_speed_10m: { value: 12, unit: "kmh", timestamp: "2026-08-30T07:00:00Z", freshness_status: "fresh", status: "available" },
    wind_direction_10m: { value: 90, unit: "degree", timestamp: "2026-08-30T07:00:00Z", freshness_status: "fresh", status: "available" },
    sea_level_pressure: { value: 1008, unit: "hPa", timestamp: "2026-08-30T07:00:00Z", freshness_status: "fresh", status: "available" },
  },
  warnings: [],
  provider: { name: "Open-Meteo", attribution: "Data cuaca disediakan oleh Open-Meteo." },
};

let weatherResponse = currentWeatherResponse;

describe("primary Rain Prediction card", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    weatherResponse = currentWeatherResponse;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const body = String(input).includes("/weather/current")
          ? weatherResponse
          : currentPredictionResponse;
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }),
    );
  });

  it("renders the decision information from the HTTP contract", async () => {
    render(<App />);

    expect(await screen.findByText("Peluang hujan dalam 3 jam ke depan")).toBeVisible();
    expect(screen.getByText("49,9%")).toBeVisible();
    expect(screen.getByText("Mendekati ambang keputusan")).toBeVisible();
    expect(screen.getByText("Hujan berarti akumulasi minimal 0,1 mm dalam tiga jam ke depan.")).toBeVisible();
    expect(screen.getByText("Prediksi model")).toBeVisible();
    expect(screen.getByText("Tidak hujan")).toBeVisible();
    expect(
      screen.getByText("Prediksi model memakai ambang keputusan; Tingkat persiapan mengikuti rentang peluang hujan."),
    ).toBeVisible();
    expect(screen.getByText("Tingkat persiapan").parentElement).toHaveTextContent("Sedang");
    expect(
      screen.getByText("Bawa perlindungan hujan dan periksa kesiapan lokasi cadangan."),
    ).toBeVisible();
    expect(screen.getByText("15:00-18:00 WIB")).toBeVisible();
    expect(screen.getByText("Model: baseline-v1")).toBeVisible();
  });

  it("renders the complete Current Weather section from its HTTP contract", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Cuaca saat ini" })).toBeVisible();
    expect(
      screen.getByText("Kondisi terbaru adalah data cuaca saat ini, bukan prediksi untuk tiga jam ke depan."),
    ).toBeVisible();
    expect(screen.getByText("27,3 °C")).toBeVisible();
    expect(screen.getByText("82,0%")).toBeVisible();
    expect(screen.getByText("Curah hujan 1 jam terakhir (mm)")).toBeVisible();
    expect(screen.getByText("0,2 mm")).toBeVisible();
    expect(screen.getByText("75,0%")).toBeVisible();
    expect(screen.getByText("12,0 km/jam")).toBeVisible();
    expect(screen.getByText("90,0°")).toBeVisible();
    expect(screen.getByText("1.008,0 hPa")).toBeVisible();
    expect(screen.getByText("Data cuaca disediakan oleh Open-Meteo.")).toBeVisible();
  });

  it("keeps valid values visible when Current Weather is partial", async () => {
    weatherResponse = {
      ...currentWeatherResponse,
      status: "partial",
      warnings: [
        { code: "partial_current_weather", message: "Sebagian data cuaca saat ini tidak tersedia." },
      ],
      variables: {
        ...currentWeatherResponse.variables,
        wind_speed_10m: {
          ...currentWeatherResponse.variables.wind_speed_10m,
          value: null,
          freshness_status: "unavailable",
          status: "unavailable",
        },
      },
    };

    render(<App />);

    expect(await screen.findByText("Sebagian data cuaca saat ini tidak tersedia.")).toBeVisible();
    expect(screen.getByText("27,3 °C")).toBeVisible();
    expect(screen.getByText("Tidak tersedia")).toBeVisible();
  });

  it("shows an unavailable state without fabricated weather values", async () => {
    weatherResponse = {
      ...currentWeatherResponse,
      status: "unavailable",
      variables: {},
      warnings: [
        { code: "current_weather_unavailable", message: "Kondisi cuaca saat ini belum tersedia." },
      ],
    };

    render(<App />);

    expect(await screen.findByText("Kondisi cuaca saat ini belum tersedia.")).toBeVisible();
    expect(screen.queryByText("Suhu udara")).not.toBeInTheDocument();
    expect(screen.queryByText("0,0 °C")).not.toBeInTheDocument();
  });
});
