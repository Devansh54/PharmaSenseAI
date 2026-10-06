import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from pharmasense.db.source_schema import Base
from pharmasense.data.ingest.import_csvs import import_all_csvs
from pharmasense.retrieval.ingestion import run_ingestion
from pharmasense.retrieval.embeddings import BGEEmbedder
from pharmasense.config import EMBEDDING_DIM
import logging

logging.basicConfig(level=logging.INFO)

db_url = os.environ.get(
    "EVAL_DATABASE_URL",
    os.environ.get(
        "PHARMASENSE_TEST_DATABASE_URL",
        "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense_test",
    ),
)

engine = create_engine(db_url)
print(f"Bootstrapping DB: {db_url}")

print("Creating extensions and schema...")
with engine.begin() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

print("Importing CSV data...")
import_all_csvs(engine)

print("Ingesting research documents (RAG)...")
session_local = sessionmaker(bind=engine)
with session_local() as session:
    embedder = BGEEmbedder()
    run_ingestion(session, embedder)

print("Bootstrap complete.")
