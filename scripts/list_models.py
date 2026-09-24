"""Print the model ids available to your Nebius Token Factory key (needs NEBIUS_API_KEY)."""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"),
                api_key=os.environ["NEBIUS_API_KEY"])
ids = sorted(m.id for m in client.models.list())
for i in ids:
    print(i)
print(f"{len(ids)} models; nvidia/*:", [i for i in ids if i.startswith("nvidia/")])
