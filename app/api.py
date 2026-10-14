"""Small Flask prototype: accounts, friends, restaurants, reviews and comments."""

from __future__ import annotations

import math
import os
import re
import secrets
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from typing import Any, Callable

import psycopg
from flask import Flask, Response, jsonify, render_template, request, session

from .db import DatabaseConfigError, close_db, get_db


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message
        super().__init__(message)


def response(data: Any, status: int = 200) -> tuple[Response, int]:
    def encode(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: encode(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [encode(item) for item in value]
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value
    return jsonify(encode(data)), status


def body() -> dict[str, Any]:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ApiError(400, "Send a JSON object in the request body.")
    return value


def text_field(data: dict[str, Any], key: str, max_length: int = 1000) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, f"{key} must be a non-empty string.")
    value = value.strip()
    if len(value) > max_length:
        raise ApiError(400, f"{key} must be at most {max_length} characters.")
    return value


def int_value(value: Any, name: str, minimum: int = 1, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(400, f"{name} must be an integer.")
    if value < minimum or (maximum is not None and value > maximum):
        raise ApiError(400, f"{name} is outside the allowed range.")
    return value


def query_int(name: str, default: int, maximum: int) -> int:
    try:
        value = int(request.args.get(name, str(default)))
    except ValueError as exc:
        raise ApiError(400, f"{name} must be an integer.") from exc
    return int_value(value, name, minimum=0 if name == "offset" else 1, maximum=maximum)


def friends_filter() -> bool:
    value = request.args.get("friends_only", "0")
    if value not in {"0", "1"}:
        raise ApiError(400, "friends_only must be 0 or 1.")
    if value == "1":
        current_user_id()
    return value == "1"


def current_user_id() -> int:
    user_id = session.get("user_id")
    if not isinstance(user_id, int):
        raise ApiError(401, "Sign in to use this feature.")
    return user_id


def login_required(function: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        current_user_id()
        return function(*args, **kwargs)
    return wrapper


def password_field(data: dict[str, Any], *, registering: bool = False) -> str:
    password = data.get("password")
    minimum = 8 if registering else 1
    # bcrypt uses at most 72 bytes; never silently truncate a user's password.
    if not isinstance(password, str) or not minimum <= len(password):
        raise ApiError(400, f"Password must contain at least {minimum} characters.")
    if len(password.encode("utf-8")) > 72 or "\x00" in password:
        raise ApiError(400, "Password must be at most 72 UTF-8 bytes and contain no null characters.")
    return password


REVIEW_SELECT = """
    SELECT rv.review_id, rv.rating, rv.review_text, rv.created_at,
           v.visit_id, v.visit_date, v.user_id, v.restaurant_id,
           u.user_name, r.restaurant_name
    FROM review rv
    JOIN visit v ON v.visit_id = rv.visit_id
    JOIN app_user u ON u.user_id = v.user_id
    JOIN restaurant r ON r.restaurant_id = v.restaurant_id
"""


def review_row(review_id: int) -> dict[str, Any]:
    row = get_db().execute(REVIEW_SELECT + " WHERE rv.review_id = %s", (review_id,)).fetchone()
    if row is None:
        raise ApiError(404, "Review not found.")
    return row


def restaurant_row(restaurant_id: int) -> dict[str, Any]:
    row = get_db().execute(
        """
        SELECT r.*, s.name AS suburb, s.state, s.postcode, rs.review_count, rs.avg_rating,
               COALESCE((SELECT array_agg(c.cuisine_name ORDER BY c.cuisine_name)
                         FROM restaurant_cuisine rc JOIN cuisine c USING (cuisine_id)
                         WHERE rc.restaurant_id = r.restaurant_id), ARRAY[]::text[]) AS cuisines
        FROM restaurant r JOIN suburb s USING (suburb_id)
        JOIN restaurant_rating_summary rs USING (restaurant_id)
        WHERE r.restaurant_id = %s
        """, (restaurant_id,),
    ).fetchone()
    if row is None:
        raise ApiError(404, "Restaurant not found.")
    return row


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("APP_SECRET_KEY") or secrets.token_hex(32)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("APP_HTTPS") == "1",
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    app.teardown_appcontext(close_db)
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "").rstrip("/")

    @app.before_request
    def check_origin() -> Response | None:
        origin = request.headers.get("Origin", "").rstrip("/")
        allowed = {request.host_url.rstrip("/")}
        if frontend_origin:
            allowed.add(frontend_origin)
        if origin and origin not in allowed:
            raise ApiError(403, "This browser origin is not allowed.")
        if request.method == "OPTIONS":
            return Response(status=204)
        return None

    @app.after_request
    def cors_headers(result: Response) -> Response:
        if frontend_origin and request.headers.get("Origin", "").rstrip("/") == frontend_origin:
            result.headers["Access-Control-Allow-Origin"] = frontend_origin
            result.headers["Access-Control-Allow-Credentials"] = "true"
            result.headers["Access-Control-Allow-Headers"] = "Content-Type"
            result.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
            result.headers["Vary"] = "Origin"
        return result

    @app.errorhandler(ApiError)
    def api_error(error: ApiError):
        return response({"error": error.message}, error.status)

    @app.errorhandler(DatabaseConfigError)
    def config_error(_error):
        return response({"error": "Database connection is not configured."}, 503)

    @app.errorhandler(psycopg.Error)
    def database_error(error):
        if isinstance(error, psycopg.OperationalError):
            app.logger.exception("PostgreSQL is unavailable")
            return response({"error": "Database is unavailable."}, 503)
        if isinstance(error, psycopg.errors.UniqueViolation):
            return response({"error": "This email or record already exists."}, 409)
        if isinstance(error, (psycopg.errors.ForeignKeyViolation, psycopg.errors.CheckViolation)):
            return response({"error": "The request violates a database rule."}, 400)
        app.logger.exception("Unexpected PostgreSQL error")
        return response({"error": "A database error occurred."}, 500)

    @app.errorhandler(404)
    def not_found(_error):
        return response({"error": "Endpoint not found.", "hint": "Open /api for entry points."}, 404)

    @app.get("/")
    def home_page():
        return render_template("index.html")

    @app.get("/api")
    @app.get("/api/")
    def api_index():
        return response({"name": "Tablemates API", "links": {
            "health": "/api/health", "catalog": "/api/catalog", "restaurants": "/api/restaurants",
            "me": "/api/me"}, "accounts": "POST /api/register or /api/login"})

    @app.get("/api/health")
    def health():
        get_db().execute("SELECT 1")
        return response({"database": "ok"})

    @app.post("/api/register")
    def register():
        data = body()
        name = text_field(data, "user_name", 100)
        email = text_field(data, "email", 254).lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ApiError(400, "Enter a valid email address.")
        password = password_field(data, registering=True)
        with get_db().transaction():
            user = get_db().execute(
                """
                INSERT INTO app_user (user_name, user_email, password_hash)
                VALUES (%s, %s, crypt(%s, gen_salt('bf', 10)))
                RETURNING user_id, user_name, user_email, created_at
                """, (name, email, password),
            ).fetchone()
        session.clear()
        session["user_id"] = user["user_id"]
        return response({"user": user}, 201)

    @app.post("/api/login")
    def login():
        data = body()
        email = text_field(data, "email", 254)
        password = password_field(data)
        user = get_db().execute(
            """
            SELECT user_id, user_name, user_email, created_at FROM app_user
            WHERE lower(user_email) = lower(%s) AND password_hash = crypt(%s, password_hash)
            """, (email, password),
        ).fetchone()
        if user is None:
            raise ApiError(401, "Invalid email or password.")
        session.clear()
        session["user_id"] = user["user_id"]
        return response({"user": user})

    @app.post("/api/logout")
    def logout():
        session.clear()
        return response({"signed_out": True})

    @app.get("/api/me")
    @login_required
    def me():
        user = get_db().execute(
            "SELECT user_id, user_name, user_email, created_at FROM app_user WHERE user_id = %s",
            (current_user_id(),),
        ).fetchone()
        if user is None:
            session.clear()
            raise ApiError(401, "This account is no longer available.")
        return response({"user": user})

    @app.get("/api/catalog")
    def catalog():
        return response({
            "suburbs": get_db().execute("SELECT suburb_id, name FROM suburb ORDER BY name").fetchall(),
            "cuisines": get_db().execute("SELECT cuisine_id, cuisine_name FROM cuisine ORDER BY cuisine_name").fetchall(),
        })

    @app.get("/api/restaurants")
    def restaurants():
        search = request.args.get("q", "").strip()
        if len(search) > 100:
            raise ApiError(400, "q must be at most 100 characters.")
        suburb, cuisine = request.args.get("suburb", ""), request.args.get("cuisine", "")
        friend_only = friends_filter()
        sort = request.args.get("sort", "rating")
        sorts = {
            "rating": "rs.avg_rating DESC NULLS LAST, rs.review_count DESC, r.restaurant_id",
            "reviews": "rs.review_count DESC, r.restaurant_id",
            "name": "r.restaurant_name, r.restaurant_id",
            "price": "r.price_level, r.restaurant_name, r.restaurant_id",
            "friends": "fa.last_friend_visit_date DESC NULLS LAST, fa.friend_visit_count DESC NULLS LAST, r.restaurant_id",
        }
        if sort not in sorts:
            raise ApiError(400, "sort must be rating, reviews, name, price or friends.")
        if sort == "friends":
            current_user_id()
        price = query_int("price_level", 4, 4) if request.args.get("price_level") else None
        try:
            minimum_rating = float(request.args.get("min_rating") or 0)
        except ValueError as exc:
            raise ApiError(400, "min_rating must be a number.") from exc
        if not math.isfinite(minimum_rating) or not 0 <= minimum_rating <= 5:
            raise ApiError(400, "min_rating must be between 0 and 5.")
        limit, offset = query_int("limit", 20, 50), query_int("offset", 0, 10000)
        rows = get_db().execute(
            f"""
            WITH recent_friend_visits AS (
                SELECT v.restaurant_id, v.user_id, u.user_name, max(v.visit_date) AS visit_date
                FROM visit v JOIN accepted_friend af ON af.friend_id = v.user_id
                JOIN app_user u ON u.user_id = v.user_id
                WHERE af.user_id = %s AND v.visit_date BETWEEN current_date - 90 AND current_date
                GROUP BY v.restaurant_id, v.user_id, u.user_name
            ), friend_activity AS (
                SELECT restaurant_id, count(*) AS friend_visit_count,
                       max(visit_date) AS last_friend_visit_date,
                       array_agg(user_name ORDER BY visit_date DESC, user_id) AS friend_names
                FROM recent_friend_visits GROUP BY restaurant_id
            )
            SELECT r.restaurant_id, r.restaurant_name, r.street_address, r.price_level,
                   s.name AS suburb, rs.review_count, rs.avg_rating,
                   COALESCE(fa.friend_visit_count, 0) AS friend_visit_count,
                   fa.last_friend_visit_date, COALESCE(fa.friend_names, ARRAY[]::text[]) AS friend_names,
                   COALESCE((SELECT array_agg(c.cuisine_name ORDER BY c.cuisine_name)
                             FROM restaurant_cuisine rc JOIN cuisine c USING (cuisine_id)
                             WHERE rc.restaurant_id = r.restaurant_id), ARRAY[]::text[]) AS cuisines
            FROM restaurant r JOIN suburb s USING (suburb_id)
            JOIN restaurant_rating_summary rs USING (restaurant_id)
            LEFT JOIN friend_activity fa USING (restaurant_id)
            WHERE r.is_active AND (%s = '' OR r.restaurant_name ILIKE %s)
              AND (%s = '' OR lower(s.name) = lower(%s))
              AND (%s = '' OR EXISTS (
                  SELECT 1 FROM restaurant_cuisine rc JOIN cuisine c USING (cuisine_id)
                  WHERE rc.restaurant_id = r.restaurant_id AND lower(c.cuisine_name) = lower(%s)))
              AND (%s::smallint IS NULL OR r.price_level = %s)
              AND (%s = 0 OR rs.avg_rating >= %s)
              AND (NOT %s OR COALESCE(fa.friend_visit_count, 0) > 0)
            ORDER BY {sorts[sort]} LIMIT %s OFFSET %s
            """,
            (session.get("user_id", -1), search, f"%{search}%", suburb, suburb, cuisine, cuisine,
             price, price, minimum_rating, minimum_rating, friend_only, limit, offset),
        ).fetchall()
        return response({"items": rows, "limit": limit, "offset": offset})

    @app.get("/api/restaurants/<int:restaurant_id>")
    def restaurant_detail(restaurant_id):
        return response({"restaurant": restaurant_row(restaurant_id)})

    @app.get("/api/restaurants/<int:restaurant_id>/friend-visits")
    @login_required
    def friend_visits(restaurant_id):
        restaurant_row(restaurant_id)
        rows = get_db().execute(
            """
            SELECT v.user_id, u.user_name, max(v.visit_date) AS visit_date
            FROM visit v JOIN accepted_friend af ON af.friend_id = v.user_id
            JOIN app_user u ON u.user_id = v.user_id
            WHERE af.user_id = %s AND v.restaurant_id = %s
              AND v.visit_date BETWEEN current_date - 90 AND current_date
            GROUP BY v.user_id, u.user_name ORDER BY visit_date DESC, v.user_id
            """, (current_user_id(), restaurant_id),
        ).fetchall()
        return response({"items": rows, "friend_count": len(rows), "recent_days": 90})

    @app.get("/api/users")
    @login_required
    def users():
        viewer, search = current_user_id(), request.args.get("q", "").strip()
        if len(search) > 100:
            raise ApiError(400, "q must be at most 100 characters.")
        rows = get_db().execute(
            """
            SELECT u.user_id, u.user_name, f.friendship_id, f.status AS friendship_status,
                   CASE WHEN f.requester_id = %s THEN 'sent' ELSE 'received' END AS request_direction
            FROM app_user u LEFT JOIN friendship f
              ON (f.requester_id = %s AND f.addressee_id = u.user_id)
              OR (f.addressee_id = %s AND f.requester_id = u.user_id)
            WHERE u.user_id <> %s AND (%s = '' OR u.user_name ILIKE %s)
            ORDER BY u.user_name, u.user_id LIMIT 30
            """, (viewer, viewer, viewer, viewer, search, f"%{search}%"),
        ).fetchall()
        return response({"items": rows})

    @app.get("/api/friends")
    @login_required
    def friends():
        viewer = current_user_id()
        rows = get_db().execute(
            """
            SELECT f.*, CASE WHEN f.requester_id = %s THEN 'sent' ELSE 'received' END AS direction,
                   u.user_id AS other_user_id, u.user_name AS other_user_name
            FROM friendship f JOIN app_user u ON u.user_id =
                CASE WHEN f.requester_id = %s THEN f.addressee_id ELSE f.requester_id END
            WHERE f.requester_id = %s OR f.addressee_id = %s
            ORDER BY f.requested_at DESC, f.friendship_id DESC
            """, (viewer, viewer, viewer, viewer),
        ).fetchall()
        return response({"items": rows})

    @app.post("/api/friend-requests")
    @login_required
    def send_friend_request():
        target, viewer = int_value(body().get("addressee_id"), "addressee_id"), current_user_id()
        if target == viewer:
            raise ApiError(400, "You cannot send a request to yourself.")
        if not get_db().execute("SELECT 1 FROM app_user WHERE user_id = %s", (target,)).fetchone():
            raise ApiError(404, "User not found.")
        row = get_db().execute(
            """
            INSERT INTO friendship (requester_id, addressee_id) VALUES (%s, %s)
            RETURNING friendship_id, requester_id, addressee_id, status, requested_at
            """, (viewer, target),
        ).fetchone()
        return response({"friendship": row}, 201)

    @app.post("/api/friend-requests/<int:friendship_id>/<action>")
    @login_required
    def decide_friend_request(friendship_id, action):
        if action not in {"accept", "reject"}:
            raise ApiError(404, "Friend request action not found.")
        status = "accepted" if action == "accept" else "rejected"
        row = get_db().execute(
            """
            UPDATE friendship SET status = %s,
                accepted_at = CASE WHEN %s = 'accepted' THEN now() ELSE NULL END
            WHERE friendship_id = %s AND addressee_id = %s AND status = 'pending'
            RETURNING friendship_id, status, accepted_at
            """, (status, status, friendship_id, current_user_id()),
        ).fetchone()
        if row is None:
            existing = get_db().execute(
                "SELECT addressee_id FROM friendship WHERE friendship_id = %s", (friendship_id,),
            ).fetchone()
            if existing is None:
                raise ApiError(404, "Friend request not found.")
            if existing["addressee_id"] != current_user_id():
                raise ApiError(403, "Only the recipient can decide this request.")
            raise ApiError(409, "This request is no longer pending.")
        return response({"friendship": row})

    @app.get("/api/favorites")
    @login_required
    def favorites():
        rows = get_db().execute(
            """
            SELECT r.restaurant_id, r.restaurant_name, r.street_address, r.price_level,
                   s.name AS suburb, rs.review_count, rs.avg_rating, f.added_at
            FROM favorite f JOIN restaurant r USING (restaurant_id)
            JOIN suburb s USING (suburb_id) JOIN restaurant_rating_summary rs USING (restaurant_id)
            WHERE f.user_id = %s ORDER BY f.added_at DESC, r.restaurant_id
            """, (current_user_id(),),
        ).fetchall()
        return response({"items": rows})

    @app.post("/api/favorites")
    @login_required
    def add_favorite():
        restaurant_id = int_value(body().get("restaurant_id"), "restaurant_id")
        restaurant_row(restaurant_id)
        get_db().execute(
            "INSERT INTO favorite (user_id, restaurant_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (current_user_id(), restaurant_id),
        )
        return response({"saved": True})

    @app.delete("/api/favorites/<int:restaurant_id>")
    @login_required
    def remove_favorite(restaurant_id):
        get_db().execute(
            "DELETE FROM favorite WHERE user_id = %s AND restaurant_id = %s",
            (current_user_id(), restaurant_id),
        )
        return Response(status=204)

    @app.get("/api/restaurants/<int:restaurant_id>/reviews")
    def restaurant_reviews(restaurant_id):
        restaurant_row(restaurant_id)
        friend_only = friends_filter()
        limit, offset = query_int("limit", 20, 50), query_int("offset", 0, 10000)
        rows = get_db().execute(
            REVIEW_SELECT + """
            WHERE v.restaurant_id = %s AND (NOT %s OR EXISTS (
                SELECT 1 FROM accepted_friend af WHERE af.user_id = %s AND af.friend_id = v.user_id))
            ORDER BY rv.created_at DESC, rv.review_id DESC LIMIT %s OFFSET %s
            """, (restaurant_id, friend_only, session.get("user_id", -1), limit, offset),
        ).fetchall()
        return response({"items": rows, "limit": limit, "offset": offset})

    @app.get("/api/reviews/<int:review_id>")
    def review_detail(review_id):
        return response({"review": review_row(review_id)})

    @app.patch("/api/reviews/<int:review_id>")
    @login_required
    def edit_review(review_id):
        data = body()
        rating = int_value(data.get("rating"), "rating", maximum=5)
        review_text = text_field(data, "review_text", 5000)
        row = get_db().execute(
            """
            UPDATE review rv SET rating = %s, review_text = %s FROM visit v
            WHERE rv.visit_id = v.visit_id AND rv.review_id = %s AND v.user_id = %s
            RETURNING rv.review_id, rv.rating, rv.review_text
            """, (rating, review_text, review_id, current_user_id()),
        ).fetchone()
        if row is None:
            review_row(review_id)
            raise ApiError(403, "You can edit only your own reviews.")
        return response({"review": row})

    @app.delete("/api/reviews/<int:review_id>")
    @login_required
    def delete_review(review_id):
        row = get_db().execute(
            """
            DELETE FROM review rv USING visit v
            WHERE rv.visit_id = v.visit_id AND rv.review_id = %s AND v.user_id = %s
            RETURNING rv.review_id
            """, (review_id, current_user_id()),
        ).fetchone()
        if row is None:
            review_row(review_id)
            raise ApiError(403, "You can delete only your own reviews.")
        # PostgreSQL cascades comments; the visit remains as historical evidence.
        return Response(status=204)

    @app.get("/api/reviews/<int:review_id>/comments")
    def comments(review_id):
        review_row(review_id)
        rows = get_db().execute(
            """
            SELECT c.*, u.user_name AS author_name
            FROM review_comment c JOIN app_user u ON u.user_id = c.author_id
            WHERE c.review_id = %s ORDER BY c.created_at, c.comment_id
            """, (review_id,),
        ).fetchall()
        return response({"items": rows})

    @app.post("/api/reviews/<int:review_id>/comments")
    @login_required
    def add_comment(review_id):
        review_row(review_id)
        data = body()
        text = text_field(data, "comment_text", 1000)
        parent = data.get("parent_comment_id")
        if parent is not None:
            parent = int_value(parent, "parent_comment_id")
        row = get_db().execute(
            """
            INSERT INTO review_comment (review_id, author_id, parent_comment_id, comment_text)
            VALUES (%s, %s, %s, %s) RETURNING *
            """, (review_id, current_user_id(), parent, text),
        ).fetchone()
        return response({"comment": row}, 201)

    @app.get("/api/me/visits")
    @login_required
    def my_visits():
        limit, offset = query_int("limit", 20, 50), query_int("offset", 0, 10000)
        rows = get_db().execute(
            """
            SELECT v.*, r.restaurant_name, rv.review_id, rv.rating, rv.review_text
            FROM visit v JOIN restaurant r USING (restaurant_id)
            LEFT JOIN review rv USING (visit_id) WHERE v.user_id = %s
            ORDER BY v.visit_date DESC, v.visit_id DESC LIMIT %s OFFSET %s
            """, (current_user_id(), limit, offset),
        ).fetchall()
        return response({"items": rows, "limit": limit, "offset": offset})

    @app.post("/api/visits")
    @login_required
    def create_visit():
        data = body()
        restaurant_id = int_value(data.get("restaurant_id"), "restaurant_id")
        restaurant_row(restaurant_id)
        party = int_value(data.get("party_size", 1), "party_size", maximum=30)
        try:
            visit_date = date.fromisoformat(data.get("visit_date", date.today().isoformat()))
        except (TypeError, ValueError) as exc:
            raise ApiError(400, "visit_date must be an ISO date.") from exc
        if visit_date > date.today():
            raise ApiError(400, "A visit cannot be in the future.")
        rating = data.get("rating")
        if rating is None and "review_text" in data:
            raise ApiError(400, "Provide rating together with review_text.")
        text = None
        if rating is not None:
            rating = int_value(rating, "rating", maximum=5)
            text = text_field(data, "review_text", 5000)
        with get_db().transaction():
            visit = get_db().execute(
                """
                INSERT INTO visit (user_id, restaurant_id, visit_date, party_size)
                VALUES (%s, %s, %s, %s) RETURNING *
                """, (current_user_id(), restaurant_id, visit_date, party),
            ).fetchone()
            review = None
            if rating is not None:
                review = get_db().execute(
                    "INSERT INTO review (visit_id, rating, review_text) VALUES (%s, %s, %s) RETURNING *",
                    (visit["visit_id"], rating, text),
                ).fetchone()
        return response({"visit": visit, "review": review}, 201)

    @app.post("/api/visits/<int:visit_id>/review")
    @login_required
    def review_visit(visit_id):
        data = body()
        rating, text = int_value(data.get("rating"), "rating", maximum=5), text_field(data, "review_text", 5000)
        with get_db().transaction():
            visit = get_db().execute(
                "SELECT user_id FROM visit WHERE visit_id = %s FOR UPDATE", (visit_id,),
            ).fetchone()
            if visit is None:
                raise ApiError(404, "Visit not found.")
            if visit["user_id"] != current_user_id():
                raise ApiError(403, "You can review only your own visits.")
            row = get_db().execute(
                "INSERT INTO review (visit_id, rating, review_text) VALUES (%s, %s, %s) RETURNING *",
                (visit_id, rating, text),
            ).fetchone()
        return response({"review": row}, 201)

    return app
