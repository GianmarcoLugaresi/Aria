"""LLM via API compatibile OpenAI (llama.cpp server, Ollama, mlx-lm, LM Studio...), in streaming."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from typing import AsyncIterator

import httpx

log = logging.getLogger("aria.llm")


class ThinkFilter:
    """Elimina <think>...</think> anche se i tag arrivano spezzati tra un pezzo e l'altro dello stream."""

    def __init__(self):
        self.inside = False
        self.buf = ""

    def push(self, chunk: str) -> str:
        self.buf += chunk
        out = ""
        while True:
            if self.inside:
                j = self.buf.find("</think>")
                if j < 0:
                    self.buf = self.buf[-8:]
                    return out
                self.buf, self.inside = self.buf[j + 8:], False
            else:
                i = self.buf.find("<think>")
                if i >= 0:
                    out += self.buf[:i]
                    self.buf, self.inside = self.buf[i + 7:], True
                    continue
                keep = 0
                for k in range(1, 7):                           # coda che potrebbe essere l'inizio di "<think>"
                    if "<think>".startswith(self.buf[-k:]):
                        keep = k
                out += self.buf[: len(self.buf) - keep]
                self.buf = self.buf[len(self.buf) - keep:]
                return out

    def flush(self) -> str:
        out = "" if self.inside else self.buf
        self.buf, self.inside = "", False
        return out


class OpenAILLM:
    def __init__(self, cfg: dict):
        self.base = cfg["base_url"].rstrip("/")
        self.model = cfg.get("model", "local")
        self.temperature = cfg.get("temperature", 0.8)
        self.max_tokens = cfg.get("max_tokens", 180)
        self.extra = cfg.get("extra_body", {}) or {}
        self.key = cfg.get("api_key", "none")
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=2.0))

    async def stream(self, messages: list[dict], max_tokens: int | None = None, temperature: float | None = None) -> AsyncIterator[str]:
        """Streaming. Se il server rifiuta i parametri extra (es. reasoning_effort su un modello che non ragiona), ritenta senza."""
        extra = self.extra
        for attempt in (0, 1):
            body = {"model": self.model, "messages": messages, "stream": True, "temperature": self.temperature if temperature is None else temperature,
                    "top_p": 0.92, "max_tokens": max_tokens or self.max_tokens, **extra}
            flt = ThinkFilter()
            produced = reasoning = 0
            async with self.http.stream("POST", self.base + "/chat/completions", json=body,
                                        headers={"Authorization": f"Bearer {self.key}"}) as r:
                if r.status_code >= 400:
                    err = (await r.aread())[:300]
                    if r.status_code == 400 and extra and attempt == 0:
                        log.warning("il server rifiuta i parametri extra (%r): riprovo senza", err)
                        extra = {}
                        self.extra = {}
                        continue
                    raise RuntimeError(f"LLM HTTP {r.status_code}: {err!r}")
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0].get("delta", {})
                    except (ValueError, KeyError, IndexError):
                        continue
                    if delta.get("reasoning") or delta.get("reasoning_content"):
                        reasoning += 1
                    text = flt.push(delta.get("content") or "")
                    if text:
                        produced += 1
                        yield text
            tail = flt.flush()
            if tail:
                produced += 1
                yield tail
            if not produced and reasoning:
                raise RuntimeError("il modello ha solo 'ragionato' e non ha risposto: disattiva il thinking "
                                   "(Ollama: extra_body {reasoning_effort: none}; llama.cpp: extra_body {chat_template_kwargs: {enable_thinking: false}})")
            return

    async def warmup(self) -> None:
        """Una richiesta minima: Ollama/llama.cpp caricano il modello in memoria ora, non al primo "Ciao Aria"."""
        body = {"model": self.model, "messages": [{"role": "user", "content": "ciao"}], "max_tokens": 1, "stream": False, **self.extra}
        r = await self.http.post(self.base + "/chat/completions", json=body, timeout=120.0)
        r.raise_for_status()

    async def complete(self, messages: list[dict]) -> str:
        return "".join([t async for t in self.stream(messages)])


_TURN_MARKS = re.compile(r"<end_of_turn>|<start_of_turn>(?:model|user)?\n?|<\|im_end\|>|<\|eot_id\|>|<\|end\|>|<eos>|<bos>")


def _free_buffers() -> None:
    """MLX tiene in serbo i buffer temporanei (anche ~1 GB dopo aver elaborato il prompt): li restituisce al sistema."""
    try:
        import mlx.core as mx
        (getattr(mx, "clear_cache", None) or mx.metal.clear_cache)()
    except Exception:                                            # noqa: BLE001
        pass


class MLXLLM:
    """Chatbot DENTRO Aria, con Apple MLX: niente server, niente Ollama. Usa un modello MLX di Hugging Face (di solito a 4 bit).

    Rispetto a un server, ricorda in cache la parte iniziale del prompt (il carattere di Aria, che non cambia): le risposte successive
    non la rielaborano e partono prima."""

    PREFIX_MIN = 256                                              # sotto questa lunghezza non vale la pena di tenere la cache

    def __init__(self, cfg: dict):
        self.repo = cfg["model"]
        self.temperature = cfg.get("temperature", 0.8)
        self.top_p = cfg.get("top_p", 0.92)
        self.min_p = cfg.get("min_p") or 0.0
        self.repetition_penalty = cfg.get("repetition_penalty")           # >1 scoraggia le parole appena dette: meno giri a vuoto e frasi ripetute
        self.max_tokens = cfg.get("max_tokens", 180)
        self.chat_kwargs = cfg.get("chat_template_kwargs", {}) or {}
        self.use_cache = cfg.get("prompt_cache", True)
        self.model = self.tokenizer = None
        self._snap = None                                         # (token, cache) del prefisso comune
        self._last: list[int] | None = None

    # ---- tutto quello che segue gira nel thread MLX
    def _load(self) -> None:
        if self.model is None:
            from huggingface_hub import snapshot_download
            from mlx_lm import load
            self.model, self.tokenizer = load(snapshot_download(self.repo))
            self._add_end_tokens()
            try:                                                  # una generazione minima: compila i kernel ora, non alla prima domanda
                from mlx_lm import generate
                generate(self.model, self.tokenizer, self._tokens([{"role": "user", "content": "ciao"}]), max_tokens=1)
            except Exception as e:                                # noqa: BLE001
                log.debug("riscaldamento del chatbot non riuscito: %s", e)
            log.info("MLX LM '%s' pronto", self.repo)

    # i segni che alcuni modelli usano per chiudere il turno: se il tokenizer non li dichiara come "fine", la generazione continuerebbe (e li leggerebbe a voce)
    END_MARKS = ("<end_of_turn>", "<|im_end|>", "<|eot_id|>", "<|end|>", "<|endoftext|>")

    def _add_end_tokens(self) -> None:
        tok = self.tokenizer
        vocab = getattr(tok, "get_vocab", lambda: {})()
        for mark in self.END_MARKS:
            if mark in vocab:
                try:
                    tok.add_eos_token(mark)
                except Exception as e:                            # noqa: BLE001
                    log.debug("non riesco a registrare %s come fine turno: %s", mark, e)

    def _tokens(self, messages: list[dict]) -> list[int]:
        """Il prompt in token. Se il modello non ha il ruolo 'system' (es. Gemma 2) il carattere passa nel primo messaggio dell'utente."""
        def enc(msgs):
            out = self.tokenizer.apply_chat_template(msgs, add_generation_prompt=True, **self.chat_kwargs)
            if hasattr(out, "get") and out.get("input_ids") is not None:      # alcune versioni restituiscono un dizionario
                out = out["input_ids"]
            return list(out)
        try:
            return enc(messages)
        except Exception:                                         # noqa: BLE001
            msgs = [dict(m) for m in messages]
            if msgs and msgs[0]["role"] == "system":
                sys_text = msgs.pop(0)["content"]
                if msgs and msgs[0]["role"] == "user":
                    msgs[0]["content"] = sys_text + "\n\n" + msgs[0]["content"]
                else:
                    msgs.insert(0, {"role": "user", "content": sys_text})
            return enc(msgs)

    def _prefill(self, cache, tokens: list[int]) -> None:
        import mlx.core as mx
        y = mx.array(tokens)
        while y.size > 0:
            n = min(512, y.size)
            self.model(y[:n][None], cache=cache)
            mx.eval([c.state for c in cache])
            y = y[n:]
        _free_buffers()

    def _start(self, tokens: list[int]):
        """Restituisce (cache, token_da_elaborare): riusa il prefisso comune alle richieste precedenti se c'e'."""
        from mlx_lm.models.cache import make_prompt_cache
        import copy
        if not self.use_cache:
            return make_prompt_cache(self.model), tokens
        try:
            snap = self._snap
            if snap and len(tokens) > len(snap[0]) and tokens[:len(snap[0])] == snap[0]:
                return copy.deepcopy(snap[1]), tokens[len(snap[0]):]
            b = 0
            if self._last:
                while b < min(len(self._last), len(tokens)) - 1 and self._last[b] == tokens[b]:
                    b += 1
            if b >= self.PREFIX_MIN:
                cache = make_prompt_cache(self.model)
                self._prefill(cache, tokens[:b])
                self._snap = (tokens[:b], copy.deepcopy(cache))
                return cache, tokens[b:]
        except Exception as e:                                    # noqa: BLE001
            log.warning("cache del prompt non usabile (%s): la disattivo", e)
            self.use_cache, self._snap = False, None
        return make_prompt_cache(self.model), tokens

    def _prime(self, sys_a: str, sys_b: str) -> int:
        """Prepara la cache del prefisso fisso. Il prefisso e' la parte in comune a due prompt che differiscono solo in coda (data e memoria):
        cosi' non dipende da quando e' stata fatta la prima domanda. Restituisce quanti token ha messo in cache (0 = niente)."""
        self._load()
        if not self.use_cache:
            return 0
        ta = self._tokens([{"role": "system", "content": sys_a}, {"role": "user", "content": "ciao"}])
        tb = self._tokens([{"role": "system", "content": sys_b}, {"role": "user", "content": "ciao"}])
        b = 0
        while b < min(len(ta), len(tb)) and ta[b] == tb[b]:
            b += 1
        b -= 4                                                    # margine: l'ultima parola in comune puo' fondersi con quella che segue
        if b < self.PREFIX_MIN:
            return 0
        import copy
        from mlx_lm.models.cache import make_prompt_cache
        cache = make_prompt_cache(self.model)
        self._prefill(cache, ta[:b])
        self._snap = (ta[:b], copy.deepcopy(cache))
        self._last = ta
        del cache
        _free_buffers()
        return b

    def _generate(self, messages: list[dict], loop, q, cancel: threading.Event, max_tokens: int | None = None, temperature: float | None = None) -> None:
        try:
            self._load()
            from mlx_lm import stream_generate
            from mlx_lm.sample_utils import make_logits_processors, make_sampler
            tokens = self._tokens(messages)
            cache, feed = self._start(tokens)
            self._last = tokens
            sampler = make_sampler(temp=self.temperature if temperature is None else temperature, top_p=self.top_p, min_p=self.min_p)
            extra = {}
            if self.repetition_penalty and self.repetition_penalty != 1.0:
                extra["logits_processors"] = make_logits_processors(repetition_penalty=self.repetition_penalty, repetition_context_size=96)
            for r in stream_generate(self.model, self.tokenizer, feed, max_tokens=max_tokens or self.max_tokens, sampler=sampler, prompt_cache=cache, **extra):
                if cancel.is_set():
                    break
                if r.text:
                    loop.call_soon_threadsafe(q.put_nowait, r.text)
        except Exception as e:                                    # noqa: BLE001
            loop.call_soon_threadsafe(q.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)
            _free_buffers()

    # ---- interfaccia uguale a OpenAILLM
    async def stream(self, messages: list[dict], max_tokens: int | None = None, temperature: float | None = None) -> AsyncIterator[str]:
        from .mlxpool import POOL
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        cancel = threading.Event()
        loop.run_in_executor(POOL, self._generate, messages, loop, q, cancel, max_tokens, temperature)
        flt = ThinkFilter()
        try:
            while True:
                item = await q.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                text = flt.push(_TURN_MARKS.sub("", item))
                if text:
                    yield text
            tail = flt.flush()
            if tail:
                yield tail
        finally:
            cancel.set()                                          # chi ascolta ha smesso (stop, interruzione): il thread MLX si ferma al prossimo token

    async def warmup(self) -> None:
        from .mlxpool import POOL
        await asyncio.get_running_loop().run_in_executor(POOL, self._load)

    async def prime(self, sys_a: str, sys_b: str) -> int:
        from .mlxpool import POOL
        return await asyncio.get_running_loop().run_in_executor(POOL, self._prime, sys_a, sys_b)

    async def complete(self, messages: list[dict]) -> str:
        return "".join([t async for t in self.stream(messages)])


def make_llm(cfg: dict):
    """kind 'mlx-lm' = chatbot dentro Aria (nessun Ollama); altrimenti un server compatibile OpenAI (Ollama, llama.cpp, LM Studio...)."""
    return MLXLLM(cfg) if cfg.get("kind") == "mlx-lm" else OpenAILLM(cfg)
