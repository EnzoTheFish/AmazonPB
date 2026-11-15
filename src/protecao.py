"""Protecoes simples contra repeticao acidental e spam na sessao atual."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

import streamlit as st


_tentativas: dict[str, deque[float]] = defaultdict(deque)
_bloqueios: dict[str, float] = {}
_lock = threading.Lock()


def _sessao() -> str:
	"""Cria um identificador estavel enquanto a sessao do Streamlit existir."""
	if "protecao_sessao" not in st.session_state:
		st.session_state["protecao_sessao"] = f"sessao-{time.monotonic_ns()}"
	return st.session_state["protecao_sessao"]


def verificar(acao: str, limite: int, janela: int = 60,
			  bloqueio: int = 60) -> tuple[bool, int]:
	"""Retorna se a acao esta liberada e quantos segundos faltam, se bloqueada."""
	agora = time.monotonic()
	chave = f"{_sessao()}:{acao}"

	with _lock:
		bloqueado_ate = _bloqueios.get(chave, 0)
		if bloqueado_ate > agora:
			return False, max(1, int(bloqueado_ate - agora + 0.999))

		tentativas = _tentativas[chave]
		while tentativas and tentativas[0] <= agora - janela:
			tentativas.popleft()

		if len(tentativas) >= limite:
			_bloqueios[chave] = agora + bloqueio
			tentativas.clear()
			return False, bloqueio

		tentativas.append(agora)
		return True, 0


def mensagem(acao: str, segundos: int) -> str:
	"""Monta uma mensagem curta para exibir na interface."""
	return f"Muitas tentativas de {acao}. Aguarde {segundos}s e tente novamente."
