# Hasil Pengujian LK-10 — Model Serving dan Replikasi

Pengujian dilakukan pada 26 November 2026 di WSL laptop. Model yang digunakan
adalah `rain-risk-classifier` versi 2, berstatus **Production** pada registry
LK-07, dengan run ID `ae0a53c91f30442a8d5d178f79baa3d7`.
Model tersebut memiliki signature 60 fitur dan diekspor sebagai versi tetap
sebelum pengujian API dan pembuatan image.

## Pengujian REST API

[Masukkan screenshot input dan output permintaan `/invocations`.]

Model dijalankan sebagai API lokal menggunakan `mlflow models serve` pada
port 5003. Permintaan menggunakan dua sampel dari input example yang
tersimpan bersama model, sehingga nama dan tipe fiturnya mengikuti signature
model. API mengembalikan HTTP 200 dengan respons `{"predictions": [1, 0]}`.
Hasil tersebut sama dengan prediksi langsung dari model yang diekspor.
Pengujian input yang kekurangan fitur menghasilkan HTTP 400, sehingga input
yang tidak sesuai skema tidak diproses sebagai prediksi yang sah.

Setelah pengujian lokal, image `rain-risk-model:v2` dibangun menggunakan
`mlflow models build-docker --env-manager local`. Image ID yang diperoleh:

```text
sha256:20b66b8a58c483107a9fc6384ee279e91018adec416f3e1620c588fdc5f5c172
```

## Tiga Replika dan Pembagian Permintaan

[Masukkan screenshot `docker compose --profile serving ps model-api model-gateway`.]

Konfigurasi `deploy.replicas: 3` menjalankan tiga container `model-api` secara
bersamaan. Ketiganya berstatus **Up (healthy)** dan memakai image serta
artefak model yang sama. Satu gateway Nginx menerima permintaan pada port
5001, kemudian meneruskannya ke replika melalui nama service pada jaringan
Docker. Dengan cara ini, replika tidak perlu memakai host port yang sama.

| Pengujian | Hasil |
|---|---|
| API lokal MLflow | HTTP 200, prediksi `[1, 0]` |
| Input tidak lengkap | HTTP 400 |
| Jumlah replika awal | 3, seluruhnya healthy |
| 30 permintaan melalui gateway | 30 berhasil, masing-masing replika menerima 10 |
| Scaling menjadi 4 replika | 4 healthy, 40 permintaan berhasil, masing-masing menerima 10 |
| Dikembalikan menjadi 3 replika | 3 healthy, pengujian ulang 30 permintaan berhasil |
| Kesamaan artefak | SHA-256 model dalam setiap container sama dengan hasil ekspor |
| Pemeriksaan kode | 59 tes backend dan 12 pemeriksaan infrastruktur lulus |

Fingerprint lengkap artefak model:

```text
49fc0cf68a77db018a1ee54ade54feeb4d1ae960ae735882db95efbc0095fd66
```

Alamat IP container dapat berubah ketika dibuat ulang. Pemeriksaan pembagian
permintaan menggunakan header `X-Model-Upstream`, kemudian mencocokkannya
dengan alamat container yang benar-benar hidup. Setelah scale-down, DNS
gateway memerlukan waktu pembaruan; permintaan pada masa transisi dapat
menghasilkan HTTP 502. Pengujian akhir dilakukan setelah DNS kembali stabil.

## Kesimpulan

Model Production berhasil disajikan sebagai REST API melalui MLflow Models
dan dikemas menjadi Docker image. Docker Compose berhasil menjalankan tiga
replika model, sedangkan gateway menyediakan satu endpoint untuk mengakses
ketiganya. Pengujian juga menunjukkan jumlah replika dapat ditambah dan
dikurangi tanpa mengubah model yang disajikan. Hasil ini membuktikan fungsi
serving dan replikasi pada satu host; pengujian tersebut belum merupakan
benchmark kapasitas produksi atau pengujian sistem pada banyak mesin.

Output model pada pengujian ini adalah label kelas dari fungsi `predict`
model sklearn. Endpoint ini menerima fitur yang sudah diproses dan tidak
menjalankan pengambilan cuaca atau menggantikan pipeline dashboard.

## Lokasi Bukti Lokal

Direktori `artifacts/model-serving/` menyimpan `release.json`, `request.json`,
`expected.json`, log `build-docker.log`, hasil `compose-ps-final.txt`,
`api-response.txt`, dan laporan JSON verifikasi. Bukti lokal ini tidak
diunggah sebagai artefak model besar ke Git.
