-- Representative SQL for the simplified assignment prototype.
-- Run SELECT examples against the seeded v2 database.
-- The final transaction deliberately uses ROLLBACK and leaves no records behind.

-- 1. Filter restaurants, including unrated restaurants when no minimum is specified.
SELECT r.restaurant_id, r.restaurant_name, s.name AS suburb,
       rs.avg_rating, rs.review_count
FROM restaurant r
JOIN suburb s USING (suburb_id)
JOIN restaurant_rating_summary rs USING (restaurant_id)
WHERE s.name = 'Newtown' AND r.price_level <= 2
ORDER BY rs.avg_rating DESC NULLS LAST, r.restaurant_id;

-- 2. Only Alice's accepted friends' restaurant reviews.
SELECT u.user_name, r.restaurant_name, v.visit_date, rv.rating, rv.review_text
FROM accepted_friend af
JOIN visit v ON v.user_id = af.friend_id
JOIN review rv USING (visit_id)
JOIN app_user u ON u.user_id = v.user_id
JOIN restaurant r USING (restaurant_id)
WHERE af.user_id = 1
ORDER BY v.visit_date DESC, rv.review_id DESC;

-- 3. How many distinct friends recently visited each restaurant?
SELECT r.restaurant_name, COUNT(DISTINCT v.user_id) AS friend_count
FROM accepted_friend af
JOIN visit v ON v.user_id = af.friend_id
JOIN restaurant r USING (restaurant_id)
WHERE af.user_id = 1 AND v.visit_date BETWEEN current_date - 90 AND current_date
GROUP BY r.restaurant_id, r.restaurant_name
ORDER BY friend_count DESC, r.restaurant_id;

-- 4. A multi-step visit + review transaction. The identity links both inserts.
-- COMMIT would persist both records. ROLLBACK here makes this example safe to repeat.
BEGIN;
INSERT INTO visit (user_id, restaurant_id, visit_date, party_size)
VALUES (1, 1, current_date, 2);
INSERT INTO review (visit_id, rating, review_text)
VALUES (currval(pg_get_serial_sequence('visit', 'visit_id')), 5,
        'A welcoming restaurant with a satisfying meal and attentive service.');
ROLLBACK;

-- Failure example: in a separate transaction, use rating 6 in the second INSERT.
-- The CHECK fails; ROLLBACK removes the first INSERT too.
-- scripts/check_project.py verifies this against an isolated temporary database.
