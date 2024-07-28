import os
from pathlib import Path

from dotenv import load_dotenv

dotenv_path = Path(Path(__file__).parent) / "../../.env"
load_dotenv(dotenv_path)
db_path = Path(__file__).parent / "db/"
test_db_path = Path(__file__).parent / "db/test"

BOT_TOKEN = os.environ.get("BOT_TOKEN")

BOT_TOKEN_ARRAY = os.environ.get("TOKEN_ARRAY")
