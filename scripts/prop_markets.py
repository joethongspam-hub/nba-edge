"""NBA EDGE supported player markets and game-level derived combo stats."""
import math

BASE_MARKETS = ("player_points", "player_rebounds", "player_assists", "player_threes")
COMBO_COMPONENTS = {
    "player_points_rebounds": ("player_points", "player_rebounds"),
    "player_points_assists": ("player_points", "player_assists"),
    "player_rebounds_assists": ("player_rebounds", "player_assists"),
    "player_points_rebounds_assists": ("player_points", "player_rebounds", "player_assists"),
}
MARKETS = BASE_MARKETS + tuple(COMBO_COMPONENTS)


def stat_value(game, market):
    """Return a verified statistic; never treat a missing combo component as zero."""
    if market not in MARKETS:
        return None
    components = COMBO_COMPONENTS.get(market, (market,))
    values = []
    for component in components:
        try:
            value = float(game[component])
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(value) or value < 0:
            return None
        values.append(value)
    return sum(values)
