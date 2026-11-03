import os

# Tests never read the developer's .env keys implicitly.
os.environ.setdefault("OPENAI_API_KEY", "")
