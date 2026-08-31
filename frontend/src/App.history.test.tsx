import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const historyResponse = {
  server_time: "2026-08-30T07:05:00Z",
  slot_count: 24,
  slots: [
    {
      official_prediction_time: "2026-08-30T07:00:00Z",
      status: "pending",
      prediction: null,
    },
    {
      official_prediction_time: "2026-08-30T06:00:00Z",
      status: "issued",
      prediction: {
        prediction_horizon: { start: "2026-08-30T07:00:00Z", end: "2026-08-30T10:00:00Z" },
        rain_probability: 0.784,
        predicted_class: "rain",
        risk_level: "high",
        preparation_action: "Siapkan perlengkapan hujan dan lokasi cadangan.",
        decision_threshold: 0.5,
        feature_timestamp: "2026-08-30T06:00:00Z",
        data_freshness_seconds: 3900,
        freshness_status: "stale",
      },
    },
  ],
};

const unavailableWeather = {
  server_time: "2026-08-30T07:05:00Z",
  primary_location: { id: "filkom-ub", name: "FILKOM Universitas Brawijaya" },
  status: "unavailable",
  variables: {},
  warnings: [],
};

describe("prediction history", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders the accessible history table and successful-record chart data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        const body = path.includes("/history")
          ? historyResponse
          : path.includes("/weather/current")
            ? unavailableWeather
            : {
                server_time: "2026-08-30T07:05:00Z",
                primary_location: { name: "FILKOM Universitas Brawijaya" },
                status: "pending",
                prediction: null,
                warnings: [{ code: "prediction_pending", message: "Prediksi sedang disiapkan." }],
              };
        return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
      }),
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Riwayat prediksi 24 jam" })).toBeVisible();
    expect(screen.getByRole("table")).toBeVisible();
    expect(screen.getByText("Berhasil diterbitkan")).toBeVisible();
    expect(screen.getByText("Menunggu penerbitan")).toBeVisible();
    expect(screen.getByText("78,4%")).toBeVisible();
    expect(screen.getByText("Peluang hujan tertinggi dalam 24 jam terakhir adalah 78,4% pada pukul 13:00 WIB.")).toBeVisible();
  });

  it("shows the approved empty history message when no records were issued", async () => {
    const emptyHistory = { ...historyResponse, slots: historyResponse.slots.map((slot) => ({ ...slot, status: "unavailable", prediction: null })) };
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        const body = path.includes("/history")
          ? emptyHistory
          : path.includes("/weather/current")
            ? unavailableWeather
            : {
                server_time: "2026-08-30T07:05:00Z",
                primary_location: { name: "FILKOM Universitas Brawijaya" },
                status: "pending",
                prediction: null,
                warnings: [{ code: "prediction_pending", message: "Prediksi sedang disiapkan." }],
              };
        return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
      }),
    );

    render(<App />);

    expect(await screen.findByText("Belum ada prediksi yang berhasil diterbitkan dalam 24 slot terakhir.")).toBeVisible();
    expect(screen.queryByText("0,0%")).not.toBeInTheDocument();
  });
});
