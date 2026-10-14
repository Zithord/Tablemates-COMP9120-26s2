-- Ten-table implementation of the friends' restaurant review prototype.
-- Docker runs this only for a new data volume. CSV data is imported separately.

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

CREATE TABLE visit (
    visit_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
    restaurant_id bigint NOT NULL REFERENCES restaurant(restaurant_id) ON DELETE RESTRICT,
    visit_date    date NOT NULL,
    party_size    integer NOT NULL CHECK (party_size BETWEEN 1 AND 30)
);

CREATE INDEX visit_user_date_idx ON visit (user_id, visit_date DESC);
CREATE INDEX visit_restaurant_idx ON visit (restaurant_id);

CREATE TABLE review (
    review_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    visit_id    bigint NOT NULL UNIQUE REFERENCES visit(visit_id) ON DELETE RESTRICT,
    rating      smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text text NOT NULL CHECK (btrim(review_text) <> ''),
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

COMMIT;
