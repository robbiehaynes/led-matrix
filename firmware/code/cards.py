"""
Pixel layout for the card markers on the football/rugby score rows.

Pure Python (no board/displayio imports) so it can be unit-tested on a
desktop. Each team gets up to CARD_SLOTS single pixels in a vertical column
just right of its name, in the whitespace the row text already leaves there.
The relay sends each team's cards as a string like "RYY" (reds first).
"""
CARD_SLOTS = 3


def text_width(text, advance):
    """Pixel width of text, given advance(char) -> pixels for one glyph."""
    return sum(advance(ch) for ch in text)


def card_pixels(match, text_x, advance):
    """
    Returns [(x, slot, kind), ...]: slot 0 is the top pixel, kind is "R" or
    "Y". Mirrors the row text built by LeagueScorePager._match_line:
    "<home> <h>-<a> <away>  <status>".
    """
    score = f"{match['home_score']}-{match['away_score']}"
    home, away = match["home"], match["away"]

    pixels = []
    # +1 skips the glyph's blank spacing column, leaving a 1px gap after the name
    home_x = text_x + text_width(home, advance) + 1
    away_x = text_x + text_width(f"{home} {score} {away}", advance) + 1
    for x, cards in ((home_x, match.get("home_cards") or ""),
                     (away_x, match.get("away_cards") or "")):
        for slot, kind in enumerate(cards[:CARD_SLOTS]):
            pixels.append((x, slot, kind))
    return pixels
