"""Il modello che vede, in un processo a parte: `python -m aria.vision --image foto.png --model org/nome --prompt "..."` -> una riga JSON {"text": "..."}.
Un processo a parte perche' i ~4 GB del modello tornano liberi appena ha risposto e non disturbano il chatbot di Aria (MLX, GPU) che sta lavorando."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--budget", type=int, default=1120, help="quanti 'pezzi' di immagine guarda (70, 140, 280, 560, 1120): piu' alto = legge meglio i dettagli, piu' lento")
    ap.add_argument("--max-tokens", type=int, default=260)
    a = ap.parse_args(argv)
    try:
        from mlx_vlm import generate, load
        from mlx_vlm.prompt_utils import apply_chat_template
        from mlx_vlm.utils import load_config
    except ImportError:
        print(json.dumps({"error": "manca il componente per la visione (mlx-vlm): rilancia l'installazione di Aria"}))
        return 1
    try:
        model, processor = load(a.model)
        config = load_config(a.model)
        if hasattr(getattr(processor, "image_processor", None), "max_soft_tokens"):
            processor.image_processor.max_soft_tokens = a.budget
        prompt = apply_chat_template(processor, config, a.prompt, num_images=1)
        out = generate(model, processor, prompt, [a.image], max_tokens=a.max_tokens, temperature=0.2, verbose=False)
        print(json.dumps({"text": getattr(out, "text", str(out))}, ensure_ascii=False))
        return 0
    except Exception as e:                                           # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {str(e)[:200]}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
