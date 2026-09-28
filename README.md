# MLOps Rain Prediction

Proyek MLOps untuk memprediksi kemungkinan terjadinya hujan dalam tiga jam ke depan di Kota Malang berdasarkan data cuaca dinamis dari Open-Meteo.

Sistem dirancang sebagai alat bantu pengambilan keputusan untuk kegiatan luar ruangan. Hasil prediksi bersifat eksperimental dan bukan peringatan cuaca resmi dari lembaga pemerintah.

## Tujuan Proyek

Proyek ini bertujuan untuk:

1. Mengumpulkan data cuaca Kota Malang secara berkala dari Open-Meteo API.
2. Membersihkan dan memvalidasi data mentah secara otomatis.
3. Mengembangkan model machine learning untuk mengklasifikasikan kondisi `Hujan` atau `Tidak hujan` dalam horizon tiga jam ke depan.
4. Menyediakan hasil prediksi melalui backend API dan dashboard web.
5. Membangun alur MLOps yang mencakup data ingestion, preprocessing, feature engineering, training, evaluasi, deployment, dan monitoring.
6. Menyediakan lingkungan pengembangan yang konsisten dan reproducible menggunakan GitHub Codespaces.

Pada tahap awal, aplikasi masih dapat menggunakan mock predictor sebelum model machine learning hasil training tersedia.

## Sumber Data

Data cuaca diperoleh dari [Open-Meteo](https://open-meteo.com/) melalui Forecast API.

Koordinat yang digunakan untuk mewakili Kota Malang:

- Latitude: `-7.9666`
- Longitude: `112.6326`
- Timezone: `Asia/Jakarta`
- Interval data: satu jam

Variabel cuaca yang dikumpulkan meliputi:

| Variabel | Deskripsi | Satuan |
|---|---|---|
| `time` | Waktu observasi cuaca | WIB |
| `temperature_2m` | Suhu udara pada ketinggian 2 meter | °C |
| `relative_humidity_2m` | Kelembapan relatif | % |
| `precipitation` | Total presipitasi | mm |
| `rain` | Curah hujan | mm |
| `cloud_cover` | Persentase tutupan awan | % |
| `wind_speed_10m` | Kecepatan angin pada ketinggian 10 meter | km/jam |
| `wind_direction_10m` | Arah angin pada ketinggian 10 meter | derajat |
| `pressure_msl` | Tekanan udara pada permukaan laut | hPa |

## Alur Data

Alur pengolahan data pada proyek ini adalah:

```text
Open-Meteo API
      │
      ▼
Data Ingestion
src/data/ingest_data.py
      │
      ▼
Raw Data
data/raw/open_meteo/
      │
      ▼
Cleaning dan Validation
src/data/preprocess.py
      │
      ▼
Processed Data
data/processed/
      │
      ▼
Feature Engineering
      │
      ▼
Model Training dan Evaluation
      │
      ▼
Model Artifact dan Prediction Service
```

Setiap hasil pengambilan data disimpan menggunakan timestamp pada nama file. Mekanisme ini mencegah data lama tertimpa ketika skrip ingestion dijalankan kembali.

## Struktur Direktori

Repository disusun menggunakan struktur proyek data science dan MLOps agar kode, data, model, konfigurasi, dan eksperimen tersimpan secara terpisah.

```text
MLOps-Rain-Prediction/
├── .devcontainer/
│   └── devcontainer.json       Konfigurasi GitHub Codespaces
├── .github/
│   └── workflows/              Workflow Continuous Integration
├── configs/                    Konfigurasi development dan production
├── data/
│   ├── raw/
│   │   ├── open_meteo/         Data mentah hasil ingestion
│   │   └── sample/             Sampel data mentah untuk repository
│   ├── processed/              Data yang telah dibersihkan
│   ├── quarantine/             Data yang gagal validasi
│   └── predictions/            Riwayat hasil prediksi
├── docs/                       Dokumentasi proyek dan arsitektur
├── frontend/                   Dashboard React, TypeScript, dan Vite
├── infrastructure/             Konfigurasi deployment dan monitoring
├── models/                     Artifact model machine learning lokal
├── notebooks/                  Notebook EDA dan eksperimen model
├── scripts/                    Skrip operasional proyek
├── src/
│   ├── data/
│   │   ├── ingest_data.py      Pengambilan data dari Open-Meteo
│   │   └── preprocess.py       Pembersihan dan validasi data
│   └── rain_prediction/
│       ├── api/                Backend FastAPI
│       ├── evaluation/         Evaluasi performa model
│       ├── features/           Feature engineering
│       ├── inference/          Proses inferensi model
│       ├── ingestion/          Komponen pengambilan data
│       ├── monitoring/         Monitoring data dan model
│       ├── schemas/            Kontrak dan validasi data
│       └── training/           Training model
├── tests/                      Pengujian unit dan integrasi
├── docker-compose.yml          Orkestrasi container aplikasi
├── pyproject.toml              Konfigurasi dan dependency Python
└── uv.lock                     Versi dependency Python yang dikunci
```

Data runtime berukuran besar, model hasil training, file environment, serta informasi rahasia tidak disimpan langsung di Git. Repository hanya menyimpan sampel data yang diperlukan sebagai bukti dan contoh struktur.

## Menjalankan Proyek dengan GitHub Codespaces

GitHub Codespaces menyediakan lingkungan pengembangan berbasis cloud sehingga proyek dapat dijalankan tanpa memasang seluruh dependency secara manual di komputer lokal.

### Membuat Codespace

1. Buka repository ini di GitHub.
2. Klik tombol **Code**.
3. Pilih tab **Codespaces**.
4. Klik **Create codespace on main**.
5. Tunggu proses pembuatan container dan `postCreateCommand` selesai.
6. Buka terminal di dalam Codespaces.

Konfigurasi `.devcontainer/devcontainer.json` akan menyiapkan:

- Python 3.11;
- Node.js 22;
- `uv` sebagai package manager Python;
- dependency untuk pengolahan data, backend, EDA, dan testing;
- dependency frontend;
- ekstensi Python, Pylance, Jupyter, GitLens, dan Docker.

### Verifikasi Environment

Jalankan perintah berikut melalui terminal Codespaces:

```bash
python --version
node --version
uv --version
```

Pastikan dependency utama dapat digunakan:

```bash
uv run --frozen --extra dev python -c "import pandas, sklearn, fastapi, httpx; print('Environment siap')"
```

Jika environment berhasil dikonfigurasi, terminal akan menampilkan:

```text
Environment siap
```

## Menjalankan Data Ingestion

Skrip ingestion mengambil data cuaca terbaru dari Open-Meteo dan menyimpannya sebagai data mentah.

Jalankan:

```bash
uv run python src/data/ingest_data.py
```

Hasil pengambilan data disimpan pada:

```text
data/raw/open_meteo/
```

Contoh nama file:

```text
open_meteo_20260928T140500Z.json
```

Timestamp pada nama file membuat proses ingestion bersifat non-destructive. Menjalankan skrip kembali akan membuat file baru dan tidak menimpa data sebelumnya.

Jalankan skrip minimal dua kali untuk membuktikan bahwa setiap proses ingestion menghasilkan file yang berbeda:

```bash
uv run python src/data/ingest_data.py
uv run python src/data/ingest_data.py
```

Kemudian periksa hasilnya:

```bash
ls -lah data/raw/open_meteo/
```

## Menjalankan Preprocessing

Skrip preprocessing membaca data mentah terbaru, melakukan validasi, membersihkan data, dan menyimpan hasilnya sebagai CSV.

Jalankan:

```bash
uv run python src/data/preprocess.py
```

Proses preprocessing meliputi:

1. Memeriksa kelengkapan kolom.
2. Mengubah waktu menjadi format datetime.
3. Mengubah variabel cuaca menjadi tipe numerik.
4. Menghapus baris duplikat berdasarkan waktu.
5. Mengurutkan data berdasarkan waktu observasi.
6. Menangani nilai kosong.
7. Memeriksa rentang nilai yang tidak valid.
8. Menyimpan data bersih ke folder `data/processed/`.
9. Memindahkan data bermasalah ke `data/quarantine/` jika validasi gagal.

Contoh pemeriksaan rentang nilai:

| Variabel | Rentang valid |
|---|---|
| `relative_humidity_2m` | 0–100% |
| `cloud_cover` | 0–100% |
| `precipitation` | Minimal 0 mm |
| `rain` | Minimal 0 mm |
| `wind_speed_10m` | Minimal 0 km/jam |
| `wind_direction_10m` | 0–360° |
| `pressure_msl` | Nilai positif |

Hasil preprocessing disimpan pada:

```text
data/processed/
```

Contoh nama file:

```text
weather_processed_20260928T140600Z.csv
```

## Menjalankan Pipeline Secara Berurutan

Untuk menjalankan ingestion dan preprocessing:

```bash
uv run python src/data/ingest_data.py
uv run python src/data/preprocess.py
```

Alur tersebut dapat dijalankan berulang kali untuk mengambil data cuaca terbaru. Pada tahap deployment, perintah yang sama dapat dipanggil secara periodik menggunakan scheduler seperti cron atau GitHub Actions.

Contoh jadwal pengambilan data:

```text
Setiap 3 jam
      │
      ├── Jalankan ingest_data.py
      ├── Simpan raw data baru
      ├── Jalankan preprocess.py
      └── Simpan processed data baru
```

Automasi scheduler belum menjadi bagian utama implementasi tahap ini, tetapi skrip telah dirancang agar aman dijalankan berulang kali.

## Sampel Data

Karena data hasil ingestion terus bertambah, seluruh data runtime tidak disimpan ke Git.

Satu sampel data mentah disediakan pada:

```text
data/raw/sample/open_meteo_sample.json
```

Sampel tersebut berfungsi sebagai:

- bukti keberhasilan akses Open-Meteo API;
- contoh skema data mentah;
- data pengujian untuk preprocessing;
- referensi bagi pengembang lain.

## Menjalankan Pengujian

Jalankan pengujian Python:

```bash
uv run --frozen --extra dev pytest
```

Jalankan pemeriksaan kualitas kode:

```bash
uv run --frozen --extra dev ruff check .
```

Jalankan pengujian dan build frontend:

```bash
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

## Menjalankan Aplikasi

### Backend FastAPI

Jalankan backend:

```bash
uv run uvicorn rain_prediction.api.main:app --host 0.0.0.0 --port 8000
```

Dokumentasi interaktif API dapat dibuka melalui port `8000` pada menu **Ports** di Codespaces.

### Frontend

Buka terminal kedua, kemudian jalankan:

```bash
npm --prefix frontend run dev -- --host 0.0.0.0
```

Dashboard dapat dibuka melalui port `5173` pada menu **Ports**.

### Docker Compose

Seluruh aplikasi juga dapat dijalankan menggunakan:

```bash
docker compose up --build
```

Dashboard tersedia melalui port `8080`, sedangkan backend tersedia melalui port `8000`.

Untuk menghentikan aplikasi:

```bash
docker compose down
```

## Versioning Data

Pada tahap ini, versi data dibedakan menggunakan:

1. Timestamp pada nama file.
2. Metadata waktu pengambilan data.
3. Pemisahan antara data mentah dan data hasil preprocessing.
4. Sampel data yang dicatat dalam riwayat Git.

Contoh:

```text
data/raw/open_meteo/open_meteo_20260928T140500Z.json
data/processed/weather_processed_20260928T140600Z.csv
```

Pada tahap berikutnya, data akan dikelola menggunakan DVC agar setiap versi dataset dapat dihubungkan dengan commit Git tanpa memasukkan seluruh file berukuran besar ke repository.

## GitHub Flow

Proyek menggunakan GitHub Flow untuk menjaga agar perubahan dapat ditinjau dan divalidasi sebelum masuk ke branch `main`.

Alur pengembangan:

1. Memperbarui branch `main`.
2. Membuat branch eksperimen atau fitur.
3. Melakukan perubahan dalam commit yang terpisah dan informatif.
4. Push branch ke GitHub.
5. Membuat pull request.
6. Memastikan seluruh pemeriksaan Continuous Integration berhasil.
7. Merge pull request setelah perubahan tervalidasi.
8. Menghapus branch yang telah selesai digunakan.

Contoh membuat branch untuk implementasi pipeline data:

```bash
git switch main
git pull origin main
git switch -c feat/data-ingestion-pipeline
```

Contoh commit:

```bash
git add src/data/ingest_data.py
git commit -m "feat: add Open-Meteo data ingestion"

git add src/data/preprocess.py
git commit -m "feat: add weather data preprocessing"

git add data/raw/sample README.md .gitignore
git commit -m "docs: document data ingestion pipeline"
```

Push branch:

```bash
git push -u origin feat/data-ingestion-pipeline
```

Setelah itu, buat pull request dari `feat/data-ingestion-pipeline` menuju `main` melalui GitHub.

## Continual Learning

Pipeline data dirancang sebagai fondasi continual learning. Ketika dijalankan secara berkala, sistem akan memperoleh data cuaca baru tanpa menghapus data sebelumnya.

Data baru tersebut nantinya dapat digunakan untuk:

1. Memperbarui dataset training.
2. Mendeteksi perubahan distribusi data.
3. Mengevaluasi penurunan performa model.
4. Menjalankan training ulang ketika kondisi retraining terpenuhi.
5. Membandingkan model baru dengan model yang sedang digunakan.

Implementasi retraining otomatis dan monitoring model akan dilakukan pada tahap pengembangan MLOps berikutnya.

## Catatan Penggunaan

- Jangan menyimpan API key, password, atau informasi rahasia di repository.
- Open-Meteo tidak membutuhkan API key untuk penggunaan dasar.
- Data pada `data/raw/open_meteo/` dan `data/processed/` merupakan data runtime.
- Hanya sampel data berukuran kecil yang dimasukkan ke Git.
- Hasil prediksi proyek ini bukan peringatan cuaca resmi.

## Lisensi

Proyek ini menggunakan MIT License. Ketentuan lengkap tersedia pada file `LICENSE`.