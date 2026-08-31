# Infrastructure

Folder ini berisi konfigurasi deployment yang dipisahkan dari implementasi aplikasi.

Dockerfile backend dan frontend berada di `docker/`. Nginx melayani hasil build
React dan meneruskan request `/api/` ke service FastAPI bernama `backend`.

Jalankan seluruh demo dari root repository dengan:

```bash
docker compose up --build
```
