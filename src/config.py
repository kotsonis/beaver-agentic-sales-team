# ------------------------------------------------------------------------
# config.py
# contains the definition of the model and loads the relevant API Key and URL
# defined here so that we can import in different places
# 2026-01-05 - S. Kotsonis
# ------------------------------------------------------------------------
import os
import dotenv
from smolagents import OpenAIServerModel

dotenv.load_dotenv()

model = OpenAIServerModel(
    model_id="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    api_base=os.getenv("OPENAI_BASE_URL"),
)