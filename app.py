import math
import random
import time

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room

from game import Game


app = Flask(__name__)
app.config["SECRET_KEY"] = "1a100-secret-key"

socketio = SocketIO(app, cors_allowed_origins="*")


rooms = {}
player_rooms = {}


def generate_room_code():
    characters = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    while True:
        code = "".join(
            random.choice(characters)
            for _ in range(4)
        )

        if code not in rooms:
            return code


def get_room():
    room_code = player_rooms.get(request.sid)

    if room_code is None:
        return None, None

    room = rooms.get(room_code)

    if room is None:
        return None, None

    return room_code, room


def public_game_state(room):
    game = room["game"]

    timer_seconds = None
    if room.get("timer_deadline") is not None and game.phase in ("clue", "guessing"):
        timer_seconds = max(
            0,
            math.ceil(room["timer_deadline"] - time.time())
        )

    players_connected = sum(
        sid is not None
        for sid in room["players"].values()
    )

    return {
        "lives": game.lives,
        "max_lives": game.max_lives,
        "correct_answers": game.correct_answers,
        "elements": game.elements,
        "current_player": game.current_player,
        "phase": game.phase,
        "mode": game.mode,
        "timer_seconds": timer_seconds,
        "players_connected": players_connected,
        "max_players": 2,
    }


def player_number(room, sid):
    for number, player_sid in room["players"].items():
        if player_sid == sid:
            return number

    return None


@app.route("/")
def index():
    return render_template("index.html")


def emit_round_timeout(room_code, round_id):
    socketio.sleep(rooms.get(room_code, {}).get("game", Game()).timer_seconds or 0)

    room = rooms.get(room_code)
    if room is None or room.get("round_id") != round_id:
        return

    game = room["game"]
    if game.phase not in ("clue", "guessing"):
        return

    secret_number = game.current_number
    clue = game.current_word
    correct_position = game.get_correct_position()
    between_min = None
    between_max = None

    if correct_position is not None:
        elements = game.elements
        between_min = elements[correct_position - 1]["number"] if correct_position > 0 else 0
        between_max = elements[correct_position]["number"] if correct_position < len(elements) else 100

    game.timeout_round()
    room["timer_deadline"] = None

    socketio.emit(
        "round_result",
        {
            "correct": False,
            "timed_out": True,
            "chosen_position": None,
            "correct_position": correct_position,
            "number": secret_number,
            "clue": clue,
            "between_min": between_min,
            "between_max": between_max,
            "state": public_game_state(room),
        },
        to=room_code,
    )

    if game.phase in ("win", "lose"):
        socketio.emit(
            "game_over",
            {
                "result": game.phase,
                "state": public_game_state(room),
            },
            to=room_code,
        )
    else:
        socketio.emit(
            "next_round",
            {"state": public_game_state(room)},
            to=room_code,
        )


@socketio.on("create_room")
def create_room(data=None):

    if request.sid in player_rooms:
        emit("error_message", {
            "message": "Você já está em uma partida."
        })
        return

    mode = data.get("mode", "normal") if isinstance(data, dict) else "normal"
    if mode not in Game.MODE_SETTINGS:
        mode = "normal"

    code = generate_room_code()

    rooms[code] = {
        "game": Game(mode),
        "mode": mode,
        "round_id": 0,
        "timer_deadline": None,
        "reconnect_deadlines": {},
        "players": {
            1: request.sid,
            2: None
        }
    }

    player_rooms[request.sid] = code

    join_room(code)

    emit("room_created", {
        "room": code,
        "player": 1
    })

    emit(
        "room_state",
        public_game_state(rooms[code])
    )


@socketio.on("join_room")
def join_existing_room(data):

    if request.sid in player_rooms:
        emit("error_message", {
            "message": "Você já está em uma partida."
        })
        return

    if not isinstance(data, dict):
        emit("error_message", {
            "message": "Dados inválidos."
        })
        return

    code = data.get("room", "")

    if not isinstance(code, str):
        emit("error_message", {
            "message": "Código da sala inválido."
        })
        return

    code = code.strip().upper()

    if len(code) != 4:
        emit("error_message", {
            "message": "O código deve ter 4 caracteres."
        })
        return

    room = rooms.get(code)

    if room is None:
        emit("error_message", {
            "message": "Sala não encontrada."
        })
        return

    if room["players"][2] is not None:
        emit("error_message", {
            "message": "Essa sala já está cheia."
        })
        return

    room["players"][2] = request.sid
    player_rooms[request.sid] = code

    join_room(code)

    emit("room_joined", {
        "room": code,
        "player": 2
    })

    socketio.emit(
        "room_state",
        public_game_state(room),
        to=code
    )


@socketio.on("start_round")
def start_round():

    room_code, room = get_room()

    if room is None:
        emit("error_message", {
            "message": "Você não está em uma sala."
        })
        return

    game = room["game"]

    current_player = player_number(
        room,
        request.sid
    )

    if current_player is None:
        emit("error_message", {
            "message": "Jogador inválido."
        })
        return

    players_connected = sum(
        sid is not None
        for sid in room["players"].values()
    )

    if players_connected < 2:
        emit("error_message", {
            "message": "É necessário ter dois jogadores."
        })
        return

    if current_player != game.current_player:
        emit("error_message", {
            "message": "Não é sua vez."
        })
        return

    if game.phase != "waiting":
        emit("error_message", {
            "message": "A rodada já está em andamento."
        })
        return

    started = game.start_round()

    if not started:
        emit("error_message", {
            "message": "Não foi possível iniciar a rodada."
        })
        return

    room["round_id"] += 1
    if game.timer_seconds is not None:
        room["timer_deadline"] = time.time() + game.timer_seconds

    socketio.emit(
        "round_started",
        {
            "state": public_game_state(room)
        },
        to=room_code
    )

    # Somente o jogador que dará a pista recebe o número.
    emit("secret_number", {
        "number": game.current_number
    })

    if game.timer_seconds is not None:
        socketio.start_background_task(
            emit_round_timeout,
            room_code,
            room["round_id"],
        )


@socketio.on("submit_clue")
def submit_clue(data):

    room_code, room = get_room()

    if room is None:
        emit("error_message", {
            "message": "Você não está em uma sala."
        })
        return

    game = room["game"]

    current_player = player_number(
        room,
        request.sid
    )

    if current_player is None:
        emit("error_message", {
            "message": "Jogador inválido."
        })
        return

    if current_player != game.current_player:
        emit("error_message", {
            "message": "Não é sua vez."
        })
        return

    if game.phase != "clue":
        emit("error_message", {
            "message": "Não é hora de enviar uma pista."
        })
        return

    if not isinstance(data, dict):
        emit("error_message", {
            "message": "Dados inválidos."
        })
        return

    word = data.get("word", "")

    if not isinstance(word, str):
        emit("error_message", {
            "message": "A pista precisa ser um texto."
        })
        return

    word = word.strip()

    if not word:
        emit("error_message", {
            "message": "A pista não pode estar vazia."
        })
        return

    if not game.submit_clue(word):
        emit("error_message", {
            "message": "Pista inválida."
        })
        return

    socketio.emit(
        "clue_submitted",
        {
            "clue": game.current_word,
            "state": public_game_state(room)
        },
        to=room_code
    )


@socketio.on("submit_answer")
def submit_answer(data):

    room_code, room = get_room()

    if room is None:
        emit("error_message", {
            "message": "Você não está em uma sala."
        })
        return

    game = room["game"]

    current_player = player_number(
        room,
        request.sid
    )

    if current_player is None:
        emit("error_message", {
            "message": "Jogador inválido."
        })
        return

    if game.phase in ("win", "lose"):
        emit("error_message", {
            "message": "O jogo já terminou."
        })
        return

    if current_player == game.current_player:
        emit("error_message", {
            "message": "Você deu a pista nesta rodada."
        })
        return

    if game.phase != "guessing":
        emit("error_message", {
            "message": "Não é hora de responder."
        })
        return

    if not isinstance(data, dict):
        emit("error_message", {
            "message": "Dados inválidos."
        })
        return

    chosen_position = data.get("position")

    if (
        not isinstance(chosen_position, int)
        or isinstance(chosen_position, bool)
    ):
        emit("error_message", {
            "message": "Posição inválida."
        })
        return

    if not 0 <= chosen_position <= len(game.elements):
        emit("error_message", {
            "message": "Essa posição não existe."
        })
        return

    secret_number = game.current_number
    clue = game.current_word
    correct_position = game.get_correct_position()

    # --- NOVO: Cálculo do intervalo (mínimo e máximo) ---
    elements = game.elements
    pos = correct_position

    between_min = elements[pos - 1]['number'] if pos > 0 else 0
    between_max = elements[pos]['number'] if pos < len(elements) else 100
    # ----------------------------------------------------

    result = game.submit_answer(
        chosen_position
    )

    game_state = game.phase
    room["timer_deadline"] = None
    room["round_id"] += 1

    socketio.emit(
        "round_result",
        {
            "correct": result,
            "chosen_position": chosen_position,
            "correct_position": correct_position,
            "number": secret_number,
            "clue": clue,
            "between_min": between_min,
            "between_max": between_max,
            "state": public_game_state(room)
        },
        to=room_code
    )

    if game_state in ("win", "lose"):

        socketio.emit(
            "game_over",
            {
                "result": game_state,
                "state": public_game_state(room)
            },
            to=room_code
        )

        return

    socketio.emit(
        "next_round",
        {
            "state": public_game_state(room)
        },
        to=room_code
    )


@socketio.on("restart_game")
def restart_game():
    room_code, room = get_room()

    if room is None:
        emit("error_message", {
            "message": "Você não está em uma sala."
        })
        return

    if any(sid is None for sid in room["players"].values()):
        emit("error_message", {
            "message": "É necessário que os dois jogadores estejam conectados."
        })
        return

    if room["game"].phase not in ("win", "lose"):
        emit("error_message", {
            "message": "A partida ainda não terminou."
        })
        return

    room["game"] = Game(room["mode"])
    room["round_id"] += 1
    room["timer_deadline"] = None

    socketio.emit(
        "room_state",
        public_game_state(room),
        to=room_code,
    )


def remove_player_from_room(player_sid, preserve_for_reconnect=True):
    room_code = player_rooms.pop(
        player_sid,
        None
    )

    if room_code is None:
        return

    room = rooms.get(room_code)

    if room is None:
        return

    disconnected_player = None
    other_player_sid = None

    for number, current_sid in room["players"].items():

        if current_sid == player_sid:
            disconnected_player = number
            room["players"][number] = None

        elif current_sid is not None:
            other_player_sid = current_sid

    if preserve_for_reconnect:
        deadline = time.time() + 15
        room["reconnect_deadlines"][disconnected_player] = deadline

        socketio.emit(
            "player_disconnected",
            {
                "player": disconnected_player,
            },
            to=room_code,
        )

        socketio.start_background_task(
            close_disconnected_room,
            room_code,
            disconnected_player,
            deadline,
        )
        return

    socketio.emit(
        "player_disconnected",
        {
            "player": disconnected_player
        },
        to=room_code
    )

    rooms.pop(
        room_code,
        None
    )


def close_disconnected_room(room_code, player_number, deadline):
    socketio.sleep(15)

    room = rooms.get(room_code)
    if room is None:
        return

    if room["reconnect_deadlines"].get(player_number) != deadline:
        return

    if room["players"].get(player_number) is not None:
        return

    for sid in room["players"].values():
        if sid is not None:
            player_rooms.pop(sid, None)

    rooms.pop(room_code, None)


@socketio.on("rejoin_room")
def rejoin_room(data):
    if not isinstance(data, dict):
        emit("error_message", {"message": "Dados inválidos."})
        return

    room_code = data.get("room", "")
    player = data.get("player")

    if not isinstance(room_code, str) or player not in (1, 2):
        emit("error_message", {"message": "Dados de reconexão inválidos."})
        return

    room_code = room_code.strip().upper()
    room = rooms.get(room_code)
    if room is None:
        emit("error_message", {"message": "A sala expirou."})
        return

    deadline = room["reconnect_deadlines"].get(player)
    if room["players"].get(player) is not None or deadline is None or deadline < time.time():
        emit("error_message", {"message": "Não foi possível reconectar à sala."})
        return

    room["players"][player] = request.sid
    room["reconnect_deadlines"].pop(player, None)
    player_rooms[request.sid] = room_code
    join_room(room_code)

    emit("room_joined", {
        "room": room_code,
        "player": player,
    })
    socketio.emit(
        "room_state",
        public_game_state(room),
        to=room_code,
    )


@socketio.on("leave_room")
def leave_current_room():
    room_code = player_rooms.get(request.sid)

    if room_code is not None:
        leave_room(room_code)
        remove_player_from_room(request.sid, preserve_for_reconnect=False)


@socketio.on("disconnect")
def disconnect():
    remove_player_from_room(request.sid)


if __name__ == "__main__":

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True
    )