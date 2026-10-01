import os
import shutil
from pathlib import Path

repo = Path(r"d:\PharmaSenseAI\PharmaSenseAI")
src = repo / "src" / "pharmasense"

print("Creating directories...")
directories = [
    "db", "data", "data/audit", "data/ingest", "llm", "retrieval", 
    "tools", "agents", "orchestration", "escalation", "validation", "observability", "api", "ui"
]
for d in directories:
    (src / d).mkdir(parents=True, exist_ok=True)

(repo / "src" / "__init__.py").touch(exist_ok=True)
(src / "__init__.py").touch(exist_ok=True)
(src / "db" / "__init__.py").touch(exist_ok=True)
(src / "data" / "__init__.py").touch(exist_ok=True)
(src / "data" / "audit" / "__init__.py").touch(exist_ok=True)
(src / "data" / "ingest" / "__init__.py").touch(exist_ok=True)
(src / "llm" / "__init__.py").touch(exist_ok=True)
(src / "retrieval" / "__init__.py").touch(exist_ok=True)

print("Moving alembic...")
if (repo / "phase1" / "alembic").exists():
    shutil.move(str(repo / "phase1" / "alembic"), str(repo / "migrations"))

print("Merging config files...")
config_content = '"""Central configuration for PharmaSenseAI."""\n\n'
for phase in ["phase1", "phase2", "phase3"]:
    cfg = repo / phase / "config.py"
    if cfg.exists():
        with open(cfg, "r") as f:
            config_content += f"\n# --- {phase} ---\n" + f.read()
with open(src / "config.py", "w") as f:
    f.write(config_content)

print("Moving database models...")
if (repo / "phase1" / "db" / "models.py").exists():
    shutil.move(str(repo / "phase1" / "db" / "models.py"), str(src / "db" / "source_schema.py"))
if (repo / "phase3" / "db" / "models.py").exists():
    shutil.move(str(repo / "phase3" / "db" / "models.py"), str(src / "db" / "models.py"))

print("Moving phase files...")
if (repo / "phase1" / "provenance.py").exists():
    shutil.move(str(repo / "phase1" / "provenance.py"), str(src / "data" / "provenance.py"))
if (repo / "phase1" / "schemas.py").exists():
    shutil.move(str(repo / "phase1" / "schemas.py"), str(src / "contracts.py"))
if (repo / "phase1" / "ingestion").exists():
    for file in (repo / "phase1" / "ingestion").glob("*.py"):
        shutil.move(str(file), str(src / "data" / "ingest" / file.name))
if (repo / "phase1" / "audit").exists():
    for file in (repo / "phase1" / "audit").glob("*.py"):
        shutil.move(str(file), str(src / "data" / "audit" / file.name))

if (repo / "phase2" / "llm").exists():
    for file in (repo / "phase2" / "llm").glob("*.py"):
        shutil.move(str(file), str(src / "llm" / file.name))

phase3_retrieval_files = ["baseline.py", "chunking.py", "embeddings.py", "ingestion.py", "references.py", "retrieval.py"]
for f in phase3_retrieval_files:
    path = repo / "phase3" / f
    if path.exists():
        shutil.move(str(path), str(src / "retrieval" / f))

if (repo / "phase3" / "golden_set.json").exists():
    (repo / "evals").mkdir(exist_ok=True)
    shutil.move(str(repo / "phase3" / "golden_set.json"), str(repo / "evals" / "golden_set.json"))

print("Updating alembic.ini...")
alembic_ini = repo / "alembic.ini"
if alembic_ini.exists():
    content = alembic_ini.read_text()
    content = content.replace("script_location = phase1/alembic", "script_location = migrations")
    alembic_ini.write_text(content)

print("Updating imports in Python files...")
def update_imports(filepath):
    if "site-packages" in str(filepath) or ".venv" in str(filepath): return
    try:
        content = filepath.read_text(encoding="utf-8")
        original = content
        
        # General module replacements
        content = content.replace("pharmasense.db.source_schema", "pharmasense.db.source_schema")
        content = content.replace("pharmasense.db.models", "pharmasense.db.models")
        
        content = content.replace("pharmasense.config", "pharmasense.config")
        content = content.replace("pharmasense.config", "pharmasense.config")
        content = content.replace("pharmasense.config", "pharmasense.config")
        
        content = content.replace("pharmasense.data.provenance", "pharmasense.data.provenance")
        content = content.replace("pharmasense.contracts", "pharmasense.contracts")
        content = content.replace("pharmasense.data.ingest", "pharmasense.data.ingest")
        content = content.replace("pharmasense.data.audit", "pharmasense.data.audit")
        
        content = content.replace("pharmasense.llm", "pharmasense.llm")
        
        content = content.replace("pharmasense.retrieval.baseline", "pharmasense.retrieval.baseline")
        content = content.replace("pharmasense.retrieval.chunking", "pharmasense.retrieval.chunking")
        content = content.replace("pharmasense.retrieval.embeddings", "pharmasense.retrieval.embeddings")
        content = content.replace("pharmasense.retrieval.ingestion", "pharmasense.retrieval.ingestion")
        content = content.replace("pharmasense.retrieval.references", "pharmasense.retrieval.references")
        content = content.replace("pharmasense.retrieval.retrieval", "pharmasense.retrieval.retrieval")
        content = content.replace("pharmasense.db", "pharmasense.db")
        
        if original != content:
            filepath.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"Failed to read {filepath}: {e}")

for file in repo.rglob("*.py"):
    update_imports(file)

print("Updating migrations env.py...")
env_py = repo / "migrations" / "env.py"
if env_py.exists():
    content = env_py.read_text(encoding="utf-8")
    content = content.replace("from pharmasense.db.source_schema import Base", "from pharmasense.db.source_schema import Base\nfrom pharmasense.db.models import DocumentChunk")
    env_py.write_text(content, encoding="utf-8")

print("Removing empty old phase directories...")
for phase in ["phase1", "phase2", "phase3"]:
    d = repo / phase
    if d.exists():
        # Remove empty directories inside
        for root, dirs, files in os.walk(d, topdown=False):
            for name in dirs:
                try: os.rmdir(os.path.join(root, name))
                except OSError: pass
        try: os.rmdir(d)
        except OSError: print(f"Could not remove {d}, might not be empty.")

print("Done.")
