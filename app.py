import random

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

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

    players_connected = sum(
        sid is not None
        for sid in room["players"].values()
    )

    return {
        "lives": game.lives,
        "correct_answers": game.correct_answers,
        "elements": game.elements,
        "current_player": game.current_player,
        "phase": game.phase,
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


@socketio.on("create_room")
def create_room():

    if request.sid in player_rooms:
        emit("error_message", {
            "message": "Você já está em uma partida."
        })
        return

    code = generate_room_code()

    rooms[code] = {
        "game": Game(),
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

    result = game.submit_answer(
        chosen_position
    )

    game_state = game.phase

    socketio.emit(
        "round_result",
        {
            "correct": result,
            "chosen_position": chosen_position,
            "correct_position": correct_position,
            "number": secret_number,
            "clue": clue,
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


@socketio.on("disconnect")
def disconnect():

    room_code = player_rooms.pop(
        request.sid,
        None
    )

    if room_code is None:
        return

    room = rooms.get(room_code)

    if room is None:
        return

    disconnected_player = None
    other_player_sid = None

    for number, sid in room["players"].items():

        if sid == request.sid:
            disconnected_player = number
            room["players"][number] = None

        elif sid is not None:
            other_player_sid = sid

    socketio.emit(
        "player_disconnected",
        {
            "player": disconnected_player
        },
        to=room_code
    )

    # A partida é encerrada quando um dos jogadores sai.
    if other_player_sid is not None:
        player_rooms.pop(
            other_player_sid,
            None
        )

    rooms.pop(
        room_code,
        None
    )


if __name__ == "__main__":

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True
    )