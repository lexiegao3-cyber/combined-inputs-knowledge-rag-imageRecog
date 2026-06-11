import os
import glob
import hashlib
import re
import json
from typing import Dict, Any, List
from src.multimodal import extract_image_text, transcribe_audio
from src.pipeline import init_db
from src.rag_pipeline import run_rag_pipeline

# --- Configuration Constants ---
INPUT_DIRECTORY = "./demo_inputs"

# Simulate ElastiCache Redis deduplication map
_local_redis_dedup_cache: Dict[str, str] = {}

# ---------------------------------------------------------------------------
# Security: Automated PII Masking Engine
# ---------------------------------------------------------------------------

def redact_sensitive_pii(text_content: str) -> str:
    """
    Guards heavily restricted employee fields (SSN, Routing numbers, explicit values)
    by running a localized regex masking pass before sending data to the AI agent layer.
    """
    # Mask US Social Security Numbers (SSN) / National IDs
    text_content = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_NATIONAL_ID]', text_content)
    # Mask Standard Bank Routing Numbers (9 digits)
    text_content = re.sub(r'\b\d{9}\b', '[REDACTED_BANK_ROUTING_NUMBER]', text_content)
    # Mask Explicit Credit Card Sequences
    text_content = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[REDACTED_PAYMENT_CARD]', text_content)
    
    return text_content

# ---------------------------------------------------------------------------
# Data Drivers: Multi-Format Extraction Core
# ---------------------------------------------------------------------------

def extract_flat_files(file_path: str) -> str:
    """Handles .TXT, .CSV data like tracking sheets and general ledgers."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def extract_pdf_and_images(file_path: str) -> str:
    """Handles portable documents, supply chain manifests, and scans."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in [".jpeg", ".jpg", ".png", ".tiff", ".tif", ".webp"]:
        return extract_image_text(file_path)

    try:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        return "\n".join([page.extract_text() or "" for page in reader.pages])
    except ImportError:
        logger_warn("pypdf wrapper missing. Simulating vision text layout extraction.")
        return f"[OCR Manifest Scan Object: {os.path.basename(file_path)}]"

def extract_excel_sheets(file_path: str) -> str:
    """Handles inventory counts, AP/AR, and macro-enabled .XLSM sheets."""
    try:
        import pandas as pd
        # Read all sheets natively to preserve multi-account context matrices
        xl = pd.ExcelFile(file_path)
        combined_text = []
        for sheet in xl.sheet_names:
            df = xl.parse(sheet)
            combined_text.append(f"--- Sheet: {sheet} ---\n{df.to_string()}")
        return "\n".join(combined_text)
    except ImportError:
        logger_warn("pandas/openpyxl missing. Reading data stream via flat string projection.")
        return f"[Structured Spreadsheet Matrix Stream: {os.path.basename(file_path)}]"

def extract_word_documents(file_path: str) -> str:
    """Handles corporate legal agreements and contract histories."""
    try:
        import docx
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    except ImportError:
        return f"[Structured Word Document Text block: {os.path.basename(file_path)}]"

def extract_structured_json_api(file_path: str) -> str:
    """Handles NoSQL document stores, CRM parameters, and clickstream JSON logs."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return json.dumps(data, indent=2)

def extract_audio_transcripts(file_path: str) -> str:
    """Handles blob audio recording streams (.MP3, .WAV) from user tickets."""
    return transcribe_audio(file_path)

# ---------------------------------------------------------------------------
# Orchestration: Ingestion Routing Router
# ---------------------------------------------------------------------------

def calculate_file_hash(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def logger_warn(msg: str):
    print(f"   ⚠️  [Driver Alert] {msg}")

def run_multi_format_ingestion_gateway():
    """
    Main entry point scanning your local workspace folder. Runs format 
    detection routing, PII scrub filters, and dispatches streams to the pipeline.
    """
    init_db()
    print("=== [ENTERPRISE INGESTION GATEWAY] Service Active ===")
    print(f"[*] Monitoring local multi-format channel target: '{INPUT_DIRECTORY}'\n")

    if not os.path.exists(INPUT_DIRECTORY):
        os.makedirs(INPUT_DIRECTORY)
        return

    # Scan for all incoming files across structured, unstructured, and blob allocations
    discovered_files = [f for f in glob.glob(os.path.join(INPUT_DIRECTORY, "*")) if os.path.isfile(f)]

    if not discovered_files:
        print("[-] Gateway status: Idle. No business documents discovered in input queues.")
        return

    print(f"[*] Discovered {len(discovered_files)} distinct objects waiting in ingestion queue.")

    for file_path in discovered_files:
        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()
        
        print(f"\n--- Processing Ingestion Event: {filename} ({ext.upper()}) ---")

        # 1. Deduplication Filter (ElastiCache Redis Emulation)
        file_hash = calculate_file_hash(file_path)
        if file_hash in _local_redis_dedup_cache:
            print(f"   [Cache Hit] Signature match verified. Skipping redundant run.")
            continue

        # 2. Driver Routing Logic Mapping
        extracted_raw_text = ""
        if ext in [".txt", ".csv", ".log"]:
            extracted_raw_text = extract_flat_files(file_path)
        elif ext in [".pdf", ".jpeg", ".jpg", ".png", ".tiff", ".tif", ".webp"]:
            extracted_raw_text = extract_pdf_and_images(file_path)
        elif ext in [".xlsx", ".xlsm"]:
            extracted_raw_text = extract_excel_sheets(file_path)
        elif ext in [".docx"]:
            extracted_raw_text = extract_word_documents(file_path)
        elif ext in [".json"]:
            extracted_raw_text = extract_structured_json_api(file_path)
        elif ext in [".mp3", ".wav"]:
            extracted_raw_text = extract_audio_transcripts(file_path)
        else:
            print(f"   ❌ [Driver Error] No compatible parser driver mapped for extension '{ext}'. Skipping object.")
            continue

        if not extracted_raw_text.strip():
            print(f"   ❌ [Parser Error] Extracted content payload empty.")
            continue

        # 3. Security Scrub Layer Pass
        print("   [*] Running automated security PII redaction filters...")
        scrubbed_payload = redact_sensitive_pii(extracted_raw_text)

        # 4. Amazon SQS Virtual Decoupled Transfer Loop
        print("   [+] Appending message metadata to SQS virtual decoupled queue channel...")
        print("   [+] Forwarding clean data stream to core validation pipeline...")
        
        pipeline_run = run_rag_pipeline(
            scrubbed_payload,
            {
                "filename": filename,
                "source_type": ext.lstrip(".").upper() or "RAW_DOCUMENT",
                "document_id": f"doc-{file_hash[:12]}",
            },
        )

        # 5. Cache Sync Commit Check
        if pipeline_run.success:
            _local_redis_dedup_cache[file_hash] = filename
            print(f"   ✅ [Ingestion Success] Transferred safely to DB run ID: {pipeline_run.run_id}")
        else:
            print(f"   ❌ [Downstream Intercept] Pipeline stopped processing data.")
            if hasattr(pipeline_run, "output_data") and pipeline_run.output_data:
                print(f"      Reason Details: {pipeline_run.output_data}")

    print("\n=== [ENTERPRISE INGESTION GATEWAY] Process Execution Run Concluded ===")

if __name__ == "__main__":
    run_multi_format_ingestion_gateway()
