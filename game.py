import random
from pathlib import Path


def carregar_palavras():
    caminho = Path(__file__).parent / "palavras.txt"

    with open(caminho, "r", encoding="utf-8") as arquivo:
        palavras = [
            linha.strip()
            for linha in arquivo
            if linha.strip()
        ]

    return palavras


class Game:
    MODE_SETTINGS = {
        "normal": {"lives": 3, "timer_seconds": None},
        "hard": {"lives": 3, "timer_seconds": 80},
        "hardcore": {"lives": 1, "timer_seconds": 40},
    }

    def __init__(self, mode="normal"):
        if mode not in self.MODE_SETTINGS:
            mode = "normal"

        self.mode = mode
        self.max_lives = self.MODE_SETTINGS[mode]["lives"]
        self.timer_seconds = self.MODE_SETTINGS[mode]["timer_seconds"]
        self.lives = self.max_lives
        self.correct_answers = 0

        self.elements = []
        self.used_numbers = set()
        self.used_words = set()

        self.current_number = None
        self.current_word = None

        self.current_player = 1
        self.phase = "waiting"

        self.create_initial_elements()

    def create_initial_elements(self):
        palavras = carregar_palavras()

        if len(palavras) < 3:
            raise ValueError(
                "O banco de palavras precisa ter pelo menos 3 palavras."
            )

        numbers = random.sample(range(1, 101), 3)
        words = random.sample(palavras, 3)

        self.used_numbers.update(numbers)
        self.used_words.update(
            word.casefold()
            for word in words
        )

        self.elements = [
            {
                "number": number,
                "word": word
            }
            for number, word in zip(numbers, words)
        ]

        self.elements.sort(
            key=lambda element: element["number"]
        )

    def draw_number(self):
        available_numbers = [
            number
            for number in range(1, 101)
            if number not in self.used_numbers
        ]

        if not available_numbers:
            return None

        self.current_number = random.choice(
            available_numbers
        )

        self.used_numbers.add(self.current_number)

        return self.current_number

    def get_correct_position(self):
        if self.current_number is None:
            return None

        for index, element in enumerate(self.elements):
            if self.current_number < element["number"]:
                return index

        return len(self.elements)

    def check_answer(self, chosen_position):
        if self.phase != "guessing":
            return False

        if (
            not isinstance(chosen_position, int)
            or isinstance(chosen_position, bool)
        ):
            return False

        correct_position = self.get_correct_position()

        if correct_position is None:
            return False

        if chosen_position == correct_position:
            self.correct_answers += 1
            return True

        self.lives -= 1
        return False

    def add_element(self, word):
        if self.current_number is None:
            return False

        if not isinstance(word, str):
            return False

        word = word.strip()

        if not word:
            return False

        self.elements.append({
            "number": self.current_number,
            "word": word
        })

        self.elements.sort(
            key=lambda element: element["number"]
        )

        return True

    def switch_player(self):
        if self.current_player == 1:
            self.current_player = 2
        else:
            self.current_player = 1

    def is_game_over(self):
        if self.correct_answers >= 10:
            return "win"

        if self.lives <= 0:
            return "lose"

        return None

    def start_round(self):
        if self.phase != "waiting":
            return False

        if self.is_game_over() is not None:
            return False

        number = self.draw_number()

        if number is None:
            return False

        self.current_word = None
        self.phase = "clue"

        return True

    def submit_clue(self, word):
        if self.phase != "clue":
            return False

        if not isinstance(word, str):
            return False

        word = word.strip()

        if (
            not word
            or any(character.isspace() for character in word)
            or any(character.isdigit() for character in word)
        ):
            return False

        normalized_word = word.casefold()

        if normalized_word in self.used_words:
            return False

        self.current_word = word
        self.used_words.add(normalized_word)
        self.phase = "guessing"

        return True

    def timeout_round(self):
        if self.phase not in ("clue", "guessing"):
            return False

        self.lives -= 1
        game_state = self.is_game_over()

        if game_state is not None:
            self.phase = game_state
            return True

        self.switch_player()
        self.current_number = None
        self.current_word = None
        self.phase = "waiting"

        return True

    def submit_answer(self, chosen_position):
        if self.phase != "guessing":
            return False

        if (
            not isinstance(chosen_position, int)
            or isinstance(chosen_position, bool)
        ):
            return False

        if not 0 <= chosen_position <= len(self.elements):
            return False

        result = self.check_answer(chosen_position)

        if result:
            self.add_element(self.current_word)

        game_state = self.is_game_over()

        if game_state is not None:
            self.phase = game_state
            return result

        self.switch_player()

        self.current_number = None
        self.current_word = None
        self.phase = "waiting"

        return result