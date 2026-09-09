import os
import sys

# Vercel imports this module from a sandboxed directory; make the project
# root importable so `app` resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

# Vercel's Python runtime expects a WSGI application named `app`.