import { useEffect, useState } from "react";

type PredictionResponse = {
  primary_location: { name: string };
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
  };
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

export function App() {
  const [response, setResponse] = useState<PredictionResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    let isCurrent = true;

    fetch("/api/v1/predictions/current")
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
      </section>
    </main>
  );
}
