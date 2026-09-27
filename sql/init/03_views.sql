BEGIN;

-- A user appears once for each accepted friend, regardless of request direction.
CREATE VIEW accepted_friend AS
SELECT requester_id AS user_id, addressee_id AS friend_id
FROM friendship WHERE status = 'accepted'
UNION ALL
SELECT addressee_id AS user_id, requester_id AS friend_id
FROM friendship WHERE status = 'accepted';

-- Derived ER attributes. Only public reviews contribute to the public summary.
CREATE VIEW restaurant_rating_summary AS
SELECT r.restaurant_id,
       r.restaurant_name,
       COUNT(rv.review_id) AS review_count,
       ROUND(AVG(rv.rating)::numeric, 2) AS avg_rating
FROM restaurant r
LEFT JOIN visit v
  ON v.restaurant_id = r.restaurant_id AND v.visibility = 'public'
LEFT JOIN review rv ON rv.visit_id = v.visit_id
GROUP BY r.restaurant_id, r.restaurant_name;

CREATE VIEW plan_vote_tally AS
SELECT pc.plan_id,
       pc.restaurant_id,
       r.restaurant_name,
       COUNT(pv.user_id) AS vote_count
FROM plan_candidate pc
JOIN restaurant r ON r.restaurant_id = pc.restaurant_id
LEFT JOIN plan_vote pv
  ON pv.plan_id = pc.plan_id AND pv.restaurant_id = pc.restaurant_id
GROUP BY pc.plan_id, pc.restaurant_id, r.restaurant_name;

COMMIT;
