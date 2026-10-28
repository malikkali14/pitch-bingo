"""Server-side wording in every language (spec 5.4): question bank, live squares, option labels,
explanations, strategist reasons and recaps. These are the template fallbacks, so French works
with Foundry off. Club names, player names and fan handles are never translated.
"""

from typing import Any

LANGUAGES = ("en", "fr")

QUESTIONS: dict[str, dict[str, str]] = {
    "en": {},          # English lives on the templates themselves (bank.py)
    "fr": {
        "yellow_cards": "Combien de cartons jaunes avant {m} ?",
        "corners": "Combien de corners avant {m} ?",
        "more_shots": "Qui a le plus de tirs à {m} ?",
        "goal": "Y aura-t-il un but avant {m} ?",
        "offsides": "Combien de hors-jeu avant {m} ?",
        "possession": "Qui a le plus la possession à {m} ?",
        "subs": "Combien de remplacements avant {m} ?",
        "focus_shot": "Un tir de {player} avant {m} ?",
        "club_fouls": "Combien de fautes de {club} avant {m} ?",
        "first_foul": "Qui commet la première faute ?",
        "first_corner": "Qui obtient le premier corner ?",
        "first_shot": "Qui tente le premier tir ?",
        "first_on_target": "Qui cadre le premier tir ?",
        "first_offside": "Qui est le premier hors-jeu ?",
        "first_booking": "Qui reçoit le premier carton ?",
        "first_sub_off": "Qui est remplacé en premier ?",
        "first_goal": "Qui marque en premier ?",
        "first_free_kick": "Qui obtient le premier coup franc ?",
        "first_throw_in": "Qui effectue la première touche ?",
        # live squares
        "referee": "Qu'a sifflé l'arbitre ?",
        "restart": "Comment le jeu reprend-il ?",
        "throw_team": "Quelle équipe obtient la touche ?",
        "shot_xg": "Estimez l'xG de ce tir",
        "pass_length": "Quelle était la longueur de cette passe ?",
        "shot_speed": "À quelle vitesse est parti ce tir ?",
        "move_passes": "Combien de passes dans cette action ?",
    },
}

# Labels for option keys that aren't clubs, players or plain ranges.
OPTION_LABELS: dict[str, dict[str, str]] = {
    "en": {"yes": "Yes", "no": "No", "level": "Level", "foul": "Foul", "offside": "Offside",
           "advantage": "Advantage played", "no_call": "No call", "corner": "Corner",
           "goal_kick": "Goal kick", "throw_in": "Throw-in"},
    "fr": {"yes": "Oui", "no": "Non", "level": "Égalité", "foul": "Faute", "offside": "Hors-jeu",
           "advantage": "Avantage", "no_call": "Rien", "corner": "Corner",
           "goal_kick": "Sortie de but", "throw_in": "Touche"},
}

# Measured live-square buckets: (lower, upper) edges in the template's own unit.
UNDER = {"en": "under {v}", "fr": "moins de {v}"}
OVER = {"en": "over {v}", "fr": "plus de {v}"}

LINES: dict[str, dict[str, str]] = {
    "en": {
        "answer": "{question} Answer: {answer}.",
        "none": "none",
        "void": "It didn't happen this match.",
        "row": "row {n}", "col": "column {n}", "diag0": "the diagonal",
        "diag1": "the other diagonal", "blank": "blank", "wildcard": "wildcard",
        "moved_any": "Moved a square to raise your chance of a line.",
        "moved_full": "Moved a {what} into {line} to complete it.",
        "moved_fresh": "Moved a {what} into {line}, a line with nothing lost yet.",
        "moved_some": "Moved a {what} into {line}: {good} of its 5 squares are already correct.",
        "headline": "{label}: {score}", "in_control": "{club} in control",
        "recap_halftime": "Half-time", "recap_full_time": "Full time",
        "recap_catch_up": "Catch-up", "recap_other": "Recap",
        "goals": "Goals: {list}.", "no_goals": "No goals yet.",
        "own_goal": "an own goal",
        "possession": "{home} had {share}% of the ball, with {hs} shots to {as_}.",
        "standout": "{player} ({club}) stood out with {touches} touches.",
        "shots_point": "{home} {hs} shots, {away} {as_}",
        "standout_point": "{player} the standout", "open_point": "All to play for",
        "bingo": "You have {points} points, {correct} correct and {lines} lines.",
        "club_paragraph": "For {club}: {situation}.",
        "club_ahead": "ahead {score}", "club_behind": "behind {score}",
        "club_level": "level at {score}",
        "player_paragraph": "{player}: {touches} touches, {passes} passes, {shots} shots.",
        "focus_line": "{player} so far: {touches} touches, {passes} passes, {shots} shots.",
        "milestone": "Milestone for {player}: {what}.",
    },
    "fr": {
        "answer": "{question} Réponse : {answer}.",
        "none": "aucune",
        "void": "Ce n'est pas arrivé pendant ce match.",
        "row": "la ligne {n}", "col": "la colonne {n}", "diag0": "la diagonale",
        "diag1": "l'autre diagonale", "blank": "case vide", "wildcard": "joker",
        "moved_any": "Case déplacée pour augmenter vos chances de ligne.",
        "moved_full": "Un {what} déplacé dans {line} pour la compléter.",
        "moved_fresh": "Un {what} déplacé dans {line}, une ligne encore intacte.",
        "moved_some": "Un {what} déplacé dans {line} : {good} cases sur 5 déjà justes.",
        "headline": "{label} : {score}", "in_control": "{club} maîtrise le match",
        "recap_halftime": "Mi-temps", "recap_full_time": "Fin du match",
        "recap_catch_up": "Le point", "recap_other": "Résumé",
        "goals": "Buts : {list}.", "no_goals": "Pas encore de but.",
        "own_goal": "contre son camp",
        "possession": "{home} a eu {share} % du ballon, avec {hs} tirs contre {as_}.",
        "standout": "{player} ({club}) s'est distingué avec {touches} ballons touchés.",
        "shots_point": "{home} {hs} tirs, {away} {as_}",
        "standout_point": "{player}, l'homme du match", "open_point": "Tout reste à jouer",
        "bingo": "Vous avez {points} points, {correct} bonnes réponses et {lines} lignes.",
        "club_paragraph": "Pour {club} : {situation}.",
        "club_ahead": "devant au score, {score}", "club_behind": "mené, {score}",
        "club_level": "à égalité, {score}",
        "player_paragraph": "{player} : {touches} ballons touchés, {passes} passes, {shots} tirs.",
        "focus_line": "{player} jusqu'ici : {touches} ballons touchés, {passes} passes, "
                      "{shots} tirs.",
        "milestone": "Cap franchi pour {player} : {what}.",
    },
}

MILESTONES: dict[str, dict[str, str]] = {
    "en": {"passes_50": "50 passes", "saves_5": "a fifth save", "distance_10km": "10 km covered",
           "appearance_100": "a 100th appearance",
           "goal_first_season": "a first goal of the season",
           "goal_round": "goal number {value} of the season"},
    "fr": {"passes_50": "50 passes", "saves_5": "un cinquième arrêt",
           "distance_10km": "10 km parcourus", "appearance_100": "un 100e match",
           "goal_first_season": "un premier but de la saison",
           "goal_round": "le {value}e but de la saison"},
}


def normalize(language: str | None) -> str:
    return language if language in LANGUAGES else "en"


def say(language: str, key: str, **values: Any) -> str:
    table = LINES[normalize(language)]
    return table.get(key, LINES["en"][key]).format(**values)


def number(value: float, language: str, digits: int = 2) -> str:
    """0.15 in English, 0,15 in French (spec 5.4)."""
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{value:.0f}"
    return text.replace(".", ",") if normalize(language) == "fr" else text
