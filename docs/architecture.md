# Arsitektur Awal

```text
Browser
   |
   v
Frontend React
   |
   v
Backend FastAPI
   |
   +--> Weather provider interface --> Mock/Open-Meteo adapter
   |
   +--> Prediction interface -------> Mock/ML model adapter
   |
   +--> Prediction repository ------> SQLite/PostgreSQL adapter
```

Frontend hanya bergantung pada kontrak respons HTTP backend. Backend bergantung
pada tiga interface utama: sumber cuaca, prediksi, dan penyimpanan. Implementasi
mock digunakan selama pengembangan; implementasi produksi dipasang pada seam yang
sama ketika pipeline ML sudah tersedia.

## Alur produksi yang dituju

```text
Open-Meteo -> ingestion -> storage -> features -> model -> prediction history
                                                        |
                                                        v
                                                FastAPI -> Web UI
```
