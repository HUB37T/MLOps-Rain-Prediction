# Rain Risk MLOps

Repository untuk aplikasi prediksi risiko hujan tiga jam ke depan di Kota Malang.
Repository ini memakai satu struktur untuk web UI, backend FastAPI, pipeline data,
training model, deployment, dan monitoring.

## Status

Tahap saat ini adalah penyusunan fondasi repository. Frontend dan backend akan
dikembangkan menggunakan kontrak data yang sama. Sebelum model ML tersedia,
backend akan memakai mock predictor yang nantinya dapat diganti dengan adapter
model produksi tanpa mengubah frontend.

## Struktur

```text
rain-risk-mlops/
├── data/                 Data mentah, terproses, dan riwayat prediksi
├── models/               Artifact model lokal (tidak disimpan langsung di Git)
├── src/rain_prediction/  Package Python utama
├── notebooks/            EDA dan eksperimen
├── tests/                Pengujian unit dan integrasi
├── docs/                 Dokumentasi arsitektur dan model
├── configs/              Konfigurasi non-rahasia per environment
├── frontend/             React, TypeScript, dan Vite
├── infrastructure/       Docker, reverse proxy, dan monitoring
└── scripts/              Perintah masuk untuk job operasional
```

## Prinsip pengembangan

- Frontend hanya mengambil data dari backend aplikasi, bukan langsung dari Open-Meteo.
- Kode produksi berada di `src/`; notebook hanya dipakai untuk eksplorasi.
- Data besar dan model tidak di-commit langsung ke Git.
- Rahasia disimpan di `.env`, bukan di `configs/` atau source code.
- Mock predictor dan model produksi memenuhi interface prediksi yang sama.

## Menjalankan Demo dengan Docker

Pastikan Docker Engine dan Docker Compose tersedia, lalu jalankan dari root repository:

```bash
docker compose up --build
```

Buka dashboard pada `http://localhost:8080`. Backend API dan dokumentasinya tersedia
di `http://localhost:8000/docs`. Untuk menghentikan demo:

```bash
docker compose down
```

Compose memakai mock predictor dan Open-Meteo untuk Current Weather secara default.
Pengaturan provider yang didukung dapat diubah melalui `.env`: `OPEN_METEO_BASE_URL`,
`WEATHER_LATITUDE`, dan `WEATHER_LONGITUDE`. Port host dapat diubah dengan
`WEB_PORT` dan `API_PORT`.

## Tahapan berikutnya

1. Scaffold backend FastAPI dan kontrak respons dashboard.
2. Tambahkan mock predictor beserta pengujian.
3. Scaffold frontend React + TypeScript + Vite.
4. Hubungkan dashboard dengan backend.
5. Tambahkan adapter Open-Meteo dan penyimpanan riwayat.
6. Integrasikan model ML dan MLflow pada tahap MLOps berikutnya.
