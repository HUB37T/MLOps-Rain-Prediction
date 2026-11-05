# Catatan verifikasi lokal LK-08

Pengujian dilakukan pada 5 November 2026 menggunakan Python 3.12 di WSL.
Ini bukti lokal, bukan klaim keberhasilan GitHub Actions.

## Hasil yang sudah diamati

- Full pytest: 48 passed, satu warning deprecation Starlette/httpx dari dependency.
- actionlint pada workflow: lulus (shellcheck/pyflakes tidak diaktifkan).
- YAML parsed; dependency training -> test dan kedua filter paths valid.
- DVC push: dua cache objects; DVC pull ke cache kosong: dua objects diambil,
  satu file raw dipulihkan sesuai pointer dataset historis.
- Preprocessing raw historis: 26.304 baris valid, 26.294 siap training,
  nol quarantine dan nol raw file bermasalah.
- Training: Random Forest, 500 trees, max_depth 10, class_weight balanced,
  min_samples_leaf 2, max_features sqrt, random_state 42.
- Validation PR-AUC: 0.9200854601149122.
- Validation F1: 0.8378464479133482.
- Test PR-AUC: 0.9319301112659721 (dilaporkan, bukan gate).
- Test F1: 0.8504804612427931 (dilaporkan, bukan gate).
- Decision threshold: 0.44753426103920146.
- Evaluator memuat model dari logged model URI MLflow 3 dan memverifikasi
  inference, processed SHA-256 serta pointer DVC yang dilog saat training.
- Registry lokal `rain-risk-classifier-ci-local`: Version 1 terkonfirmasi Staging,
  report `passed=true`, `registered=true`, dan `errors=[]`.

Audit pertama ada di `artifacts/automation-local-6Ncd5P/`: tests.log, dvc.log,
preprocess.log, train.log, run.json, registry.log, evaluation.json dan SQLite.
Source revision diberi suffix `-working-tree` karena pengujian dilakukan
sebelum commit. Report tidak dipresentasikan sebagai hasil commit GitHub final.

## Yang masih diperlukan untuk bukti tugas

Daftar Actions variables dan secrets di GitHub telah dicek dan masih kosong
pada saat implementasi. Diperlukan remote DVC berisi dataset serta endpoint
MLflow yang bisa diakses runner. Nama variables dan secrets ada di
`docs/mlops-automation.md`.

Setelah konfigurasi tersebut diisi: lakukan simulasi perubahan konfigurasi,
ambil URL workflow sukses dan screenshot, kemudian lampirkan bersama YAML
dan PDF refleksi. Draft PR tidak boleh dianggap sebagai bukti eksekusi sukses.
