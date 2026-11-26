# LK-10 — Model Serving dan Horizontal Scaling

## Alur yang digunakan

Model Production di registry LK-07 → ekspor versi tetap dan contoh input asli →
`mlflow models serve` → uji `/invocations` → `mlflow models build-docker` →
tiga replika `model-api` → satu Nginx `model-gateway` pada port 5001.

Model API ini menerima fitur yang sudah diproses, termasuk lag dan rolling.
Ia tidak menerima koordinat lalu mengambil cuaca sendiri. Registry model
`rain-risk-classifier` versi 2 memiliki 60 fitur. PyFunc sklearn yang dicatat
pada LK-06 menggunakan `predict`, sehingga respons adalah label 0/1 dengan
aturan estimator, bukan probabilitas dan bukan keputusan memakai threshold
dashboard yang dituning. Endpoint ini merupakan demonstrasi serving LK-10;
dashboard tetap menggunakan hourly pipeline yang sudah ada.

Tiga replika meningkatkan jumlah proses yang dapat menerima permintaan.
Ketiganya masih berada pada satu mesin: ini simulasi horizontal scaling,
bukan penambahan kapasitas hardware atau perlindungan jika host mati.

## 1. Lingkungan dan registry

Jalankan di terminal Linux Codespaces atau WSL pada folder repo branch LK-10.
Docker Engine harus aktif. Gunakan environment training yang sama:

```bash
uv sync --frozen --extra ci
docker compose version
```

Sediakan akses ke registry LK-07. Jika model ada pada VM, buat SSH tunnel
dan gunakan URI tunnel tersebut. Jangan mengarahkan URI ke registry baru
yang kosong. Untuk registry lokal WSL yang sudah digunakan di LK-07, buka
terminal A dan jalankan:

```bash
export LOCAL_MLFLOW_ROOT="$HOME/mlflow-lk07"
uv run --frozen --extra ci mlflow server \
  --backend-store-uri "sqlite:///$LOCAL_MLFLOW_ROOT/mlflow.db" \
  --artifacts-destination "$LOCAL_MLFLOW_ROOT/artifacts" \
  --serve-artifacts --host 127.0.0.1 --port 5004 --workers 1
```

Ini membuka database dan artefak lama pada port 5004, bukan membuat salinan
model baru. Port 5000 tetap untuk tracking VM, 5003 untuk serving lokal,
dan 5001 untuk gateway model. Di terminal B:

```bash
export MLFLOW_TRACKING_URI=http://127.0.0.1:5004
uv run --frozen --extra ci python scripts/prepare_model_serving.py
```

Skrip mensyaratkan tepat satu versi READY berstatus Production. Versi itu
diunduh menggunakan URI bernomor, misalnya `models:/rain-risk-classifier/2`.
Direktori `artifacts/model-serving/` berisi model MLflow lengkap,
`release.json`, contoh `request.json` dari artefak input asli, dan respons
referensi `expected.json`. Skrip menolak output lama agar rilis tidak tertimpa.
Untuk rilis baru gunakan `--output artifacts/model-serving-v3`, lalu sesuaikan
path seluruh perintah berikut.

**Screenshot opsional:** daftar registry Production dan keluaran ekspor versi.

## 2. Serve model secara lokal

Di terminal B:

```bash
uv run --frozen --extra ci mlflow models serve \
  -m artifacts/model-serving/model \
  --env-manager local --host 127.0.0.1 --port 5003 --workers 1
```

Direktori lokal berasal dari model Production yang baru diekspor. Penggunaan
salinan versi tetap membuat uji lokal dan image membaca artefak yang sama.
`--env-manager local` memakai environment aktif; dependensinya harus cocok
dengan `model/requirements.txt`. Bila environment training berbeda, gunakan
environment yang sesuai, jangan abaikan peringatan ketidakcocokan library.

Di terminal C:

```bash
curl --fail-with-body -sS http://127.0.0.1:5003/ping
cat artifacts/model-serving/request.json
curl --fail-with-body -sS http://127.0.0.1:5003/invocations \
  -H 'Content-Type: application/json' \
  --data-binary @artifacts/model-serving/request.json
python3 scripts/verify_model_serving.py --url http://127.0.0.1:5003
```

**Screenshot wajib 1:** tampilkan input dan output prediksi. Input cukup
ditampilkan dengan dua baris sampel dan daftar fiturnya; output berupa
`{"predictions": [...]}`. Perintah verifikasi membandingkan HTTP output dengan
prediksi langsung dari model, kemudian menyimpan laporan JSON. Contoh ini
memakai sampel historis, bukan klaim prediksi cuaca terkini.

## 3. Bangun image menggunakan MLflow Models

Setelah uji lokal selesai, hentikan hanya proses serving terminal B dengan
Ctrl+C. Jangan hentikan registry yang masih diperlukan untuk eksperimen lain.

```bash
uv run --frozen --extra ci mlflow models build-docker \
  -m artifacts/model-serving/model -n rain-risk-model:v2 --env-manager local
docker image inspect rain-risk-model:v2 --format '{{.Id}}'
```

MLflow membungkus artefak dan dependensi model di dalam image. Model tidak
diunduh ulang saat tiap replika mulai; registry tidak harus hidup untuk
menjalankan image ini. Simpan keluaran build sebagai bukti penggunaan
`mlflow models build-docker`, bukan Dockerfile buatan tangan sebagai pengganti.
Pada build, `--env-manager local` berarti requirements model dipasang langsung
ke Python image yang dihasilkan MLflow; ini berbeda dari memakai environment
host saat menjalankan `models serve --env-manager local`.

## 4. Jalankan tiga replika

```bash
docker compose --profile serving config --quiet
docker compose --profile serving up -d --no-deps \
  --wait --wait-timeout 360 model-api model-gateway
docker compose --profile serving ps model-api model-gateway
```

Manifest menetapkan `deploy.replicas: 3` pada `model-api`. Setiap replika
memiliki satu worker dan memakai image yang sama. Service tidak memiliki
`container_name` maupun host port tetap, sehingga tidak terjadi bentrok port.
Nginx meneruskan permintaan ke `model-api:8080` melalui custom bridge
`rain-network`, dan memperbarui DNS ketika jumlah replika berubah.

Flag `--no-deps` dan nama layanan eksplisit digunakan untuk menyalakan bagian
LK-10 saja saat demonstrasi lokal. Perintah ini tidak perlu menyalakan ulang
backend, frontend, atau tracking VM. Tanpa profile `serving`, startup LK-09
tetap tidak memuat tiga model tambahan.

**Screenshot wajib 2:** hasil `docker compose ... ps` yang memperlihatkan
`model-api-1`, `model-api-2`, dan `model-api-3` dengan status **Up (healthy)**.

## 5. Uji endpoint bersama dan distribusi permintaan

```bash
curl --fail-with-body -sS -i http://127.0.0.1:5001/invocations \
  -H 'Content-Type: application/json' \
  --data-binary @artifacts/model-serving/request.json
python3 scripts/verify_model_serving.py --replicas 3 --requests 30
```

Skrip memeriksa jumlah, kesehatan dan image ID seluruh replika; mengirim
30 permintaan (maksimal enam bersamaan); membandingkan setiap hasil dengan
referensi; serta memastikan header `X-Model-Upstream` menunjukkan ketiga IP
replika menerima permintaan. Ini uji fungsi dan distribusi, bukan benchmark
throughput atau bukti sistem sudah tahan beban produksi.

Port gateway dibatasi ke localhost. Pada Codespaces, forward port 5001
secara privat. Untuk akses gateway VM dari laptop:

```bash
ssh -L 5001:127.0.0.1:5001 member@IP_VM
```

## 6. Tambah atau kurangi replika secara dinamis

```bash
docker compose --profile serving up -d --no-deps \
  --scale model-api=4 --wait --wait-timeout 360 model-api
docker compose --profile serving ps model-api
```

Setelah DNS gateway diperbarui (TTL lima detik), uji ulang:

```bash
sleep 6
python3 scripts/verify_model_serving.py --replicas 4 --requests 40
```

Kembalikan ke tiga untuk bukti LK:

```bash
docker compose --profile serving up -d --no-deps \
  --scale model-api=3 --wait --wait-timeout 360 model-api
sleep 6
python3 scripts/verify_model_serving.py --replicas 3 --requests 30
```

`--scale` adalah override pada perintah tersebut. Startup selanjutnya tanpa
override kembali mengikuti `deploy.replicas: 3` pada manifest.
Saat replika dihapus, gateway dapat sementara mencoba alamat lama sebelum
DNS diperbarui dan mengembalikan HTTP 502. Beri waktu propagasi tersebut
sebelum verifikasi. Simulasi ini tidak menerapkan connection draining atau
menjanjikan scale-down tanpa putus layanan.

## Kapasitas dan penghentian demonstrasi

Lakukan demonstrasi tiga replika di laptop atau Codespaces yang cukup RAM.
VM proyek sebelumnya hanya memiliki sekitar 1,6 GiB RAM efektif dan juga
menjalankan MLflow, dashboard serta hourly pipeline. Tambahan tiga model
dapat membebani VM. Untuk memindahkan demonstrasi ke VM, ukur pemakaian
memori dahulu dengan `docker stats`; salin image menggunakan `docker save`
dan `docker load` bila image dibangun di laptop. Jangan mengira image lokal
otomatis tersedia di VM setelah Git pull.

Untuk menghentikan hanya layanan demonstrasi:

```bash
docker compose --profile serving stop model-gateway model-api
```

## Luaran

- File `docker-compose.yaml`, konfigurasi gateway, dan README di GitHub.
- PDF singkat berisi screenshot input/output API dan tiga replika healthy.
- Bukti tambahan: keluaran build-docker, ringkasan versi Production,
  dan JSON verifikasi distribusi di `artifacts/model-serving/`.

Referensi: [MLflow Models CLI](https://mlflow.org/docs/latest/api_reference/cli.html),
[Compose deploy replicas](https://docs.docker.com/reference/compose-file/deploy/#replicas),
dan [NGINX upstream DNS resolve](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#resolve).
