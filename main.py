import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import questionary
import yaml

STORY_PATH = Path(__file__).resolve().parent / "story.yaml"

# Choice labels the game treats specially, rather than looking up as a
# destination in the current scene's "choices". GO BACK is added to the
# menu by ask_choice() itself; the other two are literal labels in story.yaml.
CHOICE_GAME_OVER = "GAME OVER"
CHOICE_RESTART = "RESTART"
CHOICE_GO_BACK = "GO BACK"


class StoryError(Exception):
    """story.yaml exists and is valid YAML, but doesn't describe a playable story."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _warn_about_unreachable_scenes(scenes):
    """Print a warning (not an error - dead content isn't a crash) listing
    any scene the player could never actually reach from the first scene."""
    if not scenes:
        return

    start = next(iter(scenes))
    seen = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current in seen or current not in scenes:
            continue
        seen.add(current)
        scene = scenes[current]
        stack.extend(scene.get("choices", {}).values())
        stack.extend(
            option["destination"] for option in scene.get("random", []) if "destination" in option
        )
        condition = scene.get("condition")
        if condition:
            stack.append(condition.get("true_destination"))
            stack.append(condition.get("false_destination"))

    unreachable = set(scenes) - seen
    if unreachable:
        print(
            f"Warning: {len(unreachable)} scene(s) in story.yaml are unreachable "
            f"from {start!r}: {', '.join(sorted(unreachable))}",
            file=sys.stderr,
        )


def validate_story(story):
    """Check that every destination in story.yaml points to a real scene,
    and that every scene has a shape play() knows how to handle. Raises
    StoryError listing every problem found, so a typo in the story fails
    loudly at startup instead of only when a player walks into it."""
    scenes = story.get("scenes", {})
    tokens = set(story.get("init_tokens", {}))
    problems = []

    def check_destination(where, destination):
        if destination not in scenes:
            problems.append(f"{where} points to unknown scene {destination!r}")

    for name, scene in scenes.items():
        choices = scene.get("choices")
        random_options = scene.get("random")
        condition = scene.get("condition")

        if choices is None and random_options is None and condition is None:
            problems.append(f"scene {name!r} has no 'choices', 'random', or 'condition'")

        if choices is not None:
            for label, destination in choices.items():
                if label in (CHOICE_GAME_OVER, CHOICE_RESTART):
                    continue  # destination is intentionally unused for these
                check_destination(f"scene {name!r} choice {label!r}", destination)

        if random_options is not None:
            for i, option in enumerate(random_options):
                if "probability" not in option:
                    # Not caught by check_destination below - nothing else
                    # looks at it, so it would otherwise crash with a bare
                    # KeyError only when the dice happen to land on it.
                    problems.append(f"scene {name!r} random option {i} is missing 'probability'")
                check_destination(f"scene {name!r} random option {i}", option.get("destination"))

        if condition is not None:
            if "expected" not in condition:
                # Same idea - missing "expected" isn't caught anywhere else,
                # so it would crash mid-playthrough instead of at startup.
                problems.append(f"scene {name!r} condition is missing 'expected'")
            if condition.get("token") not in tokens:
                problems.append(
                    f"scene {name!r} condition checks unknown token {condition.get('token')!r}"
                )
            check_destination(
                f"scene {name!r} condition true_destination", condition.get("true_destination")
            )
            check_destination(
                f"scene {name!r} condition false_destination", condition.get("false_destination")
            )

    if problems:
        details = "\n  - " + "\n  - ".join(problems)
        raise StoryError(f"story.yaml has {len(problems)} problem(s):{details}")

    _warn_about_unreachable_scenes(scenes)


def load_story(path=STORY_PATH):
    """Read, parse, and validate story.yaml, raising StoryError with a clear
    message on any failure - including a bad edit to the story itself, not
    just a broken file."""
    try:
        with open(path, "r", encoding="utf-8") as file:
            story = yaml.safe_load(file)
    except FileNotFoundError as exc:
        raise StoryError(f"Story file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise StoryError(f"Story file is not valid YAML: {path}") from exc

    validate_story(story)
    return story


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    """Everything that changes as the player moves through the story."""

    story: dict
    scene_title: str
    tokens: dict
    progress: list = field(default_factory=list)

    @classmethod
    def new_game(cls, story):
        first_scene = next(iter(story["scenes"]))
        return cls(story=story, scene_title=first_scene, tokens=dict(story["init_tokens"]))

    @property
    def scene(self):
        return self.story["scenes"][self.scene_title]

    def go_to(self, scene_title):
        self.scene_title = scene_title

    def can_go_back(self):
        return len(self.progress) > 1

    def visit_current_scene(self):
        scene = self.scene
        if "tokens" in scene:
            self.tokens.update(scene["tokens"])
        self.progress.append(self.scene_title)

    def go_back(self):
        leaving_scene = self.scene
        for token in leaving_scene.get("tokens", {}):
            self.tokens[token] = self.story["init_tokens"][token]

        # Rewind by one full scene: drop the one we're leaving, then land on
        # the one before it.
        self.progress.pop()
        self.scene_title = self.progress.pop()

    def apply_choice(self, choice):
        if choice is None or choice == CHOICE_GAME_OVER:
            sys.exit()
        if choice == CHOICE_RESTART:
            return GameState.new_game(self.story)
        if choice == CHOICE_GO_BACK:
            self.go_back()
            return self
        self.go_to(self.scene["choices"][choice])
        return self


# ---------------------------------------------------------------------------
# Rerouting (pure decision logic - no I/O, no mutation)
# ---------------------------------------------------------------------------

def roll_dice(scene):
    destinations = [opt["destination"] for opt in scene["random"]]
    weights = [opt["probability"] for opt in scene["random"]]

    return random.choices(destinations, weights=weights, k=1)[0]


def check_condition(scene, tokens):
    condition = scene["condition"]

    if tokens.get(condition["token"]) == condition["expected"]:
        return condition["true_destination"]
    else:
        return condition["false_destination"]


def reroute_scene(scene, tokens):
    if "random" in scene:
        return roll_dice(scene)

    if "condition" in scene:
        return check_condition(scene, tokens)

    return None


# ---------------------------------------------------------------------------
# Console UI (the only functions that touch the terminal)
# ---------------------------------------------------------------------------

def show_scene(text):
    print(text + "\n")


def ask_choice(choices, can_go_back):
    menu = list(choices)

    if can_go_back:
        menu.append(CHOICE_GO_BACK)

    return questionary.select("", choices=menu).ask()


# ---------------------------------------------------------------------------
# Game loop
# ---------------------------------------------------------------------------

def play(state):
    while True:
        redirect = reroute_scene(state.scene, state.tokens)

        if redirect is not None:
            state.go_to(redirect)
            continue

        state.visit_current_scene()
        scene = state.scene
        show_scene(scene["text"])

        choice = ask_choice(scene["choices"], state.can_go_back())
        state = state.apply_choice(choice)


def main():
    story = load_story()
    state = GameState.new_game(story)
    play(state)


if __name__ == "__main__":
    main()
