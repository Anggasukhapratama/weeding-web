from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from config import Config
import string
import random

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)


class AdminUser(db.Model):
    __tablename__ = "admin_users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Guest(db.Model):
    __tablename__ = "guests"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    phone = db.Column(db.String(32))
    email = db.Column(db.String(128))
    invitation_name = db.Column(db.String(128))

    rsvp_status = db.Column(db.String(16), default="none")
    rsvp_guest_count = db.Column(db.Integer, default=1)
    rsvp_message = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    checkins = db.relationship("GuestCheckin", backref="guest", lazy=True)
    wishes = db.relationship("Wish", backref="guest", lazy=True)


class GuestCheckin(db.Model):
    __tablename__ = "guest_checkins"
    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey("guests.id"), nullable=False)
    checked_in_at = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.Text)


class Wish(db.Model):
    __tablename__ = "wishes"
    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey("guests.id"), nullable=True)
    name = db.Column(db.String(128))
    message = db.Column(db.Text, nullable=False)
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Photo(db.Model):
    __tablename__ = "photos"
    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    order_index = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Setting(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def generate_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return "GUEST-" + "".join(random.choice(chars) for _ in range(length))


def get_setting(key, default=""):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else default


def login_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Silakan login sebagai admin.", "danger")
            return redirect(url_for("admin_login"))
        return func(*args, **kwargs)

    return wrapper


@app.route("/", methods=["GET", "POST"])
def index():
    # Halaman ini sekarang jadi form pendaftaran merch + generate barcode
    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        email = request.form.get("email")

        if not name:
            flash("Nama wajib diisi.", "danger")
            return redirect(url_for("index"))

        # Buat code unik untuk barcode
        code = generate_code()

        guest = Guest(
            code=code,
            name=name,
            phone=phone,
            email=email,
            invitation_name=name,  # bisa aja dipakai lagi nanti jika perlu
        )
        db.session.add(guest)
        db.session.commit()

        # Arahkan ke halaman tiket yang berisi barcode
        return redirect(url_for("ticket", code=code))

    wedding_title = get_setting("wedding_title", "Pendaftaran Merchandise")
    wedding_date = get_setting("wedding_date", "2025-01-01")
    location = get_setting("wedding_location", "Lokasi acara belum diatur")
    return render_template(
        "index.html",
        wedding_title=wedding_title,
        wedding_date=wedding_date,
        location=location,
    )


@app.route("/ticket/<code>")
def ticket(code):
    # Halaman untuk menampilkan barcode/QR yang akan discan di admin/checkin
    guest = Guest.query.filter_by(code=code).first_or_404()

    # URL QR pakai layanan eksternal (bisa diganti pakai library qrcode kalau mau offline)
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={guest.code}"

    return render_template(
        "ticket.html",
        guest=guest,
        qr_url=qr_url,
    )


@app.route("/invite/<code>", methods=["GET", "POST"])
def invite(code):
    guest = Guest.query.filter_by(code=code).first_or_404()

    # Handle RSVP
    if request.method == "POST":
        rsvp_status = request.form.get("rsvp_status", "none")
        rsvp_guest_count = request.form.get("rsvp_guest_count", "1")
        rsvp_message = request.form.get("rsvp_message", "")

        try:
            rsvp_guest_count = int(rsvp_guest_count)
        except ValueError:
            rsvp_guest_count = 1

        guest.rsvp_status = rsvp_status
        guest.rsvp_guest_count = rsvp_guest_count
        guest.rsvp_message = rsvp_message
        db.session.commit()
        flash("Terima kasih, RSVP Anda sudah tersimpan. 💌", "success")
        return redirect(url_for("invite", code=code))

    # Ucapan publik terbaru
    public_wishes = (
        Wish.query.filter(
            ((Wish.guest_id == guest.id) | (Wish.guest_id.is_(None))),
            Wish.is_public.is_(True),
        )
        .order_by(Wish.created_at.desc())
        .limit(20)
        .all()
    )

    # Galeri foto (untuk section galeri)
    photos = (
        Photo.query.filter_by(is_active=True)
        .order_by(Photo.order_index.asc(), Photo.created_at.desc())
        .all()
    )

    # Setting acara
    wedding_title = get_setting("wedding_title", "Pernikahan Kami")
    bride_name = get_setting("bride_name", "Mempelai Wanita")
    groom_name = get_setting("groom_name", "Mempelai Pria")
    wedding_date = get_setting("wedding_date", "2025-01-01")
    wedding_time = get_setting("wedding_time", "10:00")
    wedding_location = get_setting("wedding_location", "Gedung / Lokasi")
    wedding_address = get_setting("wedding_address", "Alamat lengkap acara")
    maps_embed_url = get_setting(
        "wedding_maps_embed_url",
        ""  # bisa kosong dulu
    )

    return render_template(
        "invite.html",
        guest=guest,
        wedding_title=wedding_title,
        bride_name=bride_name,
        groom_name=groom_name,
        wedding_date=wedding_date,
        wedding_time=wedding_time,
        wedding_location=wedding_location,
        wedding_address=wedding_address,
        maps_embed_url=maps_embed_url,
        public_wishes=public_wishes,
        photos=photos,
    )

@app.route("/guestbook", methods=["POST"])
def guestbook():
    name = request.form.get("name")
    message = request.form.get("message")
    is_public = request.form.get("is_public") == "on"
    guest_code = request.form.get("guest_code")

    guest = None
    if guest_code:
        guest = Guest.query.filter_by(code=guest_code).first()

    if not message:
        flash("Ucapan tidak boleh kosong.", "danger")
        return redirect(request.referrer or url_for("index"))

    wish = Wish(
        guest_id=guest.id if guest else None,
        name=name or (guest.name if guest else "Tamu"),
        message=message,
        is_public=is_public,
    )
    db.session.add(wish)
    db.session.commit()
    flash("Terima kasih atas ucapan dan doanya. ❤️", "success")
    return redirect(request.referrer or url_for("index"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        admin = AdminUser.query.filter_by(username=username).first()
        if admin and admin.password == password:
            session["admin_logged_in"] = True
            session["admin_username"] = username
            flash("Berhasil login.", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Username atau password salah.", "danger")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("Anda telah logout.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    total_guests = Guest.query.count()
    rsvp_yes = Guest.query.filter_by(rsvp_status="yes").count()
    rsvp_no = Guest.query.filter_by(rsvp_status="no").count()
    rsvp_none = Guest.query.filter_by(rsvp_status="none").count()
    total_checkins = GuestCheckin.query.count()

    latest_checkins = (
        GuestCheckin.query.order_by(GuestCheckin.checked_in_at.desc()).limit(10).all()
    )

    return render_template(
        "admin_dashboard.html",
        total_guests=total_guests,
        rsvp_yes=rsvp_yes,
        rsvp_no=rsvp_no,
        rsvp_none=rsvp_none,
        total_checkins=total_checkins,
        latest_checkins=latest_checkins,
    )


@app.route("/admin/guests", methods=["GET", "POST"])
@login_required
def admin_guests():
    if request.method == "POST":
        name = request.form.get("name")
        phone = request.form.get("phone")
        email = request.form.get("email")
        invitation_name = request.form.get("invitation_name") or name

        code = generate_code()
        new_guest = Guest(
            code=code,
            name=name,
            phone=phone,
            email=email,
            invitation_name=invitation_name,
        )
        db.session.add(new_guest)
        db.session.commit()
        flash("Tamu baru berhasil ditambahkan.", "success")
        return redirect(url_for("admin_guests"))

    guests = Guest.query.order_by(Guest.created_at.desc()).all()
    return render_template("admin_guests.html", guests=guests)


@app.route("/admin/guests/<int:guest_id>")
@login_required
def admin_guest_detail(guest_id):
    guest = Guest.query.get_or_404(guest_id)
    return render_template("admin_guest_detail.html", guest=guest)


@app.route("/admin/checkin")
@login_required
def admin_checkin():
    return render_template("admin_checkin.html")


@app.route("/api/checkin", methods=["POST"])
@login_required
def api_checkin():
    data = request.get_json() or {}
    code = data.get("code")

    if not code:
        return jsonify({"success": False, "message": "Code tidak ditemukan."}), 400

    guest = Guest.query.filter_by(code=code).first()
    if not guest:
        return jsonify({"success": False, "message": "Tamu dengan kode ini tidak ditemukan."}), 404

    already = GuestCheckin.query.filter_by(guest_id=guest.id).first()
    if already:
        msg = f"{guest.name} sudah pernah check-in sebelumnya."
    else:
        checkin = GuestCheckin(guest_id=guest.id)
        db.session.add(checkin)
        db.session.commit()
        msg = f"Check-in berhasil. Selamat datang, {guest.name}!"

    return jsonify(
        {
            "success": True,
            "message": msg,
            "guest": {
                "name": guest.name,
                "code": guest.code,
                "rsvp_status": guest.rsvp_status,
                "rsvp_guest_count": guest.rsvp_guest_count,
            },
        }
    )


def setup():
    db.create_all()
    # buat admin default jika belum ada
    if not AdminUser.query.filter_by(username="admin").first():
        admin = AdminUser(username="admin", password="admin123")
        db.session.add(admin)
        db.session.commit()


if __name__ == "__main__":
    # panggil setup() di dalam app_context
    with app.app_context():
        setup()
    app.run(debug=True)

