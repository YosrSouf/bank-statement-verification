import os
import secrets
import sqlite3

from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory

import click

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # Store the account database and session key outside static/templates.
    instance_folder = Path(app.instance_path)
    instance_folder.mkdir(exist_ok=True)

    key_file = instance_folder / "session.key"

    if not key_file.exists():
        try:
            with key_file.open("x") as file:
                file.write(secrets.token_hex(32))
        except FileExistsError:
            pass

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or key_file.read_text(),
        DATABASE=str(instance_folder / "accounts.sqlite"),
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    # --------------------------------------------------
    # Database connection
    # --------------------------------------------------

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row

        return g.db

    @app.teardown_appcontext
    def close_db(error):
        connection = g.pop("db", None)

        if connection is not None:
            connection.close()

    # Create the users table if it does not exist.
    with app.app_context():
        get_db().execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                is_admin INTEGER NOT NULL DEFAULT 0
            )
        """)

        get_db().commit()

    # --------------------------------------------------
    # Load the signed-in user and protect POST forms
    # --------------------------------------------------

    @app.before_request
    def load_user():
        user_id = session.get("user_id")

        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        # CSRF tokens help prevent another website from submitting forms
        # using the advisor's logged-in session.
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)

        if request.method == "POST":
            submitted_token = request.form.get("csrf", "")

            if not secrets.compare_digest(
                session["csrf"],
                submitted_token,
            ):
                abort(
                    400,
                    "Your form expired. Reload the page and try again.",
                )

    @app.after_request
    def add_headers(response):
        # Avoid caching financial reports and account pages.
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"

        return response

    # --------------------------------------------------
    # Route permissions
    # --------------------------------------------------

    def approved_required(admin_only=False):
        def decorator(view):
            @wraps(view)
            def wrapped_view(*args, **kwargs):
                if g.user is None:
                    return redirect(url_for("login"))

                if g.user["status"] != "approved":
                    abort(403, "Your account has not been approved.")

                if admin_only and not g.user["is_admin"]:
                    abort(403, "Administrator access is required.")

                return view(*args, **kwargs)

            return wrapped_view

        return decorator

    # --------------------------------------------------
    # Home
    # --------------------------------------------------

    @app.route("/")
    def home():
        return render_template("home.html")

    # --------------------------------------------------
    # Sign up
    # --------------------------------------------------

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            if not name or len(name) > 100:
                flash("Enter your name.")

            elif "@" not in email or len(email) > 254:
                flash("Enter a valid email address.")

            elif not 12 <= len(password) <= 128:
                flash("Use a password containing 12–128 characters.")

            else:
                try:
                    # New accounts are pending and never administrators.
                    get_db().execute(
                        """
                        INSERT INTO users (name, email, password)
                        VALUES (?, ?, ?)
                        """,
                        (
                            name,
                            email,
                            generate_password_hash(password),
                        ),
                    )

                    get_db().commit()

                    flash(
                        "Request received. An administrator must "
                        "approve your account before you can sign in."
                    )

                    return redirect(url_for("login"))

                except sqlite3.IntegrityError:
                    flash("An account with this email already exists.")

        return render_template("auth.html", signup=True)

    # --------------------------------------------------
    # Log in
    # --------------------------------------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            user = get_db().execute(
                "SELECT * FROM users WHERE email = ?",
                (email,),
            ).fetchone()

            if user is None or not check_password_hash(
                user["password"],
                password,
            ):
                flash("Email or password is incorrect.")

            elif user["status"] == "pending":
                flash("Your account is pending administrator approval.")

            elif user["status"] != "approved":
                flash(
                    "Your account request was declined. "
                    "Contact your administrator."
                )

            else:
                session.clear()

                session["user_id"] = user["id"]
                session["csrf"] = secrets.token_urlsafe(32)

                return redirect(url_for("home"))

        return render_template("auth.html", signup=False)

    # --------------------------------------------------
    # Log out
    # --------------------------------------------------

    @app.post("/logout")
    def logout():
        session.clear()

        return redirect(url_for("home"))

    # --------------------------------------------------
    # Administrator page
    # --------------------------------------------------

    @app.route("/admin")
    @approved_required(admin_only=True)
    def admin():
        pending_users = get_db().execute("""
            SELECT id, name, email
            FROM users
            WHERE status = 'pending'
            ORDER BY id
        """).fetchall()

        return render_template(
            "admin.html",
            users=pending_users,
        )

    @app.post("/admin/<int:user_id>/<action>")
    @approved_required(admin_only=True)
    def decide_account(user_id, action):
        if action not in ("approve", "decline"):
            abort(404)

        new_status = (
            "approved" if action == "approve" else "declined"
        )

        get_db().execute(
            """
            UPDATE users
            SET status = ?
            WHERE id = ?
              AND status = 'pending'
              AND is_admin = 0
            """,
            (new_status, user_id),
        )

        get_db().commit()

        flash("Account request updated.")

        return redirect(url_for("admin"))

    # --------------------------------------------------
    # Upload and generate a report
    # --------------------------------------------------

    @app.route("/review", methods=["GET", "POST"])
    @approved_required()
    def review():
        if request.method == "GET":
            return render_template("review.html")

        uploaded_file = request.files.get("statement")

        # Validate the required funding amount.
        try:
            required_amount = Decimal(
                request.form.get("required_amount", "")
            )

            if (
                not required_amount.is_finite()
                or required_amount <= 0
                or required_amount > 10_000_000
            ):
                raise InvalidOperation

        except InvalidOperation:
            return render_template(
                "review.html",
                error=(
                    "Enter a required amount greater than zero "
                    "and no more than $10,000,000."
                ),
            ), 400

        if (
            uploaded_file is None
            or not uploaded_file.filename
            or not uploaded_file.filename.lower().endswith(".pdf")
        ):
            return render_template(
                "review.html",
                error="Select a PDF file.",
            ), 400

        # Each upload gets its own temporary folder.
        # The folder is deleted when this block finishes.
        with TemporaryDirectory(prefix="statement-") as folder:
            pdf_path = Path(folder) / "statement.pdf"

            uploaded_file.save(pdf_path)

            with pdf_path.open("rb") as file:
                signature = file.read(5)

            if signature != b"%PDF-":
                return render_template(
                    "review.html",
                    error="The uploaded file is not a valid PDF.",
                ), 400

            try:
                from main import verify_statement

                report = verify_statement(
                    pdf_path=pdf_path,
                    required_amount=str(required_amount),
                )

            except Exception as error:
                # Avoid logging statement text or private API responses.
                app.logger.warning(
                    "Analysis failed: %s",
                    type(error).__name__,
                )

                return render_template(
                    "review.html",
                    error=(
                        "Analysis failed. Check your API configuration, "
                        "PDF, and OCR dependencies, then try again. "
                        "No report was generated."
                    ),
                ), 502

        return render_template(
            "report.html",
            report=report,
        )

    # --------------------------------------------------
    # Error pages
    # --------------------------------------------------

    @app.errorhandler(413)
    def upload_too_large(error):
        return render_template(
            "error.html",
            message="The upload exceeds the 20 MB limit.",
        ), 413

    @app.errorhandler(400)
    @app.errorhandler(403)
    def request_error(error):
        return render_template(
            "error.html",
            message=error.description,
        ), error.code

    # --------------------------------------------------
    # Create an administrator from the terminal
    # --------------------------------------------------

    @app.cli.command("create-admin")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_admin(name, email, password):
        if (
            not name.strip()
            or "@" not in email
            or not 12 <= len(password) <= 128
        ):
            raise click.ClickException(
                "Enter a name, valid email, and a "
                "12–128 character password."
            )

        try:
            get_db().execute(
                """
                INSERT INTO users
                    (name, email, password, status, is_admin)
                VALUES (?, ?, ?, 'approved', 1)
                """,
                (
                    name.strip(),
                    email.strip().lower(),
                    generate_password_hash(password),
                ),
            )

            get_db().commit()

        except sqlite3.IntegrityError:
            raise click.ClickException(
                "That email already exists. "
                "Use a separate administrator email."
            )

        click.echo("Administrator created.")

    return app