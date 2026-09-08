# MLOps Rain Prediction

Proyek MLOps untuk memprediksi kemungkinan terjadinya hujan dalam tiga jam ke depan di Kota Malang berdasarkan data cuaca.

Sistem dirancang sebagai alat bantu pengambilan keputusan untuk kegiatan luar ruangan. Hasil prediksi bersifat eksperimental dan bukan peringatan cuaca resmi.

## Tujuan Proyek

Proyek ini bertujuan untuk:

1. Mengembangkan model machine learning untuk mengklasifikasikan kondisi `Hujan` atau `Tidak hujan` dalam horizon tiga jam ke depan.
2. Menggunakan data cuaca seperti suhu, kelembapan, curah hujan, tekanan udara, tutupan awan, kecepatan angin, dan arah angin.
3. Menyediakan hasil prediksi melalui backend API dan dashboard web.
4. Membangun fondasi MLOps yang mencakup pengumpulan data, eksperimen, training, evaluasi, deployment, dan monitoring model.
5. Menyediakan lingkungan pengembangan yang reproducible menggunakan GitHub Codespaces.

Data cuaca diperoleh dari Open-Meteo. Pada tahap awal, sistem menggunakan mock predictor untuk mendukung pengembangan aplikasi sebelum model machine learning produksi tersedia.

## Struktur Direktori

Repository disusun menggunakan struktur proyek data science dan MLOps agar kode, data, model, konfigurasi, serta eksperimen tersimpan secara terpisah.

```text
MLOps-Rain-Prediction/
├── .devcontainer/          Konfigurasi lingkungan GitHub Codespaces
├── .github/
│   └── workflows/          Workflow Continuous Integration
├── configs/                Konfigurasi development dan production
├── data/
│   ├── raw/                Data asli yang belum diproses
│   ├── processed/          Data yang telah diproses
│   └── predictions/        Riwayat hasil prediksi
├── docs/                   Dokumentasi proyek dan arsitektur
├── frontend/               Dashboard React, TypeScript, dan Vite
├── infrastructure/         Konfigurasi deployment dan monitoring
├── models/                 Artifact model machine learning lokal
├── notebooks/              Notebook EDA dan eksperimen model
├── scripts/                Script untuk pekerjaan operasional
├── src/
│   └── rain_prediction/
│       ├── api/             Backend FastAPI
│       ├── evaluation/      Evaluasi performa model
│       ├── features/        Feature engineering
│       ├── inference/       Proses inferensi model
│       ├── ingestion/       Pengambilan data cuaca
│       ├── monitoring/      Monitoring data dan model
│       ├── schemas/         Kontrak dan validasi data
│       └── training/        Training model
├── tests/                  Pengujian unit dan integrasi
├── docker-compose.yml      Orkestrasi container aplikasi
├── pyproject.toml          Konfigurasi proyek dan dependency Python
└── uv.lock                 Versi dependency Python yang dikunci
```

Data berukuran besar, model hasil training, file environment, dan informasi rahasia tidak disimpan langsung di Git.

## Menjalankan Proyek dengan GitHub Codespaces

GitHub Codespaces menyediakan lingkungan pengembangan berbasis cloud sehingga proyek dapat dijalankan tanpa memasang seluruh dependency secara manual di komputer lokal.

### Membuat Codespace

1. Buka repository ini di GitHub.
2. Klik tombol **Code**.
3. Pilih tab **Codespaces**.
4. Klik **Create codespace on main**.
5. Tunggu proses pembuatan container dan `postCreateCommand` selesai.

Konfigurasi `.devcontainer/devcontainer.json` akan menyiapkan:

- Python 3.11;
- Node.js 22;
- `uv` sebagai package manager Python;
- dependency Python untuk backend, EDA, dan testing;
- dependency frontend;
- ekstensi Python, Pylance, Jupyter, GitLens, dan Docker.

### Verifikasi Environment

Setelah Codespace selesai dibuat, buka terminal dan jalankan:

```bash
python --version
node --version
uv --version
```

Versi utama yang diharapkan:

```text
Python 3.11.x
Node.js v22.x
uv 0.11.28
```

Pastikan dependency utama dapat digunakan:

```bash
uv run --frozen --extra dev python -c "import pandas, sklearn, fastapi; print('Environment siap')"
```

Apabila konfigurasi berhasil, terminal akan menampilkan:

```text
Environment siap
```

### Menjalankan Pengujian

Jalankan pengujian backend:

```bash
uv run --frozen --extra dev pytest
```

Jalankan pengujian dan build frontend:

```bash
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

## Menjalankan Aplikasi di Codespaces

### Backend FastAPI

```bash
uv run uvicorn rain_prediction.api.main:app --host 0.0.0.0 --port 8000
```

Dokumentasi API tersedia melalui port `8000` pada menu **Ports** di Codespaces.

### Frontend

Buka terminal kedua lalu jalankan:

```bash
npm --prefix frontend run dev -- --host 0.0.0.0
```

Dashboard tersedia melalui port `5173` pada menu **Ports**.

### Docker Compose

Sebagai alternatif, seluruh aplikasi dapat dijalankan dengan:

```bash
docker compose up --build
```

Dashboard tersedia melalui port `8080`, sedangkan backend tersedia melalui port `8000`.

Untuk menghentikan aplikasi:

```bash
docker compose down
```

## Alur Pengembangan

Proyek menggunakan GitHub Flow:

1. Membuat branch dari `main`.
2. Melakukan perubahan dan commit dengan pesan yang informatif.
3. Push branch ke GitHub.
4. Membuat pull request.
5. Menunggu seluruh pemeriksaan Continuous Integration berhasil.
6. Merge pull request ke `main` setelah perubahan tervalidasi.

Contoh pembuatan branch:

```bash
git switch main
git pull origin main
git switch -c feat/nama-fitur
```

## Lisensi

Proyek ini menggunakan MIT License. Ketentuan selengkapnya tersedia pada file `LICENSE`.