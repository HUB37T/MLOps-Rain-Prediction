# Refleksi LK-08: Code as a Trigger

Perubahan kecil pada kode prapemrosesan atau hyperparameter dapat menghasilkan
model yang berbeda meskipun aplikasi tetap dapat dinyalakan. Karena itu,
keberhasilan menjalankan program belum cukup untuk menyatakan model layak dipakai.
Prinsip Code as a Trigger membantu memastikan setiap perubahan yang relevan
melewati pengujian, pelatihan ulang dan evaluasi yang konsisten.

Pada proyek prediksi hujan ini, workflow GitHub Actions menjalankan pytest,
mengambil data berversi melalui DVC, membangun ulang fitur, lalu menjalankan
train.py. Dataset mengikuti pointer pada commit yang diuji, sementara dependency
mengikuti uv.lock. Konfigurasi model dan threshold juga tercatat di Git, sehingga
input suatu eksperimen dapat ditelusuri kembali.

Risiko silent failure muncul ketika pipeline selesai tanpa error tetapi
kemampuan prediksinya menurun. Evaluation gate memeriksa validation PR-AUC dan
F1 sebelum registrasi. Nilai yang hilang atau tidak finite dianggap gagal,
bukan dilewati. Smoke test juga memanggil artefak model untuk memastikan model
benar-benar dapat dimuat dan menghasilkan keluaran yang sesuai.

Kebijakan awal yang diusulkan adalah validation PR-AUC minimal 0,90 dan F1
minimal 0,82, mengacu pada hasil champion LK-06. Angka tersebut harus disesuaikan
dengan target pada LK-01 sebelum workflow diterima. Kebijakan ini tidak memakai
test set untuk memilih kandidat karena hal tersebut dapat membiasakan evaluasi.

Model yang lolos pada push ke main didaftarkan sebagai Staging, bukan langsung
menjadi champion. Hal ini menjaga batas antara kandidat yang lolos evaluasi
offline dengan model yang telah disetujui untuk produksi. Model baru tetap
memerlukan review dan monitoring setelah deployment untuk mendeteksi perubahan
data dan penurunan performa yang tidak tertangkap oleh holdout historis.

Luaran kode mencatat Run ID, model URI, commit source, hash dataset dan hasil
evaluasi. Bukti eksekusi GitHub yang nyata dilampirkan secara terpisah setelah
remote DVC dan endpoint MLflow tersedia. Hasil pengujian lokal tidak menggantikan
URL workflow otomatis yang diminta tugas.
