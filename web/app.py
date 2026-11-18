import io
import os
import re
import secrets
import zipfile
from datetime import datetime, timezone
from functools import wraps

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, render_template, request, session, send_file
from PIL import Image, ImageOps, ExifTags, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,
)
Image.MAX_IMAGE_PIXELS = 40_000_000
ALLOWED = {"jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"}
FORMATS = {"JPG": "JPEG", "JPEG": "JPEG", "PNG": "PNG", "WEBP": "WEBP", "BMP": "BMP", "TIFF": "TIFF"}
SCHEMA_READY = False


def db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured.")
    return psycopg2.connect(url, connect_timeout=8, sslmode="require")


def ensure_schema():
    global SCHEMA_READY
    if SCHEMA_READY:
        return
    with db() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hulagway_users (
                id BIGSERIAL PRIMARY KEY,
                username VARCHAR(24) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS hulagway_history (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES hulagway_users(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                operation VARCHAR(24) NOT NULL,
                input_bytes BIGINT NOT NULL,
                output_bytes BIGINT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS hulagway_history_user_time
                ON hulagway_history(user_id, created_at DESC);
        """)
    SCHEMA_READY = True


@app.before_request
def prepare_database():
    if request.endpoint not in ("static",):
        ensure_schema()


def current_user():
    return session.get("user_id")


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            return jsonify(error="Please sign in to continue."), 401
        return fn(*args, **kwargs)
    return wrapped


def json_error(message, status=400):
    return jsonify(error=message), status


@app.errorhandler(413)
def too_large(_):
    return json_error("The total upload is too large. Please use images under 4 MB per request.", 413)


@app.route("/")
def home():
    return render_template("index.html")


@app.get("/api/me")
def me():
    if not current_user():
        return jsonify(authenticated=False)
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT username FROM hulagway_users WHERE id=%s", (current_user(),))
        row = cur.fetchone()
    if not row:
        session.clear()
        return jsonify(authenticated=False)
    return jsonify(authenticated=True, username=row[0])


@app.post("/api/signup")
def signup():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not re.fullmatch(r"[A-Za-z0-9_]{3,24}", username):
        return json_error("Username must be 3–24 characters using letters, numbers, or underscores.")
    if len(password) < 10 or len(password) > 128 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return json_error("Use a password of 10–128 characters with at least one letter and one number.")
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO hulagway_users(username,password_hash) VALUES(%s,%s) RETURNING id",
                (username, generate_password_hash(password, method="scrypt"))
            )
            user_id = cur.fetchone()[0]
    except psycopg2.errors.UniqueViolation:
        return json_error("That username is already taken.", 409)
    session.clear()
    session["user_id"] = user_id
    session["csrf"] = secrets.token_urlsafe(24)
    return jsonify(ok=True, username=username, csrf=session["csrf"])


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, password_hash FROM hulagway_users WHERE username=%s", (username,))
        row = cur.fetchone()
    if not row or not check_password_hash(row[1], password):
        return json_error("Incorrect username or password.", 401)
    session.clear()
    session["user_id"] = row[0]
    session["csrf"] = secrets.token_urlsafe(24)
    return jsonify(ok=True, username=username, csrf=session["csrf"])


@app.post("/api/logout")
@login_required
def logout():
    session.clear()
    return jsonify(ok=True)


def verify_csrf():
    token = request.headers.get("X-CSRF-Token", "")
    return bool(token and secrets.compare_digest(token, session.get("csrf", "")))


def open_upload(file):
    if not file or not file.filename:
        raise ValueError("Choose an image first.")
    name = secure_filename(file.filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise ValueError("Unsupported file type. Use JPG, PNG, WebP, BMP, or TIFF.")
    raw = file.read()
    if not raw:
        raise ValueError("The selected file is empty.")
    try:
        im = Image.open(io.BytesIO(raw))
        if (im.format or "").upper() not in {"JPEG", "PNG", "WEBP", "BMP", "TIFF"}:
            raise ValueError("This image format is not supported.")
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        im.load()
        im = ImageOps.exif_transpose(im)
        return name, raw, im.copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("This image is invalid, corrupted, or too large to process.")


def encode_image(im, fmt, quality, background):
    fmt = FORMATS.get(fmt.upper())
    if not fmt:
        raise ValueError("Choose a supported output format.")
    if fmt == "JPEG":
        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            base = Image.new("RGB", rgba.size, background)
            base.paste(rgba, mask=rgba.getchannel("A"))
            im = base
        else:
            im = im.convert("RGB")
    elif fmt == "BMP":
        im = im.convert("RGB")
    elif fmt == "PNG" and im.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        im = im.convert("RGBA" if "A" in im.mode else "RGB")
    out = io.BytesIO()
    kwargs = {}
    if fmt in ("JPEG", "WEBP"):
        kwargs["quality"] = max(1, min(100, int(quality)))
        if fmt == "JPEG":
            kwargs["optimize"] = True
    if fmt == "PNG":
        kwargs["optimize"] = True
    im.save(out, format=fmt, **kwargs)
    return out.getvalue(), fmt


@app.post("/api/process")
@login_required
def process():
    if not verify_csrf():
        return json_error("Your session expired. Refresh and try again.", 403)
    files = request.files.getlist("images")
    if not files:
        return json_error("Choose at least one image.")
    if len(files) > 8:
        return json_error("Process up to 8 images at a time.")
    operation = request.form.get("operation", "compress")
    if operation not in {"compress", "convert", "resize", "optimize"}:
        return json_error("Unknown image operation.")
    try:
        quality = int(request.form.get("quality", 82))
        width = int(request.form.get("width", 0) or 0)
        height = int(request.form.get("height", 0) or 0)
        if not 1 <= quality <= 100:
            raise ValueError("Quality must be between 1 and 100.")
        if operation == "resize" and (not 1 <= width <= 20000 or not 1 <= height <= 20000):
            raise ValueError("Enter width and height between 1 and 20,000 pixels.")
        output_format = request.form.get("format", "WEBP" if operation in {"compress", "optimize"} else "PNG")
        bg = (255, 255, 255)
        outputs, rows = [], []
        for file in files:
            name, raw, im = open_upload(file)
            original_dims = im.size
            if operation == "resize":
                im.thumbnail((width, height), Image.Resampling.LANCZOS)
            payload, fmt = encode_image(im, output_format, quality, bg)
            if operation in {"compress", "optimize"} and len(payload) >= len(raw) and fmt in {"JPEG", "WEBP"}:
                payload, fmt = raw, (im.format or fmt)
            ext = {"JPEG":"jpg","PNG":"png","WEBP":"webp","BMP":"bmp","TIFF":"tiff"}[fmt]
            outname = f"{name.rsplit('.',1)[0]}_hulagway.{ext}"
            outputs.append((outname, payload))
            rows.append({"filename":name,"output":outname,"before":len(raw),"after":len(payload),
                         "width":original_dims[0],"height":original_dims[1],
                         "saved":max(0,len(raw)-len(payload))})
        with db() as conn, conn.cursor() as cur:
            for row in rows:
                cur.execute("""INSERT INTO hulagway_history
                    (user_id,filename,operation,input_bytes,output_bytes)
                    VALUES(%s,%s,%s,%s,%s)""",
                    (current_user(),row["filename"],operation,row["before"],row["after"]))
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, payload in outputs:
                zf.writestr(name, payload)
        archive.seek(0)
        token = secrets.token_urlsafe(12)
        session["download_token"] = token
        session["download_data"] = __import__("base64").b64encode(archive.getvalue()).decode("ascii")
        session["download_name"] = "hulagway-processed.zip"
        return jsonify(ok=True, results=rows, download="/api/download?token="+token)
    except (ValueError, OSError) as exc:
        return json_error(str(exc))


@app.get("/api/download")
@login_required
def download():
    token = request.args.get("token", "")
    if not token or not secrets.compare_digest(token, session.get("download_token", "")):
        return json_error("This download has expired. Process your images again.", 404)
    import base64
    data = base64.b64decode(session.get("download_data", ""))
    return send_file(io.BytesIO(data), mimetype="application/zip",
                     as_attachment=True, download_name="hulagway-processed.zip")


@app.get("/api/history")
@login_required
def history():
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT filename,operation,input_bytes,output_bytes,created_at
            FROM hulagway_history WHERE user_id=%s ORDER BY created_at DESC LIMIT 50""",
            (current_user(),))
        rows = cur.fetchall()
    for row in rows:
        row["created_at"] = row["created_at"].isoformat()
    return jsonify(items=rows)


@app.get("/api/inspect")
@login_required
def inspect():
    file = request.files.get("image")
    try:
        name, raw, im = open_upload(file)
        exif = im.getexif()
        metadata = []
        for key, value in exif.items():
            label = ExifTags.TAGS.get(key, str(key))
            if isinstance(value, bytes):
                value = "[binary data]"
            metadata.append({"key":str(label),"value":str(value)[:160]})
        return jsonify(filename=name,format=im.format or "Unknown",mode=im.mode,
                       width=im.width,height=im.height,size=len(raw),
                       has_alpha="A" in im.mode,metadata=metadata[:30])
    except ValueError as exc:
        return json_error(str(exc))


@app.get("/api/health")
def health():
    return jsonify(ok=True, service="Hulagway Web")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
