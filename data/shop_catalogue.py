# data/shop_catalogue.py
# ──────────────────────────────────────────────
# Catalogue d'objets achetables/vendables + revente de personnages
# ──────────────────────────────────────────────

CURRENCY_NAME = "GoldValis"

# Catalogue d'objets achetables/vendables
ITEMS_CATALOGUE = {
    "❄️": {"achat": 2,  "vente": 0},
    "🪓": {"achat": 6,  "vente": 1},
    "🔥": {"achat": 10, "vente": 2},
    "⚡": {"achat": 20, "vente": 5},
    "🔫": {"achat": 30, "vente": 7},
    "🧨": {"achat": 40, "vente": 10},
    "☠️": {"achat": 60, "vente": 12},
    "🦠": {"achat": 40, "vente": 20},
    "🧪": {"achat": 30, "vente": 15},
    "🧟": {"achat": 55, "vente": 27},
    "🍀": {"achat": 4,  "vente": 1},
    "🩸": {"achat": 12, "vente": 3},
    "🩹": {"achat": 18, "vente": 4},
    "💊": {"achat": 30, "vente": 7},
    "💕": {"achat": 25, "vente": 5},
    "📦": {"achat": 32, "vente": 8},
    "🔍": {"achat": 28, "vente": 7},
    "💉": {"achat": 34, "vente": 8},
    "🛡": {"achat": 36, "vente": 9},
    "👟": {"achat": 28, "vente": 7},
    "🪖": {"achat": 32, "vente": 8},
    "⭐️": {"achat": 44, "vente": 11},
    "🎟️": {"achat": 200, "vente": 0},  # Ticket d’invocation
}

# Prix de revente des personnages selon rareté
RARETE_SELL_VALUES = {
    "Commun": 50,
    "Rare": 100,
    "Épique": 200,
    "Légendaire": 400,
}
