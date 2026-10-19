"""Il chatbot dentro Aria (MLX): scelta del motore, formato del prompt e, se il modellino di prova e' in cache, una risposta vera."""
import asyncio
import os

import pytest

from aria.llm import MLXLLM, OpenAILLM, make_llm
from aria.router import LOCAL_KINDS


def test_make_llm_picks_the_engine_from_the_config():
    assert isinstance(make_llm({"kind": "mlx-lm", "model": "mlx-community/gemma-3-text-4b-it-4bit"}), MLXLLM)
    assert isinstance(make_llm({"base_url": "http://127.0.0.1:11434/v1", "model": "gemma3:4b"}), OpenAILLM)
    assert "mlx-lm" in LOCAL_KINDS                          # gira nel processo: sempre "raggiungibile", niente controllo di rete


class FakeTok:
    """Come Gemma 2: non accetta il ruolo 'system'."""

    def __init__(self, accept_system):
        self.accept_system, self.seen = accept_system, []

    def apply_chat_template(self, msgs, add_generation_prompt=True, **kw):
        self.seen.append((msgs, kw))
        if not self.accept_system and any(m["role"] == "system" for m in msgs):
            raise ValueError("System role not supported")
        return list(range(len(msgs) * 3))


def test_end_of_turn_tokens_are_registered_as_stop_tokens():
    """Gemma 2 chiude il turno con <end_of_turn>: se il tokenizer non lo dichiara 'fine', Aria lo leggerebbe a voce e continuerebbe a generare."""
    class Tok:
        def __init__(self):
            self.eos = []

        def get_vocab(self):
            return {"<end_of_turn>": 107, "ciao": 5}

        def add_eos_token(self, t):
            self.eos.append(t)

    llm = make_llm({"kind": "mlx-lm", "model": "x"})
    llm.tokenizer = Tok()
    llm._add_end_tokens()
    assert llm.tokenizer.eos == ["<end_of_turn>"]            # solo quelli che il vocabolario conosce


def test_leaked_turn_markers_never_reach_the_voice():
    from aria.llm import _TURN_MARKS
    assert _TURN_MARKS.sub("", "Ciao!<end_of_turn>") == "Ciao!"
    assert _TURN_MARKS.sub("", "<start_of_turn>model\nCiao") == "Ciao"
    assert _TURN_MARKS.sub("", "Il 5 < 7 e 9 > 2") == "Il 5 < 7 e 9 > 2"          # i simboli normali restano


def test_prompt_falls_back_when_the_template_has_no_system_role():
    llm = MLXLLM({"model": "x/y"})
    msgs = [{"role": "system", "content": "Sei Aria."}, {"role": "user", "content": "ciao"}]
    llm.tokenizer = FakeTok(accept_system=True)
    assert llm._tokens(msgs) == list(range(6)) and len(llm.tokenizer.seen) == 1
    llm.tokenizer = FakeTok(accept_system=False)
    assert llm._tokens(msgs) == list(range(3))               # un solo messaggio: il carattere e' passato nel primo dell'utente
    merged = llm.tokenizer.seen[-1][0]
    assert merged == [{"role": "user", "content": "Sei Aria.\n\nciao"}] and msgs[0]["role"] == "system"    # l'originale non e' modificato
    llm.chat_kwargs = {"enable_thinking": False}
    llm.tokenizer = FakeTok(accept_system=True)
    llm._tokens(msgs)
    assert llm.tokenizer.seen[-1][1] == {"enable_thinking": False}


def _tiny_model_cached() -> bool:
    try:
        from huggingface_hub import snapshot_download
        snapshot_download("mlx-community/gemma-3-270m-it-4bit", local_files_only=True)
        return True
    except Exception:                                        # noqa: BLE001
        return False


@pytest.mark.skipif(not _tiny_model_cached() or os.environ.get("ARIA_SKIP_REAL_MODEL"), reason="il modellino di prova non e' in cache")
async def test_real_tiny_model_streams_caches_and_can_be_cancelled():
    pytest.importorskip("mlx_lm")
    llm = MLXLLM({"model": "mlx-community/gemma-3-270m-it-4bit", "max_tokens": 12, "temperature": 0.0})
    persona = "Sei Aria, un'assistente vocale italiana. " + "Rispondi in modo breve e caloroso. " * 90          # prefisso lungo: si puo' mettere in cache
    out = []
    for i in range(3):
        msgs = [{"role": "system", "content": persona + f" Sono le {i}."}, {"role": "user", "content": "Ciao, come stai?"}]
        out.append("".join([t async for t in llm.stream(msgs)]))
    assert all(out) and llm._snap is not None and len(llm._snap[0]) >= MLXLLM.PREFIX_MIN       # dalla seconda richiesta il prefisso e' in cache
    gen = llm.stream([{"role": "user", "content": "Raccontami una storia lunga."}])
    async for _ in gen:
        break
    await gen.aclose()                                                                         # chi ascolta smette: il thread MLX si libera
    assert await asyncio.wait_for(llm.complete([{"role": "user", "content": "Dimmi ciao."}]), 30)
