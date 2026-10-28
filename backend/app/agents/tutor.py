"""Explanations when a window closes (spec 5.1, 8.4 window-close workflow, 8.6).

Normal mode: the rules tutor (fast model, spec 8.2) explains the call or rule in one or two lines a
new fan understands, from a stored rule summary. Advanced mode: the narrator's voice adds the
tactical context (fast model). Either way the template explanation has already posted, and
this replaces it only if it passes the verifier.
"""

from typing import Any

from app.agents.messages import Definition, Explanation
from app.agents.runner import AgentSpec
from app.verify.verifier import verify_line

# The calls and rules the dots can show (spec 8.6), in our own words.
RULES = {
    "foul": "A foul is an unfair challenge, like a trip, push or late tackle. The other side "
            "gets a free kick from where it happened.",
    "advantage": "If stopping play would help the side that was fouled, the referee lets it "
                 "carry on. That is playing advantage; the foul can still be punished later.",
    "offside": "A player is offside if, when a team-mate passes, they are nearer the goal line "
               "than both the ball and the second-last defender, in the opponents' half. Being "
               "level with that defender is onside. The defending side gets a free kick.",
    "corner": "When the defending side last touches the ball before it crosses their own goal "
              "line, the attackers take a corner from the corner flag.",
    "goal_kick": "When the attacking side last touches the ball before it crosses the goal line "
                 "without a goal, the defenders restart with a goal kick.",
    "throw_in": "When the ball crosses a touchline, the side that didn't touch it last throws it "
                "back in with both hands, from behind the head.",
    "yellow_card": "A yellow card is a caution for reckless fouls, time wasting or dissent. Two "
                   "in one match make a red.",
    "red_card": "A red card sends a player off for the rest of the match, and the team plays on "
                "with one fewer. It comes from a second yellow or a serious offence.",
    "free_kick": "A free kick restarts play after a foul or an offside; opponents must stand "
                 "at least 9.15 metres away.",
    "substitution": "Each side can change players during stoppages. A player taken off can't "
                    "come back on.",
    "goal": "A goal counts when the whole ball crosses the goal line between the posts and "
            "under the bar. The side that conceded kicks off.",
    "shot_on_target": "A shot on target would have gone in without the keeper or a last "
                      "defender. Saves and goals count; shots wide or blocked don't.",
    "possession": "Possession is the share of time each side has the ball while it is in play.",
    "xg": "Expected goals (xG) is the chance a shot becomes a goal, from where and how it was "
          "taken. 0.10 means about one in ten such shots go in.",
    "pass": "Long passes skip lines of opponents but are harder to complete; short ones keep the "
            "ball safely.",
    "shot_speed": "Shot speed is how fast the ball leaves the boot. Over 100 km/h gives a keeper "
                  "little time to react.",
    "build_up": "A long passing move pulls defenders out of shape before the final pass or shot.",
}

# One-line definitions for the stats a viewer can tap (spec 5.1), plus every rule above.
STAT_DEFINITIONS = {
    "shots": "Shots count every attempt at goal; on target means it would have gone in without "
             "the keeper or a last defender.",
    "corners": "How many corners each side has won.",
    "fouls": "How many fouls each side has committed.",
    "cards": "Yellow cards are cautions; a red card, or two yellows, sends a player off.",
    "momentum": "Momentum shows which side has been creating more danger over the last few "
                "minutes.",
    "chaos": "Calm to Chaotic measures how scrappy play is: lots of turnovers and long balls "
             "read as chaotic, long spells of passing as calm.",
    "pass_accuracy": "Pass accuracy is the share of passes that reach a team-mate.",
    "ppda": "Pressure counts the passes a side allows before it wins the ball back; fewer means "
            "a harder press.",
    "field_tilt": "Field tilt is each side's share of the touches in the final third: who is "
                  "pinning whom back.",
    "tempo": "Tempo is how quickly play is moving: events per minute while the ball is in play.",
    "top_performer": "The top performer is the player with the most touches so far.",
}
DEFINITIONS = {**RULES, **STAT_DEFINITIONS}

DEFINITIONS_FR = {
    "foul": "Une faute est une intervention irrégulière, comme un croche-pied, une poussée ou un "
            "tacle en retard. L'adversaire obtient un coup franc à l'endroit de la faute.",
    "advantage": "Si arrêter le jeu pénaliserait l'équipe qui a subi la faute, l'arbitre laisse "
                 "jouer : c'est l'avantage. La faute peut quand même être sanctionnée après.",
    "offside": "Un joueur est hors-jeu si, au moment de la passe d'un coéquipier, il est plus "
               "près du but adverse que le ballon et l'avant-dernier défenseur, dans la moitié "
               "adverse. Être à la même hauteur, c'est être en jeu. L'adversaire obtient un "
               "coup franc.",
    "corner": "Quand l'équipe qui défend touche le ballon en dernier avant qu'il ne franchisse sa "
              "propre ligne de but, l'attaque obtient un corner.",
    "goal_kick": "Quand l'équipe qui attaque touche le ballon en dernier avant qu'il ne sorte "
                 "derrière le but sans but marqué, la défense repart par une sortie de but.",
    "throw_in": "Quand le ballon franchit une ligne de touche, l'équipe qui ne l'a pas touché en "
                "dernier le remet en jeu à deux mains, au-dessus de la tête.",
    "yellow_card": "Le carton jaune est un avertissement pour une faute imprudente, un gain de "
                   "temps ou une contestation. Deux jaunes dans le même match font un rouge.",
    "red_card": "Le carton rouge exclut un joueur jusqu'à la fin du match, et son équipe joue à "
                "un de moins. Il vient d'un second jaune ou d'une faute grave.",
    "free_kick": "Le coup franc fait repartir le jeu après une faute ou un hors-jeu ; les "
                 "adversaires doivent se placer à au moins 9,15 mètres.",
    "substitution": "Chaque équipe peut changer de joueurs pendant les arrêts de jeu. Un joueur "
                    "remplacé ne peut pas revenir.",
    "goal": "Un but compte quand le ballon a entièrement franchi la ligne entre les poteaux et "
            "sous la barre. L'équipe qui encaisse donne le coup d'envoi.",
    "shot_on_target": "Un tir cadré serait entré sans le gardien ou un dernier défenseur. Les "
                      "arrêts et les buts comptent ; les tirs à côté ou contrés, non.",
    "possession": "La possession est la part du temps de jeu effectif où chaque équipe a le "
                  "ballon.",
    "xg": "Les buts attendus (xG) mesurent la chance qu'un tir devienne un but, selon l'endroit "
          "et la façon dont il est pris. 0,10 veut dire environ un tir sur dix au fond.",
    "pass": "Les longues passes éliminent des lignes adverses mais sont plus difficiles à "
            "réussir ; les courtes gardent le ballon en sécurité.",
    "shot_speed": "La vitesse de frappe est la vitesse du ballon au départ du tir. Au-delà de "
                  "100 km/h, le gardien a très peu de temps pour réagir.",
    "build_up": "Une longue action à base de passes déséquilibre la défense avant la dernière "
                "passe ou le tir.",
    "shots": "Les tirs comptent chaque tentative vers le but ; un tir cadré serait entré sans le "
             "gardien ou un dernier défenseur.",
    "corners": "Le nombre de corners obtenus par chaque équipe.",
    "fouls": "Le nombre de fautes commises par chaque équipe.",
    "cards": "Le jaune est un avertissement ; un rouge, ou deux jaunes, exclut le joueur.",
    "momentum": "La dynamique montre quelle équipe se crée le plus de danger depuis quelques "
                "minutes.",
    "chaos": "De Calme à Chaotique mesure à quel point le jeu est décousu : beaucoup de pertes de "
             "balle et de longs ballons, c'est chaotique ; de longues séquences de passes, "
             "c'est calme.",
    "pass_accuracy": "La précision des passes est la part des passes qui arrivent à un "
                     "coéquipier.",
    "ppda": "Le pressing compte les passes qu'une équipe laisse faire avant de récupérer le "
            "ballon ; moins il y en a, plus le pressing est intense.",
    "field_tilt": "L'inclinaison du terrain est la part de chaque équipe dans les ballons "
                  "touchés dans le dernier tiers : qui repousse qui.",
    "tempo": "Le tempo mesure la vitesse du jeu : le nombre d'actions par minute de jeu "
             "effectif.",
    "top_performer": "Le meilleur joueur est celui qui a touché le plus de ballons jusqu'ici.",
}
LANGUAGE_NAMES = {"en": "English", "fr": "French"}


def definition(term: str, language: str = "en") -> str | None:
    """The stored one-line definition of a term, in the viewer's language."""
    if language == "fr" and term in DEFINITIONS_FR:
        return DEFINITIONS_FR[term]
    return DEFINITIONS.get(term)


def language_rule(language: str) -> str:
    """The line every agent prompt gets when the viewer reads another language (spec 5.4)."""
    if language == "en":
        return ""
    name = LANGUAGE_NAMES.get(language, "English")
    return (f"\nWrite directly in {name}, not a translation; numbers in {name} format "
            "(0,15 not 0.15). Keep club and player names exactly as in INPUT.")

TEMPLATE_RULES = {
    "yellow_cards": "yellow_card", "first_booking": "yellow_card", "corners": "corner",
    "first_corner": "corner", "offsides": "offside", "first_offside": "offside",
    "first_foul": "foul", "club_fouls": "foul", "first_free_kick": "free_kick",
    "subs": "substitution", "first_sub_off": "substitution", "goal": "goal",
    "first_goal": "goal", "more_shots": "shot_on_target", "first_shot": "shot_on_target",
    "first_on_target": "shot_on_target", "focus_shot": "shot_on_target",
    "possession": "possession", "first_throw_in": "throw_in", "throw_team": "throw_in",
    "shot_xg": "xg", "shot_speed": "shot_speed", "pass_length": "pass",
    "move_passes": "build_up",
}

TUTOR_PROMPT = """You are a friendly rules tutor for new football fans watching a live match.
In one or two short sentences, explain the call or rule behind the bingo square in INPUT,
using the rule summary and the incident. Plain words, no jargon. Use only facts and numbers
from INPUT. No betting language. Return JSON matching the Explanation schema."""

CONTEXT_PROMPT = """You add tactical context for a knowledgeable football fan. In one or two
short sentences, say what the moment behind the bingo square in INPUT tells us about the
match: how it came about and what it means. Use only facts and numbers from INPUT. No betting
language. Return JSON matching the Explanation schema."""

DEFINITION_PROMPT = """You are a friendly rules tutor for new football fans. In one sentence,
explain the football term in INPUT so a newcomer gets it, using the stored definition. Plain
words, no jargon, no numbers that aren't in INPUT. Return JSON matching the Definition schema,
copying term from INPUT."""

TUTOR = AgentSpec("rules_tutor", "fast", TUTOR_PROMPT, Explanation, budget_s=3.0)
DEFINE = AgentSpec("definitions", "fast", DEFINITION_PROMPT, Definition, budget_s=3.0)
CONTEXT = AgentSpec("narrator_context", "fast", CONTEXT_PROMPT, Explanation, budget_s=3.0)


def rule_for(template: str, answer: str | None) -> str | None:
    """The rule a square is about. Referee and restart squares depend on the answer."""
    if template == "referee":
        return answer if answer in RULES else "foul"
    if template == "restart":
        return answer if answer in RULES else None
    return TEMPLATE_RULES.get(template)


def build_input(square: dict[str, Any]) -> dict[str, Any]:
    """square: question, kind, template, answer (label), answer key, result, clock, events."""
    answer_key = square.get("answer_key") or \
        square.get("answer", "").lower().replace("-", "_").replace(" ", "_")
    rule = rule_for(square["template"], answer_key)
    keys = ("square_id", "question", "kind", "answer", "result", "clock", "half", "events")
    payload: dict[str, Any] = {k: square[k] for k in keys if k in square}
    if rule:
        payload["rule"] = {"call": rule, "summary": RULES[rule]}
    return payload


def check_definition(value: Definition, payload: dict[str, Any], meta: dict[str, Any]
                     ) -> tuple[str | None, list[str]]:
    text = value.text.strip()
    errors = verify_line(text, payload, meta, "normal")
    return (None, errors) if errors else (text, [])


def check(value: Explanation, payload: dict[str, Any], meta: dict[str, Any], mode: str
          ) -> tuple[str | None, list[str]]:
    text = value.text.strip()
    errors = verify_line(text, payload, meta, mode)
    return (None, errors) if errors else (text, [])
