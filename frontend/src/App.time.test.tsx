import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const weatherResponse = {
  server_time: "2026-08-30T07:00:00Z",
  primary_location: { id: "filkom-ub", name: "FILKOM Universitas Brawijaya" },
  status: "unavailable",
  variables: {},
  warnings: [],
};

const historyResponse = {
  server_time: "2026-08-30T07:00:00Z",
  slot_count: 24,
  slots: [],
};

const predictionResponse = {
  server_time: "2026-08-30T07:00:00Z",
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
    data_freshness_seconds: 0,
    freshness_status: "fresh",
    model: { version: "baseline-v1" },
  },
  warnings: [],
};

function response(body: object): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

describe("authoritative session time", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("rejects a prediction response without a verified server time", async () => {
    const invalidPrediction = { ...predictionResponse } as Record<string, unknown>;
    delete invalidPrediction.server_time;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        return Promise.resolve(
          response(path.includes("/weather/current") ? weatherResponse : path.includes("/history") ? historyResponse : invalidPrediction),
        );
      }),
    );

    render(<App />);

    expect(await screen.findByText("Status waktu tidak dapat diverifikasi. Prediksi saat ini tidak tersedia.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Coba lagi" })).toBeVisible();
  });

  it("transitions a verified prediction using monotonic session time", async () => {
    vi.useFakeTimers();
    let monotonicTime = 0;
    vi.spyOn(performance, "now").mockImplementation(() => monotonicTime);
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        return Promise.resolve(
          response(path.includes("/weather/current") ? weatherResponse : path.includes("/history") ? historyResponse : predictionResponse),
        );
      }),
    );

    render(<App />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(screen.getByText("49,9%")).toBeVisible();

    monotonicTime = 2 * 60 * 60 * 1000 + 1_000;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(
      screen.getByText("Data belum diperbarui—jangan gunakan sebagai satu-satunya dasar keputusan."),
    ).toBeVisible();
    expect(screen.getByText("49,9%")).toBeVisible();

    monotonicTime = 4 * 60 * 60 * 1000;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(screen.getByText("Prediksi untuk periode saat ini belum tersedia.")).toBeVisible();
    expect(screen.queryByText("Peluang hujan dalam 3 jam ke depan")).not.toBeInTheDocument();
  });
});
