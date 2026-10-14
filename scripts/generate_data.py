"""Generate ten UTF-8 CSV files. No database or third-party packages required."""

from __future__ import annotations

import argparse
import csv
import itertools
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from catalog import FIRST_NAMES, LAST_NAMES, NEW_SUBURBS, NEW_CUISINES, NEW_RESTAURANTS, STREET_BY_SUBURB, FOOD_MENTIONS

ROOT = Path(__file__).resolve().parents[1]
SEED = 9120
# Stable CSV headings also define the import order and expected schema.
FILES = {
    "users": ("app_user", ("user_id", "user_name", "user_email", "created_at")),
    "suburbs": ("suburb", ("suburb_id", "name", "state", "postcode")),
    "cuisines": ("cuisine", ("cuisine_id", "cuisine_name")),
    "restaurants": ("restaurant", ("restaurant_id", "restaurant_name", "street_address", "suburb_id", "price_level", "is_active")),
    "restaurant_cuisines": ("restaurant_cuisine", ("restaurant_id", "cuisine_id")),
    "friendships": ("friendship", ("friendship_id", "requester_id", "addressee_id", "status", "requested_at", "accepted_at")),
    "favorites": ("favorite", ("user_id", "restaurant_id", "added_at")),
    "visits": ("visit", ("visit_id", "user_id", "restaurant_id", "visit_date", "party_size")),
    "reviews": ("review", ("review_id", "visit_id", "rating", "review_text", "created_at")),
    "review_comments": ("review_comment", ("comment_id", "review_id", "author_id", "parent_comment_id", "comment_text", "created_at")),
}

QUALITY = {
    5: ("The food was fresh and full of flavour.", "The team made us feel welcome from the moment we arrived.", "Every plate was well prepared and the service was thoughtful."),
    4: ("The food was enjoyable, although the room became noisy.", "Everything tasted good, but the wait was a little longer than expected.", "Friendly service and a satisfying meal, with just a small seasoning issue."),
    3: ("The meal was fine, but the service was inconsistent.", "Some dishes worked better than others, and the prices felt slightly high.", "A reasonable meal, although nothing particularly stood out."),
    2: ("The food arrived lukewarm and we waited a long time.", "The room was comfortable, but the cooking did not meet our expectations.", "The team seemed rushed and our order needed correcting."),
    1: ("Our order was wrong and the team did not resolve it.", "The long wait and cold food made this a disappointing visit.", "The food and service both fell well below our expectations."),
}
ENDINGS = {
    5: ("I would happily bring friends here again.", "This is now on my list for a relaxed dinner.", "Excellent value for the overall experience."),
    4: ("I would return at a quieter time.", "A good option for a casual catch-up.", "Worth another visit despite those small issues."),
    3: ("I might try it again, but it would not be my first choice.", "There is potential here if the service improves.", "An acceptable stop when you are nearby."),
    2: ("I hope the team can improve before our next visit.", "There are better options nearby for the same price.", "I would hesitate to recommend it at the moment."),
    1: ("I would choose somewhere else next time.", "Unfortunately, I cannot recommend it based on this visit.", "The overall experience was not worth the price."),
}


def generate(output: Path, anchor: date) -> dict[str, int]:
    rng = random.Random(SEED)
    base = datetime.combine(anchor, time(0), timezone.utc)
    timestamp = lambda days: (base - timedelta(days=days)).isoformat()
    rows = {key: [] for key in FILES}
    fixed_names = ["Alice Morgan", "Ben Carter", "Cara Nguyen", "Dina Patel", "Evan Brooks",
                   "Faye Liu", "Grace Wilson", "Henry Chen", "Ivy Reed", "Julian Park"]
    names = list(itertools.product(FIRST_NAMES, LAST_NAMES))
    rng.shuffle(names)
    people = fixed_names + [f"{first} {last}" for first, last in names[:90]]
    for user_id, name in enumerate(people, 1):
        email = name.lower().replace(" ", ".").replace("'", "") + "@example.test"
        rows["users"].append((user_id, name, email, timestamp(400 + user_id)))

    suburbs = [("Newtown", "NSW", "2042"), ("Surry Hills", "NSW", "2010"), ("Haymarket", "NSW", "2000")]
    suburbs += [item[:3] for item in NEW_SUBURBS]
    rows["suburbs"] = [(i, *item) for i, item in enumerate(suburbs, 1)]
    cuisines = ["Chinese", "Japanese", "Cafe", "Italian", *NEW_CUISINES]
    rows["cuisines"] = [(i, name) for i, name in enumerate(cuisines, 1)]
    places = [("Lantern Noodles", 1, 1, 2), ("Sakura Table", 2, 2, 3),
              ("Corner Coffee", 3, 3, 1), ("Pasta Garden", 4, 1, 2), *NEW_RESTAURANTS]
    for restaurant_id, (name, cuisine, suburb, price) in enumerate(places, 1):
        address = f"{12 if restaurant_id == 1 else 8 + restaurant_id * 3} {STREET_BY_SUBURB[suburb]}"
        rows["restaurants"].append((restaurant_id, name, address, suburb, price, "true"))
        rows["restaurant_cuisines"].append((restaurant_id, cuisine))
        # A few venues have two cuisines, demonstrating the junction table.
        if cuisine == 3 and restaurant_id % 2 == 1:
            rows["restaurant_cuisines"].append((restaurant_id, 11))

    friendships = [(1, 2, "accepted"), (1, 3, "accepted"), (10, 1, "accepted"),
                   (8, 1, "pending"), (9, 1, "pending"), (1, 4, "pending"), (1, 11, "rejected")]
    pairs = {tuple(sorted((a, b))) for a, b, _ in friendships}
    while len(friendships) < 240:
        a, b = rng.sample(range(2, 101), 2)
        pair = tuple(sorted((a, b)))
        if pair in pairs:
            continue
        pairs.add(pair)
        friendships.append((a, b, rng.choices(["accepted", "pending", "rejected"], [8, 1, 1])[0]))
    for friendship_id, (a, b, status) in enumerate(friendships, 1):
        rows["friendships"].append((friendship_id, a, b, status, timestamp(30),
                                     timestamp(29) if status == "accepted" else ""))

    for user in range(1, 101):
        saved = [1, 3, 5] if user == 1 else rng.sample(range(1, 51), 3)
        rows["favorites"].extend((user, restaurant, timestamp(5 + i)) for i, restaurant in enumerate(saved))

    fixed_visits = [(1, 1, 2, 5), (2, 1, 1, 4), (3, 1, 3, 5),
                    (1, 2, 4, 4), (10, 2, 2, 4), (2, 5, 5, 3)]
    for review_id in range(1, 1001):
        if review_id <= len(fixed_visits):
            user, restaurant, days, rating = fixed_visits[review_id - 1]
        else:
            user, restaurant, days = rng.randint(2, 100), rng.randint(1, 50), rng.randint(1, 240)
            rating = rng.choices([1, 2, 3, 4, 5], [2, 6, 17, 45, 30])[0]
        party = rng.choice([1, 2, 2, 3, 4, 6])
        food = rng.choice(FOOD_MENTIONS[places[restaurant - 1][1]])
        occasion = rng.choice(["after work", "for lunch", "on a rainy evening", "for a weekend catch-up",
                               "with family", "with a couple of friends"])
        review_text = f"I visited {places[restaurant - 1][0]} {occasion} and tried the {food}. {rng.choice(QUALITY[rating])} {rng.choice(ENDINGS[rating])}"
        if review_id == 1:
            review_text = "We stopped at Lantern Noodles after work. The dan dan noodles had a lovely sesame flavour, the staff were welcoming, and the whole meal felt good value. I would bring friends here again."
        rows["visits"].append((review_id, user, restaurant, (anchor - timedelta(days=days)).isoformat(), party))
        rows["reviews"].append((review_id, review_id, rating, review_text, timestamp(days)))
    for i in range(20):
        rows["visits"].append((1001 + i, 1 if i == 0 else rng.randint(2, 100),
                              3 if i == 0 else rng.randint(1, 50),
                              (anchor - timedelta(days=1 + i)).isoformat(), 2))

    rows["review_comments"] = [
        (1, 1, 2, "", "Those noodles sound great. Was it busy when you went?", timestamp(1)),
        (2, 1, 1, 1, "It was quite calm around six. We found a table straight away.", timestamp(0)),
        (3, 2, 1, "", "Thanks, Ben. I enjoyed this place too. Would you go back?", timestamp(0)),
        (4, 2, 2, 3, "Definitely. I would probably book a table for Friday evening.", timestamp(0)),
    ]
    for i in range(5, 225):
        review = rng.choice(rows["reviews"])
        author = rng.randint(1, 100)
        parent = ""
        text = rng.choice([
            "Thanks for sharing. I have been curious about this place.",
            "Would you recommend booking, or was it easy to get a table?",
            "This sounds useful for our next catch-up. How was the atmosphere?",
            "I had a similar experience last month. Thanks for the honest review.",
            "Good to know about the service. I might try a quieter time.",
        ])
        created = review[4]
        rows["review_comments"].append((i, review[0], author, parent, text, created))
        if i % 10 == 0:
            rows["review_comments"].append((1000 + i, review[0], rng.randint(1, 100), i,
                                           "We went early and did not need a booking.", created))

    output.mkdir(parents=True, exist_ok=True)
    for name, (_, columns) in FILES.items():
        with (output / f"{name}.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(columns)
            writer.writerows(rows[name])
    return {name: len(data) for name, data in rows.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(),
                        help="Anchor date YYYY-MM-DD; same date and seed produce the same CSV.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    counts = generate(args.output_dir, args.date)
    print(f"Generated CSV for {args.date.isoformat()} in {args.output_dir}")
    for name, count in counts.items():
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
