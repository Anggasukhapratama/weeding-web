import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Deteksi kalau jalan di Vercel
IS_VERCEL = os.getenv("VERCEL") == "1"

if IS_VERCEL:
    # Di Vercel hanya boleh nulis ke /tmp (sifatnya sementara)
    DB_PATH = "/tmp/wedding.db"
else:
    # Di lokal pakai file wedding.db di folder project
    DB_PATH = os.path.join(BASE_DIR, "wedding.db")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "super-rahasia-untuk-wedding"
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + DB_PATH
    SQLALCHEMY_TRACK_MODIFICATIONS = False
