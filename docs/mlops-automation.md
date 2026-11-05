# LK-08: Code as a Trigger

## Alur yang diimplementasikan

Perubahan source, tests, konfigurasi training, pointer DVC, dependency, atau
workflow memicu `.github/workflows/mlops-automation.yaml` melalui PR ke main
atau push ke main. Perubahan README saja tidak memicu training.

1. `test`: menjalankan pytest dengan dependency dari uv.lock.
2. `training` menunggu test sukses, lalu mengambil dataset tepat sesuai pointer
   `data/raw/open_meteo_history.dvc` pada commit yang diuji.
3. Preprocessing membangun ulang fitur di direktori baru milik runner. Dataset
   lokal atau file processed lama tidak menjadi input tersembunyi.
4. `automated_train.py` memanggil train.py dengan hyperparameter dari
   `configs/automated-training.json`. Train.py menulis Run ID, model URI dan
   SHA-256 processed file sehingga evaluator tidak memilih run terbaru secara acak.
5. Evaluator memeriksa run FINISHED, validation PR-AUC/F1, kepemilikan model,
   digest dataset, dan inference model dengan contoh input yang tercatat di MLflow.
6. Hanya push ke main yang telah lolos yang mendaftarkan model ke
   `rain-risk-classifier-ci`, stage Staging. PR hanya melatih dan mengevaluasi.
   Workflow manual juga hanya mengevaluasi. Kontribusi fork mendapat unit test
   tanpa akses kredensial.

Registry CI sengaja memiliki nama sendiri. Registry Production, alias champion,
dan model VM tidak diganti oleh workflow. Staging adalah kandidat yang masih
memerlukan persetujuan sebelum diterapkan. Stage legacy tetap digunakan karena
diminta tugas; alias saja bukan bukti transisi stage.

## Kebijakan evaluasi yang perlu direview

PR-AUC >= 0.90 DAN F1 >= 0.82 pada validation. Angka ini adalah **usulan**
berdasarkan champion LK-06, bukan klaim bahwa LK-01 memuat angka tersebut.
Cocokkan dengan dokumen LK-01 sebelum menerima PR. Threshold performa berbeda
dengan decision threshold probabilitas atau rain threshold 0.1 mm.
Nilai hilang, NaN, infinity, di luar [0,1], atau threshold tidak valid ditolak.
Test set tidak digunakan sebagai gate pemilihan hyperparameter.

Data "terbaru" berarti versi dataset yang ditunjuk commit Git, bukan mengunduh
ulang API cuaca setiap workflow. Untuk memperbarui data, jalankan ingestion,
`dvc add`, `dvc push`, lalu commit pointer. Data minimal harus cukup untuk tiga
annual holdout sesuai trainer. Ingestion per jam bukan retraining per jam.

## Prasyarat layanan eksternal

Checkout awal belum memiliki DVC remote. Workflow tidak dapat mengambil isi
dataset hanya dari file .dvc. Localhost laptop juga tidak dapat diakses runner.
Gunakan DagsHub repository yang kamu miliki (atau endpoint yang kompatibel):

1. Hubungkan GitHub repository melalui akun DagsHub. Salin URL dari menu Remote.
   Jangan mengasumsikan nama akun DagsHub sama dengan GitHub.
2. Tambahkan GitHub **Actions variables**:
   - `MLFLOW_TRACKING_URI`: `https://dagshub.com/USER/REPO.mlflow`
   - `DVC_REMOTE_URL`: `s3://dvc`
   - `DVC_ENDPOINT_URL`: `https://dagshub.com/USER/REPO.s3`
3. Tambahkan GitHub **Actions secrets**:
   - `DAGSHUB_USERNAME`: username DagsHub sebenarnya.
   - `DAGSHUB_TOKEN`: token milik akun dengan akses repository tersebut.
4. Dari WSL, upload dataset sekali. Ambil endpoint aktual dari DagsHub:

```bash
uv run --frozen --extra dev dvc remote add --local ci s3://dvc
uv run --frozen --extra dev dvc remote modify --local ci endpointurl https://dagshub.com/USER/REPO.s3
read -r -s -p 'DagsHub token: ' AWS_ACCESS_KEY_ID
export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY="$AWS_ACCESS_KEY_ID"
uv run --frozen --extra dev dvc push -r ci data/raw/open_meteo_history.dvc
uv run --frozen --extra dev dvc status -c -r ci data/raw/open_meteo_history.dvc
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
```

Token tidak ditulis ke repo. `.dvc/config.local` diabaikan Git. Instalasi memakai
dvc-s3 yang telah dicatat pada pyproject.toml dan uv.lock. Server MLflow DagsHub
harus kompatibel dengan client MLflow 3.17.0; cek satu run sebelum merge.

## Verifikasi lokal yang terisolasi

```bash
UV_BIN=/home/attacker/.local/bin/uv bash scripts/verify_mlops_automation.sh
```

Script menguji pytest, push ke filesystem DVC remote sementara, pull dengan cache
kosong, preprocessing ulang, train.py, evaluation dan Staging. SQLite, cache,
model dan log pengujian hanya berada di direktori audit baru `artifacts/`.
Registry LK-07 dan Production tidak diubah. Hasil lokal bukan bukti bahwa GitHub
Actions telah berhasil; bukti cloud baru diambil setelah variables/secrets siap.

## Review, simulasi dan screenshot

1. Review policy, workflow dan kode. Commit di branch `feat/mlops-code-trigger`.
2. Push branch dan buat PR ke main setelah layanan siap. Workflow otomatis berjalan.
   Simpan screenshot PR/check dan log Pytest.
3. Ubah `n_estimators` pada `configs/automated-training.json` dari 500 ke 550,
   commit dan push lagi. Ini perubahan kode/konfigurasi yang memicu run baru.
   Tidak perlu menekan Run workflow untuk membuktikan Code as a Trigger.
4. Screenshot run otomatis sukses, log DVC pull/preprocessing/training, dan
   `MODEL VALIDATION PASSED`. Salin URL run, bukan hanya halaman daftar Actions.
5. Merge PR setelah review. Push ke main memicu training ulang dan registrasi Staging.
   Screenshot log register, source commit, dan daftar versi Staging di MLflow.
6. Download artifact `mlops-evaluation-RUN_ID-ATTEMPT`: run.json, evaluation.json,
   konfigurasi training, dan pointer DVC. Retensi 30 hari; simpan salinan untuk tugas.
7. Kumpulkan workflow YAML, URL run sukses, serta PDF refleksi dari naskah
   `docs/lk08-refleksi.md`. Jangan menuliskan URL sukses sebelum run benar-benar ada.

## Kegagalan yang harus terlihat

Konfigurasi kosong, DVC pull gagal, test gagal, run belum selesai, metrik buruk,
digest berbeda, smoke test gagal dan registry gagal semuanya menghentikan workflow.
Tidak ada `continue-on-error` pada tahap tersebut. Laporan evaluasi diupload bahkan
saat evaluasi gagal. Unit tests memastikan gate gagal tidak memanggil registrasi.

Threshold tidak bisa mendeteksi semua silent failure. Model yang lolos holdout
masih perlu monitoring prediksi dan delayed label setelah deployment. Pipeline ini
menyaring kandidat; tidak mengklaim bahwa performa produksi akan selalu sama.
