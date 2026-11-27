-- =====================================================================
-- Tablemates - representative SQL (COMP9120 Group Project, Report Section 4)
--
-- Run against the seeded demo database:
--     psql -h 127.0.0.1 -p 5433 -U friend_app -d friend_review -f sql/demo_queries.sql
--
-- Safe to run repeatedly: every data modification runs inside a
-- transaction that ends with ROLLBACK, and every intentional constraint
-- violation is caught and reported as a NOTICE. The database is unchanged
-- after the script finishes.
--
-- Section numbers refer to the report; O1-O8 are the representative
-- operations in Section 1.5, Q1-Q5 the queries in Section 4.2.
-- Alice is user_id = 1 throughout.
-- =====================================================================

\set ON_ERROR_STOP on
\pset footer on
\echo

-- ---------------------------------------------------------------------
-- PART A. Queries (SELECT)
-- ---------------------------------------------------------------------

\echo '=== Q1 (O1) Filter restaurants: suburb, price, cuisine (correlated EXISTS) ==='
SELECT r.restaurant_id, r.restaurant_name, s.name AS suburb,
       rs.avg_rating, rs.review_count
FROM restaurant r
JOIN suburb s USING (suburb_id)
JOIN restaurant_rating_summary rs USING (restaurant_id)
WHERE r.is_active AND s.name = 'Newtown' AND r.price_level <= 2
  AND EXISTS (SELECT 1 FROM restaurant_cuisine rc
              JOIN cuisine c USING (cuisine_id)
              WHERE rc.restaurant_id = r.restaurant_id
                AND lower(c.cuisine_name) = lower('Italian'))
ORDER BY rs.avg_rating DESC NULLS LAST, r.restaurant_id;

\echo '=== Q1b (O1) Same filter without cuisine; unrated restaurants stay visible (NULLS LAST) ==='
SELECT r.restaurant_id, r.restaurant_name, s.name AS suburb,
       rs.avg_rating, rs.review_count
FROM restaurant r
JOIN suburb s USING (suburb_id)
JOIN restaurant_rating_summary rs USING (restaurant_id)
WHERE r.is_active AND s.name = 'Newtown' AND r.price_level <= 2
ORDER BY rs.avg_rating DESC NULLS LAST, r.restaurant_id;

\echo '=== Q1c (O1) Minimum-rating filter using HAVING over the base tables ==='
SELECT r.restaurant_name, ROUND(AVG(rv.rating), 2) AS avg_rating,
       COUNT(*) AS review_count
FROM restaurant r
JOIN visit v USING (restaurant_id)
JOIN review rv USING (visit_id)
WHERE r.is_active
GROUP BY r.restaurant_id, r.restaurant_name
HAVING AVG(rv.rating) >= 4.2 AND COUNT(*) >= 10
ORDER BY avg_rating DESC, review_count DESC;

\echo '=== Q2 (O2) Restaurants Alice''s friends visited in the last 90 days (CTE + aggregation) ==='
WITH recent AS (                     -- one row per friend per restaurant
  SELECT v.restaurant_id, v.user_id, MAX(v.visit_date) AS last_visit
  FROM visit v
  JOIN accepted_friend af ON af.friend_id = v.user_id
  WHERE af.user_id = 1
    AND v.visit_date BETWEEN current_date - 90 AND current_date
  GROUP BY v.restaurant_id, v.user_id
)
SELECT r.restaurant_name,
       COUNT(*)                                   AS friend_count,
       MAX(last_visit)                            AS most_recent,
       string_agg(u.user_name, ', ' ORDER BY last_visit DESC) AS friends
FROM recent
JOIN restaurant r USING (restaurant_id)
JOIN app_user  u ON u.user_id = recent.user_id
GROUP BY r.restaurant_id, r.restaurant_name
ORDER BY most_recent DESC, friend_count DESC;

\echo '=== Q3 (O3) Reviews of restaurant 1 written by Alice''s friends (EXISTS) ==='
SELECT u.user_name, v.visit_date, rv.rating, LEFT(rv.review_text, 60) AS review_excerpt
FROM review rv
JOIN visit v USING (visit_id)
JOIN app_user u ON u.user_id = v.user_id
WHERE v.restaurant_id = 1
  AND EXISTS (SELECT 1 FROM accepted_friend af
              WHERE af.user_id = 1 AND af.friend_id = v.user_id)
ORDER BY rv.created_at DESC;

\echo '=== Q3b (O4) Alice''s friendships with direction (CASE + self-join on app_user) ==='
SELECT f.friendship_id,
       CASE WHEN f.requester_id = 1 THEN 'sent' ELSE 'received' END AS direction,
       u.user_name AS other_user, f.status, f.requested_at::date
FROM friendship f
JOIN app_user u
  ON u.user_id = CASE WHEN f.requester_id = 1 THEN f.addressee_id ELSE f.requester_id END
WHERE 1 IN (f.requester_id, f.addressee_id)
ORDER BY f.status, f.requested_at DESC;

\echo '=== Q3c Visits Alice has not reviewed yet (anti-join with NOT EXISTS) ==='
SELECT v.visit_id, r.restaurant_name, v.visit_date
FROM visit v
JOIN restaurant r USING (restaurant_id)
WHERE v.user_id = 1
  AND NOT EXISTS (SELECT 1 FROM review rv WHERE rv.visit_id = v.visit_id)
ORDER BY v.visit_date DESC;

\echo '=== Q3d Most-discussed reviews (comment threads, LEFT JOIN + GROUP BY) ==='
SELECT rv.review_id, r.restaurant_name, u.user_name AS reviewer,
       COUNT(c.comment_id)                                   AS comments,
       COUNT(c.comment_id) FILTER (WHERE c.parent_comment_id IS NOT NULL) AS replies
FROM review rv
JOIN visit v USING (visit_id)
JOIN restaurant r USING (restaurant_id)
JOIN app_user u ON u.user_id = v.user_id
LEFT JOIN review_comment c ON c.review_id = rv.review_id
GROUP BY rv.review_id, r.restaurant_name, u.user_name
ORDER BY comments DESC, rv.review_id
LIMIT 5;

\echo '=== Q3e Rating distribution per cuisine (M:N join + aggregation) ==='
SELECT c.cuisine_name,
       COUNT(DISTINCT rc.restaurant_id) AS restaurants,
       COUNT(rv.review_id)              AS reviews,
       ROUND(AVG(rv.rating), 2)         AS avg_rating
FROM cuisine c
LEFT JOIN restaurant_cuisine rc USING (cuisine_id)
LEFT JOIN visit v ON v.restaurant_id = rc.restaurant_id
LEFT JOIN review rv USING (visit_id)
GROUP BY c.cuisine_id, c.cuisine_name
ORDER BY avg_rating DESC NULLS LAST;

-- ---------------------------------------------------------------------
-- PART B. Data modification (rolled back at the end)
-- ---------------------------------------------------------------------

\echo '=== Q4 (O4) Alice accepts Henry''s pending request (conditional UPDATE) ==='
BEGIN;
UPDATE friendship
SET status = 'accepted', accepted_at = now()
WHERE friendship_id = 4 AND addressee_id = 1 AND status = 'pending'
RETURNING friendship_id, status, accepted_at;

\echo '--- Repeating the same UPDATE affects 0 rows: the request is no longer pending'
UPDATE friendship
SET status = 'accepted', accepted_at = now()
WHERE friendship_id = 4 AND addressee_id = 1 AND status = 'pending'
RETURNING friendship_id;

\echo '--- Henry now appears in the accepted_friend view for Alice'
SELECT af.friend_id, u.user_name
FROM accepted_friend af JOIN app_user u ON u.user_id = af.friend_id
WHERE af.user_id = 1 ORDER BY af.friend_id;

\echo '=== (O4) Alice rejects Ivy''s request; sends a new request to Grace (INSERT) ==='
UPDATE friendship SET status = 'rejected'
WHERE friendship_id = 5 AND addressee_id = 1 AND status = 'pending'
RETURNING friendship_id, status;

INSERT INTO friendship (requester_id, addressee_id) VALUES (1, 7)
RETURNING friendship_id, requester_id, addressee_id, status;

\echo '=== (O8) Save and remove a favourite (composite primary key) ==='
INSERT INTO favorite (user_id, restaurant_id) VALUES (1, 2)
RETURNING user_id, restaurant_id, added_at;
DELETE FROM favorite WHERE user_id = 1 AND restaurant_id = 2
RETURNING user_id, restaurant_id;

\echo '=== (O6) Edit Alice''s own review (UPDATE ... FROM with ownership predicate) ==='
UPDATE review rv
SET rating = 5, review_text = 'Updated after a second visit: even better.'
FROM visit v
WHERE rv.visit_id = v.visit_id AND rv.review_id = 1 AND v.user_id = 1
RETURNING rv.review_id, rv.rating, rv.review_text;

\echo '--- The same UPDATE issued as Ben (user 2) affects 0 rows: not his review'
UPDATE review rv SET rating = 1
FROM visit v
WHERE rv.visit_id = v.visit_id AND rv.review_id = 1 AND v.user_id = 2
RETURNING rv.review_id;

\echo '=== (O7) Reply to the first comment on review 1 (self-referencing FK) ==='
INSERT INTO review_comment (review_id, author_id, parent_comment_id, comment_text)
SELECT 1, 2, MIN(comment_id), 'Agreed - the dumplings were the highlight.'
FROM review_comment WHERE review_id = 1 AND parent_comment_id IS NULL
RETURNING comment_id, review_id, parent_comment_id, comment_text;

\echo '=== Q5 (O6) Delete Alice''s review 1: its comments and replies cascade, the visit is kept ==='
SELECT (SELECT COUNT(*) FROM review_comment WHERE review_id = 1) AS comments_before,
       (SELECT visit_id FROM review WHERE review_id = 1)         AS visit_id;

DELETE FROM review rv USING visit v
WHERE rv.visit_id = v.visit_id AND rv.review_id = 1 AND v.user_id = 1
RETURNING rv.review_id;

SELECT (SELECT COUNT(*) FROM review_comment WHERE review_id = 1) AS comments_after,
       (SELECT COUNT(*) FROM visit WHERE visit_id = 1)          AS visit_still_exists;

\echo '--- The derived rating updates automatically (view, nothing stored)'
SELECT restaurant_id, restaurant_name, review_count, avg_rating
FROM restaurant_rating_summary
WHERE restaurant_id = (SELECT restaurant_id FROM visit WHERE visit_id = 1);

ROLLBACK;
\echo '--- PART B rolled back: all demo modifications undone'

-- ---------------------------------------------------------------------
-- PART C. Integrity constraints - each invalid operation is rejected
-- (Report Section 4.3, Table 6). Each attempt runs in its own block and
-- the error is caught, so the script continues and nothing is written.
-- ---------------------------------------------------------------------

\echo '=== PART C: invalid operations rejected by PostgreSQL ==='
DO $$
DECLARE
  attempt record;
  msg     text;
  cname   text;
BEGIN
  FOR attempt IN
    SELECT * FROM (VALUES
      (1, 'Reverse duplicate friendship (Ben -> Alice, already friends)',
          $q$INSERT INTO friendship (requester_id, addressee_id) VALUES (2, 1)$q$),
      (2, 'Self friendship (user 5 -> user 5)',
          $q$INSERT INTO friendship (requester_id, addressee_id) VALUES (5, 5)$q$),
      (3, 'Review with rating 6',
          $q$INSERT INTO review (visit_id, rating, review_text) VALUES (1001, 6, 'Too good')$q$),
      (4, 'Second review for visit 1',
          $q$INSERT INTO review (visit_id, rating, review_text) VALUES (1, 4, 'Duplicate')$q$),
      (5, 'Blank review text',
          $q$INSERT INTO review (visit_id, rating, review_text) VALUES (1001, 4, '   ')$q$),
      (6, 'Case-variant duplicate email',
          $q$INSERT INTO app_user (user_name, user_email, password_hash)
             VALUES ('Copy', 'ALICE.MORGAN@example.test', '$2b$10$xxxxxxxxxxxxxxxxxxxxxx')$q$),
      (7, 'Reply whose parent comment belongs to a different review',
          $q$INSERT INTO review_comment (review_id, author_id, parent_comment_id, comment_text)
             SELECT 3, 1, MIN(comment_id), 'Wrong thread'
             FROM review_comment WHERE review_id = 1$q$),
      (8, 'Delete a visit that already has a review',
          $q$DELETE FROM visit WHERE visit_id = 1$q$),
      (9, 'Accept a friendship without setting accepted_at',
          $q$UPDATE friendship SET status = 'accepted' WHERE friendship_id = 4$q$),
      (10, 'Unknown friendship status',
          $q$UPDATE friendship SET status = 'blocked' WHERE friendship_id = 5$q$),
      (11, 'Price level outside 1-4',
          $q$UPDATE restaurant SET price_level = 5 WHERE restaurant_id = 1$q$),
      (12, 'Party size of 0',
          $q$INSERT INTO visit (user_id, restaurant_id, visit_date, party_size)
             VALUES (1, 1, current_date, 0)$q$),
      (13, 'Visit for a user that does not exist',
          $q$INSERT INTO visit (user_id, restaurant_id, visit_date, party_size)
             VALUES (99999, 1, current_date, 2)$q$),
      (14, 'Duplicate favourite',
          $q$INSERT INTO favorite (user_id, restaurant_id) VALUES (1, 1)$q$),
      (15, 'Invalid postcode format',
          $q$INSERT INTO suburb (name, state, postcode) VALUES ('Nowhere', 'NSW', '20A0')$q$)
    ) AS t(no, label, stmt)
    ORDER BY no
  LOOP
    BEGIN
      EXECUTE attempt.stmt;
      RAISE NOTICE '% %  ->  UNEXPECTEDLY ACCEPTED', lpad(attempt.no::text, 2), attempt.label;
      RAISE EXCEPTION 'undo';           -- never keep an unexpected write
    EXCEPTION
      WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS msg = MESSAGE_TEXT, cname = CONSTRAINT_NAME;
        IF msg <> 'undo' THEN
          RAISE NOTICE '% %  ->  rejected by %',
            lpad(attempt.no::text, 2), attempt.label, COALESCE(NULLIF(cname, ''), msg);
        END IF;
    END;
  END LOOP;
END
$$;

-- ---------------------------------------------------------------------
-- PART D. Multi-step transactions (Report Section 4.4)
-- ---------------------------------------------------------------------

\echo '=== T1 (O5) Visit + review as one transaction - success path ==='
SELECT COUNT(*) AS visits_before FROM visit;
BEGIN;
INSERT INTO visit (user_id, restaurant_id, visit_date, party_size)
VALUES (1, 1, current_date, 2)
RETURNING visit_id;
INSERT INTO review (visit_id, rating, review_text)
VALUES (currval(pg_get_serial_sequence('visit', 'visit_id')), 5,
        'Welcoming staff and excellent dumplings.')
RETURNING review_id, visit_id, rating;
\echo '--- Inside the transaction both rows are visible'
SELECT COUNT(*) AS visits_inside_txn FROM visit;
ROLLBACK;   -- COMMIT would persist both rows; ROLLBACK keeps the demo repeatable
SELECT COUNT(*) AS visits_after_rollback FROM visit;

\echo '=== T1 (O5) Failure path: second INSERT violates CHECK, first INSERT is undone ==='
\set ON_ERROR_STOP off
BEGIN;
INSERT INTO visit (user_id, restaurant_id, visit_date, party_size)
VALUES (1, 1, current_date, 2)
RETURNING visit_id;
INSERT INTO review (visit_id, rating, review_text)
VALUES (currval(pg_get_serial_sequence('visit', 'visit_id')), 6, 'Rating out of range');
COMMIT;     -- the transaction is already aborted, so PostgreSQL performs ROLLBACK
\set ON_ERROR_STOP on
SELECT COUNT(*) AS visits_after_failed_txn FROM visit;   -- unchanged

\echo '=== T2 (O6) Review an existing visit with a row lock (FOR UPDATE) ==='
BEGIN;
SELECT visit_id, user_id FROM visit WHERE visit_id = 1001 FOR UPDATE;  -- lock + ownership check
INSERT INTO review (visit_id, rating, review_text)
VALUES (1001, 4, 'Good coffee, slow service at lunch.')
RETURNING review_id, visit_id;
-- A concurrent session running the same block would wait on the FOR UPDATE
-- above, then fail on UNIQUE(review.visit_id) once this transaction commits.
ROLLBACK;

\echo
\echo 'Done. All modifications were rolled back; the demo database is unchanged.'
