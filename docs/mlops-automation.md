# LK-08: Code as a Trigger tanpa layanan tambahan

## Alur

GitHub Actions mengatur test -> DVC pull -> preprocessing -> train.py -> validasi
metrik dan smoke test -> registrasi Staging. Test memakai ubuntu-latest;
training memakai runner resmi dalam container Docker di WSL laptop.
Dependency CPU untuk workflow memakai extra `ci`; extra `dev` tetap menyediakan
XGBoost/LightGBM untuk eksperimen lain. Kedua library diimport hanya saat dipilih.
Tidak diperlukan VM, layanan cloud lain, Actions secrets atau variables.
Laptop, WSL dan Docker harus menyala; runner offline membuat job Queued.

Kandidat yang lolos pada PR pemilik repository dari repository yang sama,
push main, atau workflow manual otomatis masuk rain-risk-classifier-ci Staging.
Registry CI memakai SQLite dan volume permanen; nomor versi bertambah antar-run.
Registry LK-07 serta Production/champion VM tidak berubah. Fork/pihak lain hanya
menjalankan test pada runner GitHub, bukan kode training di laptop.

## Setup Windows + WSL

Prasyarat: Docker di WSL aktif, dependency project dan cache DVC tersedia,
serta akun GitHub login melalui Git Credential Manager dengan hak admin repo.
Personal access token tidak dicetak, disimpan script, atau diberikan ke runner.

Dari terminal Windows pada root repository:

```powershell
python scripts/local_actions_runner.py prepare
python scripts/local_actions_runner.py serve
```

Biarkan terminal serve menyala. Pada terminal lain:

```powershell
python scripts/local_actions_runner.py status
```

prepare membangun image Python 3.12 + uv + runner resmi. SHA-256 paket runner
diverifikasi terhadap GitHub API. Dataset dalam cache dipush ke filesystem
remote khusus tanpa mengubah konfigurasi checkout pengguna.

start mengambil registration token satu jam lewat GitHub API dan memberikannya
lewat stdin. Runner berlabel self-hosted, Linux, X64, rain-lk08 bersifat ephemeral:
otomatis unregister dan berhenti setelah satu training job. serve menyediakan
container baru otomatis setelah job selesai, sehingga commit berikutnya tidak
memerlukan start manual. start tersedia untuk pengujian satu job saja.

## Penyimpanan dan akses

State WSL: /home/attacker/.local/share/rain-mlops-ci/.

- dvc/: filesystem remote, dipasang read-only pada /dvc-remote.
- registry/: SQLite dan artefak MLflow pada /mlops-state/registry.
- uv-cache/: cache dependency untuk mempercepat job berikutnya.

Container tanpa privileged, tanpa Docker socket, tanpa mount home atau working
copy laptop. Checkout memakai token read-only dan persist-credentials false.
Jangan memperluas filter PR pemilik untuk menjalankan kode yang tidak dipercaya.

## MLflow UI

Setelah run sukses:

```powershell
python scripts/local_actions_runner.py ui
```

Buka http://127.0.0.1:5002. UI memakai volume registry yang sama. Hentikan dengan
`wsl docker stop rain-lk08-mlflow-ui`. Port hanya terikat pada localhost.

## Kebijakan evaluasi

PR-AUC >= 0.90 DAN F1 >= 0.82 pada validation adalah usulan berdasarkan LK-06.
Cocokkan dengan LK-01 sebelum mengadopsinya. Ini bukan decision threshold
probabilitas atau rain threshold 0.1 mm. Metrik hilang, NaN, infinity atau di luar
[0,1] ditolak. Test set dilaporkan, bukan dipakai untuk memilih kandidat.

Evaluator menggunakan Run ID/model URI yang tepat, mencocokkan SHA-256 processed
data dan pointer DVC yang dilog saat training, serta mencoba inference PyFunc.
Kegagalan test, DVC, training, evaluasi atau registrasi menghentikan workflow.

Data terbaru berarti versi yang ditunjuk commit, bukan mengunduh API setiap job.
Untuk dataset baru: ingestion, dvc add, ulangi prepare untuk push cache baru,
lalu commit pointer. Trainer tetap memerlukan tiga annual holdout.

## Simulasi dan screenshot tugas

1. Pastikan serve aktif dan push branch PR. Screenshot pemicu otomatis dan SHA.
2. Screenshot pytest, DVC pull, preprocessing dan training yang sukses.
3. Screenshot MODEL VALIDATION PASSED dan log registrasi stage Staging.
4. Screenshot versi baru rain-risk-classifier-ci pada MLflow UI localhost:5002.
5. Ubah n_estimators 500 -> 550 dalam configs/automated-training.json, commit,
   lalu push. Ini bukti perubahan kode memicu seluruh alur.
6. Simpan URL run sukses dan download artifact evaluasi (retensi 30 hari).
7. Setelah review boleh merge; serve menyiapkan runner untuk workflow push main.

Kumpulkan YAML, URL/log sukses dan PDF refleksi. Source PDF ada pada
docs/lk08-refleksi.md dan generator scripts/build_lk08_reflection.py.

## Verifikasi lokal tambahan

```bash
UV_BIN=/home/attacker/.local/bin/uv bash scripts/verify_mlops_automation.sh
```

Script menguji alur dengan DVC remote dan registry sementara. Ini bukti tambahan;
URL GitHub Actions yang selesai sampai Staging tetap diperlukan untuk tugas.
