# Infrastructure

Folder ini berisi konfigurasi deployment yang dipisahkan dari implementasi aplikasi.

Dockerfile backend dan frontend berada di `docker/`. Nginx melayani hasil build
React dan meneruskan request `/api/` ke service FastAPI bernama `backend`.

Jalankan seluruh demo dari root repository dengan:

```bash
docker compose up -d --build --wait --wait-timeout 240
```

Manifest utama: `docker-compose.yaml` pada root repository. MLflow, backend dan
frontend memakai custom bridge `rain-network`. Backend menunggu MLflow sehat,
dan frontend menunggu backend sehat. Penyimpanan memakai bind mount pada data/;
lokasi VM lama tidak berubah. Panduan verifikasi ada di docs/compose-orchestration.md.
