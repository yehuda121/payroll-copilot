import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

path = pathlib.Path(
    r"C:\Users\yehud\.cursor\projects\c-Users-yehud-Desktop-payroll-copilot"
    r"\agent-transcripts\143a9150-1935-4fb1-b66f-e422c0a2bd87"
    r"\143a9150-1935-4fb1-b66f-e422c0a2bd87.jsonl"
)
out_dir = pathlib.Path("_audit/recovered")
out_dir.mkdir(parents=True, exist_ok=True)

want = {
    "document_model.py",
    "document_builder.py",
    "document_projector.py",
    "review_dto.py",
    "document_editor.py",
    "document_freeze.py",
    "document_payload_entries.py",
    "extraction_l0_tokenize.py",
    "presentation_safe_keys.py",
}

latest: dict[str, str] = {}
materializer_hits = 0

with path.open("r", encoding="utf-8") as f:
    for line in f:
        if "document_review_materializer" in line:
            materializer_hits += 1
        if '"name":"Write"' not in line and '"name": "Write"' not in line:
            # json may have spaces
            if "Write" not in line or "contents" not in line:
                continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        for part in obj.get("message", {}).get("content", []):
            if part.get("type") != "tool_use" or part.get("name") != "Write":
                continue
            inp = part.get("input") or {}
            wp = str(inp.get("path") or "")
            contents = inp.get("contents")
            if not isinstance(contents, str):
                continue
            base = wp.replace("\\", "/").split("/")[-1]
            if base in want or "materializer" in base:
                latest[base] = contents
                (out_dir / base).write_text(contents, encoding="utf-8")
                print(f"WROTE {base} bytes={len(contents)}")

print("materializer_line_hits", materializer_hits)
print("recovered", sorted(latest))
