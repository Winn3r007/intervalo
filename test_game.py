from game import Game


game = Game()

print("=== INÍCIO ===")
print("Fase:", game.phase)
print("Jogador:", game.current_player)
print("Lista:", game.elements)


print("\n=== INICIANDO RODADA ===")

game.start_round()

print("Fase:", game.phase)
print("Jogador:", game.current_player)
print("Número secreto:", game.current_number)


print("\n=== ENVIANDO PISTA ===")

game.submit_clue("Professor")

print("Pista:", game.current_word)
print("Fase:", game.phase)


print("\n=== ENVIANDO RESPOSTA ===")

correct_position = game.get_correct_position()

result = game.submit_answer(correct_position)

print("Acertou:", result)


print("\n=== FINAL ===")
print("Fase:", game.phase)
print("Jogador:", game.current_player)
print("Vidas:", game.lives)
print("Acertos:", game.correct_answers)
print("Número atual:", game.current_number)
print("Pista atual:", game.current_word)
print("Lista:", game.elements)