import { useEffect, useRef, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type PredictionResponse = {
  server_time: string;
  primary_location: { name: string };
  status: "available" | "pending" | "insufficient_feature_window" | "unavailable" | "invalid";
  prediction: {
    prediction_horizon: { start: string; end: string };
    rain_probability: number;
    predicted_class: "rain" | "no_rain";
    risk_level: "low" | "moderate" | "high";
    preparation_action: string;
    decision_threshold: number;
    feature_timestamp: string;
    data_freshness_seconds: number;
    freshness_status: "fresh" | "stale" | "unavailable";
    model: { version: string };
  } | null;
  warnings: { code: string; message: string }[];
};

type WeatherVariable = {
  value: number | null;
  unit: string;
  timestamp: string;
  freshness_status: "fresh" | "stale" | "unavailable";
  status: "available" | "unavailable";
  interval_start?: string;
};

type WeatherResponse = {
  server_time: string;
  status: "complete" | "partial" | "unavailable";
  current_weather_timestamp?: string;
  variables: Record<string, WeatherVariable>;
  warnings: { code: string; message: string }[];
  provider?: { attribution: string };
};

type HistoryPrediction = {
  prediction_horizon: { start: string; end: string };
  rain_probability: number;
  predicted_class: "rain" | "no_rain";
  risk_level: "low" | "moderate" | "high";
  decision_threshold: number;
  feature_timestamp: string;
  data_freshness_seconds: number;
  freshness_status: "fresh" | "stale" | "unavailable";
};

type HistorySlot = {
  official_prediction_time: string;
  status: "pending" | "issued" | "failed" | "unavailable";
  prediction: HistoryPrediction | null;
};

type HistoryResponse = {
  server_time: string;
  slot_count: number;
  slots: HistorySlot[];
};

class ApiRequestError extends Error {
  constructor(readonly code: string) {
    super(code);
  }
}

type SessionClock = {
  serverTimeMs: number | null;
  monotonicTimeMs: number | null;
  greatestServerTimeMs: number | null;
};

const SESSION_TIME_TOLERANCE_MS = 5_000;

function verifyServerTime(value: unknown, clock: SessionClock): boolean {
  if (typeof value !== "string") return false;
  const serverTimeMs = Date.parse(value);
  if (!Number.isFinite(serverTimeMs)) return false;

  const monotonicTimeMs = performance.now();
  if (clock.serverTimeMs === null || clock.monotonicTimeMs === null) {
    clock.serverTimeMs = serverTimeMs;
    clock.monotonicTimeMs = monotonicTimeMs;
    clock.greatestServerTimeMs = serverTimeMs;
    return true;
  }

  const elapsedMs = Math.max(0, monotonicTimeMs - clock.monotonicTimeMs);
  const expectedServerTimeMs = clock.serverTimeMs + elapsedMs;
  if (serverTimeMs > expectedServerTimeMs + SESSION_TIME_TOLERANCE_MS) return false;
  if (
    clock.greatestServerTimeMs !== null &&
    serverTimeMs < clock.greatestServerTimeMs - SESSION_TIME_TOLERANCE_MS
  ) {
    return false;
  }
  if (serverTimeMs > clock.greatestServerTimeMs!) {
    clock.serverTimeMs = serverTimeMs;
    clock.monotonicTimeMs = monotonicTimeMs;
    clock.greatestServerTimeMs = serverTimeMs;
  }
  return true;
}

function sessionTimeMs(clock: SessionClock): number | null {
  if (clock.serverTimeMs === null || clock.monotonicTimeMs === null) return null;
  return clock.serverTimeMs + Math.max(0, performance.now() - clock.monotonicTimeMs);
}

function resolveSessionPrediction(response: PredictionResponse, nowMs: number): PredictionResponse {
  if (response.status !== "available" || response.prediction === null) return response;

  const featureTimeMs = Date.parse(response.prediction.feature_timestamp);
  const horizonEndMs = Date.parse(response.prediction.prediction_horizon.end);
  if (!Number.isFinite(featureTimeMs) || !Number.isFinite(horizonEndMs)) {
    return {
      ...response,
      status: "invalid",
      prediction: null,
      warnings: [
        ...response.warnings,
        {
          code: "unverified_prediction",
          message: "Prediksi saat ini tidak tersedia karena hasilnya tidak dapat diverifikasi.",
        },
      ],
    };
  }

  const dataFreshnessSeconds = Math.max(0, Math.floor((nowMs - featureTimeMs) / 1_000));
  if (nowMs >= horizonEndMs || dataFreshnessSeconds > 6 * 60 * 60) {
    return {
      ...response,
      status: "unavailable",
      prediction: null,
      warnings: [
        ...response.warnings.filter((warning) => warning.code !== "prediction_stale"),
        { code: "prediction_expired", message: "Prediksi untuk periode saat ini belum tersedia." },
      ],
    };
  }

  const freshnessStatus = dataFreshnessSeconds <= 2 * 60 * 60 ? "fresh" : "stale";
  const warnings = response.warnings.filter((warning) => warning.code !== "prediction_stale");
  if (freshnessStatus === "stale") {
    warnings.push({
      code: "prediction_stale",
      message: "Data belum diperbarui—jangan gunakan sebagai satu-satunya dasar keputusan.",
    });
  }
  return {
    ...response,
    warnings,
    prediction: {
      ...response.prediction,
      data_freshness_seconds: dataFreshnessSeconds,
      freshness_status: freshnessStatus,
    },
  };
}

async function fetchJson<T>(url: string): Promise<T> {
  const result = await fetch(url);
  if (!result.ok) {
    let code = "backend_unavailable";
    try {
      const body = (await result.json()) as { error?: { code?: string } };
      code = body.error?.code ?? code;
    } catch {
      // Preserve the safe generic code when the error body is not JSON.
    }
    throw new ApiRequestError(code);
  }
  return result.json() as Promise<T>;
}

const classLabels = {
  rain: "Hujan",
  no_rain: "Tidak hujan",
} as const;

const riskLabels = {
  low: "Rendah",
  moderate: "Sedang",
  high: "Tinggi",
} as const;

const percentageFormatter = new Intl.NumberFormat("id-ID", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function formatPercentage(value: number): string {
  return percentageFormatter.format(value);
}

function formatWibTime(value: string): string {
  const parts = new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Jakarta",
  }).formatToParts(new Date(value));
  const hour = parts.find((part) => part.type === "hour")?.value ?? "--";
  const minute = parts.find((part) => part.type === "minute")?.value ?? "--";
  return `${hour}:${minute}`;
}

function formatHorizon(start: string, end: string): string {
  return `${formatWibTime(start)}-${formatWibTime(end)} WIB`;
}

function formatFeatureTimestamp(value: string): string {
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "Asia/Jakarta",
  }).format(new Date(value));
}

function formatFreshness(seconds: number): string {
  const minutes = Math.max(0, Math.floor(seconds / 60));
  return `Diperbarui ${minutes} menit lalu`;
}

function formatWeatherNumber(value: number): string {
  return new Intl.NumberFormat("id-ID", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value);
}

function formatWeatherValue(field: string, value: number): string {
  const formatted = formatWeatherNumber(value);
  const units: Record<string, string> = {
    temperature_2m: "°C",
    relative_humidity_2m: "%",
    precipitation_1h: "mm",
    cloud_cover: "%",
    wind_speed_10m: "km/jam",
    wind_direction_10m: "°",
    sea_level_pressure: "hPa",
  };
  const unit = units[field];
  return unit === "%" || unit === "°" ? `${formatted}${unit}` : `${formatted} ${unit}`;
}

const weatherLabels: Record<string, string> = {
  temperature_2m: "Suhu udara",
  relative_humidity_2m: "Kelembapan relatif",
  precipitation_1h: "Curah hujan 1 jam terakhir (mm)",
  cloud_cover: "Tutupan awan",
  wind_speed_10m: "Kecepatan angin",
  wind_direction_10m: "Arah angin",
  sea_level_pressure: "Tekanan udara permukaan laut",
};

const weatherOrder = [
  "temperature_2m",
  "relative_humidity_2m",
  "precipitation_1h",
  "cloud_cover",
  "wind_speed_10m",
  "wind_direction_10m",
  "sea_level_pressure",
];

const predictionStatusMessages: Record<Exclude<PredictionResponse["status"], "available">, string> = {
  pending: "Prediksi sedang disiapkan.",
  insufficient_feature_window: "Sedang mengumpulkan data yang cukup untuk membuat prediksi.",
  unavailable: "Prediksi untuk periode saat ini belum tersedia.",
  invalid: "Prediksi saat ini tidak tersedia karena hasilnya tidak dapat diverifikasi.",
};

const historyStatusLabels: Record<HistorySlot["status"], string> = {
  pending: "Menunggu penerbitan",
  issued: "Berhasil diterbitkan",
  failed: "Penerbitan prediksi gagal",
  unavailable: "Prediksi tidak tersedia",
};

function PredictionHistory({ history }: { history: HistoryResponse }) {
  const issuedSlots = history.slots.filter(
    (slot): slot is HistorySlot & { prediction: HistoryPrediction } =>
      slot.status === "issued" && slot.prediction !== null,
  );
  const highest = issuedSlots.reduce<HistorySlot & { prediction: HistoryPrediction } | null>(
    (current, slot) =>
      current === null || slot.prediction.rain_probability > current.prediction.rain_probability
        ? slot
        : current,
    null,
  );
  const chartData = history.slots.map((slot) => ({
    time: formatWibTime(slot.official_prediction_time),
    rainProbability: slot.prediction?.rain_probability ?? null,
    decisionThreshold: slot.prediction?.decision_threshold ?? null,
  }));

  return (
    <section className="history-card" aria-labelledby="history-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Riwayat</p>
          <h2 id="history-title">Riwayat prediksi 24 jam</h2>
        </div>
      </div>

      <p className="history-summary" role="status">
        {highest
          ? `Peluang hujan tertinggi dalam 24 jam terakhir adalah ${formatPercentage(highest.prediction.rain_probability)} pada pukul ${formatWibTime(highest.official_prediction_time)} WIB.`
          : "Tidak ada prediksi yang berhasil diterbitkan dalam 24 jam terakhir."}
      </p>

      {issuedSlots.length === 0 ? (
        <p className="history-empty">Belum ada prediksi yang berhasil diterbitkan dalam 24 slot terakhir.</p>
      ) : null}

      <div className="history-chart" role="img" aria-label="Grafik peluang hujan dan ambang keputusan">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData} margin={{ top: 12, right: 12, bottom: 8, left: 12 }}>
            <CartesianGrid stroke="#38514e" strokeDasharray="3 3" />
            <XAxis dataKey="time" minTickGap={24} />
            <YAxis domain={[0, 1]} tickFormatter={formatPercentage} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="rainProbability"
              name="Peluang hujan"
              stroke="#f6c66e"
              strokeWidth={3}
              dot={false}
              connectNulls={false}
            />
            <Line
              type="stepAfter"
              dataKey="decisionThreshold"
              name="Ambang keputusan yang digunakan"
              stroke="#9eb4ad"
              strokeWidth={2}
              dot={false}
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="history-table-wrapper">
        <table>
          <caption>Tabel riwayat prediksi per slot</caption>
          <thead>
            <tr>
              <th scope="col">Waktu resmi</th>
              <th scope="col">Status</th>
              <th scope="col">Horizon</th>
              <th scope="col">Peluang hujan</th>
              <th scope="col">Prediksi model</th>
              <th scope="col">Tingkat persiapan</th>
              <th scope="col">Ambang</th>
              <th scope="col">Data</th>
            </tr>
          </thead>
          <tbody>
            {history.slots.map((slot) => {
              const prediction = slot.prediction;
              return (
                <tr key={slot.official_prediction_time}>
                  <th scope="row">{formatWibTime(slot.official_prediction_time)} WIB</th>
                  <td>{historyStatusLabels[slot.status]}</td>
                  <td>{prediction ? formatHorizon(prediction.prediction_horizon.start, prediction.prediction_horizon.end) : "-"}</td>
                  <td>{prediction ? formatPercentage(prediction.rain_probability) : "-"}</td>
                  <td>{prediction ? classLabels[prediction.predicted_class] : "-"}</td>
                  <td>{prediction ? riskLabels[prediction.risk_level] : "-"}</td>
                  <td>{prediction ? formatPercentage(prediction.decision_threshold) : "-"}</td>
                  <td>{prediction ? formatFreshness(prediction.data_freshness_seconds) : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function predictionErrorMessage(code: string, hasVerifiedData: boolean): string {
  if (code === "unverified_time") {
    return "Status waktu tidak dapat diverifikasi. Prediksi saat ini tidak tersedia.";
  }
  if (hasVerifiedData) {
    return "Layanan belum dapat dihubungi. Menampilkan data terakhir yang berhasil dimuat.";
  }
  if (code === "prediction_service_unavailable") {
    return "Prediksi belum dapat dibuat. Coba lagi nanti.";
  }
  return "Layanan belum dapat dihubungi. Prediksi saat ini belum dapat dimuat.";
}

export function App() {
  const [response, setResponse] = useState<PredictionResponse | null>(null);
  const [weather, setWeather] = useState<WeatherResponse | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const [weatherError, setWeatherError] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [sessionNowMs, setSessionNowMs] = useState<number | null>(null);
  const mountedRef = useRef(true);
  const sessionClockRef = useRef<SessionClock>({
    serverTimeMs: null,
    monotonicTimeMs: null,
    greatestServerTimeMs: null,
  });
  const predictionRequestId = useRef(0);
  const weatherRequestId = useRef(0);
  const historyRequestId = useRef(0);

  const loadPrediction = () => {
    const requestId = ++predictionRequestId.current;
    return fetchJson<PredictionResponse>("/api/v1/predictions/current")
      .then((data) => {
        if (!verifyServerTime(data.server_time, sessionClockRef.current)) {
          throw new ApiRequestError("unverified_time");
        }
        if (mountedRef.current && requestId === predictionRequestId.current) {
          setResponse(data);
          setPredictionError(null);
          setSessionNowMs(sessionTimeMs(sessionClockRef.current));
        }
      })
      .catch((error: unknown) => {
        if (mountedRef.current && requestId === predictionRequestId.current) {
          setPredictionError(error instanceof ApiRequestError ? error.code : "backend_unavailable");
        }
      });
  };

  const loadWeather = () => {
    const requestId = ++weatherRequestId.current;
    return fetchJson<WeatherResponse>("/api/v1/weather/current")
      .then((data) => {
        if (!verifyServerTime(data.server_time, sessionClockRef.current)) {
          throw new ApiRequestError("unverified_time");
        }
        if (mountedRef.current && requestId === weatherRequestId.current) {
          setWeather(data);
          setWeatherError(false);
          setSessionNowMs(sessionTimeMs(sessionClockRef.current));
        }
      })
      .catch(() => {
        if (mountedRef.current && requestId === weatherRequestId.current) {
          setWeatherError(true);
        }
      });
  };

  const loadHistory = () => {
    const requestId = ++historyRequestId.current;
    return fetchJson<HistoryResponse>("/api/v1/predictions/history?slots=24")
      .then((data) => {
        if (!verifyServerTime(data.server_time, sessionClockRef.current)) {
          throw new ApiRequestError("unverified_time");
        }
        if (!Array.isArray(data.slots)) {
          throw new ApiRequestError("history_unavailable");
        }
        if (mountedRef.current && requestId === historyRequestId.current) {
          setHistory(data);
          setHistoryError(false);
          setSessionNowMs(sessionTimeMs(sessionClockRef.current));
        }
      })
      .catch(() => {
        if (mountedRef.current && requestId === historyRequestId.current) {
          setHistoryError(true);
        }
      });
  };

  const retry = () => {
    if (isRetrying) return;
    setIsRetrying(true);
    Promise.allSettled([loadPrediction(), loadWeather(), loadHistory()]).then(() => {
      if (mountedRef.current) {
        setIsRetrying(false);
      }
    });
  };

  useEffect(() => {
    mountedRef.current = true;
    const predictionRequest = loadPrediction();
    const weatherRequest = loadWeather();
    const historyRequest = loadHistory();

    Promise.allSettled([predictionRequest, weatherRequest, historyRequest]).then(() => {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    });

    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const updateSessionTime = () => {
      if (mountedRef.current) {
        setSessionNowMs(sessionTimeMs(sessionClockRef.current));
      }
    };
    updateSessionTime();
    const interval = window.setInterval(updateSessionTime, 1_000);
    return () => window.clearInterval(interval);
  }, []);

  if (isLoading) {
    return (
      <main className="page-shell" aria-busy="true">
        <div className="skeleton" aria-label="Memuat prediksi" />
      </main>
    );
  }

  const displayResponse = response && sessionNowMs !== null
    ? resolveSessionPrediction(response, sessionNowMs)
    : response;
  const prediction = displayResponse?.prediction ?? null;
  const statusMessage = displayResponse && displayResponse.status !== "available"
    ? predictionStatusMessages[displayResponse.status]
    : null;
  const hasRecoverableError = predictionError !== null || weatherError || historyError;

  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">Rain Risk Prediction</p>
        <h1>Persiapan kegiatan</h1>
        <p className="disclaimer">
          Prediksi eksperimental untuk membantu persiapan kegiatan, bukan peringatan cuaca resmi.
        </p>
      </header>

      <section className="prediction-card" aria-labelledby="prediction-title">
        <div className="location-row">
          <span>Lokasi utama</span>
          <strong>{displayResponse?.primary_location.name ?? "FILKOM Universitas Brawijaya"}</strong>
        </div>

        {predictionError && response ? (
          <p className="prediction-warning" role="status">
            {predictionErrorMessage(predictionError, true)}
          </p>
        ) : null}

        {displayResponse?.warnings
          .filter((warning) => warning.message !== statusMessage)
          .map((warning) => (
            <p className="prediction-warning" key={warning.code} role="status">
              {warning.message}
            </p>
          ))}

        {prediction ? (
          <>
            <div className="probability-block">
              <p className="label" id="prediction-title">
                Peluang hujan dalam 3 jam ke depan
              </p>
              <strong className="probability">{formatPercentage(prediction.rain_probability)}</strong>
            </div>

            <div className="decision-grid">
              <div>
                <p className="label">Prediksi model</p>
                <p className="value">{classLabels[prediction.predicted_class]}</p>
              </div>
              <div>
                <p className="label">Tingkat persiapan</p>
                <p className="value">{riskLabels[prediction.risk_level]}</p>
              </div>
            </div>

            <div className="preparation">
              <p className="label">Panduan persiapan</p>
              <p>{prediction.preparation_action}</p>
            </div>

            <dl className="metadata">
              <div>
                <dt>Periode prediksi</dt>
                <dd>{formatHorizon(prediction.prediction_horizon.start, prediction.prediction_horizon.end)}</dd>
              </div>
              <div>
                <dt>Data model</dt>
                <dd>{formatFreshness(prediction.data_freshness_seconds)}</dd>
              </div>
              <div>
                <dt>Feature Timestamp</dt>
                <dd>{formatFeatureTimestamp(prediction.feature_timestamp)} WIB</dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>Model: {prediction.model.version}</dd>
              </div>
              <div>
                <dt>Ambang keputusan yang digunakan</dt>
                <dd>{formatPercentage(prediction.decision_threshold)}</dd>
              </div>
            </dl>
          </>
        ) : (
          <p className="prediction-status" id="prediction-title" role={predictionError ? "alert" : undefined}>
            {statusMessage ??
              (predictionError
                ? predictionErrorMessage(predictionError, false)
                : "Prediksi untuk periode saat ini belum tersedia.")}
          </p>
        )}
      </section>

      {weather ? (
        <section className="weather-card" aria-labelledby="weather-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Kondisi terbaru</p>
              <h2 id="weather-title">Cuaca saat ini</h2>
            </div>
            {weather.current_weather_timestamp ? (
              <p className="timestamp">
                {formatFeatureTimestamp(weather.current_weather_timestamp)} WIB
              </p>
            ) : null}
          </div>

          {weather.warnings.map((warning) => (
            <p className="weather-warning" key={warning.code} role="status">
              {warning.message}
            </p>
          ))}

          {weatherError ? (
            <p className="weather-warning" role="status">
              Pembaruan cuaca gagal. Menampilkan data sebelumnya.
            </p>
          ) : null}

          {weather.status === "unavailable" ? null : (
            <dl className="weather-grid">
              {weatherOrder.map((field) => {
                const variable = weather.variables[field];
                const isUnavailable = !variable || variable.status === "unavailable";
                return (
                  <div key={field}>
                    <dt>{weatherLabels[field]}</dt>
                    <dd>
                      {isUnavailable || variable.value === null
                        ? "Tidak tersedia"
                        : formatWeatherValue(field, variable.value)}
                      {!isUnavailable && variable.freshness_status === "stale" ? (
                        <span className="stale-indicator"> (data lama)</span>
                      ) : null}
                    </dd>
                  </div>
                );
              })}
            </dl>
          )}

          {weather.provider ? <p className="attribution">{weather.provider.attribution}</p> : null}
        </section>
      ) : weatherError ? (
        <section className="weather-card" aria-labelledby="weather-title">
          <h2 id="weather-title">Cuaca saat ini</h2>
          <p className="weather-warning" role="status">
            Kondisi cuaca saat ini belum tersedia.
          </p>
        </section>
      ) : null}

      {history ? (
        <PredictionHistory history={history} />
      ) : historyError ? (
        <section className="history-card" aria-labelledby="history-title">
          <h2 id="history-title">Riwayat prediksi 24 jam</h2>
          <p className="history-empty" role="status">
            Riwayat prediksi belum dapat dimuat.
          </p>
        </section>
      ) : null}

      {hasRecoverableError ? (
        <button className="retry-button" type="button" onClick={retry} disabled={isRetrying}>
          {isRetrying ? "Mencoba kembali..." : "Coba lagi"}
        </button>
      ) : null}
    </main>
  );
}
