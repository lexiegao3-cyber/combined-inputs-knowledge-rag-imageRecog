import os

def create_demo_pdf():
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError:
        print("ReportLab is not installed. To generate real binary PDFs locally, run: pip install reportlab")
        print("Alternatively, you can keep testing your backend pipeline using the .txt files!")
        return

    pdf_path = "./demo_inputs/scenario_b_vietnam_delay.pdf"
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

    # Initialize PDF document
    doc = SimpleDocTemplate(pdf_path, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], spaceAfter=15)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], leading=14, spaceAfter=8)

    # Building document text flow (Simulating messy OCR text from an overseas port)
    story.append(Paragraph("<b>PORT RE-ROUTING & BILL OF LADING MANIFEST</b>", title_style))
    story.append(Spacer(1, 10))
    
    text_blocks = [
        "ORGANIZATION_ID: org_midmarket_01",
        "DOCUMENT_ID: doc_manifest_5512_ERR",
        "SOURCE_TYPE: PDF_SCAN_OCR",
        "INGESTED_AT: 2026-06-09T16:40:00Z",
        "--------------------------------------------------------------------------------",
        "<b>[SYSTEM PROCESSING NOTE: CRITICAL SCAN WARNING - LOW OPTICAL RESOLUTION]</b>",
        "<b>AI_CONFIDENCE_ESTIMATE: 0.55</b> (Text artifacts detected, parts of headers are unreadable)",
        "--------------------------------------------------------------------------------",
        "CARRIER: Maersk Line Inter-Asia",
        "ORIGIN_PORT: Port of Hai Phong (VNHPH)",
        "DESTINATION_PORT: Port of Rotterdam (NLRTM)",
        "EXPECTED_ARRIVAL: [SMUDGED TEXT - UNABLE TO READ YEAR]",
        "SKU_AFFECTED: SKU-1102-CHEMICALS",
        "ESTIMATED_COST_USD: 4200.00",
        "",
        "<b>LOGISTICS STATUS UPDATE (TIẾNG VIỆT):</b>",
        "Sự chậm trễ nghiêm trọng tại cảng Hải Phong. Tàu vận chuyển Maersk Line gặp sự cố thủ tục hành chính hải quan.",
        "Xảy ra tình trạng tắc nghẽn nghiêm trọng (Port Congestion) tại bến cảng khiến container chưa thể bốc dỡ lên tàu đúng hạn.",
        "",
        "<b>COMPLIANCE AUDIT FLAG:</b>",
        "REGULATORY BODY: European Maritime Safety Agency",
        "ITEM_ID: comp_992",
        "TYPE: DOCUMENTATION_CHECK",
        "STATUS: WARNING",
        "SEVERITY: MEDIUM",
        "DESCRIPTION: Missing verified gross mass (VGM) certificate compliance seal due to local system offline issues.",
        "",
        "<b>ROUTING TRIGGER:</b>",
        "ACTION_ID: act_sap_883",
        "TARGET_SYSTEM: sap",
        "ACTION_TYPE: UPDATE_RECORD",
        "SUMMARY: Hold chemical inventory batch until documentation status is verified by human customs controller.",
        "STATUS: PENDING"
    ]

    for block in text_blocks:
        story.append(Paragraph(block, body_style))

    doc.build(story)
    print(f"Successfully compiled binary test file: {pdf_path}")

if __name__ == "__main__":
    create_demo_pdf()