-- Views are created after 01_schema.sql on a new Docker data volume.
BEGIN;

-- A user appears once for each accepted friend, regardless of request direction.
CREATE VIEW accepted_friend AS
SELECT requester_id AS user_id, addressee_id AS friend_id
FROM friendship WHERE status = 'accepted'
UNION ALL
SELECT addressee_id AS user_id, requester_id AS friend_id
FROM friendship WHERE status = 'accepted';

-- All reviews are visible; ratings are derived rather than stored in restaurant.
CREATE VIEW restaurant_rating_summary AS
SELECT r.restaurant_id,
       r.restaurant_name,
       COUNT(rv.review_id) AS review_count,
       ROUND(AVG(rv.rating)::numeric, 2) AS avg_rating
FROM restaurant r
LEFT JOIN visit v ON v.restaurant_id = r.restaurant_id
LEFT JOIN review rv ON rv.visit_id = v.visit_id
GROUP BY r.restaurant_id, r.restaurant_name;

COMMIT;
