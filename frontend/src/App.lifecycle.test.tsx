import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const weatherResponse = {
  server_time: "2026-08-30T07:05:00Z",
  primary_location: { id: "filkom-ub", name: "FILKOM Universitas Brawijaya" },
  status: "unavailable",
  variables: {},
  warnings: [],
};

const responseFor = (predictionResponse: object) =>
  vi.fn((input: RequestInfo | URL) => {
    const body = String(input).includes("/weather/current") ? weatherResponse : predictionResponse;
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

describe("prediction lifecycle states", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders pending without prediction decision fields", async () => {
    vi.stubGlobal(
      "fetch",
      responseFor({
        server_time: "2026-08-30T07:05:00Z",
        primary_location: { name: "FILKOM Universitas Brawijaya" },
        status: "pending",
        prediction: null,
        warnings: [
          {
            code: "prediction_pending",
            message: "Prediksi sedang disiapkan.",
            official_prediction_time: "2026-08-30T07:00:00Z",
          },
        ],
      }),
    );

    render(<App />);

    expect(await screen.findByText("Prediksi sedang disiapkan.")).toBeVisible();
    expect(screen.queryByText("Prediksi model")).not.toBeInTheDocument();
    expect(screen.queryByText("Tingkat persiapan")).not.toBeInTheDocument();
  });

  it("renders the backend stale warning alongside a usable prediction", async () => {
    vi.stubGlobal(
      "fetch",
      responseFor({
        server_time: "2026-08-30T07:05:00Z",
        primary_location: { name: "FILKOM Universitas Brawijaya" },
        status: "available",
        prediction: {
          prediction_horizon: { start: "2026-08-30T02:00:00Z", end: "2026-08-30T05:00:00Z" },
          rain_probability: 0.2,
          predicted_class: "no_rain",
          risk_level: "low",
          preparation_action: "Tidak diperlukan persiapan khusus terkait hujan.",
          decision_threshold: 0.5,
          feature_timestamp: "2026-08-30T01:05:00Z",
          data_freshness_seconds: 21600,
          freshness_status: "stale",
          model: { version: "baseline-v1" },
        },
        warnings: [
          {
            code: "prediction_stale",
            message: "Data belum diperbarui—jangan gunakan sebagai satu-satunya dasar keputusan.",
          },
        ],
      }),
    );

    render(<App />);

    expect(
      await screen.findByText("Data belum diperbarui—jangan gunakan sebagai satu-satunya dasar keputusan."),
    ).toBeVisible();
    expect(screen.getByText("20,0%")).toBeVisible();
  });
});
