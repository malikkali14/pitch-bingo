# Pitch Bingo — Build Spec

Oct 25, 2026 · @Malik

## 1. Overview

Pitch Bingo is a standalone web viewer that replays a synthetic football match as moving dots, explains each key moment in a running feed, and keeps fans watching with a 5x5 bingo card that rewards attention and speed.

It is an entry to the Microsoft x Premier League "Inside the Game" hackathon. Submissions close on October 27, 2026. It targets the Grand Prize and the Best Multi-Agent Orchestration prize.

**Problem.** Casual and new fans drift during quiet stretches of a match, and they often don't understand calls or tactics. Leagues and broadcasters want longer, more attentive viewing.

**Answer.** A card of questions that can only be answered by watching, short answer windows that reward speed, explanations that teach the game, and two modes: one for newer fans, one for hardcore fans.

### Decisions so far

| Area | Decision |
| --- | --- |
| Format | Standalone web viewer. The pitch view stands in for the match video. |
| Data | One or more synthetic matches between fictional clubs with fictional players. No real names, crests or logos. |
| Card | 5x5. 20 static squares (deadline and first-to-happen) plus 5 blanks that become live squares during the match. No free center. |
| Answer windows | Every window lasts 20 real-world seconds. Faster correct answers earn more points. One guess per square. |
| Deadline squares | Visible from kickoff. The window opens when the deadline passes; the answer is checked against the count at the deadline. |
| First-to-happen squares | Silent: the window opens when the event happens, with no alert. Only viewers who saw it know to answer. |
| Live squares | Exactly 5 per match, generated from notable moments and spread across the match. Same moments for every viewer. |
| Movable blanks | Only blanks can be picked up and moved, by the viewer or the strategist agent. A blank stays movable after it is answered correctly (a wildcard). Static squares never move on their own; a resolved static never moves at all. |
| Modes | Normal mode teaches the game ("what was that call?"). Advanced mode adds xG and tactical stats. |
| Personalization | Favorite club, player focus mode, French as a second language, and a "my metric" setting. |
| Feed | A running feed of moments with the reason they matter. Events tied to an open square are held back and posted after the window closes. |
| Replay | Speed control at 1x, 5x and 10x. The replay never pauses for a window. |
| Points | A leaderboard against simulated fans. Points toward Premier League merch is the roadmap; points have no cash value. |
| Orchestration | Microsoft Agent Framework, with models from Microsoft Foundry, hosted on Azure Container Apps. |

### Glossary

- **Square:** one cell on the card. Every square has a question, an answer type and a rule that checks it against match events.
- **Static square:** placed on the card before kickoff. Two kinds: deadline and first-to-happen.
- **Deadline square:** resolves at a fixed match minute, for example "How many yellow cards by 70'?".
- **First-to-happen square:** resolves when a named event first occurs, for example "Who commits the first foul?".
- **Blank:** one of the 5 empty cells that will hold a live square.
- **Live square:** a question written during the match about a moment that just happened. It fills a blank.
- **Wildcard:** a blank whose live square was answered correctly. It can still be moved.
- **Window:** the 20 seconds in which a square can be answered.
- **Resolved:** a square whose window has closed. It is correct, wrong, missed or void.
- **Line:** any of the 12 rows, columns or diagonals. Five correct squares in a line is a bingo.
- **Hold-back:** keeping a feed entry off screen until a related window closes.
- **Mask:** hiding a stat, a feed entry or a pitch badge while a related window is open.

## 2. Scope and build order

Build in three tiers and stop where time runs out. The must tier alone is a complete entry that covers all five pipeline stages and the Multi-Agent criteria.

### Must

1. Synthetic match generator with every event type the brief lists, match metadata, planted moments and a validation script (section 6).
2. Match engine that replays a match at 1x, 5x or 10x and streams events and player positions (section 9).
3. Stats engine: core stats, pass difficulty, xG, control vs. chaos, pressure, rhythm, momentum (section 7).
4. Pitch view with labelled player dots, pass arrows, event cues and shot speed (section 3).
5. Running feed: narrator agent, verifier, template fallback, hold-back (sections 3 and 8).
6. 5x5 card: both static types, 5 live squares, 20-second windows, masks, speed scoring, line detection (section 4).
7. Movable blanks with wildcards, plus strategist suggestions (section 4).
8. Normal and advanced modes, favorite club, player focus, French as the second language (section 5).
9. Full-time recap.
10. Deployed on Azure Container Apps, public repo with README, tests running in GitHub Actions, demo video.

### Should

1. Player movement model with sprint and distance badges. Fallback if time runs out: show the ball, passer and receiver only, with formation positions faded behind.
2. Rules tutor agent for normal mode.
3. Leaderboard with about 20 simulated fans.
4. Halftime recap and the "what you missed" catch-up recap.
5. Studio tab: lower-third captions, live overlay JSON stream, talking points.
6. Accessibility basics: colorblind-safe colors with shapes, high contrast, screen-reader feed, reduced motion.
7. Failure switch in the dev panel that takes the narrator offline.
8. Tracing of agent handoffs in Application Insights.

### Cut first

1. Strategist auto-move (keep suggest-only and manual).
2. Tapping a feed line to see its evidence (still store the evidence).
3. "My metric" setting, km/h or mph, kickoff in the viewer's time zone.

### Out of scope

Say these are roadmap items in the README: auto-eventing from video, real merch redemption, user accounts, a mobile app, real match data, and many viewers sharing one live match clock.

### Timeline

&#91;embedded content: build timeline · Sunday to Tuesday\]

Phases follow section 14. If the official close time is earlier on Tuesday, move the freeze and submission up and cut from the should tier first.

## 3. Screen and UX

One screen holds the whole match: the pitch on the left with the feed under it, and the metrics, card and leaderboard stacked on the right. Desktop browser first, 1280 px wide minimum, designed at 1440 x 900.

&#91;embedded content: screen layout wireframe\]

The pitch takes about 60% of the width; on the card, blanks start dashed at the corners and center, green squares are correct, red is wrong, and the blue outline is an open window.

### Top bar

- Scoreboard: home club, score, away club, match clock (mm:ss, with "+2" during stoppage time), half indicator.
- Speed control: 1x, 5x, 10x as a segmented button.
- Mode toggle: Normal / Advanced.
- Settings drawer: favorite club, focus player, language, my metric, units, text size, high contrast, reduced motion.
- Studio button: switches to the Studio tab.
- Dev button: opens the dev panel.

### Pitch view

- **Rendering.** SVG, animated with requestAnimationFrame. The client interpolates between position frames from the server. Pitch is 105 x 68 m; the server sends meters, the client scales.
- **Orientation.** x runs 0 to 105, y runs 0 to 68. The home team attacks toward x = 105 in the first half and switches at halftime.
- **Players.** Home players are filled circles, away players are filled rounded squares, so teams differ by shape as well as color. Goalkeepers use a third color. The shirt number sits inside the dot.
- **Name labels.** Surname above the dot for the ball carrier, every player within 15 m of the ball, players in the current event and the focus player. A "show all names" setting labels everyone.
- **Ball.** Small white circle with a dark outline. A shadow offset shows height on lofted balls.
- **Pass arrows.** Every pass draws an arrow from passer to end point that fades over 2 seconds. Solid means completed, dashed means intercepted or out. Passes with difficulty 7.5 or more use the accent color and show a badge, for example "Difficulty 8.2 · 34 m · 61 km/h".
- **Shots.** A line from the shot location toward goal with a speed label, for example "92 km/h". A goal flashes the pitch and updates the scoreboard.
- **Event cues.** Shown at the event location for 2.5 seconds: a whistle for a foul, a flag for offside, a marker at the corner flag for a corner, a swap animation for a substitution. Cards appear as a small badge on the player's dot and stay for the match.
- **Masking.** While a window is open, any cue or badge the open square depends on is hidden (section 4).
- **Speed and distance badges** (should tier). A speed badge appears when a player passes 32 km/h, for example "33.4 km/h". Distance badges appear at 5 km and 10 km for the focus player, and at 10 km for others.
- **Incident replay.** When a normal-mode "what was that call?" square appears, a picture-in-picture inset in the pitch corner replays the last 3 seconds of dot movement in a loop until the window closes. The main pitch keeps playing.
- **Answering by tapping.** When a square asks "who", the viewer can tap a dot on the pitch to answer.

### Running feed

- Sits under the pitch. Newest entry at the top, four entries visible, scrollable history.
- Each entry: match minute, icon, one or two sentences, a moment tag, and a small "AI" label when an agent wrote it. Normal mode lines stay under 140 characters; advanced mode under 220.
- A template line appears at once. The narrator's version replaces it when it arrives (section 8).
- Held-back entries post after their window closes with a "Revealed" tag and the explanation.
- While a window is open, older entries tied to it are collapsed into "Hidden while a square is open".
- The feed region is a polite live region so screen readers announce new entries.

### Metrics panel

- **Normal mode:** possession, shots and shots on target, corners, fouls, cards, a momentum bar, and a "Calm to Chaotic" meter.
- **Advanced mode adds:** xG per team with a small xG timeline, pass accuracy, pressure (passes allowed per defensive action), field tilt, tempo, and the top performer.
- **Focus player card**, when player focus is on: name, number, position, touches, passes completed of attempted, distance, top speed, shots, xG, duels won.
- Any stat an open square depends on shows "Hidden" until the window closes.

### Bingo card

- 5x5 grid under the metrics. The header shows points, correct answers, lines completed and bingos.
- Each square shows its question (60 characters at most), a type icon and its state. Deadline squares also show their minute, for example "at 70'".
- **States:** waiting, open (20-second countdown ring), correct, wrong, too early, missed, void, empty blank, wildcard, and part of a scored line.
- **Answer popover.** Tapping a square opens the input that fits its answer type:
  - Player: tap a dot on the pitch, or pick from a list of the most likely players with search for the rest.
  - Number: a stepper with quick picks 0 to 6.
  - Choice: two to four buttons.
  - Yes or no: two buttons.
- **First-to-happen squares never signal that the event happened.** The popover opens whenever the viewer taps. An answer sent before the event counts as wrong and shows "Too early", so tapping to probe costs a guess.
- **Deadline and live squares do announce their windows**, with a pulse and a short chime.
- **Moving blanks.** Drag an empty blank or a wildcard onto a waiting static square to swap them. Dragging is disabled while any window is open and for squares in a scored line.
- **Strategist strip** under the card. Suggest mode shows a ghost arrow from a blank to its target, a one-line reason and an Apply button. Auto mode animates the move and shows the reason.

### Leaderboard

- Under the card. Top five plus your row: handle, points, correct answers, average answer time.
- Separate boards for normal and advanced mode, with a toggle.
- Simulated fans use made-up handles such as "BlueScarf\_22".

### Pre-match setup

- Choose mode, favorite club (either club or neutral), optional focus player, and language.
- A three-step how-to-play: squares, 20-second windows, moving blanks.
- Then "Kick off".

### Full-time screen

- Final score and the personalized full-time recap.
- The three biggest moments, each with its explanation.
- Your card summary: correct, wrong, missed, lines, bingos, points, rank.
- A line on points toward merch as a future feature.

### Studio tab

- Lower-third captions over the pitch in broadcast style: the current top insight as a title and one line.
- An overlay stream panel showing the raw overlay JSON messages as they are emitted (section 9).
- Talking points: three bullets from the recap agent at halftime and full time, each with a copy button.

### Dev panel

- Latency per agent and per event, LLM calls per minute, the current event rate.
- Failure switch: takes the narrator offline to show the fallback.
- Match seed picker and a jump-to-minute control for demo preparation only. Jumping skips windows.

### Accessibility

- Team colors from a colorblind-safe pair (blue and orange), plus the shape difference above.
- Text contrast at least 4.5:1, and a high-contrast setting.
- Three text sizes.
- Reduced motion turns off trails, flashes and the replay loop, and follows the system setting by default.
- Keyboard: arrow keys move around the card, Enter answers, number keys pick choices.
- Windows that announce themselves are also announced to screen readers. Silent first-to-happen windows are not.

## 4. Game rules

Every square is answered in a 20-second window, scored by speed, and checked by code against the event log. Only blanks and wildcards move, and a scored line freezes.

### 4.1 Card composition

- 25 cells: 20 static squares and 5 blanks. 12 lines: 5 rows, 5 columns, 2 diagonals.
- Static mix: 10 deadline and 10 first-to-happen. The card builder accepts 8 to 12 of each.
- Deadline minutes are spread across the match: no deadline before 10', at least 4 in the first half, at most 2 squares sharing a minute. Default set: 15, 20, 30, 40, 45:00, 55, 60, 70, 80, 90:00.
- First-to-happen squares only use events that happen in nearly every match (list in 4.10).
- Blanks start at the four corners and the center, the cells that sit on the most lines. Statics fill the other 20 cells in a seeded random order.
- 16 or 17 statics are the same for every viewer in a mode. Up to 4 are tailored to the viewer's favorite club or focus player.

### 4.2 Square record

| Field | Meaning |
| --- | --- |
| id | Stable id, for example "sq\_07" |
| kind | deadline, first or live |
| text | Question per language, 60 characters at most |
| answer\_type | player, team, number, choice or yesno |
| options | Choices for choice and team types; in normal mode, numbers become three ranges such as "0–1, 2–3, 4+", set per square from the calibrated count at its deadline so each range is about equally likely |
| deadline\_s | Deadline squares: the display-clock reading the count freezes at, for example 4200 for 70:00. The server converts it to match t using the second half's start, since t includes first-half stoppage time |
| trigger | First-to-happen squares: an event filter, for example type = card and card = yellow |
| resolver | Name of the code function that computes the correct answer from the event log |
| masks | Mask tags hidden while the window is open, for example cards |
| cell | Row and column, 0 to 4 |
| state | See 4.3 |
| answer | Value, wall-clock time and match time of submission |
| result | Status, points, explanation, evidence event ids |
| source\_event\_ids | Live squares: the events the question is about |

### 4.3 Square states

- **waiting:** static square before its window.
- **open:** window running.
- **correct**, **wrong**, **too\_early**, **missed:** final results. Too early counts as wrong.
- **void:** a first-to-happen event that never happened by full time. Counts as correct for lines, earns no points.
- **empty\_blank:** a blank with no live square yet.
- **wildcard:** a live square answered correctly.
- **locked:** any square inside a scored line.

### 4.4 Windows

- Every window lasts 20.0 seconds of real-world time, whatever the replay speed. At 10x, the match moves about 200 seconds during one window.
- **Deadline squares:** the window opens when the match clock reaches the deadline. The correct answer is the count of matching events at or before that second; later events never count. The window is announced.
- **First-to-happen squares:** the window opens the instant the first matching event is emitted. It is silent. An answer sent before the event is "too early".
- **Live squares:** the window opens when the square appears in a blank. It is announced.
- Windows can overlap. A foul that earns a yellow can open "first foul" and "first yellow" together.
- A window that is open at halftime or full time keeps running to its 20 seconds.
- "45:00" means the clock reading before stoppage time. "By halftime" means the half-time whistle. The square text always says which.
- The viewer cannot pause. The dev panel can pause for demo recording, and that freezes open windows too.

### 4.5 Answering and results

- One answer per square. The first submission is final.
- The result shows at once: the correct answer is already fixed when the window opens.
- The explanation posts to the feed when the window closes, so it can't help anyone else answer.
- A window that closes without an answer marks the square missed.

### 4.6 Scoring

Points for a correct answer fall with the seconds t between the window opening and the answer:

```latex
\text{points} = \text{base} \times \max\left(0.3,\ 1 - 0.7 \cdot \frac{\max(0,\ t - 3)}{17}\right)
```

| Event | Points |
| --- | --- |
| Correct static square, base | 100 |
| Correct live square, base | 150 |
| Wrong, too early, missed, void | 0 |
| First line | +500 |
| Each further line | +250 |
| Line made only of live squares ("Blank slate") | +300 on top |
| Full card, all 25 correct or void | +2,000 |

Answers inside 3 seconds earn the full base, and the floor is 30% at 20 seconds. Round to whole points.

### 4.7 Moving blanks and wildcards

- **What can be picked up:** empty blanks and wildcards. Nothing else.
- **A move is a swap.** The picked-up square trades cells with the target cell's square.
- **Allowed targets:** a waiting static square, or another empty blank or wildcard.
- **Blocked targets:** resolved statics (correct, wrong, missed, void), wrong or missed live squares, any open square, any square in a scored line.
- A waiting static displaced by a swap keeps its question and deadline; only its cell changes. The viewer can never pick up a static directly, and a resolved static never moves.
- No moves at all while any announced window (deadline or live) is open. Silent first-to-happen windows never block moves: a first-to-happen square in its silent window still counts as a waiting static for swaps, and its window keeps running. Otherwise a rejected move would reveal the event.
- Moves are unlimited otherwise.
- **A scored line freezes.** All five of its squares become locked, wildcards included, so one wildcard can't hop around completing several lines. A locked wildcard still counts for any other line it sits on.
- **Mistakes can't be moved out.** A wrong square stays put, so a line that holds one can never be completed.
- **Filling blanks.** When a live square is created, it lands in the empty blank the strategist ranks highest, unless the viewer has pinned a different blank as "next".
- **Winning on blanks alone is allowed.** A viewer can line up all five blanks early and needs every live answer right. It earns the Blank slate bonus.

### 4.8 Lines and bingo

- After every result and every move, the scorekeeper checks all 12 lines.
- A line with five correct, void or wildcard squares scores at once, then freezes.
- Play continues after the first bingo. Further lines and the full card keep paying.

### 4.9 Masks and hold-backs

- Each square lists mask tags. While its window is open, everything with those tags is hidden: the matching stats, the card badges on dots, and older feed entries. First-to-happen squares mask their tags from kickoff until their window closes, so a stat going hidden never signals that the event just happened.
- Feed entries created during the window with a masked tag are held back. They post when the window closes, marked "Revealed".

| Tag | Hides |
| --- | --- |
| cards | Card badges on dots, card counts, card feed entries |
| fouls | Foul counts, foul feed entries |
| corners | Corner counts, corner feed entries |
| shots | Shot and on-target counts, xG, shot feed entries |
| offsides | Offside counts, offside feed entries |
| subs | Substitution feed entries, the bench list |
| goals | Scorer names in the feed (the score itself stays visible) |
| possession | Possession and field tilt |

### 4.10 Question bank

The card builder picks statics from these templates. Normal mode uses the team or range variant; advanced mode uses the player or exact-number variant.

| Template | Kind | Normal | Advanced | Masks |
| --- | --- | --- | --- | --- |
| How many yellow cards by {m}? | deadline | range | number | cards |
| How many corners by {m}? | deadline | range | number | corners |
| Which team has more shots by {m}? | deadline | team or level | team or level | shots |
| Will there be a goal by {m}? | deadline | yes or no | yes or no | goals |
| How many offsides by {m}? | deadline | range | number | offsides |
| Who has more possession at {m}? | deadline | team | team | possession |
| How many substitutions by {m}? | deadline | range | number | subs |
| Will {focus player} have a shot by {m}? | deadline | yes or no | yes or no | shots |
| How many fouls by {club} by {m}? | deadline | range | number | fouls |
| Who commits the first foul? | first | team | player | fouls |
| Who wins the first corner? | first | team | team | corners |
| Who takes the first shot? | first | team | player | shots |
| Who has the first shot on target? | first | team | player | shots |
| Who is first caught offside? | first | team | player | offsides |
| Who is booked first? | first | team | player | cards |
| Who is subbed off first? | first | team | player | subs |
| Who scores first? | first | team | player | goals |
| Who wins the first free kick? | first | team | team | fouls |
| Who takes the first throw-in? | first | team | player | none |

### 4.11 Live squares

- Exactly 5 per match, one in each segment: 5–20', 20–38', 38–60', 60–75', 75–88'.
- The producer opens a live square when a moment's unusualness score passes the threshold (section 7). If a segment reaches 85% of its length with none, the next callable event becomes the live square.
- The generator also plants one unusual moment per segment (section 6), so the demo match always produces five good ones.
- A segment whose match file lists a planted moment (summary.json) waits for it, so the demo match's five live squares are its planted moments. Other segments take the first event scoring 60 or more that a live template fits by itself: a shot, a pass of 35 m or more, an advantage, an offside, or a move of 10 or more passes. A score that comes only from a pattern trigger doesn't qualify.
- Every viewer gets the same five moments. The question differs by mode.
- The correct answer is computed by code from the source events. The square writer only writes the wording and the wrong options, and the verifier checks that exactly one option is correct.

| Live template | Mode | Options |
| --- | --- | --- |
| What did the referee just give? | normal | Foul, Offside, Advantage played, No call |
| How does play restart? | normal | Corner, Goal kick, Throw-in |
| Which team gets the throw-in? | normal | the two clubs |
| Estimate the xG of that shot | advanced | under 0.05, 0.05–0.15, 0.15–0.35, over 0.35 |
| How long was that pass? | advanced | under 20 m, 20–35 m, 35–50 m, over 50 m |
| How fast was that shot? | advanced | under 70, 70–90, 90–110, over 110 km/h |
| How many passes in that move? | advanced | 1–3, 4–7, 8–12, 13+ |

Normal-mode referee questions only use calls the dots can show: fouls, offsides, advantage, restarts. Never handball or simulation.

A moment becomes a live square at a call: a foul without advantage, an advantage, an offside, or the ball going out of play. Normal mode asks what the referee gave, how play restarts, or (for a throw-in) which team gets it. Advanced mode asks about the move just before the call: that shot's xG or speed, that pass's length, otherwise how many passes were in the move. Planted moments use the pairs in 6.7.

### 4.12 Strategist

- **Input:** the board, every square's state and deadline, the viewer's accuracy per square kind (starting at 50%, updated after each result), and how many live squares are still to come.
- **Method:** start from the current board, try every single swap and the best pairs of swaps, and simulate 2,000 random endings for each. Each simulation draws an outcome per unresolved square from those accuracies. Pick the arrangement that completes a line most often.
- **Output:** the moves, the win chance before and after, and a one-line reason written by the LLM.
- Only suggest a move that raises the win chance by at least 3 percentage points.
- **Settings:** auto-move (default in normal mode), suggest-only (default in advanced mode), manual.
- It never moves a square in a scored line and never moves during an open window.

## 5. Modes and personalization

The same match intelligence reaches every viewer, then a viewer profile decides how it is worded, what it leads with and which squares appear. Normal mode teaches; advanced mode goes deep.

### 5.1 Normal vs. advanced

| Feature | Normal | Advanced |
| --- | --- | --- |
| Static squares | Team and range answers | Player and exact-number answers |
| Live squares | Referee calls and restarts, with the inset replay | xG, pass length, shot speed, move length |
| After each window | Rules tutor explains the call or rule in one or two lines | Narrator adds the tactical context |
| Feed language | Plain words, no jargon, under 140 characters | Tactical terms allowed, under 220 characters |
| Metrics panel | Possession, shots, corners, fouls, cards, momentum, Calm to Chaotic | Adds xG, pass accuracy, pressure, field tilt, tempo, top performer |
| Definitions | Tap any stat or cue for a one-line explanation | Off by default |
| Strategist | Auto-move | Suggest-only |
| Leaderboard | Normal board | Advanced board |

### 5.2 Favorite club

- Choose either club or neutral.
- The feed leads with your club's angle ("Northbridge's press is working: three turnovers in their half since 60'"). It stays honest about bad news and never mocks the other club.
- Two tailored static squares, for example "How many fouls by Northbridge by 60'?".
- Your club's goals get the bigger celebration animation.
- Recaps include a short "what it means for your club" paragraph.
- Neutral keeps everything balanced.

### 5.3 Player focus mode

- Pick one player from either club, before or during the match.
- Their dot gets an accent ring, a permanent name label and a short trail of the last 5 seconds of movement.
- The focus player card appears in the metrics panel (section 3).
- The feed covers the player whenever they are involved, and adds a line about them at least every 10 match minutes.
- Milestones for the player are always announced (section 7).
- One or two tailored static squares, for example "Will Okafor have a shot by 60'?". These are set before kickoff, so switching focus mid-match doesn't change the card.
- The full-time recap includes a paragraph on the player.

### 5.4 Language

- English plus French.
- Translated: interface text, feed lines, square text, explanations, recaps, strategist reasons, rules tutor answers.
- Not translated: club names, player names, fan handles.
- The personalizer writes directly in the target language rather than translating English afterward.
- Static square text is written for every language when the card is built and then cached.
- Numbers follow the language's format ("0,15 xG" in French). The verifier reads both formats.
- Interface strings live in one JSON file per language.

### 5.5 My metric (cut-first tier)

- The viewer picks one: pressing, possession, xG, pass accuracy, sprints or duels.
- That stat is pinned to the top of the metrics panel, and the feed leads with it whenever it shifts.

### 5.6 Units and time

- Speeds in km/h or mph, distances in meters or yards.
- Kickoff time shown in the viewer's time zone.

### 5.7 Viewer profile

| Field | Values |
| --- | --- |
| mode | normal, advanced |
| club | home club id, away club id, neutral |
| focus\_player\_id | a player id or none |
| language | en or fr |
| my\_metric | pressing, possession, xg, pass\_accuracy, sprints, duels, or none |
| units | metric, imperial |
| strategist | auto, suggest, manual |
| a11y | text\_size (s, m, l), high\_contrast, reduced\_motion, show\_all\_names |

The narrator writes one language-neutral insight per moment. The personalizer renders it once per distinct profile and caches the result by a hash of the profile fields it uses. That keeps one LLM call per profile type rather than per viewer, which is the scaling story for the README.

## 6. Synthetic data

A seeded Python generator produces a full match as metadata, an event log and 10 Hz player tracking, with no LLM involved, so the same seed always gives the same match. It is one of the project's deliverables, not just test data.

### 6.1 Outputs

| File | Contents |
| --- | --- |
| data/matches/{seed}/match.json | Metadata: clubs, players, lineups, referee, venue, weather, kickoff |
| data/matches/{seed}/events.jsonl | One event per line, in time order |
| data/matches/{seed}/tracking.npz | Positions of 22 players and the ball at 10 Hz |
| data/matches/{seed}/summary.json | Match aggregates, used by validation |
| schemas/\*.json | JSON Schema for match, event and overlay messages |
| docs/schema.md | Human-readable schema reference |

Default demo seed: 2610. Ship three more seeds so judges can try other matches.

### 6.2 Match metadata

- **Match:** match\_id, seed, competition ("Synthetic League"), season, matchday, kickoff\_utc.
- **Venue and conditions:** venue name, fictional city, capacity, weather condition, temperature, wind.
- **Referee:** id, name, strictness from 0 to 1, which raises foul and card rates.
- **Each club:** id, name, short name, primary and secondary color, formation (for example 4-3-3), coach name, and style values from 0 to 1 for possession, pressing, tempo and directness.
- **Each player:** id, full name, surname, shirt number, position (GK, RB, CB, LB, DM, CM, AM, RW, LW, ST), preferred foot, age, attributes from 0 to 100 (pace, passing, shooting, defending, discipline), top speed in km/h, and season history (appearances, goals, assists, yellow cards).
- 11 starters and 9 substitutes per club.
- Default clubs: Northbridge Athletic (home) and Kestrel Vale (away). All names are invented. Before recording the video, scan the player list for any name that matches a well-known real player.

### 6.3 Event fields

Every event has these fields:

| Field | Meaning |
| --- | --- |
| event\_id | Unique, for example "e000123" |
| seq | Position in the log, increasing by 1 |
| t | Seconds since kickoff, including stoppage time and the half-time gap removed |
| period | 1 or 2 |
| clock | Display clock, for example "45+2:10" |
| type | One of the types in 6.4 |
| team\_id, player\_id | Who did it, where it applies |
| x, y | Location in meters on a fixed pitch frame, 0–105 by 0–68 |
| possession\_id | Increases by 1 at each change of possession |
| under\_pressure | True when an opponent is within 3 m |
| tags | Mask and moment tags, for example \["fouls"\] |

### 6.4 Event types

| Type | Extra fields |
| --- | --- |
| period\_start, period\_end | stoppage\_added\_s |
| kickoff | none |
| pass | receiver\_id, end\_x, end\_y, length\_m, height (ground, low, high), pass\_type (open\_play, cross, through\_ball, long\_ball, switch, cutback), outcome (complete, incomplete, out, offside), ball\_speed\_kmh, opponents\_bypassed |
| carry | end\_x, end\_y, duration\_s |
| shot | shot\_type (open\_play, header, free\_kick, penalty), body\_part, outcome (goal, saved, off\_target, blocked, post), ball\_speed\_kmh, goal\_y, goal\_z |
| goal | scorer\_id, assist\_id, shot\_event\_id, own\_goal |
| save | keeper\_id, shot\_event\_id |
| tackle | opponent\_id, outcome (won, lost) |
| interception | none |
| clearance, block | none |
| pressure | target\_id, duration\_s, regained\_within\_5s |
| duel | duel\_type (ground, aerial), opponent\_id, outcome |
| foul | fouled\_id, severity from 0 to 1, advantage (true or false) |
| advantage | foul\_event\_id |
| card | card (yellow, second\_yellow, red), foul\_event\_id |
| offside | none (player\_id is the offside player) |
| throw\_in, corner, goal\_kick, free\_kick | side or none |
| out\_of\_play | last\_touch\_team\_id, line (touch or end) |
| substitution | player\_off\_id, player\_on\_id |
| possession\_change | from\_team\_id, to\_team\_id, cause (tackle, interception, out\_of\_play, foul, shot, keeper) |

Coordinates are absolute: x = 0 is always the same end, and the renderer handles teams switching ends at halftime.

### 6.5 Generator algorithm

1. **Setup.** Build clubs, players and style values from the seed.
2. **Possessions.** Simulate each half as a chain of possessions. Each possession starts from a restart or a turnover in a pitch zone: defensive third, middle third, final third or box.
3. **Actions.** At each step, pick the next action for the player on the ball: pass (by type), carry, shot, or losing the ball. Probabilities depend on zone, pressure, and the club's style values.
4. **Defending.** Each step can produce a pressure event, a tackle, an interception, a duel or a foul. Rates rise with the defending club's pressing value.
5. **Fouls and cards.** Foul chance rises with the defender's low discipline and the referee's strictness. Severity drives the card chance. A second yellow becomes a red.
6. **Shots.** Sample a location, compute xG with the same model the stats engine uses (section 7), then sample the outcome from that xG and the shooter's finishing.
7. **Time.** Advance the clock per action: passes 1.5–4 s, carries 1–5 s, fouls 15–40 s of stoppage, throw-ins 10–20 s, corners 20–40 s, goals 45–75 s, substitutions 30–45 s.
8. **Substitutions.** 3 to 5 per club, between 55' and 85'.
9. **Stoppage time.** 1–4 minutes in the first half, 3–7 in the second.
10. **Game state.** A trailing club raises tempo and pressing after 60'; a leading club lowers them. This creates momentum swings for the narrator.
11. **Planted moments.** Insert the scenarios in 6.7.
12. **Possession changes.** Emit a possession\_change event at every change, with its cause.

### 6.6 Movement model

The generator simulates movement after the events, then rewrites each event's x and y to the acting player's tracked position at that moment, so events and tracking never disagree.

1. **Ball.** Moves in a straight line during passes at the pass's ball speed, travels with the carrier during carries, and sits at the restart spot during stoppages.
2. **Target spot per player.** Their formation spot, shifted toward the ball (about 0.5 of the ball's distance from the team's center front to back, 0.35 side to side), compressed when defending, and clamped to the pitch. The back line holds a height set by the club's pressing value.
3. **Players in the action.** The passer is at the pass location at the pass time. The receiver runs to the pass end point. The carrier moves with the ball. The one or two nearest opponents chase the carrier.
4. **Physics.** Each player moves toward their target with a top speed from their attributes (28–35 km/h) and acceleration capped at about 3.5 m/s². Add a little smooth noise so the movement looks natural.
5. **Output.** tracking.npz holds positions at 10 Hz as 16-bit decimeters (about 5 MB per match).

If the movement model isn't ready, the viewer falls back to showing the ball, passer and receiver with faded formation spots (section 2).

### 6.7 Planted moments

One per live-square segment. Each supports both a normal question and an advanced question.

| Segment | Planted moment | Normal question | Advanced question |
| --- | --- | --- | --- |
| 5–20' | Foul with advantage played, then a shot | What did the referee just give? (Advantage) | Estimate the xG of that shot |
| 20–38' | Through ball, receiver just offside | What did the referee just give? (Offside) | How long was that pass? |
| 38–60' | 30 m strike tipped over the bar | How does play restart? (Corner) | How fast was that shot? |
| 60–75' | 13-pass move ending in a blocked shot | How does play restart? | How many passes in that move? |
| 75–88' | 45 m switch, then a shot that goes wide | How does play restart? (Goal kick) | How long was that pass? |

The generator exposes plant(segment, scenario) so other seeds can use different scenarios.

### 6.8 Calibration targets

Approximate per-match ranges for a top-flight-like match, both clubs combined. Check them against public league averages before finalizing.

| Measure | Target range |
| --- | --- |
| Passes | 850–1,050 |
| Pass completion | 78–86% |
| Shots | 20–30 |
| Shots on target | 30–40% of shots |
| Goals | 0–6, mean about 2.8 |
| Total xG | 2.0–3.6 |
| Fouls | 18–26 |
| Yellow cards | 2–6, mean about 4 |
| Red cards | about 1 match in 10 |
| Corners | 8–12 |
| Offsides | 2–6 |
| Throw-ins | 35–50 |
| Substitutions | 6–10 |
| Tackles | 25–40 |
| Interceptions | 15–30 |
| Possession per club | 35–65% |
| Distance per outfield player | 9–12 km |
| Fastest player's top speed | 30–36 km/h |
| Ball in play | 52–60 minutes |

### 6.9 Validation

- validate.py generates 50 seeds and checks that the mean of each measure sits inside its range. It runs as a pytest test.
- It saves a chart of the distributions to docs/validation.png for the README.
- A second test checks that every event's x and y matches the tracked player position within 0.5 m.

### 6.10 Ingest interface

- All match data enters through one EventSource interface with two methods: metadata() and stream(), which yields events and position frames in time order.
- ReplaySource reads a seed's files and emits them at the chosen speed.
- The README says a LiveSource could wrap a real feed or a video auto-eventing model with the same schema, which covers the brief's auto-eventing item as a roadmap.

## 7. Match intelligence

The stats engine is plain code. It turns events and tracking into running stats, the three patterns the brief names (control vs. chaos, pressure, rhythm), momentum, and a significance score that decides what gets narrated. All coefficients below are starting values to tune with the validation script.

### 7.1 Running stats

- **Per club:** possession (share of in-play time on the ball), shots, shots on target, xG, passes attempted and completed, pass accuracy, corners, fouls, cards, offsides, tackles won, interceptions, duels won.
- **Per player:** touches, passes attempted and completed, shots, xG, tackles, duels won, distance, top speed, sprints.
- Stats update on every event and are stored in the shared match state (section 8).

### 7.2 Pass difficulty

A completion model gives the chance p that a pass is completed. Difficulty is 10 × (1 − p), to one decimal. The generator samples pass outcomes from the same model, so difficulty and results stay consistent.

```latex
\operatorname{logit}(p) = 3.2 - 0.045\,L - 0.9\,P - 0.35\,B - 0.6\,T - 0.8\,C - 0.4\,H + 0.25\,R
```

L is length in meters, B is opponents bypassed, P is 1 if under pressure, T is 1 for a through ball, C is 1 for a cross, H is 1 for a high ball, and R is 1 for a backward pass. Tune the constant so average completion lands near 82%.

### 7.3 xG

For a shot d meters from goal, the goal-mouth angle a in radians is atan2(7.32 × dx, dx² + dy² − 13.4), where dx is the distance from the goal line and dy the offset from the center.

```latex
\operatorname{logit}(xG) = -1.2 + 1.6\,a - 0.11\,d - 0.8\,\text{header} + 0.4\,\text{assisted\_chance} - 0.3\,\text{pressure}
```

- assisted\_chance is 1 when the shot follows a through ball or cutback.
- Penalties are fixed at 0.78. Direct free kicks subtract 0.6 from the logit.
- Sanity checks: about 0.47 from 6 m central, 0.20 from 11 m central, 0.03 from 25 m central.

### 7.4 Control vs. chaos

Computed over the last 5 match minutes. Each input is scaled to 0–1 between its 10th and 90th percentile from the validation matches:

- T: possession changes per minute
- D: duels per minute
- C: pass completion
- S: share of possessions with 5 or more passes

```latex
\text{chaos} = 100 \times \left(0.4\,T + 0.25\,D + 0.2\,(1 - C) + 0.15\,(1 - S)\right)
```

- The meter shows chaos from 0 (calm) to 100 (chaotic). The club with the higher share of completed 5-pass sequences is "in control".
- **Narrate when:** chaos crosses 65 or falls below 35, or moves 20 points within 5 minutes.

### 7.5 Pressure

- **PPDA:** opponent passes in their own 60% of the pitch, divided by the pressing club's tackles, interceptions, fouls and duels in that zone. Rolling 10 minutes. Lower means more pressing.
- **Pressing height:** average distance from own goal of a club's defensive actions.
- **Field tilt:** each club's share of passes into the final third, rolling 10 minutes.
- **High regains:** possession won within 40 m of the opponent's goal.
- **Narrate when:** PPDA falls 40% against the previous 10 minutes, field tilt swings 20 points, or a club makes 3 high regains in 5 minutes.

### 7.6 Rhythm

- Events per in-play minute, passes per minute, time since the last stoppage, and share of time the ball is in play, rolling 10 minutes.
- A tempo label of Slow, Steady or Frantic, using the terciles from the validation matches.
- **Narrate when:** the tempo label changes and holds for 3 minutes, or play runs 4 minutes without a stoppage.

### 7.7 Momentum

- Each club builds a threat score that decays with a 3-minute half-life. Points: shot = 10 × xG, box entry = 1, final-third pass = 0.3, corner = 1.5, high regain = 1.
- The momentum bar shows the home club's share of total threat, from −100 to +100.
- **Narrate when:** momentum changes side and holds for 2 minutes, or one club holds more than 70% for 5 minutes.

### 7.8 Speed and distance

- Player speed comes from tracking: frame-to-frame distance at 10 Hz, averaged over 0.5 seconds, times 3.6 for km/h.
- **Sprint:** 25.2 km/h or more for at least 1 second.
- **Speed badge:** 32 km/h or more, at most once per player per 5 match minutes.
- **Distance badges:** at 5 km and 10 km (section 3).
- **Ball speed:** taken from the event's ball\_speed\_kmh. Shown on every shot, and on passes of 30 m or more.

### 7.9 Milestones

From season history and live stats, for example:

- 100th appearance, when the player starts the match on 99.
- First goal of the season, or a round number of goals (10, 25, 50).
- A club's first shot on target after a long wait, for example "first in 38 minutes".
- 50 passes at 90% accuracy or better.
- A keeper's fifth save.
- 10 km covered.

### 7.10 Significance score

Every event gets a score from 0 to 100 that sets its route (section 8).

| Moment | Base score |
| --- | --- |
| Goal | 80 |
| Planted moment | 90 |
| Shot | 30 + 100 × xG, up to 70 |
| Shot at 100 km/h or more | 45 |
| Advantage played | 45 |
| Offside on a through ball | 40 |
| Pass of 40 m or more | 35 |
| Move of 10 or more passes | 40 |
| Card | 35 |
| Keeper acting outside the box | 50 |
| Foul in the final third | 25 |
| Pattern trigger from 7.4 to 7.7 | 50 |
| Milestone | 45 |

Add 10 after 75' and 10 when the score is level or one goal apart.

### 7.11 Routing thresholds

| Score | Route |
| --- | --- |
| 60 or more, and a live template fits | Candidate live square, if its segment still needs one |
| 40 or more | Narrator writes a feed line |
| Under 40 | Template line only, or nothing |

## 8. Agents and orchestration

Six LLM agents and five code components share one match state. A producer routes every event, and nothing that affects a viewer's score waits on an LLM. That split is the answer to the Multi-Agent judges' question of why one agent couldn't do this: the parts run at different speeds and to different standards, and the verifier checks the others' work.

&#91;embedded content: moment workflow · 11 components\]

Model output always passes the verifier before it reaches the screen, and a template line covers any delay or failure.

### 8.1 Roster

| Component | Built with | Runs when | Produces | Time budget | Fallback |
| --- | --- | --- | --- | --- | --- |
| Producer | Agent Framework workflows plus routing rules | Every event | Routing, masks, hold-backs, caption timing | 20 ms | None needed (code) |
| Match engine | Code | Continuously | Events and position frames | Real time | None needed |
| Stats engine | Code | Every event | Stats, patterns, significance | 20 ms | None needed |
| Scorekeeper | Code | Windows, answers, moves | Results, points, lines, leaderboard | 20 ms | None needed |
| Verifier | Code | Every LLM output | Pass, or a list of errors | 10 ms | None needed |
| Narrator | LLM | Significance 40 or more, pattern triggers | Language-neutral insight | 3 s | Template line |
| Personalizer | LLM | Each insight, per profile | Final text in mode, club, language | 2 s | Template rendering |
| Rules tutor | LLM | Normal-mode window closes, definition taps | One or two lines on the rule | 3 s | Stored rule summary |
| Square writer | LLM | Pre-match card build, live-square moments | Square wording and wrong options | 2 s | Template wording |
| Strategist | Code plus LLM | After results and moves | Moves and a one-line reason | 3 s | Template reason |
| Recap | LLM | Halftime, full time, catch-up request | Recaps and studio talking points | 20 s | Template recap from stats |

Budgets were set on Oct 27 from calls to the real Foundry endpoint: the slowest measured call per agent, rounded up, per attempt. gpt-4.1-mini is the only fast model this subscription can run, so speed comes from budgets and prompts, not a model swap. The tutor, narrator context and strategist first measured 6 s or more because the gpt-4.1-mini deployment (capacity 10) was throttling. At capacity 100 they took 1.0–2.3 s at most, so their budgets are 3 s, as are narrator context (the advanced-mode explanation) and definitions.

Simulated fans for the leaderboard are code too: each fan has an accuracy and a typical answer time, and answers every window through the scorekeeper.

### 8.2 Models

- Real-time agents (narrator, personalizer, square writer, strategist) and the rules tutor: gpt-4.1-mini (decided). Measured from the dev machine on Oct 25: 1.6, 1.7 and 2.2 seconds per call, against 3.1 to 7.0 seconds for gpt-5-mini. The 20-second answer windows and live feed need the faster one.
- Recap: gpt-5-mini, where quality matters more than speed. The rules tutor moved to gpt-4.1-mini on Oct 27: it rephrases a stored rule summary, so it needs no reasoning, and against the real endpoint it took about 1.1–3 s on gpt-4.1-mini against about 12.5 s on gpt-5-mini. gpt-4.1-nano and gpt-4o-mini have no quota on this subscription, Mistral and Llama models can't be bought on a free subscription, and Phi-4-mini ignores the JSON schema.
- One Foundry project, one or two model deployments. Section 11 has the commands.

### 8.3 Shared match state

- One MatchSession per viewer, owned by a single asyncio task. Nothing else writes to it, which avoids race conditions.
- It holds: clock and score, the event log, stats and patterns, the card and open windows, active masks, the hold-back queue, feed entries, the insight cache, the viewer profile, the leaderboard, live-square segment status, and agent health.
- Agents get a read-only snapshot of what they need and return typed messages. The session applies them.
- Points, profiles and leaderboard rows are also saved to Cosmos DB (section 9).

### 8.4 Workflows

Each is an Agent Framework workflow: typed executors joined by edges, with agents wrapped as executors.

1. **Moment workflow** (significance 40 or more): Router → Narrator → Verifier → Personalizer → Publisher. If the moment is a live-square candidate, the router also sends it down a second branch: Square writer → Verifier → Publisher.
2. **Window-close workflow:** Scorekeeper result → Rules tutor (normal) or Narrator (advanced) → Verifier → Personalizer → Publisher, which also releases held-back entries.
3. **Strategy workflow:** Optimizer (code) → Strategist reason → Publisher.
4. **Recap workflow:** State summary (code) → Recap agent → Verifier → Personalizer → Publisher.

The Publisher is a code executor that writes to the session and pushes WebSocket messages (section 9).

As built: each agent step runs its own call, verifier check and one retry with the error list, then a Verifier executor re-checks the final text as the last gate before the Publisher. In the window-close workflow the personalizer leads the explanation with the viewer's club or focus player, and neutral viewers pass straight through; in the recap workflow it passes through in English, since the recap agent already writes the club and player paragraphs, and renders other languages in phase 7. A live square is placed and masked at once, and its window opens when the square writer's wording arrives, within its 2-second budget, or with the template wording.

### 8.5 Messages between steps

| Message | Key fields |
| --- | --- |
| Moment | moment\_id, event\_ids, type, significance, stats snapshot, pattern triggers, game state |
| Insight | moment\_id, headline facts, why facts, tags, evidence\_ids, numbers (key and value pairs) |
| RenderedLine | moment\_id, profile\_hash, language, text, ai\_written |
| LiveSquareDraft | template\_id, text per mode, options, correct\_option (from code), source\_event\_ids |
| Explanation | square\_id, text, evidence\_ids |
| StrategyAdvice | moves, win chance before and after, reason |
| Recap | kind (halftime, full\_time, catch\_up, bingo), sections, talking\_points, evidence\_ids |

All are pydantic models. LLM agents must return JSON that validates against them.

### 8.6 Agent contracts

**Narrator.** Input: a Moment. Output: an Insight. Rules: use only facts and numbers present in the input; say why the moment matters, not only what happened; name at most two players; no betting language; neutral tone, since the personalizer adds the club angle.

**Personalizer.** Input: an Insight and a profile. Output: one RenderedLine. Rules: write directly in the profile's language; normal mode uses plain words under 140 characters, advanced mode may use tactical terms under 220; lead with the favorite club, focus player or my metric when the insight involves them; never add a number that isn't in the insight.

**Rules tutor.** Input: the call type, a short incident description and the stored rule summary. Output: one or two sentences a new fan understands. The rule summaries are written in your own words for the 15 or so calls the dots can show, and sit in the prompt.

**Square writer.** Pre-match input: the template bank, the profile and the card plan from the card builder. Output: square text in every language. In-match input: a moment, a live template and the correct answer computed by code. Output: question text and wrong options. It never chooses the correct answer.

**Strategist.** Input: the optimizer's chosen moves and the board. Output: one reason under 120 characters, for example "Moved a blank into row 3: you have 3 correct there and its last square resolves at 85'."

**Recap.** Input: a state summary built by code: score, goals, top moments with their insights, pattern shifts, player highlights, and the viewer's card results. Output: a headline, three to five short paragraphs, three talking points, a paragraph for the favorite club and the focus player when set, and a bingo summary.

### 8.7 Verifier

- Every number in AI text must match a number in that agent's input: counts exactly, xG to 0.01, percentages to 1 point, speeds to 0.5 km/h, distances to 0.5 m, minutes exactly. It reads both "0.15" and "0,15".
- Every player and club name must appear in the match metadata and in the agent's input.
- Length limits by mode, and a blocklist of betting words (odds, bet, wager, stake).
- For a live square: options are unique, exactly one equals the computed answer, and the answer type matches the template.
- On failure, the step retries once with the error list added to the prompt. A second failure uses the template.
- Every failure is logged as a metric, and the dev panel shows the count.

### 8.8 Failure recovery

- Every LLM call has a timeout equal to its time budget.
- The template line or rendering always posts first. The AI version replaces it in place when it arrives.
- Circuit breaker: three failures in 60 seconds sends that agent's work to its fallback for 60 seconds, then one trial call checks whether it has recovered.
- The dev panel's failure switch forces the narrator's breaker open, so the demo can show the feed carrying on.
- Windows, scoring, masks and line checks are code, so they never stop.

### 8.9 Latency targets

| Step | Target |
| --- | --- |
| Event to pitch | under 200 ms |
| Event to template feed line | under 300 ms |
| Event to AI feed line | under 2.5 s |
| Moment to live square on the card | under 2 s |
| Window close to explanation | under 3 s |
| Recap ready | under 20 s |

At 10x speed the demo match produces roughly 10 to 20 LLM calls per real minute. Keep prompts short, send only the snapshot fields each agent needs, and cache personalizer output by profile hash.

### 8.10 Prompt skeletons

```text
NARRATOR
You explain football moments for a live match viewer.
Use ONLY the facts and numbers in INPUT. Never invent a number or a name.
Return JSON matching the Insight schema.
headline_facts: what happened. why_facts: why it matters right now,
using the pattern data (control vs. chaos, pressure, rhythm, momentum).
No betting language. Neutral tone.
INPUT: {moment_json}
```

```text
SQUARE WRITER (live)
Write one multiple-choice question about the moment in INPUT
for {mode} mode in {language}, using template {template_id}.
The correct answer is {correct_option}. Do not change it.
Write {n} wrong options from the template's option set.
Question under 60 characters. Return JSON matching LiveSquareDraft.
INPUT: {moment_json}
```

## 9. System architecture

One container on Azure Container Apps runs a Python FastAPI backend that also serves the built React frontend. Each viewer gets an in-memory match session streamed over one WebSocket; Foundry hosts the models, Cosmos DB keeps points and profiles, and Application Insights collects traces.

&#91;embedded content: system architecture · one container, three Azure services\]

Everything a viewer touches runs in one container; Foundry, Cosmos DB and Application Insights are reached over managed identity.

### 9.1 Stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12, FastAPI, uvicorn, pydantic, numpy |
| Agents | Microsoft Agent Framework (agent-framework-foundry), azure-identity |
| Frontend | React, TypeScript, Vite; the pitch is SVG |
| Real time | WebSocket from FastAPI (Container Apps ingress supports WebSocket) |
| Storage | Azure Cosmos DB for NoSQL, free tier; an in-memory store for local runs |
| Telemetry | azure-monitor-opentelemetry plus Agent Framework instrumentation |
| Deploy | Dockerfile, Azure Developer CLI (azd), Bicep |

### 9.2 Clocks

- Match time t = t0 + (now − wall0) × speed. A speed change re-anchors t0 and wall0.
- Windows run on wall-clock time on the server. The server's receipt time of an answer is what counts.
- Dev pause freezes both clocks.

### 9.3 Session lifecycle

1. The browser sends POST /api/sessions with a seed and a profile.
2. The server loads the match files, builds the card (square writer, cached per profile), and starts a MatchSession task.
3. The browser opens the WebSocket and receives session.ready.
4. The session streams frames, events, stats, feed lines and card updates until full time, then the recap.
5. Results are saved to Cosmos DB. Sessions with no socket for 10 minutes are closed.

### 9.4 WebSocket messages

Every message is JSON with type, t (match seconds) and wall (server time in ms).

**Server to browser**

| type | Payload |
| --- | --- |
| session.ready | session\_id, match metadata, profile, card |
| frame | ball \[x, y, z\], players \[\[id, x, y\], …\]; 10 per second |
| event | the raw event, for pitch cues |
| stats | club and player stats, patterns; once a second or on change |
| feed.add | entry\_id, minute, text, tag, ai (false for template lines) |
| feed.replace | entry\_id, text, ai true |
| feed.reveal | entry\_ids released after a window |
| mask.on, mask.off | square\_id, tags |
| square.window\_open | square\_id, closes\_at; deadline and live squares only |
| square.added | a live square placed in a blank |
| square.result | square\_id, status, points, correct\_answer |
| square.explanation | square\_id, text |
| board.update | cells, scored lines, points |
| strategy.advice | advice\_id, moves, chance before and after, reason |
| leaderboard | rows for the viewer's mode |
| overlay | one overlay message (9.5) |
| recap | kind, content |
| definition | term, text, ai: a one-line explanation of a tapped stat or call (5.1), stored text first, then the rules tutor's |
| health | agent status, breaker state, latency |

**Browser to server**

| type | Payload |
| --- | --- |
| profile.set | profile fields |
| replay.speed | 1, 5 or 10 |
| answer.submit | square\_id, value |
| board.move | from\_cell, to\_cell |
| strategy.apply | advice\_id |
| recap.request | kind catch\_up |
| definition.request | term (a stat or call, for example possession or offside) |
| dev.narrator\_down | on or off |
| dev.pause | on or off |
| dev.jump | t |

The server never sends anything when a first-to-happen window opens. It decides too\_early, correct or missed when the answer arrives.

### 9.5 Overlay message schema

Every caption and badge is also emitted in this shape, so a broadcast graphics system could render it. The Studio tab shows the stream, and GET /api/sessions/{id}/overlays.jsonl exports it.

```json
{
  "schema": "pitchbingo.overlay/1",
  "overlay_id": "ov_000123",
  "match_id": "m_2610",
  "kind": "lower_third",
  "priority": 2,
  "t_start": 2715.4,
  "duration_s": 6.0,
  "anchor": { "type": "screen", "slot": "lower_left" },
  "content": {
    "title": "Northbridge turn the screw",
    "body": "Three high regains in five minutes. Kestrel Vale can't get out.",
    "value": null,
    "unit": null
  },
  "language": "en",
  "profile_hash": "a91f…",
  "evidence_event_ids": ["e000811", "e000823", "e000840"],
  "ai_generated": true
}
```

- kind: lower\_third, stat\_badge, player\_tag, speed\_badge, pass\_badge, momentum, recap\_card.
- anchor type: screen (a slot), player (a player\_id) or pitch (x, y).
- The producer shows one lower third at a time. A higher priority replaces a lower one.

### 9.6 HTTP endpoints

| Method and path | Purpose |
| --- | --- |
| GET /api/health | Liveness, plus whether Foundry and Cosmos are reachable |
| GET /api/matches | Available seeds |
| POST /api/sessions | Start a session; returns session\_id |
| GET /api/sessions/{id}/state | Debug snapshot |
| GET /api/sessions/{id}/overlays.jsonl | Overlay export |
| GET /api/leaderboard?mode= | Leaderboard rows |
| WS /ws/sessions/{id} | The session stream |
| GET / | The frontend |

### 9.7 Storage

Cosmos DB for NoSQL, database pitchbingo:

| Container | Partition key | Holds |
| --- | --- | --- |
| profiles | /profile\_id | Profile and lifetime points |
| sessions | /session\_id | Card, results, points, final summary |
| leaderboard | /match\_id | One row per real session |

Simulated fans live in memory only. Set STORAGE=memory to run without Azure.

### 9.8 Scaling notes

- Sessions live in memory, so the demo runs with exactly one replica (minimum 1, maximum 1). That also avoids cold starts.
- The production path, for the README: one shared live clock per real match broadcast to all viewers through Azure Web PubSub, session state in a shared store, and a LiveSource fed by Azure Event Hubs.

### 9.9 Repository layout

```text
pitch-bingo/
  README.md
  azure.yaml                 # azd project file
  infra/                     # Bicep: Container Apps, Cosmos DB, monitoring, roles
  Dockerfile                 # builds frontend, then runs the backend
  .env.example
  .github/workflows/
    ci.yml                   # tests and lint on every push
    azure-dev.yml            # deploy, created by azd pipeline config
  backend/
    pyproject.toml
    app/
      main.py                # FastAPI app, routes, WebSocket, static files
      config.py
      session.py             # MatchSession task and clocks
      engine/                # EventSource, ReplaySource
      generator/             # synthetic match generator and validate.py
      stats/                 # core stats, xg, passes, patterns, significance
      game/                  # card builder, question bank, scorekeeper, masks, strategist, fans
      agents/                # clients, each agent, workflows, prompts, templates
      verify/                # verifier
      store/                 # cosmos and memory stores
      telemetry.py
      models.py              # pydantic messages
    tests/
  frontend/
    src/                     # App, ws client, Pitch, Feed, Metrics, Card,
                             # Leaderboard, Studio, DevPanel, Setup, FullTime
    src/i18n/                # en.json and fr.json
  data/matches/{seed}/
  schemas/
  docs/                      # schema.md, architecture image, validation chart
```

## 10. How the Microsoft products fit

Microsoft Foundry supplies the models and guardrails, Microsoft Agent Framework runs the agents and workflows, and Azure hosts, stores, secures and traces everything. Every Azure call uses a managed identity, so the public repo holds no keys.

| Product | What it does in Pitch Bingo | Pipeline stage |
| --- | --- | --- |
| [Microsoft Foundry](https://learn.microsoft.com/en-ca/azure/foundry/tutorials/quickstart-create-foundry-resources) | Project and model deployments for all six LLM agents; default guardrails on every deployment; trace viewer once connected to Application Insights | Explain, personalize |
| [Microsoft Agent Framework](https://pypi.org/project/agent-framework/1.8.0/) | The six agents, the four workflows (typed executors and edges), and OpenTelemetry instrumentation | Explain, personalize, orchestration |
| [Azure Container Apps](https://learn.microsoft.com/azure/container-apps/ingress-overview) | Hosts the one container; HTTPS ingress with WebSocket support; managed identity; fixed at one replica | Ingest, interpret, render |
| Azure Container Registry | Stores the image; created for you by azd | Deployment |
| [Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/free-tier) | Profiles, session results, leaderboard; free tier | Personalize |
| Application Insights and Log Analytics | Agent spans, producer spans, latency and verifier metrics, live metrics | All stages |
| Microsoft Entra managed identity and Azure RBAC | Keyless access from the app to Foundry and Cosmos DB | All stages |
| [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/azd-init-workflow) and Bicep | Infrastructure as code, one-command deploy, GitHub Actions setup | Deployment |
| GitHub and GitHub Actions | Public repo, tests on every push, deploy pipeline | Deployment |
| GitHub Copilot | Use it while building and say so in the README; the Multi-Agent prize names it | Development |

### 10.1 Microsoft Foundry

- One Foundry resource with one project. The project endpoint looks like https://{resource}.services.ai.azure.com/api/projects/{project}.
- Deployments: gpt-4.1-mini for the real-time agents and the rules tutor, and gpt-5-mini for recaps (section 8.2).
- **Guardrails.** New deployments get Microsoft's default guardrail, which uses Azure AI Content Safety classifiers on prompts and outputs. Keep it on and say so in the README. It sits beside the verifier: guardrails catch harmful content, the verifier catches wrong numbers and names.
- **Tracing.** Connect the project to the same Application Insights resource as the app, and the agent spans appear in Foundry's trace view.
- The roles were recently renamed. The app's identity needs **Foundry User** (formerly Azure AI User) on the project.

### 10.2 Microsoft Agent Framework

- Install agent-framework-foundry. Released packages no longer need the --pre flag; the latest release on PyPI is 1.23.0 from October 22, 2026, so pin the version you test with.
- Create a FoundryChatClient with the project endpoint, the deployment name and a credential, then call as\_agent(...) for each agent, or build Agent(client=…, name=…, instructions=…).
- Build each workflow with WorkflowBuilder: code steps are Executor subclasses with @handler methods; agents can be passed straight in and are wrapped as executors; add\_edge joins them; build() returns the workflow.
- Agents, chat calls and tool calls emit OpenTelemetry spans named invoke\_agent, chat and execute\_tool. Wrap each producer decision in a custom span with get\_tracer() so one event can be followed end to end.

```python
import os
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential

credential = DefaultAzureCredential()  # managed identity in Azure, az login locally
fast = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["FOUNDRY_MODEL_FAST"],
    credential=credential,
)
narrator = Agent(client=fast, name="narrator", instructions=NARRATOR_PROMPT)
insight_json = await narrator.run(moment.model_dump_json())
```

Treat the snippet as the shape of the code; check the current Agent Framework samples for exact signatures before building on it.

### 10.3 Azure Container Apps

- One container app with external HTTP ingress on port 8000. WebSocket works over the same ingress.
- Minimum and maximum replicas both 1, since sessions are in memory.
- A system-assigned managed identity, granted the Foundry and Cosmos DB roles in section 11.
- Environment variables from section 11.5.

### 10.4 Azure Cosmos DB

- One account with free tier enabled. Free tier gives the first 1000 RU/s and 25 GB at no charge, allows one free-tier account per subscription, and must be chosen when the account is created.
- One database with shared throughput of 400 RU/s, and the three containers in section 9.7.
- The app authenticates with its managed identity through the Cosmos DB data-plane role, so no connection key is stored anywhere.

### 10.5 Application Insights

- One Application Insights resource with a Log Analytics workspace, created by the azd infrastructure.
- The app calls configure\_azure\_monitor from azure-monitor-opentelemetry (1.8.10 or later), then Agent Framework's enable\_instrumentation().
- Leave sensitive-data capture off in Azure, since it records prompts and responses. Turn it on only locally.
- Custom metrics to record: latency per agent, verifier failures, breaker trips, LLM calls per minute.

### 10.6 Roadmap services to name in the README

- Azure Web PubSub to broadcast one live match clock to many viewers.
- Azure Event Hubs to ingest a real event feed or the output of a video auto-eventing model.
- Azure Functions for post-match jobs such as leaderboard rollups and emailed recaps.
- The A2A protocol to expose the rules tutor to other apps as an agent.

### 10.7 Cost

- A new Azure free account includes $200 of credit for the first 30 days, which should comfortably cover the hackathon.
- Cosmos DB stays inside its free tier at this scale.
- Set a budget alert on the subscription on day one.

## 11. Setup guide

Create the Foundry project and model first, since quota or region problems are the most likely early blocker. Then run everything locally, deploy with one az containerapp up command, and move to azd and Bicep once the app works.

### 11.1 Accounts and tools

- An Azure subscription. A new free account includes $200 of credit for 30 days. Also check whether the hackathon offers credits.
- A GitHub account for the public repo.
- Azure CLI 2.80.0 or later; the Foundry project commands fail on older versions. Check with az version.
- Azure Developer CLI (azd), Python 3.12, Node 20 or later, Git, and Docker Desktop.
- VS Code with GitHub Copilot, optional.

```bash
az login
azd auth login
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.CognitiveServices
az provider register --namespace Microsoft.DocumentDB
```

### 11.2 Foundry project and models

Names with -xyz must be globally unique; replace xyz with something of your own.

```bash
RG=pitchbingo-rg
LOC=eastus
FOUNDRY=pitchbingo-foundry-xyz
PROJECT=pitchbingo

az group create --name $RG --location $LOC

az cognitiveservices account create \
  --name $FOUNDRY --resource-group $RG \
  --kind AIServices --sku S0 --location $LOC \
  --custom-domain $FOUNDRY \
  --assign-identity --allow-project-management true

az cognitiveservices account project create \
  --name $FOUNDRY --resource-group $RG \
  --project-name $PROJECT --location $LOC

# See which versions and SKUs your region offers
az cognitiveservices model list --location $LOC \
  --query "[?model.name=='gpt-5-mini'].{version:model.version,skus:join(',',model.skus[].name)}" \
  --output table

az cognitiveservices account deployment create \
  --name $FOUNDRY --resource-group $RG \
  --deployment-name gpt-5-mini --model-name gpt-5-mini \
  --model-version "2025-08-07" --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 10

# Project endpoint for your .env
az cognitiveservices account project show \
  --name $FOUNDRY --resource-group $RG --project-name $PROJECT \
  --query 'properties.endpoints."AI Foundry API"' --output tsv
```

- Repeat the deployment command for a fast non-reasoning mini model if the model list shows one in your region (section 8.2).
- Microsoft's quickstart uses a capacity of 10. If the 10x replay hits rate limits, raise it as far as your quota allows, or test at 5x.
- Give your own account the Foundry User role on the project so you can call it locally. The role ID is used because the role names were recently changed:

```bash
PROJECT_ID=$(az cognitiveservices account project show \
  --name $FOUNDRY --resource-group $RG --project-name $PROJECT --query id -o tsv)
ME=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" \
  --assignee-object-id $ME --assignee-principal-type User --scope $PROJECT_ID
```

The portal route works too: create the project at ai.azure.com, deploy the model from the model catalog, and copy the endpoint from the project overview.

### 11.3 Cosmos DB

```bash
COSMOS=pitchbingo-cosmos-xyz

az cosmosdb create --name $COSMOS --resource-group $RG \
  --locations regionName=$LOC --enable-free-tier true \
  --default-consistency-level Session

az cosmosdb sql database create --account-name $COSMOS --resource-group $RG \
  --name pitchbingo --throughput 400

for c in "profiles /profile_id" "sessions /session_id" "leaderboard /match_id"; do
  set -- $c
  az cosmosdb sql container create --account-name $COSMOS --resource-group $RG \
    --database-name pitchbingo --name $1 --partition-key-path $2
done

# Data-plane access for yourself (Built-in Data Contributor)
az cosmosdb sql role assignment create --account-name $COSMOS --resource-group $RG \
  --scope "/" --principal-id $ME \
  --role-definition-id 00000000-0000-0000-0000-000000000002
```

Skip this section on day one by running with STORAGE=memory.

### 11.4 Run locally

```bash
git clone https://github.com/<you>/pitch-bingo && cd pitch-bingo
python -m venv .venv && source .venv/bin/activate
pip install -e "backend[dev]"

python -m app.generator --seed 2610 --out data/matches
python -m app.generator.validate --seeds 50

cp .env.example .env        # fill in the values from 11.5
uvicorn app.main:app --reload --port 8000

# second terminal
cd frontend && npm install && npm run dev
```

- Backend dependencies: fastapi, uvicorn\[standard\], pydantic, numpy, agent-framework-foundry, azure-identity, azure-cosmos, azure-monitor-opentelemetry (1.8.10 or later, below 2), python-dotenv. Dev: pytest, pytest-asyncio, ruff, mypy.
- Agent Framework does not load .env files by itself, so call load\_dotenv() at startup.
- DefaultAzureCredential uses your az login session locally and the managed identity in Azure, so the same code runs in both places.
- Vite proxies /api and /ws to port 8000.
- To see traces locally, run the Aspire Dashboard and set OTEL\_EXPORTER\_OTLP\_ENDPOINT=http://localhost:4317:

```bash
docker run --rm -it -d -p 18888:18888 -p 4317:18889 \
  --name aspire-dashboard mcr.microsoft.com/dotnet/aspire-dashboard:latest
```

The dashboard UI is then at http://localhost:18888.

### 11.5 Environment variables

| Name | Example | Notes |
| --- | --- | --- |
| FOUNDRY\_PROJECT\_ENDPOINT | https://pitchbingo-foundry-xyz.services.ai.azure.com/api/projects/pitchbingo | From 11.2 |
| FOUNDRY\_MODEL\_FAST | gpt-4.1-mini | Deployment name for real-time agents |
| FOUNDRY\_MODEL\_QUALITY | gpt-5-mini | Recap |
| STORAGE | memory or cosmos |  |
| COSMOS\_ENDPOINT | https://pitchbingo-cosmos-xyz.documents.azure.com:443/ | When STORAGE is cosmos |
| COSMOS\_DATABASE | pitchbingo |  |
| APPLICATIONINSIGHTS\_CONNECTION\_STRING | InstrumentationKey=… | In Azure only |
| ENABLE\_INSTRUMENTATION | true | Agent Framework telemetry |
| ENABLE\_SENSITIVE\_DATA | false | true only on your machine |
| OTEL\_SERVICE\_NAME | pitch-bingo |  |
| DEFAULT\_SEED | 2610 |  |
| LANGUAGES | en,fr |  |
| DEV\_PANEL | true | Hide it for public visitors if you prefer |

None of these are secrets, so .env.example can show them all with placeholder values. Keep .env itself out of Git.

### 11.6 Dockerfile

```dockerfile
# The frontend builds natively: its output is static files, and esbuild crashes under
# amd64 emulation on Apple-silicon Macs. Only the Python stage needs the target platform.
FROM --platform=$BUILDPLATFORM node:20-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend
COPY data/ ./data/
COPY schemas/ ./schemas/
COPY --from=web /web/dist ./backend/app/static
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 11.7 Deploy: fastest path

az containerapp up builds the image from the Dockerfile and creates the environment, registry and app in one command.

```bash
APP=pitchbingo

az containerapp up --name $APP --resource-group $RG --location $LOC \
  --source . --ingress external --target-port 8000

az containerapp identity assign --name $APP --resource-group $RG --system-assigned
APP_ID=$(az containerapp show --name $APP --resource-group $RG \
  --query identity.principalId -o tsv)

# Foundry User on the project, and Cosmos DB data access, for the app
az role assignment create --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" \
  --assignee-object-id $APP_ID --assignee-principal-type ServicePrincipal --scope $PROJECT_ID
az cosmosdb sql role assignment create --account-name $COSMOS --resource-group $RG \
  --scope "/" --principal-id $APP_ID \
  --role-definition-id 00000000-0000-0000-0000-000000000002

# Application Insights (workspace-based, so it needs a Log Analytics workspace)
az extension add --name application-insights
az monitor log-analytics workspace create --resource-group $RG \
  --workspace-name pitchbingo-logs --location $LOC
az monitor app-insights component create --app pitchbingo-ai \
  --location $LOC --resource-group $RG --workspace pitchbingo-logs
AI_CONN=$(az monitor app-insights component show --app pitchbingo-ai \
  --resource-group $RG --query connectionString -o tsv)

az containerapp update --name $APP --resource-group $RG \
  --min-replicas 1 --max-replicas 1 \
  --set-env-vars FOUNDRY_PROJECT_ENDPOINT=<endpoint> FOUNDRY_MODEL_FAST=<name> \
    FOUNDRY_MODEL_QUALITY=gpt-5-mini STORAGE=cosmos \
    COSMOS_ENDPOINT=https://$COSMOS.documents.azure.com:443/ COSMOS_DATABASE=pitchbingo \
    APPLICATIONINSIGHTS_CONNECTION_STRING="$AI_CONN" ENABLE_INSTRUMENTATION=true \
    OTEL_SERVICE_NAME=pitch-bingo
```

Then, in the Foundry portal, connect the project to the pitchbingo-ai Application Insights resource so agent traces show in Foundry as well. Role assignments can take a few minutes to apply.

To redeploy after code changes, run the same az containerapp up command again.

### 11.8 Deploy: infrastructure as code (should tier)

This is what the production-readiness criterion rewards. Do it once the app works.

1. Run azd init and choose "Use code in the current directory". azd scans the app and generates azure.yaml and Bicep files for Azure Container Apps.
2. Add Bicep modules for the Cosmos DB account, database and containers, Application Insights, and the two role assignments from 11.7. Pass the Foundry endpoint in as a parameter, since the Foundry resource already exists.
3. Run azd up to provision and deploy.
4. Run azd pipeline config to create the GitHub Actions deploy workflow and its Azure credentials.

### 11.9 CI

.github/workflows/ci.yml runs on every push:

1. Set up Python 3.12, install backend with dev extras.
2. ruff check, mypy, then pytest (tests in section 12; none of them call Azure).
3. Set up Node 20, npm ci, npm run build, and the frontend tests.

### 11.10 Smoke test after deploy

1. Open the app URL; the setup screen loads.
2. GET /api/health reports Foundry and Cosmos DB as reachable.
3. Start a match at 10x. AI feed lines replace template lines within about 2 seconds.
4. Answer a deadline square and a live square, and move a wildcard.
5. In Application Insights, transaction search shows invoke\_agent and chat spans under one producer span.
6. The full-time recap appears, and the session row appears in Cosmos DB.

### 11.11 Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| 'project' is misspelled or not recognized | Azure CLI older than 2.80.0; run az upgrade |
| CustomDomainInUse | The Foundry name is taken; pick another |
| DeploymentModelNotSupported | That model, version or SKU isn't offered in the region; use the model list output |
| 401 or 403 from Foundry | Foundry User role missing, or not applied yet; wait a few minutes |
| 429 from Foundry | Rate limit; raise capacity, shorten prompts or replay at 5x |
| 403 from Cosmos DB | Data-plane role missing for that identity |
| WebSocket drops or sessions vanish | More than one replica, or the app scaled to zero; set min and max replicas to 1 |
| Feed shows only template lines | Narrator breaker open; check the dev panel and Application Insights for errors |

### 11.12 Team and repository

Two people build this, so the shared pieces are fixed here.

- Repository: public GitHub repo named pitch-bingo (the hackathon requires it public), MIT license, with a README, a Python-and-Node .gitignore that also excludes .env and azure-names.sh, and an .env.example. The spec lives at docs/SPEC.md, and the standing agent instructions (section 14.1) are copied to CLAUDE.md and .github/copilot-instructions.md.
- Azure: one subscription and one resource group (pitchbingo-rg, eastus), one Foundry resource and project, and two deployments, gpt-4.1-mini and gpt-5-mini. The teammate is invited as a guest in the owner's directory and holds the Foundry User role on the project.
- Names: the resource names are not secrets but they stay out of git in a local azure-names.sh. The owner sends the file to the teammate, who saves it in their home folder.
- Sign-in: both people run az login against the owner's tenant ID, not the Microsoft corporate directory. Nobody puts keys in the repo; the app signs in with the Azure identity.
- Tools on each machine: Python 3.12 (the project uses python3.12 -m venv), Node, Docker-compatible runtime (Rancher Desktop works), az, azd and gh.
- Split: one person owns backend and agents, the other owns frontend, Azure deployment and the demo video. Work on short branches and merge to main by pull request.
- Schedule: the build runs from Sunday Oct 25 to the Tuesday Oct 27 submission close. The checkpoints are in the build checklist tab.

## 12. Testing, observability and responsible AI

The game rules and the verifier carry the most risk, so they get the most tests, and no test calls Azure. Every AI line is labelled, grounded in evidence and checked before it shows.

### 12.1 Tests

| Area | What to test |
| --- | --- |
| Generator | Same seed gives byte-identical files; means of 50 seeds sit inside the 6.8 ranges; event positions match tracking within 0.5 m; events validate against the JSON Schema; five planted moments, one per segment |
| xG and passes | 6 m central about 0.47, 11 m about 0.20, 25 m about 0.03, each within 0.03; difficulty rises with length and pressure |
| Patterns | Chaos stays within 0–100; PPDA and field tilt match hand-worked fixtures; significance routes to the right threshold |
| Windows | Exactly 20 s of wall time at 1x and 10x, using a fake clock; deadline counts ignore events after the deadline second; answers before a first-to-happen event come back too\_early; no answer gives missed |
| Scoring | Full base at 0 and 3 s, 30% at 20 s, never rising with time; line bonuses; Blank slate bonus |
| Moves | Table-driven: every allowed and blocked swap in 4.7; a scored line freezes; wrong squares never move; no moves during a window |
| Lines | All 12 lines detected; void counts as correct; a line scores only once |
| Masks | First-to-happen masks run from kickoff; deadline masks only during the window; held-back entries release on close |
| Live squares | Exactly five per match, one per segment, including the fallback when a segment is quiet |
| Strategist | Only suggests moves worth 3 points or more; never touches locked squares; never moves during a window |
| Verifier | Catches an invented number, an unknown name, both decimal formats, betting words, duplicate options, two correct options |
| Agents | A fake chat client returns canned JSON: valid output passes, invalid output retries once then falls back, a timeout falls back, three failures open the breaker |
| API | WebSocket round trip with FastAPI's test client: session.ready, answer.submit, square.result, board.move |
| Frontend | Card state reducer and drag rules mirror the backend tables |

Optional: run the narrator over 30 saved moments and report the verifier pass rate in the README. Only quote a number you have measured.

### 12.2 Observability

- **Spans:** a custom producer.route span per event that is routed, wrapping the workflow run and the Agent Framework spans (invoke\_agent, chat, execute\_tool) under it.
- **Span attributes:** session\_id, moment\_id, significance, agent name, fallback\_used, verifier\_errors.
- **Metrics:** latency per agent, verifier failures, breaker trips, LLM calls per minute, connected sockets.
- **Logs:** structured JSON, one line per routed moment.
- **Where to look:** Application Insights transaction search and live metrics; Foundry's trace view once the project is connected.
- **For the README:** one screenshot of a single event's trace from producer to screen.

### 12.3 Responsible AI

- **Labelled.** Every AI-written feed line carries an "AI" label, and every overlay message sets ai\_generated.
- **Grounded.** Agents only see facts from the match state, every insight stores its evidence event ids, and the verifier blocks invented numbers and names.
- **Filtered.** Foundry's default guardrails stay on for every deployment.
- **Not gambling.** Points have no cash value and can't be bought; no betting language anywhere; free to play. Merch redemption is roadmap only and would need its own terms, including age rules.
- **Private.** Viewers are a random profile id and a handle. No personal data is collected. All match data is synthetic, and names are invented.
- **Fair.** Every viewer gets the same live moments, and each mode has its own leaderboard.
- **Accessible.** See section 3.
- **Telemetry.** Sensitive-data capture is off in Azure, so prompts and responses are not stored there.
- **Honest limits, in the README:** the data is synthetic, the xG and pass models are simple formulas tuned to synthetic data, and the commentary is generated.

## 13. Submission

The entry needs four things: the project, a short pitch, a public demo video under 2 minutes, and a public GitHub repo. Script the video by Monday evening; it carries most of the presentation score.

### 13.1 Checklist

- [ ] Confirm the exact close time and time zone for October 27 in the hackathon portal.
- [ ] Read the Official Rules eligibility section. Prize contests sometimes exclude certain countries or provinces, and some employment agreements cover outside competitions and published code.
- [ ] Repo is public, with an MIT license, no keys, and no .env file committed.
- [ ] README follows the outline in 13.3.
- [ ] Video is under 2 minutes, shows the app running, and is public on YouTube or Vimeo.
- [ ] Video has no real club crests, Premier League logos or copyrighted music.
- [ ] Project page has the pitch text, the video URL and the repo URL.
- [ ] Tag a v1.0 release at submission so judges see the submitted state.
- [ ] Decide how long to keep the live app running. Winners are announced November 20, and a free account's $200 credit lasts only 30 days, after which Azure disables its services unless you move to pay as you go. If the app may go down, say so in the README and keep the local run steps clear.

### 13.2 Video script (1:55)

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:12 | Pitch view, feed scrolling | Most fans drift in the quiet minutes. Pitch Bingo makes every minute worth watching. |
| 0:12–0:35 | Setup in normal mode; tap a dot to answer "first foul"; a deadline window at 15' | Squares open when something first happens or when a deadline passes. You have 20 seconds, and faster scores more. |
| 0:35–0:55 | Live square "What did the referee just give?" with the inset replay; the rules tutor's explanation | Five squares are written live from the match's strangest moments, and normal mode teaches the rule after each one. |
| 0:55–1:10 | Move a wildcard to finish a line; strategist reason; bingo | Correct live squares become wildcards you can move to finish a line. |
| 1:10–1:25 | Switch to advanced mode in French; xG square; control vs. chaos line | Advanced mode goes deep, in your language, around your club and player. |
| 1:25–1:40 | Architecture diagram; failure switch; the feed carrying on; trace screenshot | Six Agent Framework agents on Foundry models, with a verifier on every number. If one fails, the match goes on. |
| 1:40–1:52 | Studio tab: lower third and overlay JSON; full-time recap | Every insight is also timed overlay data a broadcaster can render. |
| 1:52–1:55 | Logos of the services as text, repo URL | Built on Microsoft Foundry, Agent Framework and Azure Container Apps. |

Recording tips: record at 1440 x 900, use seed 2610 so the moments land where you expect, jump between rehearsed minutes with the dev panel, narrate in your own voice, add captions, and use no music.

### 13.3 README outline

1. Title, one-line pitch, video link, live URL, screenshot.
2. The problem and who it's for.
3. What it does, mapped to the brief's five stages: ingest, interpret, explain, render, personalize.
4. How to play, in five bullets.
5. Architecture diagram, agent roster and the four workflows.
6. Microsoft technologies used and what each does (section 10's table).
7. Synthetic data: generator, schema link, validation chart.
8. Match intelligence: the formulas from section 7.
9. Responsible AI and limitations (section 12.3).
10. Run locally, then deploy.
11. Tests and CI.
12. Roadmap: Web PubSub, Event Hubs, video auto-eventing, merch rewards, mobile.
13. Tools used to build it (say if you used GitHub Copilot), credits, license.

### 13.4 Pitch text

Pitch Bingo turns a football match into a game you can only win by watching. A synthetic match plays out as live dots on a pitch while a running feed explains why each moment matters: momentum swings, pressing, control versus chaos. Fans play a 5x5 bingo card. Some squares close at set minutes, some open the instant something first happens, and five are written live by AI from the match's most unusual moments. Every answer window lasts 20 seconds, and faster answers score more. Normal mode teaches new fans the rules as they play; advanced mode adds xG and tactical depth, in English or French, built around your club and favorite player. Six Microsoft Agent Framework agents running on Microsoft Foundry models (narrator, personalizer, rules tutor, square writer, strategist and recap) coordinate through Agent Framework workflows, and a verifier checks every number before it reaches the screen. It runs on Azure Container Apps with Cosmos DB and Application Insights.

## 14. Working with a coding agent

Export this doc as Markdown, commit it as docs/SPEC.md, and hand a coding agent one phase at a time, each with a clear finish line. Phases 1 to 4 need no Azure, so they can run while you sort out quota.

### 14.1 Standing instructions for the agent

```text
Read docs/SPEC.md before every phase. It is the source of truth.
Implement only the phase I name. Keep the layout in section 9.9.
Write tests first for any rule in section 4, and never call Azure in tests.
If the spec is silent or contradicts itself, stop and ask me.
At the end of the phase, report what changed, how to run it, and what's left.
```

### 14.2 Phases

1. **Scaffold.** Repo layout, pyproject, FastAPI serving a placeholder page, Vite React app, ci.yml, .env.example. Done when CI is green and the page loads locally.
2. **Generator and validation** (sections 6, 7.2, 7.3). Done when seed 2610's files exist, validate.py passes, and the generator tests pass.
3. **Engine, stats and the WebSocket** (sections 6.10, 7, 9.2–9.4). Done when a browser receives frames, events and stats at 1x, 5x and 10x, and the stats tests pass.
4. **Game core** (section 4). Card builder with template wording, windows, scoring, masks, moves, lines, the strategist's optimizer, simulated fans. Done when every table-driven rule test passes and a whole match is playable from the API with no LLM.
5. **Frontend** (section 3). Pitch, feed, metrics, card with dragging, leaderboard, setup and full-time screens. Done when a full match is playable in the browser with template text.
6. **Agents** (section 8). Foundry clients, the four workflows, verifier, fallbacks, breaker, dev panel. Done when AI lines replace template lines, the failure switch works, and the fake-client agent tests pass.
7. **Personalization and language** (section 5). Done when the same moment renders differently for two profiles and French works end to end.
8. **Azure** (section 11). Done when the smoke test in 11.10 passes on the deployed app.
9. **Polish and submit** (sections 2 should tier, 12, 13). Accessibility, Studio tab, README, video.

### 14.3 Habits that save time

- Commit at the end of each phase so any phase can be rolled back.
- When you change a rule, change this doc first, then tell the agent which section moved.
- Keep one terminal running the app at 10x while the agent works, so regressions show up fast.
- Ask for a short "what changed" note per phase. It becomes the README's build log.

## 15. Open questions and assumptions

Eight calls were settled on October 25. Three items are still yours to check before handing the spec to a coding agent.

- [x] A blank or wildcard moved onto a waiting static trades cells with it; resolved statics never move (4.7).
- [x] Wrong or missed live squares lock in place; only correct ones become wildcards (4.3, 4.7).
- [x] A scored line freezes, wildcards included (4.7).
- [x] Answering a first-to-happen square before the event counts as wrong (4.4).
- [x] Second language: French (5.4).
- [x] Names: Pitch Bingo, Northbridge Athletic and Kestrel Vale (6.2).
- [x] 10 deadline and 10 first-to-happen squares, with blanks starting at the corners and center (4.1).
- [x] One leaderboard per mode (3, 4.11).
- [ ] Point values and bonuses: kept as written in 4.6 unless you change them.
- [ ] Which fast model your region offers: run the model list command in 11.2.
- [ ] Submission close time, eligibility, and how long to keep the app live (13.1).

## Sources

Pages read for this spec:

- [Quickstart: Set up Microsoft Foundry resources](https://learn.microsoft.com/en-ca/azure/foundry/tutorials/quickstart-create-foundry-resources), Microsoft Learn, updated 2026-08-25
- [agent-framework on PyPI](https://pypi.org/project/agent-framework/1.8.0/), with release history through 1.23.0 on 2026-10-22
- [Agent Framework: sequential orchestrations](https://learn.microsoft.com/en-us/agent-framework/workflows/orchestrations/sequential), updated 2026-10-15
- [Agent Framework: observability](https://learn.microsoft.com/agent-framework/agents/observability), updated 2026-10-15
- [Azure Cosmos DB lifetime free tier](https://learn.microsoft.com/azure/cosmos-db/free-tier), updated 2026-04-27
- [Azure account options and free account FAQ](https://azure.microsoft.com/free/free-account-faq)

Further reading, from official search results:

- [WorkflowBuilder class reference](https://learn.microsoft.com/en-us/python/api/agent-framework-core/agent_framework.workflowbuilder)
- [Ingress in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/ingress-overview)
- [Deploy with az containerapp up](https://learn.microsoft.com/azure/container-apps/containerapp-up)
- [azd init workflow](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/azd-init-workflow)
- [Foundry guardrails overview](https://learn.microsoft.com/azure/ai-foundry/guardrails/guardrails-overview)
- [Create a workspace-based Application Insights resource](https://learn.microsoft.com/en-us/Azure/Azure-monitor/app/create-workspace-resource)
