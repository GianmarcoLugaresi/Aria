"""Un solo thread per tutto cio' che usa MLX (riconoscimento vocale e chatbot): MLX vuole caricare e usare un modello nello stesso thread."""
from concurrent.futures import ThreadPoolExecutor

POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")
