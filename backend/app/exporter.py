import docx
from docx.shared import Pt, RGBColor
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from io import BytesIO
from datetime import datetime

# Helper to clean simple markdown markers for PDF/DOCX styling
def clean_markdown_formatting(text: str) -> str:
    # Convert standard markdown bold **text** to reportlab HTML-like tags <b>text</b>
    # and clean double/single asterisks
    parts = text.split('**')
    res = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            res.append(f"<b>{part}</b>")
        else:
            res.append(part)
    text = "".join(res)
    
    # Handle single asterisks for italics
    parts = text.split('*')
    res = []
    for idx, part in enumerate(parts):
        if idx % 2 == 1:
            res.append(f"<i>{part}</i>")
        else:
            res.append(part)
    return "".join(res)

def export_brief_to_docx(sections: list) -> BytesIO:
    doc = docx.Document()
    
    # Configure document base styling
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial'
    font.size = Pt(10.5)
    
    # Cover title
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(120)
    title_p.paragraph_format.space_after = Pt(6)
    run = title_p.add_run("Project Intelligence Brief")
    run.font.size = Pt(28)
    run.font.bold = True
    run.font.color.rgb = RGBColor(17, 24, 39) # hex #111827
    
    subtitle_p = doc.add_paragraph()
    sub_run = subtitle_p.add_run("LiveBrief System Source of Truth")
    sub_run.font.size = Pt(14)
    sub_run.font.color.rgb = RGBColor(99, 102, 241) # hex #6366F1
    
    meta_p = doc.add_paragraph()
    meta_p.paragraph_format.space_before = Pt(200)
    meta_run = meta_p.add_run(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}\nCreated by LiveBrief Agentic Service")
    meta_run.font.size = Pt(9.5)
    meta_run.font.color.rgb = RGBColor(107, 114, 128) # hex #6B7280
    
    doc.add_page_break()
    
    # Append sections
    for sec in sections:
        h = doc.add_heading(level=1)
        h.paragraph_format.space_before = Pt(20)
        h.paragraph_format.space_after = Pt(10)
        h_run = h.add_run(sec.section)
        h_run.font.name = 'Arial'
        h_run.font.size = Pt(18)
        h_run.font.bold = True
        h_run.font.color.rgb = RGBColor(30, 58, 138) # hex #1E3A8A
        
        lines = sec.content.split('\n')
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            
            # Simple markdown parsing
            if line_str.startswith('#'):
                level = len(line_str) - len(line_str.lstrip('#'))
                text = line_str.lstrip('#').strip()
                sub_h = doc.add_heading(level=min(level + 1, 4))
                sub_h.paragraph_format.space_before = Pt(12)
                sub_h.paragraph_format.space_after = Pt(4)
                sub_h_run = sub_h.add_run(text)
                sub_h_run.font.name = 'Arial'
                sub_h_run.font.bold = True
                sub_h_run.font.color.rgb = RGBColor(55, 65, 81) # hex #374151
            elif line_str.startswith('-') or line_str.startswith('*'):
                text = line_str[1:].strip()
                # Clean asterisks from bold text
                text = text.replace('**', '')
                p = doc.add_paragraph(text, style='List Bullet')
                p.paragraph_format.space_after = Pt(3)
            else:
                text = line_str.replace('**', '')
                p = doc.add_paragraph(text)
                p.paragraph_format.space_after = Pt(6)
                
    file_stream = BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream

def export_brief_to_pdf(sections: list) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        rightMargin=54, 
        leftMargin=54,
        topMargin=54, 
        bottomMargin=54
    )
    
    styles = getSampleStyleSheet()
    
    # Styled document variables
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=28,
        leading=34,
        textColor=colors.HexColor('#111827'),
        spaceAfter=8
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#6366F1'),
        spaceAfter=150
    )
    
    heading_style = ParagraphStyle(
        'SecHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E3A8A'),
        spaceBefore=22,
        spaceAfter=10,
        keepWithNext=True
    )
    
    subheading_style = ParagraphStyle(
        'SecSubheading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#374151'),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'SecBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=15,
        textColor=colors.HexColor('#374151'),
        spaceAfter=6
    )
    
    bullet_style = ParagraphStyle(
        'SecBullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=15,
        textColor=colors.HexColor('#374151'),
        leftIndent=15,
        spaceAfter=4
    )
    
    story = []
    
    # Title Cover Page
    story.append(Spacer(1, 100))
    story.append(Paragraph("Project Intelligence Brief", title_style))
    story.append(Paragraph("LiveBrief System Source of Truth", subtitle_style))
    story.append(Spacer(1, 50))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", body_style))
    story.append(Paragraph("Created by LiveBrief Agentic Document Intelligence Service", body_style))
    story.append(PageBreak())
    
    for sec in sections:
        story.append(Paragraph(sec.section, heading_style))
        
        lines = sec.content.split('\n')
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            
            clean_line = clean_markdown_formatting(line_str)
            
            if line_str.startswith('#'):
                text = line_str.lstrip('#').strip()
                story.append(Paragraph(text, subheading_style))
            elif line_str.startswith('-') or line_str.startswith('*'):
                text = line_str[1:].strip()
                clean_text = clean_markdown_formatting(text)
                story.append(Paragraph(f"&bull; {clean_text}", bullet_style))
            else:
                story.append(Paragraph(clean_line, body_style))
                
        story.append(Spacer(1, 8))
        
    doc.build(story)
    buffer.seek(0)
    return buffer
