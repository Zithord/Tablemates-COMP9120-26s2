"""Generate a repeatable, fictional English-language restaurant social dataset.

Run before starting a new Docker data volume. The output extends 04_seed.sql
to about 100 people, 50 restaurants, 250 menu dishes and 1000 shop reviews.
No third-party Python packages are required.
"""

from __future__ import annotations

import itertools
import random
from pathlib import Path

from catalog import (
    BASE_MENU,
    FIRST_NAMES,
    LAST_NAMES,
    MENUS,
    NEW_CUISINES,
    NEW_RESTAURANTS,
    NEW_SUBURBS,
    STREET_BY_SUBURB,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "sql" / "init" / "05_generated_seed.sql"
RNG = random.Random(9120)
DEMO_PASSWORD = "DemoPass2026!"  # Never use this shared password for real accounts.


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def insert_values(
    output: list[str], table: str, columns: str, values: list[str], batch_size: int = 200
) -> None:
    for start in range(0, len(values), batch_size):
        output.append(f"INSERT INTO {table} ({columns}) VALUES\n  ")
        output.append(",\n  ".join(values[start : start + batch_size]))
        output.append(";\n\n")


REVIEW_DETAILS = {
    "main": {
        5: (
            "It was full of flavour and tasted freshly made.",
            "The flavours were beautifully balanced, and everything arrived at the right temperature.",
            "It had a lovely texture and tasted as though real care had gone into it.",
            "The portion was generous, and every bite was satisfying.",
        ),
        4: (
            "It was tasty and well presented, with just a small seasoning tweak needed.",
            "The flavours worked well, though I would have liked a touch more sauce.",
            "It was a satisfying choice, even if one part of the plate felt a little rushed.",
            "The texture was good, and the portion felt fair for the price.",
        ),
        3: (
            "It was pleasant enough, but the flavours did not quite come together.",
            "The portion was fine, although it needed a little more seasoning.",
            "Some bites were good, while others felt rather ordinary.",
            "It filled the gap, but I had hoped for a more memorable meal.",
        ),
        2: (
            "It arrived lukewarm and lacked the flavour I expected.",
            "The texture was uneven, and the seasoning did not rescue it.",
            "It felt rushed and was not as fresh as it should have been.",
            "The portion was small for the price, and the flavours were flat.",
        ),
        1: (
            "It was poorly prepared, and I could not finish it.",
            "It arrived cold after a long wait and tasted stale.",
            "The texture was off, and the meal did not feel worth the price.",
            "It missed the mark on both freshness and flavour.",
        ),
    },
    "drink": {
        5: (
            "It was smooth, balanced and exactly what I wanted.",
            "It tasted fresh and was made with obvious care.",
            "The flavour was clear without being too sweet or bitter.",
        ),
        4: (
            "It was enjoyable, though I would have preferred a slightly stronger flavour.",
            "It was nicely made, if a little sweeter than I expected.",
            "The balance was good, and it arrived quickly.",
        ),
        3: (
            "It was fine, but nothing about it stood out.",
            "The flavour was a little muted, even though it looked inviting.",
            "It was drinkable, but I have had better versions nearby.",
        ),
        2: (
            "It tasted watery and did not feel worth the price.",
            "The balance was off, with too much sweetness and not enough flavour.",
            "It arrived later than expected and tasted rather flat.",
        ),
        1: (
            "It tasted stale, and I left most of it untouched.",
            "It was unpleasantly bitter and poorly prepared.",
            "It arrived at the wrong temperature and tasted off.",
        ),
    },
    "dessert": {
        5: (
            "It was light, fresh and not too sweet.",
            "The texture was lovely, and the sweetness was just right.",
            "It was a delightful finish to the visit.",
        ),
        4: (
            "It was enjoyable, although a little more contrast would have helped.",
            "The flavours were good, if slightly sweeter than I prefer.",
            "It was a nice way to finish, even if the portion was modest.",
        ),
        3: (
            "It was pleasant, but a little too sweet for my taste.",
            "The texture was fine, though it did not feel especially fresh.",
            "It was acceptable, but not something I would order again.",
        ),
        2: (
            "It tasted overly sweet and lacked freshness.",
            "The texture felt heavy, and the flavours were flat.",
            "It looked better than it tasted and felt overpriced.",
        ),
        1: (
            "It tasted stale, and we left most of it behind.",
            "The texture was unpleasant, and it did not taste fresh.",
            "It was a disappointing end to an already frustrating visit.",
        ),
    },
}

REVIEW_ENDINGS = {
    5: (
        "The staff were warm and attentive, and I would happily return.",
        "The whole place had an easy, welcoming feel; I am already planning another visit.",
        "Service was thoughtful, and this is an easy place to recommend to friends.",
        "The atmosphere and service matched the food, making it a genuinely lovely visit.",
    ),
    4: (
        "Service was friendly, and I would come back to explore more of the menu.",
        "The room was comfortable, and the overall visit was worth repeating.",
        "There was a short wait, but the team handled it well.",
        "It was a good experience overall, with only a few small things to improve.",
    ),
    3: (
        "The staff were pleasant, but the overall experience felt a little uneven.",
        "The space was comfortable, although I am not in a hurry to return.",
        "Nothing went seriously wrong, but I left feeling underwhelmed.",
        "Service was fine; I may give the place another try on a quieter day.",
    ),
    2: (
        "The staff were polite, but the long wait made the visit disappointing.",
        "The room was busy, and the service never quite caught up.",
        "I hope the kitchen has a better day next time, because this visit was not great.",
        "For the price, I expected a much smoother experience.",
    ),
    1: (
        "The service did not recover the meal, so I would not rush back.",
        "We raised the issue politely, but it was not resolved during our visit.",
        "The whole experience was frustrating, and I cannot recommend it.",
        "I left disappointed and would choose somewhere else next time.",
    ),
}


def in_sentence(dish_name: str) -> str:
    """Lowercase ordinary dish names without changing national adjectives."""
    if dish_name.startswith(("Vietnamese ", "Korean ", "Thai ")):
        return dish_name
    return dish_name[0].lower() + dish_name[1:]


def review_copy(dish_name: str, kind: str, rating: int, party_size: int) -> str:
    dish_name = in_sentence(dish_name)
    if party_size == 1:
        opener = RNG.choice((
            "Stopped in after work", "Dropped by for a quiet lunch",
            "Visited on a slow afternoon", "Came in for a quick bite",
            "Tried this place for the first time", "Went in on a rainy evening",
        ))
        first = f"{opener} and ordered the {dish_name}."
    else:
        opener = RNG.choice((
            "We met here for dinner", "Came with friends for a relaxed meal",
            "We stopped in after a busy day", "Visited with family on the weekend",
            "We picked this place for lunch", "Went here with a couple of friends",
        ))
        first = f"{opener}, and I ordered the {dish_name}."
    return " ".join((
        first,
        RNG.choice(REVIEW_DETAILS[kind][rating]),
        RNG.choice(REVIEW_ENDINGS[rating]),
    ))


def comment_copy(dish_name: str, rating: int) -> str:
    dish_name = in_sentence(dish_name)
    if rating >= 4:
        return RNG.choice((
            f"That {dish_name} sounds lovely. Was it busy when you went?",
            f"I have been meaning to try the {dish_name}. Thanks for the tip!",
            f"Great to hear. Would you order the {dish_name} again?",
            "This sounds like a good spot for our next catch-up.",
            "I walked past last week and wondered if it was worth a visit.",
        ))
    return RNG.choice((
        "Sorry it did not live up to expectations. Did the team offer to fix it?",
        f"That is a shame about the {dish_name}; I had been curious to try it.",
        "Thanks for the honest review. I might try somewhere else this week.",
        "Hopefully it was just an off day for the kitchen.",
        "A long wait can really change the whole experience.",
    ))


def main() -> None:
    assert len(NEW_RESTAURANTS) == 46
    lines = [
        "-- Generated by scripts/generate_data.py from curated English-language copy.\n",
        "-- Run only after 04_seed.sql on a fresh database.\n",
        "BEGIN;\n\n",
        "DO $$ BEGIN\n",
        "  IF (SELECT COUNT(*) FROM app_user) <> 6\n",
        "     OR (SELECT COUNT(*) FROM restaurant) <> 4\n",
        "     OR (SELECT COUNT(*) FROM dish) <> 20\n",
        "     OR (SELECT COUNT(*) FROM review) <> 5 THEN\n",
        "    RAISE EXCEPTION 'Generated seed requires the untouched base seed';\n",
        "  END IF;\n",
        "END $$;\n\n",
    ]

    # People have plausible names; .test email addresses cannot receive mail.
    names = list(itertools.product(FIRST_NAMES, LAST_NAMES))
    RNG.shuffle(names)
    selected_names = names[:94]
    users = []
    for first, last in selected_names:
        email = f"{first}.{last}".replace("'", "").lower() + "@example.test"
        users.append(
            f"({quote(first + ' ' + last)}, {quote(email)}, "
            f"crypt({quote(DEMO_PASSWORD)}, gen_salt('bf', 10)))"
        )
    insert_values(lines, "app_user", "user_name, user_email, password_hash", users)

    insert_values(
        lines, "suburb", "name, state, postcode",
        [f"({quote(name)}, {quote(state)}, {quote(code)})"
         for name, state, code, _ in NEW_SUBURBS],
    )
    insert_values(
        lines, "cuisine", "cuisine_name",
        [f"({quote(name)})" for name in NEW_CUISINES],
    )

    restaurant_names = {
        1: "Lantern Noodles", 2: "Sakura Table",
        3: "Corner Coffee", 4: "Pasta Garden",
    }
    restaurant_cuisines = {1: 1, 2: 2, 3: 3, 4: 4}
    restaurant_menus = dict(BASE_MENU)
    restaurants = []
    cuisine_rows = []
    dish_rows = []
    for restaurant_id, (name, cuisine_id, suburb_id, price_level) in enumerate(
        NEW_RESTAURANTS, start=5
    ):
        restaurant_names[restaurant_id] = name
        restaurant_cuisines[restaurant_id] = cuisine_id
        address = f"{12 + restaurant_id * 3} {STREET_BY_SUBURB[suburb_id]}"
        restaurants.append(
            f"({quote(name)}, {quote(address)}, {suburb_id}, {price_level})"
        )
        cuisine_rows.append(f"({restaurant_id}, {cuisine_id})")
        # Each venue has its own five-item selection from the cuisine catalogue.
        menu = random.Random(9120 + restaurant_id).sample(MENUS[cuisine_id], 5)
        restaurant_menus[restaurant_id] = tuple((item[0], item[3]) for item in menu)
        for item_index, (dish_name, description, base_price, _) in enumerate(menu):
            price = round(base_price * (0.90 + 0.08 * (price_level - 1)) * 2) / 2
            available = "false" if restaurant_id % 13 == 0 and item_index == 4 else "true"
            dish_rows.append(
                f"({restaurant_id}, {quote(dish_name)}, {quote(description)}, "
                f"{price:.2f}, {available})"
            )
    insert_values(
        lines, "restaurant",
        "restaurant_name, street_address, suburb_id, price_level", restaurants,
    )
    insert_values(lines, "restaurant_cuisine", "restaurant_id, cuisine_id", cuisine_rows)
    insert_values(
        lines, "dish", "restaurant_id, dish_name, description, price_aud, is_available",
        dish_rows,
    )

    # Alice's dedicated incoming/outgoing request scenarios are in 06_demo_user1.sql.
    existing_pairs = {(1, 2), (1, 3), (2, 3), (1, 4), (5, 6)}
    accepted_pairs = [(1, 2), (1, 3), (2, 3), (5, 6)]
    friendships = []
    while len(friendships) < 160:
        requester, addressee = RNG.sample(range(2, 101), 2)
        pair = tuple(sorted((requester, addressee)))
        if pair in existing_pairs:
            continue
        existing_pairs.add(pair)
        status = RNG.choices(("accepted", "pending", "rejected"), (72, 18, 10))[0]
        days_ago = RNG.randint(8, 260) if status == "accepted" else RNG.randint(2, 60)
        accepted_at = (
            f"now() - interval '{days_ago - RNG.randint(1, 4)} days'"
            if status == "accepted" else "NULL"
        )
        friendships.append(
            f"({requester}, {addressee}, {quote(status)}, "
            f"now() - interval '{days_ago} days', {accepted_at})"
        )
        if status == "accepted":
            accepted_pairs.append((requester, addressee))
    insert_values(
        lines, "friendship",
        "requester_id, addressee_id, status, requested_at, accepted_at", friendships,
    )
    friends: dict[int, set[int]] = {user_id: set() for user_id in range(1, 101)}
    for a, b in accepted_pairs:
        friends[a].add(b)
        friends[b].add(a)

    preferred_cuisines = {
        user_id: set(RNG.sample(range(1, 13), 2))
        for user_id in range(1, 101)
    }
    preferred_cuisines[1] = {1, 2}
    existing_favorites = {(1, 1), (1, 2), (2, 1), (3, 3), (5, 4)}
    favorites = []
    for user_id in range(1, 101):
        current = {r for u, r in existing_favorites if u == user_id}
        preferred = [
            r for r in range(1, 51)
            if restaurant_cuisines[r] in preferred_cuisines[user_id] and r not in current
        ]
        picks = RNG.sample(preferred, min(3, len(preferred)))
        current.update(picks)
        target = RNG.randint(4, 6)
        remaining = [r for r in range(1, 51) if r not in current]
        current.update(RNG.sample(remaining, max(0, target - len(current))))
        for restaurant_id in sorted(current):
            if (user_id, restaurant_id) not in existing_favorites:
                favorites.append(f"({user_id}, {restaurant_id})")
    insert_values(lines, "favorite", "user_id, restaurant_id", favorites)

    # Additional plans cover open, draft, finalized and cancelled frontend states.
    plan_states = ["open"] * 12 + ["draft"] * 3 + ["finalized"] * 5 + ["cancelled"] * 2
    plan_rows = []
    participants = []
    candidates = []
    votes = []
    final_updates = []
    plan_prefixes = (
        "Friday dinner", "Weekend catch-up", "Birthday meal", "Team lunch",
        "Long-overdue dinner", "Sunday brunch", "After-work supper",
        "Family lunch", "A night out", "Coffee and conversation",
    )
    for plan_id, final_state in enumerate(plan_states, start=4):
        creator = RNG.choice([u for u in range(1, 101) if friends[u]])
        possible_friends = sorted(friends[creator])
        invitees = RNG.sample(possible_friends, min(len(possible_friends), RNG.randint(1, 3)))
        choices = RNG.sample(range(1, 51), 3)
        title = f"{RNG.choice(plan_prefixes)} at {restaurant_names[choices[0]]}"
        if final_state == "finalized":
            days_ago = RNG.randint(15, 180)
            date = f"now() - interval '{days_ago} days'"
            deadline = f"now() - interval '{days_ago + 5} days'"
            created = f"now() - interval '{days_ago + 14} days'"
        else:
            days_ahead = RNG.randint(14, 50)
            date = f"now() + interval '{days_ahead} days'"
            deadline = f"now() + interval '{days_ahead - 7} days'"
            created = "now() - interval '4 days'"
        initial_state = final_state if final_state in {"open", "draft"} else "draft"
        plan_rows.append(
            f"({creator}, {quote(title)}, {date}, {deadline}, "
            f"{quote(initial_state)}, {created})"
        )
        accepted_invitees = []
        for friend_id in invitees:
            rsvp = (
                "accepted" if final_state == "finalized"
                else RNG.choices(("accepted", "invited", "declined"), (65, 25, 10))[0]
            )
            responded = "now()" if rsvp != "invited" else "NULL"
            participants.append(
                f"({plan_id}, {friend_id}, {quote(rsvp)}, {responded})"
            )
            if rsvp == "accepted":
                accepted_invitees.append(friend_id)
        for restaurant_id in choices:
            candidates.append(f"({plan_id}, {restaurant_id})")
        if final_state == "open":
            for voter in [creator, *accepted_invitees]:
                votes.append(f"({plan_id}, {voter}, {RNG.choice(choices)})")
        elif final_state == "finalized":
            final_updates.append(
                f"UPDATE dining_plan SET status = 'finalized', "
                f"chosen_restaurant_id = {RNG.choice(choices)} WHERE plan_id = {plan_id};\n"
            )
        elif final_state == "cancelled":
            final_updates.append(
                f"UPDATE dining_plan SET status = 'cancelled' WHERE plan_id = {plan_id};\n"
            )
    insert_values(
        lines, "dining_plan",
        "creator_id, title, plan_date, voting_deadline, status, created_at", plan_rows,
    )
    insert_values(
        lines, "plan_participant",
        "plan_id, user_id, rsvp_status, responded_at", participants,
    )
    insert_values(lines, "plan_candidate", "plan_id, restaurant_id", candidates)
    insert_values(lines, "plan_vote", "plan_id, user_id, restaurant_id", votes)
    lines.extend(final_updates)
    lines.append(
        "UPDATE plan_participant pp\n"
        "SET invited_at = p.created_at + interval '1 day',\n"
        "    responded_at = p.created_at + interval '2 days'\n"
        "FROM dining_plan p\n"
        "WHERE pp.plan_id = p.plan_id AND p.status = 'finalized' AND p.plan_id >= 4;\n"
    )
    lines.append("\n")

    # Review volume varies by venue, unlike the former fixed 20-per-shop seed.
    targets = [8] * 50
    popularity = [0.6 + RNG.random() * 1.4 for _ in range(50)]
    for _ in range(600):
        while True:
            index = RNG.choices(range(50), weights=popularity)[0]
            if targets[index] < 45:
                targets[index] += 1
                break
    assert sum(targets) == 1000
    base_reviewers = {1: {1, 2}, 2: {1, 2}, 3: {3}}
    visits = []
    review_sources = []
    review_details = []
    review_texts = set()
    for restaurant_id in range(1, 51):
        used = base_reviewers.get(restaurant_id, set())
        required = targets[restaurant_id - 1] - len(used)
        selected = [1] if restaurant_id in {5, 6, 7, 8, 9} else []
        eligible = [u for u in range(1, 101) if u not in used and u not in selected]
        ranked = sorted(
            eligible,
            key=lambda u: RNG.random() + (
                0.40 if restaurant_cuisines[restaurant_id] in preferred_cuisines[u] else 0
            ),
            reverse=True,
        )
        selected.extend(ranked[: required - len(selected)])
        quality = 2.9 + random.Random(4000 + restaurant_id).random() * 1.8
        for user_id in selected:
            days_ago = RNG.randint(2, 310)
            party_size = RNG.randint(1, 5)
            visibility = RNG.choices(
                ("public", "friends", "private"), (72, 23, 5)
            )[0]
            rating = max(1, min(5, round(RNG.gauss(quality, 0.85))))
            dish_name, kind = RNG.choice(restaurant_menus[restaurant_id])
            review_text = review_copy(dish_name, kind, rating, party_size)
            if review_text in review_texts:
                review_text += " I visited on a weekday."
            review_texts.add(review_text)
            visits.append(
                f"({user_id}, {restaurant_id}, CURRENT_DATE - {days_ago}, "
                f"{party_size}, {quote(visibility)})"
            )
            review_sources.append(
                f"({user_id}, {restaurant_id}, CURRENT_DATE - {days_ago}, "
                f"{rating}, {quote(review_text)}, "
                f"CURRENT_DATE - {days_ago} + interval '20 hours')"
            )
            review_details.append(
                (user_id, restaurant_id, days_ago, visibility, dish_name, rating)
            )
    assert len(visits) == 995
    insert_values(
        lines, "visit",
        "user_id, restaurant_id, visit_date, party_size, visibility", visits,
    )

    # Reviews describe the overall restaurant visit; menu dishes are only
    # mentioned naturally in the prose, never rated or reviewed separately.
    for start in range(0, len(review_sources), 200):
        batch = review_sources[start : start + 200]
        lines.append("INSERT INTO review (visit_id, rating, review_text, created_at)\n")
        lines.append("SELECT v.visit_id, s.rating, s.review_text, s.created_at\n")
        lines.append("FROM (VALUES\n  ")
        lines.append(",\n  ".join(batch))
        lines.append(
            "\n) AS s(user_id, restaurant_id, visit_date, rating, review_text, created_at)\n"
            "JOIN visit v ON v.user_id = s.user_id\n"
            "            AND v.restaurant_id = s.restaurant_id\n"
            "            AND v.visit_date = s.visit_date;\n\n"
        )

    # Friends react to public restaurant reviews in varied, conversational English.
    public_reviews = [
        row for row in review_details if row[3] == "public" and row[2] >= 5
    ]
    RNG.shuffle(public_reviews)
    comments = []
    for user_id, restaurant_id, days_ago, _, dish_name, rating in public_reviews[:220]:
        possible_authors = sorted(friends[user_id])
        author = RNG.choice(possible_authors) if possible_authors else RNG.choice(
            [u for u in range(1, 101) if u != user_id]
        )
        comments.append(
            f"({user_id}, {restaurant_id}, CURRENT_DATE - {days_ago}, "
            f"{author}, {quote(comment_copy(dish_name, rating))})"
        )
    for start in range(0, len(comments), 200):
        lines.append("INSERT INTO review_comment (review_id, author_id, comment_text, created_at)\n")
        lines.append("SELECT rv.review_id, s.author_id, s.comment_text, rv.created_at + interval '1 day'\n")
        lines.append("FROM (VALUES\n  ")
        lines.append(",\n  ".join(comments[start : start + 200]))
        lines.append(
            "\n) AS s(user_id, restaurant_id, visit_date, author_id, comment_text)\n"
            "JOIN visit v ON v.user_id = s.user_id\n"
            "            AND v.restaurant_id = s.restaurant_id\n"
            "            AND v.visit_date = s.visit_date\n"
            "JOIN review rv ON rv.visit_id = v.visit_id;\n\n"
        )

    recommendations = []
    for sender, receiver in RNG.sample(accepted_pairs, 40):
        if RNG.randrange(2):
            sender, receiver = receiver, sender
        restaurant_id = RNG.randint(1, 50)
        dish_name, _ = RNG.choice(restaurant_menus[restaurant_id])
        dish_name = in_sentence(dish_name)
        message = RNG.choice((
            f"Thought of you when I saw the {dish_name} at {restaurant_names[restaurant_id]}.",
            f"I think you would like {restaurant_names[restaurant_id]}. Want to try it together?",
            f"The {dish_name} looks great. We should go to {restaurant_names[restaurant_id]} soon.",
        ))
        status = RNG.choices(("unread", "read", "dismissed"), (65, 30, 5))[0]
        recommendations.append(
            f"({sender}, {receiver}, {restaurant_id}, {quote(message)}, {quote(status)})"
        )
    insert_values(
        lines, "recommendation",
        "sender_id, receiver_id, restaurant_id, message, status", recommendations,
    )

    lines.extend((
        "DO $$ BEGIN\n",
        "  IF (SELECT COUNT(*) FROM app_user) <> 100\n",
        "     OR (SELECT COUNT(*) FROM restaurant) <> 50\n",
        "     OR (SELECT COUNT(*) FROM dish) <> 250\n",
        "     OR (SELECT COUNT(*) FROM review) <> 1000\n",
        "     OR EXISTS (SELECT 1 FROM restaurant_rating_summary WHERE review_count = 0)\n",
        "  THEN RAISE EXCEPTION 'Generated seed failed its data checks';\n",
        "  END IF;\n",
        "END $$;\n\n",
        "COMMIT;\n",
    ))
    OUTPUT.write_text("".join(lines), encoding="utf-8", newline="\n")
    print(f"Generated {OUTPUT}")
    print("Expected totals: 100 users, 50 restaurants, 250 dishes, 1000 reviews")


if __name__ == "__main__":
    main()
