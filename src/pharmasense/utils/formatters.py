import csv
import io
import json
from typing import Any

def compact_tool_result(result_raw: Any) -> str:
    """
    Compacts verbose JSON tool results into a denser CSV/Markdown-like format where safe.
    Preserves raw JSON for scalar values, errors, or unstructured objects.
    """
    if isinstance(result_raw, dict):
        if "results" in result_raw and "columns" in result_raw:
            # Looks like a SQL tabular result
            cols = result_raw["columns"]
            rows = result_raw["results"]
            error = result_raw.get("error")

            if error:
                return json.dumps({"error": error})

            if not rows:
                return "No results found."

            # Render as CSV
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(cols)
            for row in rows:
                # Handle possible missing keys gracefully, though they shouldn't be missing
                writer.writerow([row.get(c, "") for c in cols])
            return out.getvalue()

        elif "chunks" in result_raw:
            # Looks like a vector search result
            chunks = result_raw["chunks"]
            if not chunks:
                return "No chunks found."

            lines = []
            for chunk in chunks:
                chunk_id = chunk.get("chunk_id", "Unknown")
                doc_title = chunk.get("title", "Unknown")
                text = chunk.get("chunk_text", "")
                score = chunk.get("similarity_score", 0.0)
                lines.append(f"--- Chunk ID: {chunk_id} | Doc: {doc_title} | Score: {score:.3f} ---\n{text}\n")
            return "\n".join(lines)

    return json.dumps(result_raw)
