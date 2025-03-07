import os

# Set the environment variable so that when app.api is imported, it uses in‑memory SQLite.
os.environ["SUGGESTIONS_DATABASE"] = ":memory:"
