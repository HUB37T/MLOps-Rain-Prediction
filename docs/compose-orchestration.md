# Orkestrasi Docker Compose pada VM

## Komponen dan alur

| Service | Fungsi | Dependensi startup | Penyimpanan |
|---|---|---|---|
| mlflow | Metadata eksperimen, registry, artefak | Tidak ada | data/mlflow/backend dan data/mlflow/artifacts |
| backend | API cuaca dan hasil prediksi SQLite | mlflow service_healthy | data/predictions |
| frontend | Dashboard dan proxy /api ke backend | backend service_healthy | Static build dalam image |

Semua layanan memakai custom bridge rain-network. Docker menambahkan prefix
project pada nama network agar beberapa stack tidak bertabrakan. Nama DNS
service tetap mlflow, backend dan frontend; jangan mengunci IP container.
Urutan startup ditentukan healthcheck, bukan delay sleep yang tetap.

Penyimpanan bind dipilih agar data VM yang sudah digunakan tetap terbaca.
Nama file utama menjadi docker-compose.yaml; file .yml lama diganti, bukan
dipertahankan sebagai manifest kedua. Nama project tetap diturunkan dari folder
repository seperti sebelumnya, sehingga stack lama bisa diperbarui.

## Batas fitur yang benar-benar diuji

Backend menyajikan prediksi yang telah ditulis hourly pipeline di host VM.
Pada tugas ini komunikasi antar-container diuji dengan backend mengakses
http://mlflow:5000/health dan API pencarian metadata eksperimen MLflow, serta
http://frontend/healthz. Ini bukti service discovery dan HTTP antar-service.
Jangan menulis bahwa backend mengambil model dari MLflow atau menjalankan
inference on-demand apabila fitur itu belum diimplementasikan.

depends_on mengatur urutan startup. Bila tracking down setelah startup, API
tetap dapat menyajikan hasil prediksi yang sudah tersimpan; startup dependency
bukan jaminan seluruh dependency akan selalu tersedia selama runtime.

## Persiapan VM

Kerjakan setelah PR orkestrasi selesai direview dan di-merge. Tidak perlu
mengubah atau menghapus model, SQLite prediksi maupun timer hourly pipeline.

```bash
cd ~/MLOps-Rain-Prediction
git status --short
```

Jika Compose lama dimodifikasi langsung di VM, simpan salinannya di luar repo
sebelum mengambil pembaruan. Jangan menggunakan reset --hard.

```bash
cp docker-compose.yml "$HOME/docker-compose-before-orchestration-$(date -u +%Y%m%dT%H%M%SZ).yml"
git diff -- docker-compose.yml
git stash push -m "VM Compose before orchestration update" -- docker-compose.yml
```

Jalankan blok backup hanya bila file lama masih ada dan memang memiliki perubahan
lokal. Jangan otomatis mengembalikan stash ke file baru; bandingkan pengaturan
port dan konfigurasi khusus VM terlebih dahulu. Bila ada perubahan lain, simpan
atau commit perubahan tersebut sebelum melanjutkan pull.

```bash
git switch main
git pull --ff-only origin main
docker compose version
mkdir -p data/predictions data/mlflow/backend data/mlflow/artifacts
docker compose config --quiet
```

Gunakan Docker Compose plugin modern yang mendukung up --wait. Jika belum ada
pada Ubuntu yang memakai repository Docker resmi, instal docker-compose-plugin
melalui apt. Jangan menjalankan stack lain dengan port host yang sama.

## Jalankan seluruh sistem dengan satu perintah

```bash
docker compose up -d --build --wait --wait-timeout 240
```

Konfigurasi memakai image MLflow 3.17.0 yang sama dengan stack sebelumnya.
API/UI dibuild dari source. MLflow sehat lebih dulu, kemudian backend dan frontend.
Backend memakai dependency inti dari uv.lock melalui uv sync --frozen; dependency
notebook, training dan GPU tidak dipasang pada image API. Ini mencegah build
mengambil versi library baru yang berbeda dari pengujian proyek.
Jika startup gagal, periksa `docker compose logs --tail=100 mlflow backend frontend`;
jangan menghapus database untuk mengatasi error schema atau permission.

## Verifikasi dan screenshot wajib

```bash
docker compose ps
```

Screenshot 1: ketiga service Up, backend dan MLflow healthy, port sesuai.

```bash
python3 scripts/verify_compose.py
```

Screenshot 2: backend_to_mlflow_health 200, backend_to_mlflow_metadata OK,
backend_to_frontend_health 200 dan VERIFICATION PASSED. Permintaan berasal dari
container backend melalui DNS service, bukan port publik VM.

## Verifikasi penyimpanan persisten

Lakukan ketika downtime singkat diperbolehkan. Flag ini sengaja tidak menjadi
perilaku default karena container VM akan dibuat ulang.

```bash
python3 scripts/verify_compose.py --persistence
```

Script membuat satu eksperimen bernama lk-compose-verification-UUID dan penanda
unik pada tiga mount data. Selanjutnya hanya container project ini yang
di-recreate melalui up --force-recreate --no-build --wait. Tidak ada penghapusan
volume/direktori. Setelah sehat, script memeriksa isi penanda dan ID eksperimen
yang sama masih ada, lalu menguji komunikasi kembali.

Screenshot 3: persistence status passed dan docker compose ps setelah recreate.
Laporan JSON: artifacts/compose-verification/report-TIMESTAMP.json. Penanda dan
eksperimen verifikasi tetap disimpan sebagai bukti; bukan data model baru.

## Akses dashboard dan MLflow

- Dashboard: http://IP_VM:8080 (atau WEB_PORT sesuai .env).
- API docs: http://IP_VM:8000/docs (atau API_PORT).
- MLflow terikat ke loopback VM. Dari laptop: `ssh -L 5000:127.0.0.1:5000 member@IP_VM`,
  kemudian buka http://127.0.0.1:5000. Pilih port lokal lain bila 5000 sudah dipakai.

Variabel opsional API_PORT, WEB_PORT, MLFLOW_PORT dan tiga DATA_DIR terdapat pada
.env.example. Default DATA_DIR tetap memakai direktori VM lama. Jangan mengubah
DATA_DIR saat demonstrasi lalu mengira data hilang, karena perubahan itu memilih
penyimpanan host yang berbeda.

## Luaran laporan

Kumpulkan docker-compose.yaml dari GitHub, PDF dengan screenshot 1 dan 2
(ditambah screenshot 3 agar bukti persistensi kuat), serta README yang sudah
menjelaskan satu perintah startup. Catat hasil VM sesungguhnya; validasi manifest
di laptop tidak menggantikan screenshot container yang berjalan di VM.

Pemeriksaan manifest lokal tanpa menjalankan container:

```bash
python3 -m unittest discover -s infrastructure/tests -v
```
