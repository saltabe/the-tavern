# The Tavern

A choice-based text adventure that runs in the terminal. You arrive, starving, at a tavern in the snowy wilderness — every choice you make branches the story toward one of six endings. Kindness and collaboration are rewarded while self-reliance decreases your chances of survival.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python3 main.py
```

Use the arrow keys and Enter to pick from the menu at each scene. Once you've made at least one choice, a **GO BACK** option appears in the menu — picking it undoes your last choice and returns you to the scene before it, including reverting any story flag that choice had set.

`main.py` reads its story from `story.yaml`, which sits next to the script and is loaded relative to the script's own location — so the game runs correctly no matter what directory you launch it from.

## Editing the story

`story.yaml` has two top-level keys:

- `init_tokens` — the starting value of every token (a piece of state the story can remember, specifically whether you were kind to a character earlier).
- `scenes` — a map of scene name → scene, keyed by whatever the game calls that scene internally (the key is never shown to the player).

Every scene is one of three shapes:

**A normal scene** — shows text, then offers the player a menu of choices. Use `|` for `text` so line breaks in the prose are real line breaks, not escape sequences:

```yaml
old_man:
  text: |
    You collapse into a chair...
  choices:
    REPEAT YOURSELF: repeat_yourself
    THROW THE BEER AT HIM: throw_beer
```

Each choice's value is the name of the scene it leads to. A scene that just continues the story with no decision to be made still uses this shape, with a single choice labeled `NEXT`:

```yaml
accept_job:
  text: |
    You look the old man dead in the eyes...
  choices:
    NEXT: man_morning
```

A normal scene can also set tokens when the player enters it:

```yaml
stay_man:
  text: |
    ...
  choices:
    NEXT: man_falls
  tokens:
    kindness: true
```

**A random scene** — never shown to the player; picks a destination by weighted coin flip as soon as it's reached:

```yaml
exit_tavern:
  random:
    - destination: freeze_ending
      probability: 0.95
    - destination: bear_ending
      probability: 0.05
```

**A condition scene** — never shown to the player; branches on the current value of a token:

```yaml
man_dies:
  condition:
    token: kindness
    expected: true
    true_destination: reveal_fortune
    false_destination: reveal_nothing
```

(`true_destination`/`false_destination` are spelled out rather than just `true`/`false`, because YAML parses unquoted `true`/`false` as actual booleans — using them as map keys would silently turn them into the booleans `True`/`False` instead of the strings the code expects.)

Two choice labels are handled specially by the game rather than being treated as ordinary destinations: `GAME OVER` ends the game, and `RESTART` starts it over. Their destination values in `story.yaml` are `null` since they're never actually looked up.

## License

All rights reserved — see [LICENSE](LICENSE). This repository is public for portfolio and demonstration purposes; it isn't licensed for reuse.
