# LK-11 | Observabilitas model hujan

Gunakan folder proyek asli di WSL dengan Docker berbasis Linux cgroup v2.
Siapkan image dasar LK-10 dan sampel input dari registry sesuai
[panduan model serving](mlflow-serving-scaling.md).

```bash
docker compose --profile serving build model-api
docker compose --profile serving --profile monitoring up -d --no-deps \
  --wait --wait-timeout 360 model-api model-gateway prometheus grafana
docker compose --profile monitoring exec -T prometheus \
  promtool check config /etc/prometheus/prometheus.yml
```

Image `rain-risk-model:v2-observed` memakai artefak dari image LK-10.
Satu worker Uvicorn per replika menjalankan scoring app MLflow di port 8080.
Gateway LK-10 masih menerima inferensi pada port 5001. Prometheus menemukan
alamat tiap replika dari DNS Docker, lalu melakukan scrape `/metrics`
setiap 5 detik. Grafana memakai datasource dan dashboard yang otomatis
dimuat dari file provisioning. Database Prometheus dan Grafana tersimpan
di volume Compose. Retensi Prometheus adalah 7 hari dengan batas 512 MB.

Grafana tersedia sebagai Viewer lokal tanpa login. Kedua antarmuka
monitoring terikat pada loopback. Atur `GRAFANA_PORT` atau
`PROMETHEUS_PORT` bila port host sudah dipakai. Gunakan profil
`monitoring` saat ingin menyalakan kedua layanan ini.

## Pengujian dan bukti

```bash
python3 scripts/verify_model_serving.py --replicas 3 --requests 30
python3 scripts/simulate_model_traffic.py
```

Skrip pertama memeriksa kesehatan setiap replika, fingerprint artefak,
hasil inferensi, dan distribusi permintaan. Skrip kedua memakai dua sampel
historis LK-10 untuk menghasilkan trafik selama dua fase. Fase awal
menargetkan 3 request/detik dengan komposisi kelas 50/50. Fase kedua
menargetkan 12 request/detik dengan komposisi 75% kelas hujan.
Perubahan komposisi ini disengaja untuk memperlihatkan respons grafik.
Jika port gateway diubah, teruskan `--port` ke skrip simulasi.

1. Buka [Grafana](http://127.0.0.1:3300/d/rain-model-lk11/rain-risk-7c-observabilitas-model)
   dan pilih rentang yang mencakup simulasi. Ambil screenshot panel latensi,
   throughput, CPU, RAM, distribusi kelas, dan jumlah replika.
2. Buka [Prometheus Targets](http://127.0.0.1:9090/targets). Ambil screenshot
   grup `mlflow-model` dengan tiga target `UP` pada endpoint `/metrics`.

## Membaca metrik

| Metrik | Cara membaca |
| --- | --- |
| Latensi p50/p95 | Waktu MLflow untuk validasi input, inferensi, dan serialisasi respons sukses. p95 menunjukkan batas yang mencakup sekitar 95% permintaan sukses. |
| Throughput per replika | Laju POST `/invocations` pada tiap alamat container. Gunakan bersama status target untuk memeriksa distribusi. |
| CPU per replika | Laju konsumsi CPU dari cgroup. 100% setara satu inti CPU. |
| RAM per replika | Memori yang ditagihkan ke cgroup, termasuk cache, dibagi batas 768 MiB per container. |
| Distribusi kelas | Proporsi keluaran 0 (tidak hujan) dan 1 (hujan) pada jendela 30 detik. |

Rules pada halaman [Prometheus Alerts](http://127.0.0.1:9090/alerts)
memberi sinyal jika kurang dari tiga replika dapat di-scrape selama satu
menit atau jika sedikitnya tiga respons 5xx terdeteksi dalam dua menit
dan kondisinya bertahan 30 detik. Kelola ambang replika bersama target
skala konfigurasi. Status peringatan dapat dilihat di Prometheus.

## Analisis model decay

Untuk menemukan perubahan yang patut diperiksa, pantau proporsi prediksi
hujan terhadap periode pembanding pada lokasi, jam, dan musim yang serupa.
Jika proporsinya berubah terus, cek juga distribusi fitur masukan seperti
kelembapan dan curah hujan, serta kelengkapan dan kesegaran data. Pergeseran
keluaran bisa berasal dari perubahan kondisi cuaca atau komposisi trafik.
Simulasi LK ini mengubah komposisi trafik secara sengaja.

Untuk mengukur model decay, cocokkan prediksi dengan label hujan aktual
sesudah horizon tiga jam selesai. Hitung F1, recall hujan, dan proporsi
alarm palsu pada jendela waktu bergulir dengan jumlah sampel yang cukup.
Bandingkan dengan performa referensi pada periode yang setara. Gunakan
probabilitas kelas hujan jika ingin menghitung PR-AUC. Tambahkan penurunan
metrik yang konsisten sebagai pemicu evaluasi kandidat model. Grafik
operasional dan distribusi kelas membantu memulai investigasi. Evaluasi
berbasis label diperlukan untuk memastikan penurunan akurasi.

Referensi [Prometheus DNS service discovery](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#dns_sd_config),
[Grafana provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/),
dan [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html).
