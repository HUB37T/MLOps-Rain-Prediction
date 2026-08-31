import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const weatherResponse = {
  server_time: "2026-08-30T07:05:00Z",
  primary_location: { id: "filkom-ub", name: "FILKOM Universitas Brawijaya" },
  status: "partial",
  current_weather_timestamp: "2026-08-30T07:00:00Z",
  variables: {},
  warnings: [{ code: "partial_current_weather", message: "Sebagian data cuaca saat ini tidak tersedia." }],
};

const historyResponse = {
  server_time: "2026-08-30T07:05:00Z",
  slot_count: 24,
  slots: [],
};

function response(body: object): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

function stubFetch(predictionResponse: object): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      return Promise.resolve(
        response(path.includes("/weather/current") ? weatherResponse : path.includes("/history") ? historyResponse : predictionResponse),
      );
    }),
  );
}

describe("dashboard accessibility", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("announces fallback, stale, and partial-weather states politely", async () => {
    stubFetch({
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
        feature_timestamp: "2026-08-30T01:05:00Z",
        data_freshness_seconds: 21600,
        freshness_status: "stale",
        model: { version: "baseline-v1" },
      },
      warnings: [
        { code: "prediction_stale", message: "Data belum diperbarui—jangan gunakan sebagai satu-satunya dasar keputusan." },
        { code: "prediction_fallback", message: "Pembaruan terbaru gagal. Menampilkan prediksi sebelumnya." },
      ],
    });

    render(<App />);

    expect(await screen.findByText("Pembaruan terbaru gagal. Menampilkan prediksi sebelumnya.", {}, { timeout: 2_000 })).toBeVisible();
    expect(screen.getByText("Sebagian data cuaca saat ini tidak tersedia.")).toBeVisible();
    expect(document.querySelector('.prediction-warning[aria-live="polite"]')).toHaveTextContent(
      "Pembaruan terbaru gagal. Menampilkan prediksi sebelumnya.",
    );
    expect(screen.getAllByRole("status").map((element) => element.textContent)).toEqual(
      expect.arrayContaining([
        "Pembaruan terbaru gagal. Menampilkan prediksi sebelumnya.",
        "Sebagian data cuaca saat ini tidak tersedia.",
      ]),
    );
    expect(screen.getByRole("table")).toBeVisible();
  });

  it("uses an assertive alert when the current prediction is unavailable", async () => {
    stubFetch({
      server_time: "2026-08-30T07:05:00Z",
      primary_location: { name: "FILKOM Universitas Brawijaya" },
      status: "unavailable",
      prediction: null,
      warnings: [{ code: "prediction_unavailable", message: "Prediksi untuk periode saat ini belum tersedia." }],
    });

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Prediksi untuk periode saat ini belum tersedia.");
    expect(document.querySelector('[aria-live="assertive"]')).toHaveTextContent(
      "Prediksi saat ini tidak tersedia.",
    );
  });
});
