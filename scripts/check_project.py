"""Integration checks in a disposable database; the application database is not modified."""

from __future__ import annotations

import argparse
import csv
import secrets
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from app import create_app
from app.db import connect
from seed_data import import_data
from generate_data import FILES


def expect(client, method: str, path: str, status: int = 200, data=None):
    result = client.open(path, method=method, json=data)
    assert result.status_code == status, (method, path, result.status_code, result.get_json())
    return result.get_json() if status != 204 else None


def check(connection, factory):
    def count(table):
        return connection.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(table))).fetchone()["n"]

    # A late FK failure must undo all earlier table imports, including the users.
    with tempfile.TemporaryDirectory(prefix="tablemates-csv-check-") as folder:
        directory = Path(folder)
        for name in FILES:
            shutil.copyfile(ROOT / "data" / f"{name}.csv", directory / f"{name}.csv")
        path = directory / "review_comments.csv"
        with path.open(encoding="utf-8", newline="") as file:
            records = list(csv.reader(file))
        records[-1][1], records[-1][3] = "2", "1"  # Parent 1 belongs to review 1, not 2.
        with path.open("w", encoding="utf-8", newline="") as file:
            csv.writer(file).writerows(records)
        try:
            import_data(connection, directory)
            raise AssertionError("Invalid CSV import unexpectedly succeeded.")
        except psycopg.errors.ForeignKeyViolation:
            pass
        assert all(count(table) == 0 for table, _ in FILES.values())
    print("PASS: invalid CSV import rolls back all ten tables")

    counts = import_data(connection, ROOT / "data")
    assert counts["users"] == 100 and counts["restaurants"] == 50 and counts["reviews"] == 1000
    assert count("app_user") == 100 and count("review_comment") == 246
    try:
        import_data(connection, ROOT / "data")
        raise AssertionError("Repeated import unexpectedly succeeded.")
    except ValueError as error:
        assert "not empty" in str(error)
    assert count("app_user") == 100
    print("PASS: CSV import, initial scale and repeat-import protection")

    with patch("app.db.connect", side_effect=factory):
        app = create_app()
        app.testing = True
        alice, ben, anonymous = app.test_client(), app.test_client(), app.test_client()
        expect(anonymous, "GET", "/api/health")
        expect(anonymous, "GET", "/api/me", 401)
        expect(anonymous, "POST", "/api/login", 401, {"email": "' OR '1'='1", "password": "anything"})
        expect(alice, "POST", "/api/login", data={"email": "alice.morgan@example.test", "password": "DemoPass2026!"})
        expect(ben, "POST", "/api/login", data={"email": "ben.carter@example.test", "password": "DemoPass2026!"})
        expect(anonymous, "POST", "/api/register", 400, {"user_name": "New User", "email": "invalid", "password": "SecurePass123!"})
        registration = expect(anonymous, "POST", "/api/register", 201,
                              {"user_name": "New User", "email": "New.User@example.test", "password": "SecurePass123!"})
        assert registration["user"]["user_id"] == 101
        assert "password_hash" not in registration["user"]
        expect(anonymous, "POST", "/api/register", 409,
               {"user_name": "Duplicate", "email": "NEW.USER@EXAMPLE.TEST", "password": "SecurePass123!"})
        expect(anonymous, "POST", "/api/register", 400,
               {"user_name": "Too Long", "email": "long@example.test", "password": "é" * 40})
        hashed = connection.execute("SELECT password_hash FROM app_user WHERE user_id = 101").fetchone()["password_hash"]
        assert hashed.startswith("$2") and hashed != "SecurePass123!"
        expect(anonymous, "POST", "/api/logout")
        expect(anonymous, "POST", "/api/login", data={"email": "new.user@example.test", "password": "SecurePass123!"})
        print("PASS: registration, hash-only storage, duplicate email, password bounds and login")

        places = expect(alice, "GET", "/api/restaurants?limit=50")["items"]
        assert len(places) == 50
        filtered = expect(alice, "GET", "/api/restaurants?suburb=Newtown&cuisine=Chinese&price_level=2&min_rating=3")["items"]
        assert filtered and all(p["suburb"] == "Newtown" and "Chinese" in p["cuisines"] and p["price_level"] == 2 and p["avg_rating"] >= 3 for p in filtered)
        expect(alice, "GET", "/api/restaurants?min_rating=nan", 400)
        expect(alice, "GET", "/api/restaurants?sort=invalid", 400)
        friends = expect(alice, "GET", "/api/restaurants?friends_only=1&sort=friends&limit=50")["items"]
        assert friends and all(p["friend_visit_count"] > 0 for p in friends)
        visitors = expect(alice, "GET", "/api/restaurants/1/friend-visits")["items"]
        assert {2, 3}.issubset({v["user_id"] for v in visitors})
        friend_reviews = expect(alice, "GET", "/api/restaurants/1/reviews?friends_only=1&limit=50")["items"]
        assert friend_reviews and all(v["user_id"] in {2, 3, 10} for v in friend_reviews)
        assert 1 not in {v["user_id"] for v in friend_reviews}
        print("PASS: filters, aggregates, recent friend visits and friend-only reviews")

        expect(ben, "POST", "/api/friend-requests/4/accept", 403)
        expect(alice, "POST", "/api/friend-requests/4/accept")
        expect(alice, "POST", "/api/friend-requests/4/accept", 409)
        expect(alice, "POST", "/api/friend-requests/5/reject")
        expect(alice, "POST", "/api/friend-requests", 400, {"addressee_id": 1})
        expect(alice, "POST", "/api/friend-requests", 201, {"addressee_id": 7})
        expect(alice, "POST", "/api/friend-requests", 409, {"addressee_id": 7})
        expect(alice, "POST", "/api/friend-requests", 409, {"addressee_id": 2})
        print("PASS: friend requests, recipient permissions and duplicate-pair constraints")

        visits_before = count("visit")
        expect(alice, "POST", "/api/visits", 400,
               {"restaurant_id": 1, "rating": 6, "review_text": "Invalid rating."})
        assert count("visit") == visits_before
        try:
            with connection.transaction():
                visit_id = connection.execute("INSERT INTO visit (user_id,restaurant_id,visit_date,party_size) VALUES (1,1,current_date,2) RETURNING visit_id").fetchone()["visit_id"]
                connection.execute("INSERT INTO review (visit_id,rating,review_text) VALUES (%s,6,'Invalid rating')", (visit_id,))
            raise AssertionError("Invalid multi-step transaction unexpectedly succeeded.")
        except psycopg.errors.CheckViolation:
            pass
        assert count("visit") == visits_before
        print("PASS: multi-step visit/review transaction rolls back its first INSERT on failure")

        before_rating = expect(alice, "GET", "/api/restaurants/1")["restaurant"]["review_count"]
        created = expect(alice, "POST", "/api/visits", 201,
                         {"restaurant_id": 1, "party_size": 2, "rating": 5, "review_text": "A really enjoyable whole-restaurant experience."})
        visit_id, review_id = created["visit"]["visit_id"], created["review"]["review_id"]
        assert visit_id > 1020 and review_id > 1000
        assert expect(alice, "GET", "/api/restaurants/1")["restaurant"]["review_count"] == before_rating + 1
        expect(ben, "PATCH", f"/api/reviews/{review_id}", 403, {"rating": 3, "review_text": "Not mine."})
        expect(ben, "DELETE", f"/api/reviews/{review_id}", 403)
        expect(alice, "PATCH", f"/api/reviews/{review_id}", data={"rating": 3, "review_text": "Updated after reflecting on the service."})
        assert expect(alice, "GET", f"/api/reviews/{review_id}")["review"]["rating"] == 3
        root = expect(ben, "POST", f"/api/reviews/{review_id}/comments", 201, {"comment_text": "Was the service friendly?"})["comment"]
        expect(alice, "POST", f"/api/reviews/{review_id}/comments", 201,
               {"comment_text": "Yes, although it was slow.", "parent_comment_id": root["comment_id"]})
        expect(alice, "POST", "/api/reviews/2/comments", 400,
               {"comment_text": "Wrong review.", "parent_comment_id": root["comment_id"]})
        expect(alice, "DELETE", f"/api/reviews/{review_id}", 204)
        assert connection.execute("SELECT 1 FROM visit WHERE visit_id=%s", (visit_id,)).fetchone()
        assert not connection.execute("SELECT 1 FROM review_comment WHERE review_id=%s", (review_id,)).fetchone()
        assert expect(alice, "GET", "/api/restaurants/1")["restaurant"]["review_count"] == before_rating
        print("PASS: review edit/delete ownership, comment replies, cascade deletion and retained visits")

        expect(alice, "POST", "/api/favorites", data={"restaurant_id": 2})
        expect(alice, "POST", "/api/favorites", data={"restaurant_id": 2})
        assert connection.execute("SELECT count(*) AS n FROM favorite WHERE user_id=1 AND restaurant_id=2").fetchone()["n"] == 1
        expect(alice, "DELETE", "/api/favorites/2", 204)
        assert not connection.execute("SELECT 1 FROM favorite WHERE user_id=1 AND restaurant_id=2").fetchone()
        print("PASS: add/remove favorites and duplicate protection")

        def concurrent_registration(_):
            client = app.test_client()
            return client.post("/api/register", json={"user_name": "Concurrent User", "email": "concurrent@example.test", "password": "SecurePass123!"}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(concurrent_registration, range(2))) == [201, 409]

        def concurrent_review(_):
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"] = 1
            return client.post("/api/visits/1001/review", json={"rating": 4, "review_text": "A pleasant visit."}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(concurrent_review, range(2))) == [201, 409]
        print("PASS: concurrent registrations and two reviews for the same visit")

        for route in ["/api/plans", "/api/recommendations", "/api/feed", "/api/dashboard"]:
            expect(alice, "GET", route, 404)
        origin = alice.post("/api/favorites", json={"restaurant_id": 2}, headers={"Origin": "https://untrusted.example"})
        assert origin.status_code == 403
        print("PASS: removed endpoints and origin validation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help="Serve an isolated browser demo at http://127.0.0.1:5001; Ctrl+C removes its temporary database.")
    args = parser.parse_args()
    name = "tablemates_check_" + secrets.token_hex(8)
    assert name.startswith("tablemates_check_") and name.replace("_", "").isalnum()
    with connect() as control:
        control.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        options = conninfo_to_dict(control.info.dsn)
        options["dbname"] = name
        options["password"] = control.info.password
        def factory():
            return psycopg.connect(**options, autocommit=True, row_factory=dict_row)
        try:
            with factory() as connection:
                for path in sorted((ROOT / "sql" / "init").glob("*.sql")):
                    connection.execute(path.read_text(encoding="utf-8"))
                if args.serve:
                    import_data(connection, ROOT / "data")
                    with patch("app.db.connect", side_effect=factory):
                        create_app().run(host="127.0.0.1", port=5001, debug=False)
                else:
                    check(connection, factory)
                    print("All integration checks passed; the application database was not modified.")
        finally:
            control.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


if __name__ == "__main__":
    main()
