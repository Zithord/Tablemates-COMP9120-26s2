"""Flask JSON API backed by the project's PostgreSQL schema."""

from __future__ import annotations

import os
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import wraps
from typing import Any, Callable

import psycopg
from flask import Flask, Response, jsonify, render_template, request, session

from .db import DatabaseConfigError, close_db, get_db


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
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


def text_field(data: dict[str, Any], key: str, *, max_length: int = 1000) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, f"{key} must be a non-empty string.")
    value = value.strip()
    if len(value) > max_length:
        raise ApiError(400, f"{key} must be at most {max_length} characters.")
    return value


def int_value(value: Any, name: str, *, minimum: int = 1, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(400, f"{name} must be an integer.")
    if value < minimum or (maximum is not None and value > maximum):
        raise ApiError(400, f"{name} is outside the allowed range.")
    return value


def query_int(name: str, default: int, *, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ApiError(400, f"{name} must be an integer.") from exc
    return int_value(value, name, minimum=0 if name == "offset" else 1, maximum=maximum)


def id_list(data: dict[str, Any], name: str, *, minimum: int = 0, maximum: int = 10) -> list[int]:
    values = data.get(name)
    if not isinstance(values, list) or not minimum <= len(values) <= maximum:
        raise ApiError(400, f"{name} must contain {minimum} to {maximum} IDs.")
    result = [int_value(value, name) for value in values]
    if len(result) != len(set(result)):
        raise ApiError(400, f"{name} contains duplicate IDs.")
    return result


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


def parse_plan_time(data: dict[str, Any], name: str) -> datetime:
    raw = text_field(data, name, max_length=40)
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiError(400, f"{name} must be an ISO 8601 timestamp.") from exc
    if value.tzinfo is None:
        raise ApiError(400, f"{name} must include a time-zone offset.")
    return value


def visible_review(viewer_id: int, review_id: int) -> dict[str, Any] | None:
    return get_db().execute(
        """
        SELECT rv.review_id, rv.rating, rv.review_text, rv.created_at,
               v.visit_id, v.restaurant_id, v.user_id, v.visit_date, v.visibility,
               u.user_name, r.restaurant_name
        FROM review rv
        JOIN visit v ON v.visit_id = rv.visit_id
        JOIN app_user u ON u.user_id = v.user_id
        JOIN restaurant r ON r.restaurant_id = v.restaurant_id
        WHERE rv.review_id = %s
          AND (v.visibility = 'public' OR v.user_id = %s OR
               (v.visibility = 'friends' AND EXISTS (
                   SELECT 1 FROM accepted_friend af
                   WHERE af.user_id = %s AND af.friend_id = v.user_id)))
        """,
        (review_id, viewer_id, viewer_id),
    ).fetchone()


def restaurant_row(restaurant_id: int) -> dict[str, Any] | None:
    return get_db().execute(
        """
        SELECT r.restaurant_id, r.restaurant_name, r.street_address,
               r.price_level, r.is_active, s.name AS suburb, s.state, s.postcode,
               rs.review_count, rs.avg_rating,
               COALESCE((SELECT array_agg(c.cuisine_name ORDER BY c.cuisine_name)
                         FROM restaurant_cuisine rc
                         JOIN cuisine c ON c.cuisine_id = rc.cuisine_id
                         WHERE rc.restaurant_id = r.restaurant_id),
                        ARRAY[]::text[]) AS cuisines
        FROM restaurant r
        JOIN suburb s ON s.suburb_id = r.suburb_id
        JOIN restaurant_rating_summary rs ON rs.restaurant_id = r.restaurant_id
        WHERE r.restaurant_id = %s
        """,
        (restaurant_id,),
    ).fetchone()


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("APP_SECRET_KEY") or secrets.token_hex(32)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
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
    def api_error(error: ApiError) -> tuple[Response, int]:
        return response({"error": error.message}, error.status)

    @app.errorhandler(DatabaseConfigError)
    def config_error(_error: DatabaseConfigError) -> tuple[Response, int]:
        return response({"error": "Database connection is not configured."}, 503)

    @app.errorhandler(psycopg.Error)
    def database_error(error: psycopg.Error) -> tuple[Response, int]:
        if isinstance(error, psycopg.OperationalError):
            app.logger.exception("PostgreSQL is unavailable")
            return response({"error": "Database is unavailable."}, 503)
        if isinstance(error, psycopg.errors.UniqueViolation):
            return response({"error": "This record already exists."}, 409)
        if isinstance(error, (psycopg.errors.ForeignKeyViolation,
                              psycopg.errors.CheckViolation)):
            return response({"error": "The request violates a database rule."}, 400)
        if isinstance(error, psycopg.errors.RaiseException):
            return response({"error": error.diag.message_primary or "A database rule rejected the request."}, 400)
        app.logger.exception("Unexpected PostgreSQL error")
        return response({"error": "A database error occurred."}, 500)

    @app.errorhandler(404)
    def not_found(_error: Exception) -> tuple[Response, int]:
        return response({
            "error": "Endpoint not found.",
            "hint": "Open /api for the available entry points.",
        }, 404)

    @app.get("/api")
    @app.get("/api/")
    def api_index() -> tuple[Response, int]:
        return response({
            "name": "Friends Review API",
            "message": "The backend is running. Open a link below to inspect the data.",
            "links": {
                "health": "/api/health",
                "restaurants": "/api/restaurants",
                "friend_visited_restaurants_after_login": "/api/restaurants?friends_only=1&sort=friends",
                "friend_reviews_after_login": "/api/restaurants/1/reviews?friends_only=1",
                "cuisines_and_suburbs": "/api/catalog",
                "current_user_after_login": "/api/me",
            },
            "login": "POST /api/login with email and password to use personal features.",
        })

    @app.get("/")
    def home_page() -> str:
        return render_template("index.html")

    @app.get("/api/health")
    def health() -> tuple[Response, int]:
        get_db().execute("SELECT 1")
        return response({"database": "ok"})

    @app.post("/api/login")
    def login() -> tuple[Response, int]:
        data = body()
        email = text_field(data, "email", max_length=254)
        password = data.get("password")
        if not isinstance(password, str) or not 1 <= len(password) <= 200:
            raise ApiError(400, "password must be a non-empty string.")
        user = get_db().execute(
            """
            SELECT user_id, user_name, user_email
            FROM app_user
            WHERE lower(user_email) = lower(%s)
              AND password_hash = crypt(%s, password_hash)
            """,
            (email, password),
        ).fetchone()
        if user is None:
            raise ApiError(401, "Invalid email or password.")
        session.clear()
        session["user_id"] = user["user_id"]
        return response({"user": user})

    @app.post("/api/logout")
    def logout() -> tuple[Response, int]:
        session.clear()
        return response({"signed_out": True})

    @app.get("/api/me")
    @login_required
    def me() -> tuple[Response, int]:
        user = get_db().execute(
            "SELECT user_id, user_name, user_email, created_at FROM app_user WHERE user_id = %s",
            (current_user_id(),),
        ).fetchone()
        if user is None:
            session.clear()
            raise ApiError(401, "This account is no longer available.")
        return response({"user": user})

    @app.get("/api/dashboard")
    @login_required
    def dashboard() -> tuple[Response, int]:
        user_id = current_user_id()
        counts = get_db().execute(
            """
            SELECT
              (SELECT count(*) FROM accepted_friend WHERE user_id = %s) AS friend_count,
              (SELECT count(*) FROM friendship WHERE addressee_id = %s AND status = 'pending') AS incoming_requests,
              (SELECT count(*) FROM favorite WHERE user_id = %s) AS favorite_count,
              (SELECT count(*) FROM visit WHERE user_id = %s) AS visit_count,
              (SELECT count(*) FROM review rv JOIN visit v USING (visit_id)
               WHERE v.user_id = %s) AS review_count,
              (SELECT count(*) FROM recommendation WHERE receiver_id = %s
               AND status = 'unread') AS unread_recommendations
            """,
            (user_id,) * 6,
        ).fetchone()
        top = get_db().execute(
            """
            SELECT restaurant_id, restaurant_name, review_count, avg_rating
            FROM restaurant_rating_summary
            WHERE review_count >= 3
            ORDER BY avg_rating DESC NULLS LAST, review_count DESC, restaurant_id
            LIMIT 5
            """
        ).fetchall()
        return response({"counts": counts, "top_restaurants": top})

    @app.get("/api/restaurants")
    def restaurants() -> tuple[Response, int]:
        search = request.args.get("q", "").strip()
        if len(search) > 100:
            raise ApiError(400, "q must be at most 100 characters.")
        suburb = request.args.get("suburb", "").strip()
        cuisine = request.args.get("cuisine", "").strip()
        friends_only = request.args.get("friends_only", "0")
        if friends_only not in {"0", "1"}:
            raise ApiError(400, "friends_only must be 0 or 1.")
        friends_only = friends_only == "1"
        sort = request.args.get("sort", "rating")
        sorts = {
            "rating": "rs.avg_rating DESC NULLS LAST, rs.review_count DESC, r.restaurant_id",
            "reviews": "rs.review_count DESC, rs.avg_rating DESC NULLS LAST, r.restaurant_id",
            "name": "r.restaurant_name ASC, r.restaurant_id",
            "price": "r.price_level ASC, r.restaurant_name ASC",
            "friends": "friend_activity.last_friend_visit_date DESC NULLS LAST, friend_activity.friend_visit_count DESC, r.restaurant_id",
        }
        if sort not in sorts:
            raise ApiError(400, "sort must be rating, reviews, name, price or friends.")
        viewer = session.get("user_id") or -1
        if viewer == -1 and (friends_only or sort == "friends"):
            raise ApiError(401, "Log in to see places visited by friends.")
        limit = query_int("limit", 20, maximum=50)
        offset = query_int("offset", 0, maximum=10000)
        rows = get_db().execute(
            f"""
            SELECT r.restaurant_id, r.restaurant_name, r.street_address,
                   r.price_level, s.name AS suburb, rs.review_count, rs.avg_rating,
                   friend_activity.friend_visit_count,
                   friend_activity.last_friend_visit_date,
                   friend_activity.friend_names,
                   COALESCE((SELECT array_agg(c.cuisine_name ORDER BY c.cuisine_name)
                             FROM restaurant_cuisine rc
                             JOIN cuisine c ON c.cuisine_id = rc.cuisine_id
                             WHERE rc.restaurant_id = r.restaurant_id),
                            ARRAY[]::text[]) AS cuisines
            FROM restaurant r
            JOIN suburb s ON s.suburb_id = r.suburb_id
            JOIN restaurant_rating_summary rs ON rs.restaurant_id = r.restaurant_id
            CROSS JOIN LATERAL (
                SELECT count(*)::int AS friend_visit_count,
                       max(recent.visit_date) AS last_friend_visit_date,
                       COALESCE((array_agg(recent.user_name ORDER BY recent.visit_date DESC,
                                            recent.user_id))[:3], ARRAY[]::text[]) AS friend_names
                FROM (
                    SELECT DISTINCT ON (v.user_id) v.user_id, u.user_name, v.visit_date
                    FROM visit v
                    JOIN accepted_friend af ON af.friend_id = v.user_id
                                           AND af.user_id = %s
                    JOIN app_user u ON u.user_id = v.user_id
                    WHERE v.restaurant_id = r.restaurant_id
                      AND v.visibility IN ('public', 'friends')
                      AND v.visit_date >= current_date - 90
                      AND v.visit_date <= current_date
                    ORDER BY v.user_id, v.visit_date DESC, v.visit_id DESC
                ) recent
            ) friend_activity
            WHERE r.is_active
              AND (%s = '' OR r.restaurant_name ILIKE %s)
              AND (%s = '' OR lower(s.name) = lower(%s))
              AND (%s = '' OR EXISTS (
                  SELECT 1 FROM restaurant_cuisine rc
                  JOIN cuisine c ON c.cuisine_id = rc.cuisine_id
                  WHERE rc.restaurant_id = r.restaurant_id
                    AND lower(c.cuisine_name) = lower(%s)))
              AND (%s = false OR friend_activity.friend_visit_count > 0)
            ORDER BY {sorts[sort]}
            LIMIT %s OFFSET %s
            """,
            (viewer, search, f"%{search}%", suburb, suburb, cuisine, cuisine,
             friends_only, limit, offset),
        ).fetchall()
        return response({"items": rows, "limit": limit, "offset": offset})

    @app.get("/api/restaurants/<int:restaurant_id>")
    def restaurant_detail(restaurant_id: int) -> tuple[Response, int]:
        restaurant = restaurant_row(restaurant_id)
        if restaurant is None:
            raise ApiError(404, "Restaurant not found.")
        menu = get_db().execute(
            """
            SELECT dish_id, dish_name, description, price_aud, is_available
            FROM dish WHERE restaurant_id = %s ORDER BY dish_name
            """,
            (restaurant_id,),
        ).fetchall()
        return response({"restaurant": restaurant, "menu": menu})

    @app.get("/api/restaurants/<int:restaurant_id>/friend-visits")
    @login_required
    def restaurant_friend_visits(restaurant_id: int) -> tuple[Response, int]:
        if restaurant_row(restaurant_id) is None:
            raise ApiError(404, "Restaurant not found.")
        rows = get_db().execute(
            """
            SELECT DISTINCT ON (v.user_id) v.user_id, u.user_name,
                   v.visit_date, rv.review_id, rv.rating
            FROM visit v
            JOIN accepted_friend af ON af.friend_id = v.user_id
                                   AND af.user_id = %s
            JOIN app_user u ON u.user_id = v.user_id
            LEFT JOIN review rv ON rv.visit_id = v.visit_id
            WHERE v.restaurant_id = %s
              AND v.visibility IN ('public', 'friends')
              AND v.visit_date >= current_date - 90
              AND v.visit_date <= current_date
            ORDER BY v.user_id, v.visit_date DESC, v.visit_id DESC
            """,
            (current_user_id(), restaurant_id),
        ).fetchall()
        rows.sort(key=lambda row: (row["visit_date"], row["user_id"]), reverse=True)
        return response({"items": rows, "friend_count": len(rows), "recent_days": 90})

    @app.get("/api/users")
    @login_required
    def users() -> tuple[Response, int]:
        viewer = current_user_id()
        search = request.args.get("q", "").strip()
        if len(search) > 100:
            raise ApiError(400, "q must be at most 100 characters.")
        rows = get_db().execute(
            """
            SELECT u.user_id, u.user_name, f.friendship_id, f.status AS friendship_status,
                   CASE WHEN f.requester_id = %s THEN 'sent'
                        WHEN f.addressee_id = %s THEN 'received' END AS request_direction
            FROM app_user u
            LEFT JOIN friendship f
              ON (f.requester_id = %s AND f.addressee_id = u.user_id)
              OR (f.addressee_id = %s AND f.requester_id = u.user_id)
            WHERE u.user_id <> %s AND (%s = '' OR u.user_name ILIKE %s)
            ORDER BY u.user_name, u.user_id LIMIT 30
            """,
            (viewer, viewer, viewer, viewer, viewer, search, f"%{search}%"),
        ).fetchall()
        return response({"items": rows})

    @app.get("/api/users/<int:user_id>")
    def user_profile(user_id: int) -> tuple[Response, int]:
        user = get_db().execute(
            "SELECT user_id, user_name, created_at FROM app_user WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        if user is None:
            raise ApiError(404, "User not found.")
        return response({"user": user})

    @app.get("/api/friends")
    @login_required
    def friends() -> tuple[Response, int]:
        viewer = current_user_id()
        rows = get_db().execute(
            """
            SELECT f.friendship_id, f.requester_id, f.addressee_id, f.status,
                   f.requested_at, f.accepted_at,
                   CASE WHEN f.requester_id = %s THEN 'sent'
                        ELSE 'received' END AS direction,
                   u.user_id AS other_user_id, u.user_name AS other_user_name
            FROM friendship f
            JOIN app_user u ON u.user_id = CASE WHEN f.requester_id = %s
                                               THEN f.addressee_id ELSE f.requester_id END
            WHERE f.requester_id = %s OR f.addressee_id = %s
            ORDER BY CASE f.status WHEN 'pending' THEN 0 WHEN 'accepted' THEN 1 ELSE 2 END,
                     f.requested_at DESC, f.friendship_id DESC
            """,
            (viewer, viewer, viewer, viewer),
        ).fetchall()
        return response({"items": rows})

    @app.post("/api/friend-requests")
    @login_required
    def send_friend_request() -> tuple[Response, int]:
        target = int_value(body().get("addressee_id"), "addressee_id")
        viewer = current_user_id()
        if target == viewer:
            raise ApiError(400, "You cannot send a request to yourself.")
        if get_db().execute("SELECT 1 FROM app_user WHERE user_id = %s", (target,)).fetchone() is None:
            raise ApiError(404, "User not found.")
        with get_db().transaction():
            row = get_db().execute(
                """
                INSERT INTO friendship (requester_id, addressee_id, status)
                VALUES (%s, %s, 'pending')
                RETURNING friendship_id, requester_id, addressee_id, status, requested_at
                """,
                (viewer, target),
            ).fetchone()
        return response({"friendship": row}, 201)

    @app.post("/api/friend-requests/<int:friendship_id>/<action>")
    @login_required
    def decide_friend_request(friendship_id: int, action: str) -> tuple[Response, int]:
        if action not in {"accept", "reject"}:
            raise ApiError(404, "Friend request action not found.")
        viewer = current_user_id()
        with get_db().transaction():
            row = get_db().execute(
                """
                UPDATE friendship
                SET status = %s,
                    accepted_at = CASE WHEN %s = 'accepted' THEN now() ELSE NULL END
                WHERE friendship_id = %s AND addressee_id = %s AND status = 'pending'
                RETURNING friendship_id, requester_id, addressee_id, status, accepted_at
                """,
                ("accepted" if action == "accept" else "rejected",
                 "accepted" if action == "accept" else "rejected",
                 friendship_id, viewer),
            ).fetchone()
        if row is None:
            existing = get_db().execute(
                "SELECT addressee_id, status FROM friendship WHERE friendship_id = %s",
                (friendship_id,),
            ).fetchone()
            if existing is None:
                raise ApiError(404, "Friend request not found.")
            if existing["addressee_id"] != viewer:
                raise ApiError(403, "Only the recipient can decide this request.")
            raise ApiError(409, "This request is no longer pending.")
        return response({"friendship": row})

    @app.get("/api/favorites")
    @login_required
    def favorites() -> tuple[Response, int]:
        rows = get_db().execute(
            """
            SELECT f.restaurant_id, f.added_at, r.restaurant_name,
                   s.name AS suburb, rs.review_count, rs.avg_rating,
                   friend_activity.friend_visit_count,
                   friend_activity.last_friend_visit_date,
                   friend_activity.friend_names
            FROM favorite f
            JOIN restaurant r ON r.restaurant_id = f.restaurant_id
            JOIN suburb s ON s.suburb_id = r.suburb_id
            JOIN restaurant_rating_summary rs ON rs.restaurant_id = r.restaurant_id
            CROSS JOIN LATERAL (
                SELECT count(*)::int AS friend_visit_count,
                       max(recent.visit_date) AS last_friend_visit_date,
                       COALESCE((array_agg(recent.user_name ORDER BY recent.visit_date DESC,
                                            recent.user_id))[:3], ARRAY[]::text[]) AS friend_names
                FROM (
                    SELECT DISTINCT ON (v.user_id) v.user_id, u.user_name, v.visit_date
                    FROM visit v
                    JOIN accepted_friend af ON af.friend_id = v.user_id
                                           AND af.user_id = f.user_id
                    JOIN app_user u ON u.user_id = v.user_id
                    WHERE v.restaurant_id = f.restaurant_id
                      AND v.visibility IN ('public', 'friends')
                      AND v.visit_date BETWEEN current_date - 90 AND current_date
                    ORDER BY v.user_id, v.visit_date DESC, v.visit_id DESC
                ) recent
            ) friend_activity
            WHERE f.user_id = %s
            ORDER BY f.added_at DESC, f.restaurant_id
            """,
            (current_user_id(),),
        ).fetchall()
        return response({"items": rows})

    @app.post("/api/favorites")
    @login_required
    def add_favorite() -> tuple[Response, int]:
        restaurant_id = int_value(body().get("restaurant_id"), "restaurant_id")
        if restaurant_row(restaurant_id) is None:
            raise ApiError(404, "Restaurant not found.")
        with get_db().transaction():
            row = get_db().execute(
                """
                INSERT INTO favorite (user_id, restaurant_id) VALUES (%s, %s)
                ON CONFLICT (user_id, restaurant_id) DO UPDATE SET added_at = favorite.added_at
                RETURNING user_id, restaurant_id, added_at
                """,
                (current_user_id(), restaurant_id),
            ).fetchone()
        return response({"favorite": row})

    @app.delete("/api/favorites/<int:restaurant_id>")
    @login_required
    def remove_favorite(restaurant_id: int) -> Response:
        with get_db().transaction():
            get_db().execute(
                "DELETE FROM favorite WHERE user_id = %s AND restaurant_id = %s",
                (current_user_id(), restaurant_id),
            )
        return Response(status=204)

    @app.get("/api/restaurants/<int:restaurant_id>/reviews")
    def restaurant_reviews(restaurant_id: int) -> tuple[Response, int]:
        if restaurant_row(restaurant_id) is None:
            raise ApiError(404, "Restaurant not found.")
        viewer = session.get("user_id") or -1
        friends_only = request.args.get("friends_only", "0")
        if friends_only not in {"0", "1"}:
            raise ApiError(400, "friends_only must be 0 or 1.")
        friends_only = friends_only == "1"
        if viewer == -1 and friends_only:
            raise ApiError(401, "Log in to see friends' reviews.")
        limit = query_int("limit", 20, maximum=50)
        offset = query_int("offset", 0, maximum=10000)
        rows = get_db().execute(
            """
            SELECT rv.review_id, rv.rating, rv.review_text, rv.created_at,
                   v.visit_id, v.visit_date, v.visibility,
                   u.user_id, u.user_name
            FROM review rv
            JOIN visit v ON v.visit_id = rv.visit_id
            JOIN app_user u ON u.user_id = v.user_id
            WHERE v.restaurant_id = %s
              AND (v.visibility = 'public' OR v.user_id = %s OR
                   (v.visibility = 'friends' AND EXISTS (
                       SELECT 1 FROM accepted_friend af
                       WHERE af.user_id = %s AND af.friend_id = v.user_id)))
              AND (%s = false OR EXISTS (
                       SELECT 1 FROM accepted_friend af
                       WHERE af.user_id = %s AND af.friend_id = v.user_id))
            ORDER BY rv.created_at DESC, rv.review_id DESC
            LIMIT %s OFFSET %s
            """,
            (restaurant_id, viewer, viewer, friends_only, viewer, limit, offset),
        ).fetchall()
        return response({"items": rows, "limit": limit, "offset": offset})

    @app.get("/api/users/<int:user_id>/reviews")
    def user_reviews(user_id: int) -> tuple[Response, int]:
        if get_db().execute("SELECT 1 FROM app_user WHERE user_id = %s", (user_id,)).fetchone() is None:
            raise ApiError(404, "User not found.")
        viewer = session.get("user_id") or -1
        limit = query_int("limit", 20, maximum=50)
        offset = query_int("offset", 0, maximum=10000)
        rows = get_db().execute(
            """
            SELECT rv.review_id, rv.rating, rv.review_text, rv.created_at,
                   v.visit_date, v.visibility, r.restaurant_id, r.restaurant_name
            FROM review rv
            JOIN visit v ON v.visit_id = rv.visit_id
            JOIN restaurant r ON r.restaurant_id = v.restaurant_id
            WHERE v.user_id = %s
              AND (v.visibility = 'public' OR v.user_id = %s OR
                   (v.visibility = 'friends' AND EXISTS (
                       SELECT 1 FROM accepted_friend af
                       WHERE af.user_id = %s AND af.friend_id = v.user_id)))
            ORDER BY rv.created_at DESC, rv.review_id DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, viewer, viewer, limit, offset),
        ).fetchall()
        return response({"items": rows, "limit": limit, "offset": offset})

    @app.get("/api/feed")
    @login_required
    def feed() -> tuple[Response, int]:
        limit = query_int("limit", 20, maximum=50)
        offset = query_int("offset", 0, maximum=10000)
        rows = get_db().execute(
            """
            SELECT rv.review_id, rv.rating, rv.review_text, rv.created_at,
                   v.visit_date, v.visibility, u.user_id, u.user_name,
                   r.restaurant_id, r.restaurant_name
            FROM accepted_friend af
            JOIN visit v ON v.user_id = af.friend_id
            JOIN review rv ON rv.visit_id = v.visit_id
            JOIN app_user u ON u.user_id = v.user_id
            JOIN restaurant r ON r.restaurant_id = v.restaurant_id
            WHERE af.user_id = %s AND v.visibility IN ('public', 'friends')
            ORDER BY rv.created_at DESC, rv.review_id DESC
            LIMIT %s OFFSET %s
            """,
            (current_user_id(), limit, offset),
        ).fetchall()
        return response({"items": rows, "limit": limit, "offset": offset})

    @app.get("/api/reviews/<int:review_id>")
    def review_detail(review_id: int) -> tuple[Response, int]:
        row = visible_review(session.get("user_id") or -1, review_id)
        if row is None:
            raise ApiError(404, "Review not found or not visible.")
        return response({"review": row})

    @app.get("/api/reviews/<int:review_id>/comments")
    def comments(review_id: int) -> tuple[Response, int]:
        if visible_review(session.get("user_id") or -1, review_id) is None:
            raise ApiError(404, "Review not found or not visible.")
        rows = get_db().execute(
            """
            SELECT c.comment_id, c.parent_comment_id, c.comment_text, c.created_at,
                   u.user_id AS author_id, u.user_name AS author_name
            FROM review_comment c
            JOIN app_user u ON u.user_id = c.author_id
            WHERE c.review_id = %s ORDER BY c.created_at, c.comment_id
            """,
            (review_id,),
        ).fetchall()
        return response({"items": rows})

    @app.post("/api/reviews/<int:review_id>/comments")
    @login_required
    def add_comment(review_id: int) -> tuple[Response, int]:
        if visible_review(current_user_id(), review_id) is None:
            raise ApiError(404, "Review not found or not visible.")
        data = body()
        comment_text = text_field(data, "comment_text", max_length=1000)
        parent_id = data.get("parent_comment_id")
        if parent_id is not None:
            parent_id = int_value(parent_id, "parent_comment_id")
        with get_db().transaction():
            row = get_db().execute(
                """
                INSERT INTO review_comment (review_id, author_id, parent_comment_id, comment_text)
                VALUES (%s, %s, %s, %s)
                RETURNING comment_id, review_id, author_id, parent_comment_id,
                          comment_text, created_at
                """,
                (review_id, current_user_id(), parent_id, comment_text),
            ).fetchone()
        return response({"comment": row}, 201)

    @app.get("/api/me/visits")
    @login_required
    def my_visits() -> tuple[Response, int]:
        rows = get_db().execute(
            """
            SELECT v.visit_id, v.restaurant_id, r.restaurant_name, v.plan_id,
                   v.visit_date, v.party_size, v.visibility,
                   rv.review_id, rv.rating, rv.review_text
            FROM visit v
            JOIN restaurant r ON r.restaurant_id = v.restaurant_id
            LEFT JOIN review rv ON rv.visit_id = v.visit_id
            WHERE v.user_id = %s
            ORDER BY v.visit_date DESC, v.visit_id DESC LIMIT 100
            """,
            (current_user_id(),),
        ).fetchall()
        return response({"items": rows})

    @app.post("/api/visits")
    @login_required
    def create_visit() -> tuple[Response, int]:
        data = body()
        restaurant_id = int_value(data.get("restaurant_id"), "restaurant_id")
        party_size = int_value(data.get("party_size", 1), "party_size", maximum=30)
        visibility = data.get("visibility", "friends")
        if visibility not in {"public", "friends", "private"}:
            raise ApiError(400, "visibility must be public, friends or private.")
        raw_date = data.get("visit_date", date.today().isoformat())
        if not isinstance(raw_date, str):
            raise ApiError(400, "visit_date must be an ISO date.")
        try:
            visit_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ApiError(400, "visit_date must be an ISO date.") from exc
        if visit_date > date.today():
            raise ApiError(400, "A visit cannot be in the future.")
        plan_id = data.get("plan_id")
        if plan_id is not None:
            plan_id = int_value(plan_id, "plan_id")
        rating = data.get("rating")
        if rating is not None:
            rating = int_value(rating, "rating", maximum=5)
            review_text = text_field(data, "review_text", max_length=5000)
        else:
            if "review_text" in data:
                raise ApiError(400, "Provide rating together with review_text.")
            review_text = None
        with get_db().transaction():
            visit = get_db().execute(
                """
                INSERT INTO visit (user_id, restaurant_id, plan_id, visit_date,
                                   party_size, visibility)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING visit_id, user_id, restaurant_id, plan_id,
                          visit_date, party_size, visibility
                """,
                (current_user_id(), restaurant_id, plan_id, visit_date,
                 party_size, visibility),
            ).fetchone()
            review = None
            if rating is not None:
                review = get_db().execute(
                    """
                    INSERT INTO review (visit_id, rating, review_text)
                    VALUES (%s, %s, %s)
                    RETURNING review_id, visit_id, rating, review_text, created_at
                    """,
                    (visit["visit_id"], rating, review_text),
                ).fetchone()
        return response({"visit": visit, "review": review}, 201)

    @app.post("/api/visits/<int:visit_id>/review")
    @login_required
    def review_visit(visit_id: int) -> tuple[Response, int]:
        data = body()
        rating = int_value(data.get("rating"), "rating", maximum=5)
        review_text = text_field(data, "review_text", max_length=5000)
        with get_db().transaction():
            visit = get_db().execute(
                "SELECT user_id FROM visit WHERE visit_id = %s FOR UPDATE",
                (visit_id,),
            ).fetchone()
            if visit is None:
                raise ApiError(404, "Visit not found.")
            if visit["user_id"] != current_user_id():
                raise ApiError(403, "You can review only your own visits.")
            row = get_db().execute(
                """
                INSERT INTO review (visit_id, rating, review_text)
                VALUES (%s, %s, %s)
                RETURNING review_id, visit_id, rating, review_text, created_at
                """,
                (visit_id, rating, review_text),
            ).fetchone()
        return response({"review": row}, 201)

    @app.get("/api/catalog")
    def catalog() -> tuple[Response, int]:
        cuisines = get_db().execute(
            "SELECT cuisine_id, cuisine_name FROM cuisine ORDER BY cuisine_name"
        ).fetchall()
        suburbs = get_db().execute(
            "SELECT suburb_id, name, state, postcode FROM suburb ORDER BY name"
        ).fetchall()
        return response({"cuisines": cuisines, "suburbs": suburbs})

    @app.get("/api/recommendations")
    @login_required
    def recommendations() -> tuple[Response, int]:
        viewer = current_user_id()
        rows = get_db().execute(
            """
            SELECT rec.recommendation_id, rec.sender_id, sender.user_name AS sender_name,
                   rec.receiver_id, receiver.user_name AS receiver_name,
                   rec.restaurant_id, r.restaurant_name, rec.message,
                   rec.status, rec.created_at
            FROM recommendation rec
            JOIN app_user sender ON sender.user_id = rec.sender_id
            JOIN app_user receiver ON receiver.user_id = rec.receiver_id
            JOIN restaurant r ON r.restaurant_id = rec.restaurant_id
            WHERE rec.sender_id = %s OR rec.receiver_id = %s
            ORDER BY rec.created_at DESC, rec.recommendation_id DESC
            LIMIT 100
            """,
            (viewer, viewer),
        ).fetchall()
        return response({"items": rows})

    @app.post("/api/recommendations")
    @login_required
    def send_recommendation() -> tuple[Response, int]:
        data = body()
        receiver_id = int_value(data.get("receiver_id"), "receiver_id")
        restaurant_id = int_value(data.get("restaurant_id"), "restaurant_id")
        message = text_field(data, "message", max_length=1000)
        with get_db().transaction():
            row = get_db().execute(
                """
                INSERT INTO recommendation (sender_id, receiver_id, restaurant_id, message)
                VALUES (%s, %s, %s, %s)
                RETURNING recommendation_id, sender_id, receiver_id,
                          restaurant_id, message, status, created_at
                """,
                (current_user_id(), receiver_id, restaurant_id, message),
            ).fetchone()
        return response({"recommendation": row}, 201)

    @app.patch("/api/recommendations/<int:recommendation_id>")
    @login_required
    def update_recommendation(recommendation_id: int) -> tuple[Response, int]:
        status = body().get("status")
        if status not in {"read", "dismissed"}:
            raise ApiError(400, "status must be read or dismissed.")
        with get_db().transaction():
            row = get_db().execute(
                """
                UPDATE recommendation SET status = %s
                WHERE recommendation_id = %s AND receiver_id = %s
                RETURNING recommendation_id, receiver_id, status
                """,
                (status, recommendation_id, current_user_id()),
            ).fetchone()
        if row is None:
            raise ApiError(404, "Recommendation not found for this user.")
        return response({"recommendation": row})

    @app.get("/api/plans")
    @login_required
    def plans() -> tuple[Response, int]:
        rows = get_db().execute(
            """
            SELECT p.plan_id, p.creator_id, u.user_name AS creator_name,
                   p.title, p.plan_date, p.voting_deadline, p.status,
                   p.chosen_restaurant_id, r.restaurant_name AS chosen_restaurant_name,
                   pp.rsvp_status AS my_rsvp
            FROM dining_plan p
            JOIN plan_participant pp ON pp.plan_id = p.plan_id
            JOIN app_user u ON u.user_id = p.creator_id
            LEFT JOIN restaurant r ON r.restaurant_id = p.chosen_restaurant_id
            WHERE pp.user_id = %s
            ORDER BY p.plan_date DESC, p.plan_id DESC LIMIT 100
            """,
            (current_user_id(),),
        ).fetchall()
        return response({"items": rows})

    @app.post("/api/plans")
    @login_required
    def create_plan() -> tuple[Response, int]:
        data = body()
        title = text_field(data, "title", max_length=120)
        plan_date = parse_plan_time(data, "plan_date")
        deadline = parse_plan_time(data, "voting_deadline")
        if not datetime.now(timezone.utc) < deadline < plan_date:
            raise ApiError(400, "The voting deadline must be in the future and before the meal.")
        status = data.get("status", "open")
        if status not in {"draft", "open"}:
            raise ApiError(400, "A new plan must be draft or open.")
        candidate_ids = id_list(data, "candidate_restaurant_ids", minimum=2, maximum=5)
        invitee_ids = id_list(data, "invitee_ids", minimum=0, maximum=10)
        if current_user_id() in invitee_ids:
            raise ApiError(400, "The creator is included automatically.")
        with get_db().transaction():
            plan = get_db().execute(
                """
                INSERT INTO dining_plan
                    (creator_id, title, plan_date, voting_deadline, status)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING plan_id, creator_id, title, plan_date, voting_deadline, status
                """,
                (current_user_id(), title, plan_date, deadline, status),
            ).fetchone()
            for restaurant_id in candidate_ids:
                get_db().execute(
                    "INSERT INTO plan_candidate (plan_id, restaurant_id) VALUES (%s, %s)",
                    (plan["plan_id"], restaurant_id),
                )
            for invitee_id in invitee_ids:
                get_db().execute(
                    "INSERT INTO plan_participant (plan_id, user_id) VALUES (%s, %s)",
                    (plan["plan_id"], invitee_id),
                )
        return response({"plan": plan}, 201)

    @app.get("/api/plans/<int:plan_id>")
    @login_required
    def plan_detail(plan_id: int) -> tuple[Response, int]:
        plan = get_db().execute(
            """
            SELECT p.plan_id, p.creator_id, p.title, p.plan_date,
                   p.voting_deadline, p.status, p.chosen_restaurant_id,
                   r.restaurant_name AS chosen_restaurant_name, p.created_at
            FROM dining_plan p
            JOIN plan_participant pp ON pp.plan_id = p.plan_id
            LEFT JOIN restaurant r ON r.restaurant_id = p.chosen_restaurant_id
            WHERE p.plan_id = %s AND pp.user_id = %s
            """,
            (plan_id, current_user_id()),
        ).fetchone()
        if plan is None:
            raise ApiError(404, "Plan not found for this user.")
        participants = get_db().execute(
            """
            SELECT pp.user_id, u.user_name, pp.rsvp_status,
                   pp.invited_at, pp.responded_at
            FROM plan_participant pp
            JOIN app_user u ON u.user_id = pp.user_id
            WHERE pp.plan_id = %s ORDER BY pp.user_id
            """,
            (plan_id,),
        ).fetchall()
        candidates = get_db().execute(
            """
            SELECT pc.restaurant_id, r.restaurant_name, rs.avg_rating,
                   rs.review_count, count(pv.user_id) AS vote_count
            FROM plan_candidate pc
            JOIN restaurant r ON r.restaurant_id = pc.restaurant_id
            JOIN restaurant_rating_summary rs ON rs.restaurant_id = pc.restaurant_id
            LEFT JOIN plan_vote pv ON pv.plan_id = pc.plan_id
                                  AND pv.restaurant_id = pc.restaurant_id
            WHERE pc.plan_id = %s
            GROUP BY pc.restaurant_id, r.restaurant_name, rs.avg_rating, rs.review_count
            ORDER BY vote_count DESC, pc.restaurant_id
            """,
            (plan_id,),
        ).fetchall()
        votes = get_db().execute(
            """
            SELECT pv.user_id, u.user_name, pv.restaurant_id, pv.voted_at
            FROM plan_vote pv JOIN app_user u ON u.user_id = pv.user_id
            WHERE pv.plan_id = %s ORDER BY pv.user_id
            """,
            (plan_id,),
        ).fetchall()
        return response({"plan": plan, "participants": participants,
                         "candidates": candidates, "votes": votes})

    @app.post("/api/plans/<int:plan_id>/rsvp")
    @login_required
    def plan_rsvp(plan_id: int) -> tuple[Response, int]:
        rsvp = body().get("rsvp_status")
        if rsvp not in {"accepted", "declined"}:
            raise ApiError(400, "rsvp_status must be accepted or declined.")
        with get_db().transaction():
            row = get_db().execute(
                """
                UPDATE plan_participant pp
                SET rsvp_status = %s, responded_at = now()
                FROM dining_plan p
                WHERE pp.plan_id = p.plan_id AND pp.plan_id = %s
                  AND pp.user_id = %s AND pp.rsvp_status = 'invited'
                  AND p.status IN ('draft', 'open')
                RETURNING pp.plan_id, pp.user_id, pp.rsvp_status, pp.responded_at
                """,
                (rsvp, plan_id, current_user_id()),
            ).fetchone()
        if row is None:
            raise ApiError(409, "This invitation is no longer open.")
        return response({"participant": row})

    @app.post("/api/plans/<int:plan_id>/open")
    @login_required
    def open_plan(plan_id: int) -> tuple[Response, int]:
        with get_db().transaction():
            row = get_db().execute(
                """
                UPDATE dining_plan p SET status = 'open'
                WHERE p.plan_id = %s AND p.creator_id = %s AND p.status = 'draft'
                  AND p.voting_deadline > now()
                  AND (SELECT count(*) FROM plan_candidate pc
                       WHERE pc.plan_id = p.plan_id) >= 2
                RETURNING p.plan_id, p.status, p.voting_deadline
                """,
                (plan_id, current_user_id()),
            ).fetchone()
        if row is None:
            raise ApiError(409, "This draft cannot be opened by the current user.")
        return response({"plan": row})

    @app.post("/api/plans/<int:plan_id>/vote")
    @login_required
    def vote(plan_id: int) -> tuple[Response, int]:
        restaurant_id = int_value(body().get("restaurant_id"), "restaurant_id")
        with get_db().transaction():
            row = get_db().execute(
                """
                INSERT INTO plan_vote (plan_id, user_id, restaurant_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (plan_id, user_id)
                DO UPDATE SET restaurant_id = EXCLUDED.restaurant_id, voted_at = now()
                RETURNING plan_id, user_id, restaurant_id, voted_at
                """,
                (plan_id, current_user_id(), restaurant_id),
            ).fetchone()
        return response({"vote": row})

    @app.post("/api/plans/<int:plan_id>/finalize")
    @login_required
    def finalize_plan(plan_id: int) -> tuple[Response, int]:
        # The plan lock also serializes with the vote trigger's FOR UPDATE lock.
        with get_db().transaction():
            plan = get_db().execute(
                """
                SELECT plan_id, creator_id, status, voting_deadline
                FROM dining_plan WHERE plan_id = %s FOR UPDATE
                """,
                (plan_id,),
            ).fetchone()
            if plan is None:
                raise ApiError(404, "Plan not found.")
            if plan["creator_id"] != current_user_id():
                raise ApiError(403, "Only the creator can finalize the plan.")
            if plan["status"] != "open":
                raise ApiError(409, "Only an open plan can be finalized.")
            unvoted = get_db().execute(
                """
                SELECT count(*) AS n
                FROM plan_participant pp
                LEFT JOIN plan_vote pv ON pv.plan_id = pp.plan_id
                                      AND pv.user_id = pp.user_id
                WHERE pp.plan_id = %s AND pp.rsvp_status = 'accepted'
                  AND pv.user_id IS NULL
                """,
                (plan_id,),
            ).fetchone()["n"]
            if plan["voting_deadline"] > datetime.now(timezone.utc) and unvoted:
                raise ApiError(409, "Wait for accepted participants to vote or for the deadline.")
            winner = get_db().execute(
                """
                SELECT pc.restaurant_id, count(pv.user_id) AS vote_count
                FROM plan_candidate pc
                LEFT JOIN plan_vote pv ON pv.plan_id = pc.plan_id
                                      AND pv.restaurant_id = pc.restaurant_id
                WHERE pc.plan_id = %s
                GROUP BY pc.restaurant_id
                ORDER BY vote_count DESC, pc.restaurant_id ASC
                LIMIT 1
                """,
                (plan_id,),
            ).fetchone()
            if winner is None:
                raise ApiError(409, "The plan has no candidate restaurants.")
            if winner["vote_count"] == 0:
                raise ApiError(409, "At least one vote is needed to choose a restaurant.")
            result = get_db().execute(
                """
                UPDATE dining_plan
                SET status = 'finalized', chosen_restaurant_id = %s
                WHERE plan_id = %s
                RETURNING plan_id, status, chosen_restaurant_id
                """,
                (winner["restaurant_id"], plan_id),
            ).fetchone()
        return response({"plan": result, "winning_vote_count": winner["vote_count"]})

    @app.post("/api/plans/<int:plan_id>/cancel")
    @login_required
    def cancel_plan(plan_id: int) -> tuple[Response, int]:
        with get_db().transaction():
            row = get_db().execute(
                """
                UPDATE dining_plan SET status = 'cancelled'
                WHERE plan_id = %s AND creator_id = %s AND status IN ('draft', 'open')
                RETURNING plan_id, status
                """,
                (plan_id, current_user_id()),
            ).fetchone()
        if row is None:
            raise ApiError(409, "This plan cannot be cancelled by the current user.")
        return response({"plan": row})

    return app
