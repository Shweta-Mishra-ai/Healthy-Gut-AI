import os
import sys

# Add parent directory to path to import main
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mangum import Mangum
from main import app

# Wrap FastAPI app for serverless
handler = Mangum(app, lifespan="off")
