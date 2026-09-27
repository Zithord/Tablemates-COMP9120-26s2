-- Conceptual source: ../v1/9120 Gp.drawio (2).pdf
-- This script is run only when the Docker volume is first initialized.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_user (
    user_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_name     text NOT NULL CHECK (btrim(user_name) <> ''),
    user_email    text NOT NULL CHECK (btrim(user_email) <> ''),
    password_hash text NOT NULL CHECK (
        password_hash LIKE '$2a$%'
        OR password_hash LIKE '$2b$%'
        OR password_hash LIKE '$2y$%'
        OR password_hash LIKE '$argon2id$%'
    ),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX app_user_email_ci_uq ON app_user (lower(user_email));

CREATE TABLE suburb (
    suburb_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name      text NOT NULL CHECK (btrim(name) <> ''),
    state     text NOT NULL CHECK (state IN ('NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'ACT', 'NT')),
    postcode  char(4) NOT NULL CHECK (postcode ~ '^[0-9]{4}$')
);

CREATE UNIQUE INDEX suburb_location_ci_uq ON suburb (lower(name), state, postcode);

CREATE TABLE cuisine (
    cuisine_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cuisine_name text NOT NULL CHECK (btrim(cuisine_name) <> '')
);

CREATE UNIQUE INDEX cuisine_name_ci_uq ON cuisine (lower(cuisine_name));

CREATE TABLE restaurant (
    restaurant_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    restaurant_name text NOT NULL CHECK (btrim(restaurant_name) <> ''),
    street_address text NOT NULL CHECK (btrim(street_address) <> ''),
    suburb_id      bigint NOT NULL REFERENCES suburb(suburb_id) ON DELETE RESTRICT,
    price_level    smallint NOT NULL CHECK (price_level BETWEEN 1 AND 4),
    is_active      boolean NOT NULL DEFAULT true
);

CREATE INDEX restaurant_suburb_idx ON restaurant (suburb_id);

CREATE TABLE restaurant_cuisine (
    restaurant_id bigint NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE CASCADE,
    cuisine_id    bigint NOT NULL REFERENCES cuisine(cuisine_id) ON DELETE RESTRICT,
    PRIMARY KEY (restaurant_id, cuisine_id)
);

CREATE INDEX restaurant_cuisine_cuisine_idx ON restaurant_cuisine (cuisine_id);

-- Menu items are an implementation extension for the future frontend.
CREATE TABLE dish (
    dish_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    restaurant_id bigint NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE CASCADE,
    dish_name     text NOT NULL CHECK (btrim(dish_name) <> ''),
    description   text NOT NULL CHECK (btrim(description) <> ''),
    price_aud     numeric(7, 2) NOT NULL CHECK (price_aud > 0),
    is_available  boolean NOT NULL DEFAULT true
);

CREATE UNIQUE INDEX dish_restaurant_name_ci_uq
    ON dish (restaurant_id, lower(dish_name));

CREATE TABLE friendship (
    friendship_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    requester_id  bigint NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
    addressee_id  bigint NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
    status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'accepted', 'rejected')),
    requested_at  timestamptz NOT NULL DEFAULT now(),
    accepted_at   timestamptz,
    CONSTRAINT friendship_no_self CHECK (requester_id <> addressee_id),
    CONSTRAINT friendship_acceptance_time CHECK (
        (status = 'accepted' AND accepted_at IS NOT NULL AND accepted_at >= requested_at)
        OR (status <> 'accepted' AND accepted_at IS NULL)
    )
);

-- A->B and B->A are the same unordered friendship pair.
CREATE UNIQUE INDEX friendship_pair_uq ON friendship (
    LEAST(requester_id, addressee_id),
    GREATEST(requester_id, addressee_id)
);

CREATE INDEX friendship_addressee_idx ON friendship (addressee_id);

CREATE TABLE favorite (
    user_id       bigint NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    restaurant_id bigint NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE CASCADE,
    added_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, restaurant_id)
);

CREATE INDEX favorite_restaurant_idx ON favorite (restaurant_id);

CREATE TABLE dining_plan (
    plan_id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    creator_id           bigint NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
    title                text NOT NULL CHECK (btrim(title) <> ''),
    plan_date            timestamptz NOT NULL,
    voting_deadline      timestamptz NOT NULL,
    status               text NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft', 'open', 'finalized', 'cancelled')),
    chosen_restaurant_id bigint,
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT plan_deadline_before_visit CHECK (voting_deadline < plan_date),
    CONSTRAINT plan_final_choice CHECK (
        (status = 'finalized' AND chosen_restaurant_id IS NOT NULL)
        OR (status <> 'finalized' AND chosen_restaurant_id IS NULL)
    )
);

CREATE INDEX dining_plan_creator_idx ON dining_plan (creator_id);

CREATE TABLE plan_participant (
    plan_id      bigint NOT NULL REFERENCES dining_plan(plan_id) ON DELETE CASCADE,
    user_id      bigint NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
    rsvp_status  text NOT NULL DEFAULT 'invited'
                 CHECK (rsvp_status IN ('invited', 'accepted', 'declined')),
    invited_at   timestamptz NOT NULL DEFAULT now(),
    responded_at timestamptz,
    PRIMARY KEY (plan_id, user_id),
    CONSTRAINT participant_response_time CHECK (
        (rsvp_status = 'invited' AND responded_at IS NULL)
        OR (rsvp_status <> 'invited' AND responded_at IS NOT NULL AND responded_at >= invited_at)
    )
);

CREATE INDEX plan_participant_user_idx ON plan_participant (user_id);

CREATE TABLE plan_candidate (
    plan_id       bigint NOT NULL REFERENCES dining_plan(plan_id) ON DELETE CASCADE,
    restaurant_id bigint NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE RESTRICT,
    added_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (plan_id, restaurant_id)
);

CREATE INDEX plan_candidate_restaurant_idx ON plan_candidate (restaurant_id);

-- The final selection must be one of this plan's candidates.
ALTER TABLE dining_plan ADD CONSTRAINT plan_chosen_candidate_fk
    FOREIGN KEY (plan_id, chosen_restaurant_id)
    REFERENCES plan_candidate(plan_id, restaurant_id)
    DEFERRABLE INITIALLY IMMEDIATE;

CREATE TABLE plan_vote (
    plan_id       bigint NOT NULL,
    user_id       bigint NOT NULL,
    restaurant_id bigint NOT NULL,
    voted_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (plan_id, user_id),
    CONSTRAINT vote_participant_fk FOREIGN KEY (plan_id, user_id)
        REFERENCES plan_participant(plan_id, user_id) ON DELETE CASCADE,
    CONSTRAINT vote_candidate_fk FOREIGN KEY (plan_id, restaurant_id)
        REFERENCES plan_candidate(plan_id, restaurant_id) ON DELETE CASCADE
);

CREATE INDEX plan_vote_candidate_idx ON plan_vote (plan_id, restaurant_id);

CREATE TABLE visit (
    visit_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
    restaurant_id bigint NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE RESTRICT,
    plan_id       bigint REFERENCES dining_plan(plan_id) ON DELETE SET NULL,
    visit_date    date NOT NULL,
    party_size    integer NOT NULL CHECK (party_size > 0),
    visibility    text NOT NULL DEFAULT 'friends'
                  CHECK (visibility IN ('public', 'friends', 'private'))
);

CREATE INDEX visit_user_date_idx ON visit (user_id, visit_date DESC);
CREATE INDEX visit_restaurant_idx ON visit (restaurant_id);
CREATE INDEX visit_plan_idx ON visit (plan_id) WHERE plan_id IS NOT NULL;

CREATE TABLE review (
    review_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    visit_id    bigint NOT NULL UNIQUE REFERENCES visit(visit_id) ON DELETE RESTRICT,
    rating      smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE review_comment (
    comment_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    review_id         bigint NOT NULL REFERENCES review(review_id) ON DELETE CASCADE,
    author_id         bigint NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
    parent_comment_id bigint,
    comment_text      text NOT NULL CHECK (btrim(comment_text) <> ''),
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT comment_not_own_parent CHECK (parent_comment_id IS NULL OR parent_comment_id <> comment_id),
    CONSTRAINT comment_review_id_pair_uq UNIQUE (review_id, comment_id),
    CONSTRAINT comment_parent_same_review_fk
        FOREIGN KEY (review_id, parent_comment_id)
        REFERENCES review_comment(review_id, comment_id) ON DELETE NO ACTION
);

CREATE INDEX review_comment_review_idx ON review_comment (review_id, created_at);
CREATE INDEX review_comment_author_idx ON review_comment (author_id);

CREATE TABLE recommendation (
    recommendation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sender_id         bigint NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
    receiver_id       bigint NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
    restaurant_id     bigint NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE RESTRICT,
    message           text NOT NULL DEFAULT '',
    status            text NOT NULL DEFAULT 'unread'
                      CHECK (status IN ('unread', 'read', 'dismissed')),
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT recommendation_no_self CHECK (sender_id <> receiver_id)
);

CREATE INDEX recommendation_receiver_date_idx ON recommendation (receiver_id, created_at DESC);
CREATE INDEX recommendation_sender_idx ON recommendation (sender_id);
CREATE INDEX recommendation_restaurant_idx ON recommendation (restaurant_id);

COMMIT;
