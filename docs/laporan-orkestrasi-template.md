# Orkestrasi Layanan MLOps Menggunakan Docker Compose

Nama: [isi nama]
NIM: [isi NIM]
Tanggal pengujian VM: [isi setelah pengujian]

## Konfigurasi Sistem

File docker-compose.yaml digunakan untuk menjalankan backend, frontend, dan
MLflow dalam satu sistem. Ketiga layanan terhubung melalui custom bridge
rain-network, sehingga komunikasi dapat menggunakan nama layanan tanpa
bergantung pada alamat IP container.

MLflow dijalankan lebih dahulu dan diperiksa melalui healthcheck. Setelah
MLflow sehat, backend dimulai, kemudian frontend menunggu backend sehat.
Database prediksi, database MLflow, dan artefak menggunakan bind mount agar
tetap tersimpan pada direktori data VM saat container dibuat ulang.

## Status Layanan

[Masukkan screenshot docker compose ps dari VM]

Gambar 1. Status layanan setelah Docker Compose dijalankan.

[Lengkapi berdasarkan hasil nyata: status backend, frontend, MLflow dan portnya.]

## Komunikasi Antar-Container

[Masukkan screenshot python3 scripts/verify_compose.py dari VM]

Gambar 2. Pengujian komunikasi backend ke MLflow dan frontend melalui nama layanan.

Skrip mengirim permintaan dari dalam container backend ke API metadata MLflow
pada http://mlflow:5000 dan health endpoint frontend pada http://frontend/healthz.
Pengujian ini memeriksa service discovery serta akses HTTP antar-container.
[Tambahkan hasil HTTP dan status verifikasi yang muncul pada terminal VM.]

## Penyimpanan Persisten

[Masukkan screenshot python3 scripts/verify_compose.py --persistence dari VM]

Gambar 3. Pemeriksaan metadata eksperimen dan file penanda setelah recreate.

Skrip membuat metadata eksperimen serta penanda pada tiga mount data, lalu
membuat ulang container tanpa menghapus penyimpanan host. Setelah layanan
kembali sehat, ID eksperimen dan isi penanda diperiksa kembali.
[Isi hasil nyata dari field persistence dan lokasi laporan JSON.]

## Kesimpulan

[Lengkapi setelah seluruh pengujian selesai. Nyatakan hanya komponen yang
benar-benar berhasil diuji. API saat ini membaca hasil prediksi dari SQLite;
inference tetap dijalankan hourly pipeline pada host. Jangan menyatakan API
menarik model dari Registry bila yang diuji hanya akses metadata MLflow.]
