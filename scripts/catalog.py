"""Fictional English people and restaurants; food names are prose only."""

FIRST_NAMES = (
    "Amelia", "Oliver", "Mia", "Jack", "Sophie", "Noah", "Isla", "Leo",
    "Grace", "Liam", "Ava", "Ethan", "Zoe", "Lucas", "Ruby", "Henry",
    "Chloe", "Arjun", "Priya", "Aisha", "Daniel", "Hannah", "Oscar", "Ella",
    "Thomas", "Jasmine", "Mason", "Freya", "Finn", "Lily", "Harper", "Max",
    "Nina", "Rohan", "Sam", "Tara", "Theo", "Yasmin", "Jasper", "Ivy",
    "Kai", "Layla", "Maya", "Nathan", "Olivia", "Pia", "Quinn", "Ryan",
    "Sienna", "Willow", "Yuki", "Aiden", "Elena", "Marcus", "Nora", "Felix",
)

LAST_NAMES = (
    "Anderson", "Bennett", "Chen", "Davis", "Evans", "Fernandez", "Gupta",
    "Harris", "Ito", "Johnson", "Kaur", "Lewis", "Martin", "Ng", "O'Brien",
    "Park", "Quinn", "Roberts", "Singh", "Taylor", "Usman", "Walker", "Xu",
    "Young", "Zhang", "Brown", "Clarke", "Doyle", "Edwards", "Foster",
    "Green", "Hughes", "Ibrahim", "Kim", "Li", "Miller", "Nakamura",
    "Patel", "Reed", "Shah", "Tran", "Wilson", "Yamamoto", "Zhao",
)

# The generator prepends three suburbs and four cuisines to these collections.
NEW_SUBURBS = (
    ("Parramatta", "NSW", "2150", "Church Street"),
    ("Chatswood", "NSW", "2067", "Victoria Avenue"),
    ("Glebe", "NSW", "2037", "Glebe Point Road"),
    ("Redfern", "NSW", "2016", "Regent Street"),
    ("Burwood", "NSW", "2134", "Burwood Road"),
    ("Mascot", "NSW", "2020", "Botany Road"),
    ("Bondi", "NSW", "2026", "Bondi Road"),
)

STREET_BY_SUBURB = {
    1: "King Street", 2: "Crown Street", 3: "Dixon Street",
    **{index + 4: row[3] for index, row in enumerate(NEW_SUBURBS)},
}

NEW_CUISINES = (
    "Korean", "Thai", "Vietnamese", "Indian", "Middle Eastern",
    "Mexican", "Modern Australian", "Seafood",
)

# name, cuisine_id, suburb_id, price_level. All restaurants are fictional.
NEW_RESTAURANTS = (
    ("Red Lantern Kitchen", 1, 4, 2),
    ("Silk Road Dumplings", 1, 5, 2),
    ("Jade Bowl", 1, 7, 1),
    ("Golden Wok House", 1, 8, 2),
    ("Kumo Bento", 2, 5, 2),
    ("Mizu Ramen", 2, 3, 2),
    ("Hana Izakaya", 2, 2, 3),
    ("Yuzu Kitchen", 2, 4, 3),
    ("Wattle and Bean", 3, 6, 2),
    ("Field Notes Cafe", 3, 7, 2),
    ("Sunroom Coffee", 3, 10, 2),
    ("Juniper Table", 3, 1, 3),
    ("Trattoria Lume", 4, 2, 3),
    ("Olive and Flour", 4, 6, 2),
    ("Casa Sera", 4, 4, 3),
    ("Rosso Kitchen", 4, 10, 3),
    ("Seoul Garden Table", 5, 3, 2),
    ("Kimchi House", 5, 8, 2),
    ("Han River Grill", 5, 5, 3),
    ("Bap and Bowl", 5, 9, 1),
    ("Lemongrass Lane", 6, 1, 2),
    ("Nara Thai Kitchen", 6, 4, 2),
    ("Basil and Lime", 6, 7, 2),
    ("Siam Street Table", 6, 10, 3),
    ("Pho and Co", 7, 3, 1),
    ("Lotus Lane", 7, 8, 2),
    ("Saigon Bowl", 7, 9, 2),
    ("Little Hanoi", 7, 6, 2),
    ("Cardamom House", 8, 4, 3),
    ("Tamarind Table", 8, 5, 2),
    ("Saffron and Spice", 8, 2, 3),
    ("Masala Corner", 8, 7, 2),
    ("Cedar and Sumac", 9, 6, 3),
    ("Pomegranate Kitchen", 9, 2, 3),
    ("Olive Grove Mezze", 9, 4, 2),
    ("Za'atar Room", 9, 10, 2),
    ("La Palma Cantina", 10, 1, 2),
    ("Casa Verde Tacos", 10, 7, 2),
    ("Salsa Roja", 10, 9, 2),
    ("Little Mercado", 10, 8, 1),
    ("Banksia Dining", 11, 2, 4),
    ("The Local Harvest", 11, 6, 3),
    ("Paperbark Kitchen", 11, 5, 4),
    ("Harbour and Hearth", 11, 10, 3),
    ("Coastal Catch", 12, 10, 3),
    ("Saltwater Kitchen", 12, 2, 4),
)

# These are natural-language ingredients for whole-restaurant reviews, not menu records.
FOOD_MENTIONS = {
    1: ("dan dan noodles", "pork dumplings", "mapo tofu"),
    2: ("miso ramen", "salmon donburi", "chicken karaage"),
    3: ("flat white", "avocado toast", "ricotta hotcakes"),
    4: ("beef ragu", "margherita pizza", "potato gnocchi"),
    5: ("bibimbap", "Korean fried chicken", "beef bulgogi"),
    6: ("pad thai", "green curry", "tom yum soup"),
    7: ("beef pho", "banh mi", "rice paper rolls"),
    8: ("butter chicken", "dal", "vegetable biryani"),
    9: ("falafel", "lamb shawarma", "hummus"),
    10: ("fish tacos", "quesadillas", "nachos"),
    11: ("roast chicken", "pumpkin salad", "grilled barramundi"),
    12: ("fish and chips", "prawn linguine", "grilled octopus"),
}
