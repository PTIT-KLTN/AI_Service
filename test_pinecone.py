from dotenv import load_dotenv
import os
from pinecone import Pinecone

load_dotenv()  # đọc .env ở project root

api = os.getenv("PINECONE_API_KEY")
if not api:
    raise SystemExit("Missing PINECONE_API_KEY. Set env var or create .env")

index_name = os.getenv("PINECONE_INDEX", "knowledge-base")

pc = Pinecone(api_key=api)
print("Indexes:", pc.list_indexes())
idx = pc.Index(index_name)
print(idx.describe_index_stats())