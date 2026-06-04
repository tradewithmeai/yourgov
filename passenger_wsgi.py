import os
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Vercel-only analytics should not be injected on Krystal/Passenger.
os.environ.setdefault("ANALYTICS_DISABLED", "1")

from app import app as application  # noqa: E402

