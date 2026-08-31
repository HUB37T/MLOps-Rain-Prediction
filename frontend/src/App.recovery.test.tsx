import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const weatherResponse = {
  server_time: "2026-08-30T07:05:00Z",
  primary_location: { id: "filkom-ub", name: "FILKOM Universitas Brawijaya" },
  status: "complete",
  current_weather_timestamp: "2026-08-30T07:00:00Z",
  variables: {},
  warnings: [],
};

const predictionResponse = {
  server_time: "2026-08-30T07:05:00Z",
  primary_location: { name: "FILKOM Universitas Brawijaya" },
  status: "available",
  prediction: {
    prediction_horizon: { start: "2026-08-30T08:00:00Z", end: "2026-08-30T11:00:00Z" },
    rain_probability: 0.499,
    predicted_class: "no_rain",
    risk_level: "moderate",
    preparation_action: "Bawa perlindungan hujan dan periksa kesiapan lokasi cadangan.",
    decision_threshold: 0.5,
    feature_timestamp: "2026-08-30T07:00:00Z",
    data_freshness_seconds: 300,
    model: { version: "baseline-v1" },
  },
  warnings: [],
};

const historyResponse = {
  server_time: "2026-08-30T07:05:00Z",
  slot_count: 24,
  slots: Array.from({ length: 24 }, (_, index) => ({
    official_prediction_time: new Date(Date.parse("2026-08-30T07:00:00Z") - index * 60 * 60 * 1_000).toISOString(),
    status: "unavailable",
    prediction: null,
  })),
};

function response(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("error recovery", () => {
  afterEach(() => {
    cleanup();
  });

  it("keeps Current Weather visible when the initial prediction request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.includes("/weather/current")) return Promise.resolve(response(weatherResponse));
        if (path.includes("/history")) return Promise.resolve(response(historyResponse));
        return Promise.resolve(
          response(
            { error: { code: "prediction_service_unavailable", message: "safe error" } },
            503,
          ),
        );
      }),
    );

    render(<App />);

    expect(await screen.findByText("Prediksi belum dapat dibuat. Coba lagi nanti.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Cuaca saat ini" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Coba lagi" })).toBeVisible();
  });

  it("retries failed requests and prevents duplicate retries while running", async () => {
    let predictionAttempts = 0;
    let releaseRetry: (() => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path.includes("/weather/current")) return Promise.resolve(response(weatherResponse));
        if (path.includes("/history")) return Promise.resolve(response(historyResponse));
        predictionAttempts += 1;
        if (predictionAttempts === 1) {
          return Promise.resolve(
            response({ error: { code: "prediction_service_unavailable", message: "safe error" } }, 503),
          );
        }
        return new Promise((resolve) => {
          releaseRetry = () => resolve(response(predictionResponse));
        });
      }),
    );

    render(<App />);
    const retry = await screen.findByRole("button", { name: "Coba lagi" });
    fireEvent.click(retry);
    expect(screen.getByRole("button", { name: "Mencoba kembali..." })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Mencoba kembali..." }));
    expect(predictionAttempts).toBe(2);

    releaseRetry?.();
    expect(await screen.findByText("49,9%")).toBeVisible();
  });
});
