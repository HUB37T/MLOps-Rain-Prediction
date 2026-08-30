import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

describe("primary Rain Prediction card", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(currentPredictionResponse), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
  });

  it("renders the decision information from the HTTP contract", async () => {
    render(<App />);

    expect(await screen.findByText("Peluang hujan dalam 3 jam ke depan")).toBeVisible();
    expect(screen.getByText("49,9%")).toBeVisible();
    expect(screen.getByText("Prediksi model")).toBeVisible();
    expect(screen.getByText("Tidak hujan")).toBeVisible();
    expect(screen.getByText("Tingkat persiapan").parentElement).toHaveTextContent("Sedang");
    expect(
      screen.getByText("Bawa perlindungan hujan dan periksa kesiapan lokasi cadangan."),
    ).toBeVisible();
    expect(screen.getByText("15:00-18:00 WIB")).toBeVisible();
    expect(screen.getByText("Model: baseline-v1")).toBeVisible();
  });
});
