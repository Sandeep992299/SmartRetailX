import os
import io
import json
import boto3
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SENDER = os.getenv("SES_SENDER_EMAIL", "dissanayakesandeep@gmail.com")
RECIPIENT = os.getenv("SES_RECIPIENT_EMAIL", "dissanayakesandeep@gmail.com")

ses = boto3.client("ses", region_name=AWS_REGION)

def send_html_email(subject, html_content):
    res = ses.send_email(
        Source=SENDER,
        Destination={"ToAddresses": [RECIPIENT]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Html": {"Data": html_content}}
        }
    )
    print(f"Sent: '{subject}' -> MessageId: {res['MessageId']}")
    return res["MessageId"]

def send_pdf_email(subject, html_content, pdf_bytes, pdf_name):
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = SENDER
    msg['To'] = RECIPIENT
    
    msg_body = MIMEMultipart('alternative')
    msg_body.attach(MIMEText(html_content, 'html'))
    msg.attach(msg_body)
    
    pdf_part = MIMEApplication(pdf_bytes, Name=pdf_name)
    pdf_part['Content-Disposition'] = f'attachment; filename="{pdf_name}"'
    msg.attach(pdf_part)
    
    res = ses.send_raw_email(
        Source=SENDER,
        Destinations=[RECIPIENT],
        RawMessage={'Data': msg.as_string()}
    )
    print(f"Sent (with PDF): '{subject}' -> MessageId: {res['MessageId']}")
    return res["MessageId"]

def generate_pdf(orders):
    if not REPORTLAB_AVAILABLE:
        return b"SmartRetailX PDF Fallback Report"
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor('#1e1b4b'), spaceAfter=15)
    story.append(Paragraph("SmartRetailX Daily Sales Summary", title_style))
    story.append(Paragraph(f"Report Generated on: <b>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</b>", styles['Normal']))
    story.append(Spacer(1, 15))
    
    data = [["Order ID", "User ID", "Status", "Items", "Amount"]]
    total = 0.0
    for o in orders:
        amt = float(o.get('total_amount', 0))
        total += amt
        data.append([o['order_id'], o['user_id'], o['status'].upper(), str(len(o.get('items', []))), f"${amt:.2f}"])
    data.append(["TOTAL SALES", "", "", "", f"${total:.2f}"])
    
    t = Table(data, colWidths=[130, 130, 100, 80, 110])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4f46e5')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('BACKGROUND', (0,1), (-1,-2), colors.HexColor('#f9fafb')),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#e0e7ff')),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#e5e7eb')),
    ]))
    story.append(t)
    doc.build(story)
    return buffer.getvalue()

def run_tests():
    print(f"Testing All Email Types to: {RECIPIENT} via Amazon SES...")
    
    # 1. Low Stock Alert
    html1 = """
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #fee2e2; border-radius: 8px; padding: 24px;">
        <h2 style="color: #dc2626; margin-top: 0;">⚠️ Low Stock Critical Alert</h2>
        <p>The following product has dropped below the minimum reserve threshold:</p>
        <div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 12px; margin: 16px 0;">
            <strong>Product:</strong> Wireless Noise-Canceling Headphones<br>
            <strong>Stock Remaining:</strong> <span style="color: #dc2626; font-size: 18px; font-weight: bold;">3 units</span><br>
            <strong>Status:</strong> Immediate Restock Required
        </div>
        <p style="color: #6b7280; font-size: 12px;">SmartRetailX Inventory Automation · AWS us-east-1</p>
    </div>
    """
    send_html_email("⚠️ SmartRetailX Alert: Low Stock on 'Wireless Noise-Canceling Headphones' (3 units left)", html1)
    
    # 2. Order Confirmation Receipt
    html2 = """
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px;">
        <h2 style="color: #4f46e5; margin-top: 0;">🛍️ Order Confirmed #ORD-98431</h2>
        <p>Thank you for your order! Your payment was verified successfully.</p>
        <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
            <tr style="border-bottom: 2px solid #e5e7eb; text-align: left;">
                <th style="padding: 8px;">Item</th>
                <th style="padding: 8px;">Qty</th>
                <th style="padding: 8px;">Price</th>
            </tr>
            <tr style="border-bottom: 1px solid #f3f4f6;">
                <td style="padding: 8px;">Wireless Noise-Canceling Headphones</td>
                <td style="padding: 8px;">1</td>
                <td style="padding: 8px;">$299.99</td>
            </tr>
            <tr>
                <td style="padding: 8px;">Ergonomic Mechanical Keyboard</td>
                <td style="padding: 8px;">1</td>
                <td style="padding: 8px;">$129.50</td>
            </tr>
            <tr style="font-weight: bold; border-top: 2px solid #e5e7eb;">
                <td style="padding: 8px;" colspan="2">Total Paid</td>
                <td style="padding: 8px;">$429.49</td>
            </tr>
        </table>
        <p style="background: #f0fdf4; color: #166534; padding: 10px; border-radius: 6px;">
            <strong>Shipping to:</strong> No. 45, Galle Road, Colombo 03
        </p>
        <p style="color: #6b7280; font-size: 12px;">SmartRetailX Orders Engine · AWS us-east-1</p>
    </div>
    """
    send_html_email("🛍️ SmartRetailX Order Receipt #ORD-98431 ($429.49)", html2)
    
    # 3. Executive Daily Sales Summary with PDF
    orders = [
        {"order_id": "ORD-98428", "user_id": "USR-10254", "total_amount": 299.99, "status": "Paid", "items": [{"product_id": "PRD-01"}]},
        {"order_id": "ORD-98429", "user_id": "USR-10902", "total_amount": 129.50, "status": "Paid", "items": [{"product_id": "PRD-02"}]},
        {"order_id": "ORD-98430", "user_id": "USR-10114", "total_amount": 899.00, "status": "Paid", "items": [{"product_id": "PRD-03"}]},
        {"order_id": "ORD-98431", "user_id": "USR-10555", "total_amount": 429.49, "status": "Paid", "items": [{"product_id": "PRD-01"}, {"product_id": "PRD-02"}]}
    ]
    pdf_bytes = generate_pdf(orders)
    html3 = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px;">
        <h2 style="color: #1e1b4b; margin-top: 0;">📊 Executive Daily Sales Summary Report</h2>
        <p>Please find attached your daily sales breakdown and fulfillment turnover report for <strong>{datetime.utcnow().strftime('%B %d, %Y')}</strong>.</p>
        <div style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 16px; margin: 16px 0;">
            <strong>Total Orders:</strong> 4<br>
            <strong>Gross Turnover:</strong> <span style="color: #16a34a; font-size: 18px; font-weight: bold;">$1,757.98</span><br>
            <strong>System Fulfillment Rate:</strong> 100%
        </div>
        <p>The detailed transactional PDF audit log (<b>Daily_Orders_Report.pdf</b>) is attached to this email.</p>
        <p style="color: #6b7280; font-size: 12px;">SmartRetailX Executive Telemetry · AWS us-east-1</p>
    </div>
    """
    send_pdf_email("📊 SmartRetailX Executive Report: Daily Sales Summary & PDF Audit", html3, pdf_bytes, "Daily_Orders_Report.pdf")
    
    # 4. Out for Delivery Live Tracking Email
    html4 = """
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #bbf7d0; border-radius: 8px; padding: 24px;">
        <h2 style="color: #166534; margin-top: 0;">🚚 Order #ORD-98431 is Out for Delivery!</h2>
        <p>Your package has been dispatched from our Colombo Central Distribution Hub.</p>
        <div style="background: #f0fdf4; border-left: 4px solid #16a34a; padding: 12px; margin: 16px 0;">
            <strong>Assigned Courier:</strong> Ruwan Perera (#LK-4029)<br>
            <strong>Destination:</strong> Galle Coastal Hub<br>
            <strong>Estimated Delivery:</strong> ⏱️ 45 mins
        </div>
        <p style="color: #6b7280; font-size: 12px;">SmartRetailX Fleet Tracking · AWS us-east-1</p>
    </div>
    """
    send_html_email("🚚 Out for Delivery: Order #ORD-98431 · Sri Lanka Express Fleet", html4)
    
    print("\nAll 4 email types successfully dispatched via Amazon SES!")

if __name__ == "__main__":
    run_tests()
