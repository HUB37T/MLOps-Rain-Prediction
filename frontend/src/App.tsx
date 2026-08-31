import { useEffect, useState } from "react";

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
  status: "complete" | "partial" | "unavailable";
  current_weather_timestamp?: string;
  variables: Record<string, WeatherVariable>;
  warnings: { code: string; message: string }[];
  provider?: { attribution: string };
};

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

export function App() {
  const [response, setResponse] = useState<PredictionResponse | null>(null);
  const [weather, setWeather] = useState<WeatherResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    let isCurrent = true;

    const predictionRequest = fetch("/api/v1/predictions/current")
      .then((result) => {
        if (!result.ok) {
          throw new Error("prediction request failed");
        }
        return result.json() as Promise<PredictionResponse>;
      })
      .then((data) => {
        if (isCurrent) {
          setResponse(data);
          setIsLoading(false);
        }
      })
      .catch(() => {
        if (isCurrent) {
          setHasError(true);
          setIsLoading(false);
        }
      });

    const weatherRequest = fetch("/api/v1/weather/current")
      .then((result) => {
        if (!result.ok) {
          throw new Error("weather request failed");
        }
        return result.json() as Promise<WeatherResponse>;
      })
      .then((data) => {
        if (isCurrent) {
          setWeather(data);
        }
      })
      .catch(() => {
        if (isCurrent) {
          setWeather(null);
        }
      });

    Promise.allSettled([predictionRequest, weatherRequest]).then(() => {
      if (isCurrent) {
        setIsLoading(false);
      }
    });

    return () => {
      isCurrent = false;
    };
  }, []);

  if (isLoading) {
    return (
      <main className="page-shell" aria-busy="true">
        <div className="skeleton" aria-label="Memuat prediksi" />
      </main>
    );
  }

  if (hasError || !response) {
    return (
      <main className="page-shell">
        <p role="alert">Prediksi saat ini belum dapat dimuat.</p>
      </main>
    );
  }

  const { prediction } = response;
  const statusMessage = response.status === "available" ? null : predictionStatusMessages[response.status];

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
          <strong>{response.primary_location.name}</strong>
        </div>

        {response.warnings
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
          <p className="prediction-status" id="prediction-title">
            {statusMessage}
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
      ) : null}
    </main>
  );
}
