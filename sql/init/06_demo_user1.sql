-- Persisted demo state for Alice (user_id=1).
-- Run after 05_generated_seed.sql on a fresh database.
-- The frontend can accept 8, reject 9, and send a new request to 7.
BEGIN;

INSERT INTO friendship
    (requester_id, addressee_id, status, requested_at, accepted_at)
VALUES
    (8, 1, 'pending', now() - interval '5 days', NULL),
    (9, 1, 'pending', now() - interval '5 days', NULL),
    (10, 1, 'accepted', now() - interval '5 days', now() - interval '4 days'),
    (1, 11, 'rejected', now() - interval '5 days', NULL),
    (1, 12, 'pending', now() - interval '5 days', NULL);

INSERT INTO recommendation
    (sender_id, receiver_id, restaurant_id, message, status)
VALUES
    (10, 1, 5, 'The dan dan noodles at Red Lantern Kitchen look great. Shall we go next weekend?', 'unread'),
    (1, 10, 6, 'I found Silk Road Dumplings and thought you might like it. Want to try it together?', 'unread');

COMMIT;
