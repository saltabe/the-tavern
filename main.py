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


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_story(path=STORY_PATH):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        print(f"Story file not found: {path}")
        sys.exit(1)


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

    for check in condition["checks"]:
        if tokens.get(check["token"]) == check["expected"]:
            return check["destination"]

    return condition["else"]


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
