-- Synthetic demonstration data only. The visible password literal below is
-- not a real secret; pgcrypto stores only salted bcrypt results in app_user.
BEGIN;

INSERT INTO app_user (user_name, user_email, password_hash) VALUES
  ('Alice Morgan', 'alice.morgan@example.test', crypt('DemoPass2026!', gen_salt('bf', 10))),
  ('Ben Carter',   'ben.carter@example.test',   crypt('DemoPass2026!', gen_salt('bf', 10))),
  ('Cara Nguyen',  'cara.nguyen@example.test',  crypt('DemoPass2026!', gen_salt('bf', 10))),
  ('Dina Patel',   'dina.patel@example.test',   crypt('DemoPass2026!', gen_salt('bf', 10))),
  ('Evan Brooks',  'evan.brooks@example.test',  crypt('DemoPass2026!', gen_salt('bf', 10))),
  ('Faye Liu',     'faye.liu@example.test',     crypt('DemoPass2026!', gen_salt('bf', 10)));

INSERT INTO suburb (name, state, postcode) VALUES
  ('Newtown', 'NSW', '2042'),
  ('Surry Hills', 'NSW', '2010'),
  ('Haymarket', 'NSW', '2000');

INSERT INTO cuisine (cuisine_name) VALUES
  ('Chinese'), ('Japanese'), ('Cafe'), ('Italian');

INSERT INTO restaurant (restaurant_name, street_address, suburb_id, price_level) VALUES
  ('Lantern Noodles', '12 King Street', 1, 2),
  ('Sakura Table', '28 Crown Street', 2, 3),
  ('Corner Coffee', '5 George Street', 3, 1),
  ('Pasta Garden', '40 King Street', 1, 2);

INSERT INTO restaurant_cuisine (restaurant_id, cuisine_id) VALUES
  (1, 1), (2, 2), (3, 3), (4, 4);

INSERT INTO dish (restaurant_id, dish_name, description, price_aud) VALUES
  (1, 'Dan dan noodles', 'Wheat noodles with chilli oil, sesame and minced pork.', 19.50),
  (1, 'Pork and chive dumplings', 'Hand-folded dumplings served with black vinegar.', 16.00),
  (1, 'Smashed cucumber salad', 'Cucumber tossed with garlic, vinegar and sesame.', 10.50),
  (1, 'Scallion pancakes', 'Crisp layered pancakes with ginger dipping sauce.', 12.00),
  (1, 'Mapo tofu', 'Silken tofu with fermented chilli and Sichuan pepper.', 21.00),
  (2, 'Miso ramen', 'Slow-simmered miso broth with noodles and soft egg.', 23.00),
  (2, 'Salmon donburi', 'Seared salmon over rice with pickles and sesame.', 25.00),
  (2, 'Chicken karaage', 'Crisp marinated chicken with lemon and kewpie mayo.', 17.00),
  (2, 'Tempura soba', 'Buckwheat noodles with seasonal vegetable tempura.', 22.00),
  (2, 'Matcha cheesecake', 'Light baked cheesecake with matcha cream.', 13.00),
  (3, 'Flat white', 'Double espresso with silky steamed milk.', 5.50),
  (3, 'Smashed avocado toast', 'Avocado, feta and herbs on toasted sourdough.', 18.00),
  (3, 'Ricotta hotcakes', 'Fluffy hotcakes with berries and maple syrup.', 20.00),
  (3, 'Iced latte', 'Espresso and chilled milk poured over ice.', 6.50),
  (3, 'Banana bread', 'House-baked banana loaf served warm with butter.', 8.00),
  (4, 'Pappardelle beef ragu', 'Slow-braised beef ragu with wide egg pasta.', 28.00),
  (4, 'Margherita pizza', 'Tomato, mozzarella and basil on a thin crust.', 23.00),
  (4, 'Burrata with tomatoes', 'Creamy burrata with heirloom tomatoes and basil.', 19.00),
  (4, 'Potato gnocchi', 'Pillowy gnocchi with browned butter and sage.', 26.00),
  (4, 'Tiramisu', 'Coffee-soaked sponge layered with mascarpone.', 14.00);

INSERT INTO friendship
    (requester_id, addressee_id, status, requested_at, accepted_at) VALUES
  (1, 2, 'accepted', now() - interval '30 days', now() - interval '29 days'),
  (1, 3, 'accepted', now() - interval '25 days', now() - interval '24 days'),
  (2, 3, 'accepted', now() - interval '20 days', now() - interval '19 days'),
  (1, 4, 'pending',  now() - interval '2 days', NULL),
  (5, 6, 'accepted', now() - interval '15 days', now() - interval '14 days');

INSERT INTO favorite (user_id, restaurant_id) VALUES
  (1, 1), (1, 2), (2, 1), (3, 3), (5, 4);

-- The insert trigger automatically adds each creator as an accepted participant.
INSERT INTO dining_plan
    (creator_id, title, plan_date, voting_deadline, status, created_at) VALUES
  (1, 'Friday noodles with the crew', now() + interval '14 days', now() + interval '7 days', 'open', now() - interval '4 days'),
  (2, 'Weekend coffee catch-up', now() + interval '20 days', now() + interval '10 days', 'open', now() - interval '3 days'),
  (1, 'Last week''s group dinner', now() - interval '2 days', now() - interval '3 days', 'draft', now() - interval '14 days');

INSERT INTO plan_participant
    (plan_id, user_id, rsvp_status, responded_at) VALUES
  (1, 2, 'accepted', now()),
  (1, 3, 'accepted', now()),
  (2, 1, 'accepted', now()),
  (2, 3, 'invited', NULL),
  (3, 2, 'accepted', now());

INSERT INTO plan_candidate (plan_id, restaurant_id) VALUES
  (1, 1), (1, 2), (2, 2), (2, 3), (3, 1), (3, 4);

INSERT INTO plan_vote (plan_id, user_id, restaurant_id) VALUES
  (1, 1, 1), (1, 2, 2), (1, 3, 1),
  (2, 2, 2), (2, 1, 3);

-- Historical plan: it is finalized before visits can refer to it.
UPDATE dining_plan
SET status = 'finalized', chosen_restaurant_id = 1
WHERE plan_id = 3;

UPDATE plan_participant
SET invited_at = now() - interval '13 days',
    responded_at = now() - interval '12 days'
WHERE plan_id = 3;

INSERT INTO visit
    (user_id, restaurant_id, plan_id, visit_date, party_size, visibility) VALUES
  (1, 1, 3, CURRENT_DATE - 2, 2, 'public'),
  (2, 1, 3, CURRENT_DATE - 2, 2, 'friends'),
  (3, 3, NULL, CURRENT_DATE - 5, 1, 'public'),
  (1, 2, NULL, CURRENT_DATE - 8, 2, 'private'),
  (2, 2, NULL, CURRENT_DATE - 1, 3, 'public');

INSERT INTO review (visit_id, rating, review_text, created_at) VALUES
  (1, 5, 'The dan dan noodles had a lovely chilli kick without drowning out the sesame. Ben and I shared a plate of dumplings too, and the staff made us feel at home.', CURRENT_DATE - 1 + interval '13 hours'),
  (2, 4, 'The pork and chive dumplings were juicy, with a crisp edge from the pan. We waited a little for our table, but dinner with Alice was worth it.', CURRENT_DATE - 1 + interval '14 hours'),
  (3, 4, 'Stopped in for a flat white and a quiet hour with my book. The coffee was smooth and the staff did not rush me, even when the cafe got busy.', CURRENT_DATE - 4 + interval '10 hours'),
  (4, 3, 'The miso ramen broth was comforting, but the noodles were softer than I like. Service was kind, so I would come back and try the karaage.', CURRENT_DATE - 7 + interval '19 hours'),
  (5, 5, 'The chicken karaage was crisp outside and tender inside. We shared it before our mains, and everyone at the table wanted another plate.', CURRENT_DATE + interval '11 hours');

INSERT INTO review_comment
    (review_id, author_id, parent_comment_id, comment_text) VALUES
  (1, 2, NULL, 'Those noodles sound great. Was the chilli level manageable?'),
  (1, 1, 1,    'Definitely. It was warm rather than overwhelming.'),
  (2, 3, NULL, 'Adding those dumplings to my list for next time!');

INSERT INTO recommendation
    (sender_id, receiver_id, restaurant_id, message, status) VALUES
  (1, 2, 1, 'You have to try the dan dan noodles here next time.', 'unread'),
  (2, 3, 2, 'The karaage would be perfect for our next dinner.', 'read');

COMMIT;
