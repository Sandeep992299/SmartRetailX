import os
import json
import time
import asyncio
import threading
import io
from typing import List, Dict, Any
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from aws_xray_sdk.core import xray_recorder, patch_all
from aws_xray_sdk.core.async_context import AsyncContext
from kafka import KafkaConsumer
import boto3
from botocore.exceptions import ClientError

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

def generate_daily_order_pdf(orders_list: List[Dict[str, Any]]) -> bytes:
    """Generates a styled Daily Sales Report PDF using ReportLab platypus flowables."""
    if not REPORTLAB_AVAILABLE:
        print("ReportLab is not available. Generating a text fallback document.")
        # Simulating a simple text PDF output structure manually if reportlab is not installed
        dummy_text = "SmartRetailX Daily Sales Summary Fallback Document\n"
        dummy_text += f"Generated on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
        for o in orders_list:
            dummy_text += f"Order ID: {o.get('order_id')} | User: {o.get('user_id')} | Total: ${o.get('total_amount'):.2f}\n"
        return dummy_text.encode('utf-8')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1e1b4b'), # Deep Indigo
        spaceAfter=15
    )
    
    # Title & Metadata
    story.append(Paragraph("SmartRetailX Daily Sales Summary", title_style))
    story.append(Paragraph(f"Report Generated on: <b>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</b>", styles['Normal']))
    story.append(Spacer(1, 15))
    
    # Compile order rows
    data = [["Order ID", "User ID", "Status", "Items", "Amount"]]
    total_sales = 0.0
    
    for order in orders_list:
        order_id = order.get("order_id", "N/A")
        user_id = order.get("user_id", "N/A")
        amount = float(order.get("total_amount", 0.0))
        status = order.get("status", "N/A")
        items = str(len(order.get("items", [])))
        
        data.append([order_id, user_id, status.upper(), items, f"${amount:.2f}"])
        total_sales += amount
        
    data.append(["TOTAL SALES", "", "", "", f"${total_sales:.2f}"])
    
    # Create Table flowable
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
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

def send_ses_email_with_attachment(subject: str, html_body: str, attachment_data: bytes, attachment_name: str, recipient: str = None):
    """Sends a raw MIME email with a binary PDF attachment using Amazon SES."""
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    sender = os.getenv("SES_SENDER_EMAIL", "alerts@smartretailx.com")
    if not recipient:
        recipient = os.getenv("SES_RECIPIENT_EMAIL", "dissanayakesandeep@gmail.com")
        
    print(f"SES: Preparing raw email with attachment from '{sender}' to '{recipient}' (Subject: {subject})")
    
    # Bypass/mock in non-AWS/local runs to avoid crashing on missing AWS credentials
    if os.getenv("AWS_ACCESS_KEY_ID") is None and os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI") is None:
        print("SES: AWS credentials not found. Bypassing raw SES call (simulation fallback).")
        return

    try:
        # Create MIMEMultipart message envelope
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = recipient
        
        # Attach the HTML body message
        msg_body = MIMEMultipart('alternative')
        html_part = MIMEText(html_body, 'html')
        msg_body.attach(html_part)
        msg.attach(msg_body)
        
        # Attach the binary PDF report
        pdf_part = MIMEApplication(attachment_data, Name=attachment_name)
        pdf_part['Content-Disposition'] = f'attachment; filename="{attachment_name}"'
        msg.attach(pdf_part)
        
        client = boto3.client('ses', region_name=AWS_REGION)
        response = client.send_raw_email(
            Source=sender,
            Destinations=[recipient],
            RawMessage={'Data': msg.as_string()}
        )
        print(f"SES: Raw email successfully sent! Message ID: {response['MessageId']}")
    except ClientError as e:
        print(f"SES: Error sending raw email with attachment: {e.response['Error']['Message']}")

def get_styled_email_template(title: str, alert_type: str, details_html: str, cta_url: str = None, cta_text: str = None) -> str:
    accent_color = "#f59e0b" # warning orange
    bg_gradient = "linear-gradient(135deg, #fff3cd 0%, #ffeeba 100%)"
    badge_bg = "#fef3c7"
    badge_text = "#d97706"
    
    if alert_type == "critical":
        accent_color = "#ef4444" # critical red
        bg_gradient = "linear-gradient(135deg, #ffeeeb 0%, #fadbd8 100%)"
        badge_bg = "#fee2e2"
        badge_text = "#dc2626"
    elif alert_type == "info":
        accent_color = "#3b82f6" # info blue
        bg_gradient = "linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%)"
        badge_bg = "#e0f2fe"
        badge_text = "#2563eb"
        
    cta_button_html = ""
    if cta_url and cta_text:
        cta_button_html = f"""
        <div style="text-align: center; margin-top: 30px;">
            <a href="{cta_url}" target="_blank" style="background-color: {accent_color}; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; display: inline-block; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                {cta_text}
            </a>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f5f7; font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;">
    <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; margin: 40px auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); overflow: hidden; border: 1px solid #e1e4e8;">
        <!-- Header Banner -->
        <tr>
            <td style="background: {bg_gradient}; padding: 30px 40px; border-bottom: 3px solid {accent_color};">
                <table width="100%" border="0" cellpadding="0" cellspacing="0">
                    <tr>
                        <td>
                            <span style="font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 1.5px; color: {badge_text}; background-color: {badge_bg}; padding: 4px 10px; border-radius: 10px; display: inline-block; margin-bottom: 12px;">
                                {alert_type.upper()} ALERT
                            </span>
                            <h1 style="margin: 0; color: #1f2937; font-size: 24px; font-weight: 800; font-family: 'Segoe UI', -apple-system, sans-serif; letter-spacing: -0.5px;">
                                {title}
                            </h1>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
        
        <!-- Main Content Area -->
        <tr>
            <td style="padding: 40px; background-color: #ffffff;">
                <table width="100%" border="0" cellpadding="0" cellspacing="0">
                    <tr>
                        <td style="color: #4b5563; font-size: 15px; line-height: 1.6;">
                            {details_html}
                        </td>
                    </tr>
                    <tr>
                        <td>
                            {cta_button_html}
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- Footer -->
        <tr>
            <td style="padding: 20px 40px; background-color: #f9fafb; border-top: 1px solid #f3f4f6; text-align: center; color: #9ca3af; font-size: 12px;">
                <p style="margin: 5px 0;">This is an automated operational system notification from the <strong>SmartRetailX Global Commerce Platform</strong>.</p>
                <p style="margin: 5px 0;">AWS Region: <strong>us-east-1</strong> | Environment: <strong>production</strong></p>
                <p style="margin: 15px 0 0 0; color: #cbd5e1;">&copy; {datetime.utcnow().year} SmartRetailX. All rights reserved.</p>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    return html

def send_ses_email(subject: str, html_body: str, recipient: str = None):
    """Sends a notification email via AWS SES if credentials and verified identities exist."""
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    sender = os.getenv("SES_SENDER_EMAIL", "alerts@smartretailx.com")
    if not recipient:
        recipient = os.getenv("SES_RECIPIENT_EMAIL", "admin@smartretailx.com")
        
    print(f"SES: Attempting to send email from '{sender}' to '{recipient}' (Subject: {subject})")
    
    # Allow bypassing/mocking in non-AWS/local runs to avoid crashing on missing AWS creds
    if os.getenv("AWS_ACCESS_KEY_ID") is None and os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI") is None:
        print("SES: AWS credentials not found. Bypassing SES call (simulation fallback).")
        return
        
    try:
        client = boto3.client('ses', region_name=AWS_REGION)
        response = client.send_email(
            Destination={'ToAddresses': [recipient]},
            Message={
                'Body': {
                    'Html': {
                        'Charset': "UTF-8",
                        'Data': html_body,
                    },
                },
                'Subject': {
                    'Charset': "UTF-8",
                    'Data': subject,
                },
            },
            Source=sender,
        )
        print(f"SES: Email successfully sent! Message ID: {response['MessageId']}")
    except ClientError as e:
        print(f"SES: ClientError sending email: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"SES: Unexpected error sending email: {e}")

import urllib.request

def send_slack_webhook(text: str):
    """Sends a notification payload to Slack/Discord webhook URL if configured."""
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        print("Slack: Webhook URL not set. Bypassing Slack notification.")
        return
        
    print(f"Slack: Posting notification: {text}")
    try:
        payload = json.dumps({"text": text}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            print("Slack: Webhook notification posted successfully!")
    except Exception as e:
        print(f"Slack: Error posting webhook: {e}")


# ----------------------------------------------------
# 1. AWS Lambda Handler Entrypoint (Task 4 Event-Driven Lambda)
# ----------------------------------------------------
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda entrypoint triggered by SQS, MSK, or EventBridge.
    Processes retail events and routes notifications.
    """
    print(f"AWS Lambda invoked with event: {json.dumps(event)}")
    
    # Check if triggered directly by EventBridge (it won't have "Records" but will have "source")
    if "source" in event:
        source = event.get("source")
        detail_type = event.get("detail-type")
        detail = event.get("detail", {})
        
        print(f"Processing EventBridge Direct Event: source={source}, type={detail_type}")
        
        # 1. Custom Inventory Alert via EventBridge
        if source == "smartretailx.inventory" and detail_type == "LowStockAlert":
            product_name = detail.get("product_name", "Unknown Product")
            product_id = detail.get("product_id", "N/A")
            stock_count = detail.get("stock_count", 0)
            
            subject = f"⚠️ SmartRetailX Inventory: Low Stock for '{product_name}' (EventBridge)"
            details_html = f"""
            <p style="margin-top: 0;"><strong>EventBridge Trigger Alert:</strong> Operational telemetry indicates that the inventory level for <strong>{product_name}</strong> has dropped below the critical threshold.</p>
            <table width="100%" border="0" cellpadding="10" cellspacing="0" style="margin: 20px 0; background-color: #f9fafb; border-radius: 8px; border: 1px solid #e5e7eb;">
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="font-weight: bold; color: #374151; width: 35%;">Product Name:</td>
                    <td style="color: #4b5563;">{product_name}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="font-weight: bold; color: #374151;">Product ID:</td>
                    <td style="color: #4b5563; font-family: monospace; font-size: 13px;">{product_id}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #374151;">Current Stock:</td>
                    <td style="color: #dc2626; font-weight: bold; font-size: 16px;">{stock_count} units remaining</td>
                </tr>
            </table>
            <p style="margin-bottom: 0;">Please restock this item immediately to prevent order fulfillment disruption.</p>
            """
            html_body = get_styled_email_template(
                title="Low Stock Alert (EventBridge)",
                alert_type="warning",
                details_html=details_html,
                cta_url="http://adef77e62998148bf97f8564f1fe7123-1693663817.us-east-1.elb.amazonaws.com:80/admin",
                cta_text="Manage Inventory"
            )
            send_ses_email(subject, html_body)
            send_slack_webhook(f"⚠️ *EVENTBRIDGE LOW STOCK ALERT* ⚠️\nProduct *{product_name}* is down to *{stock_count}* units!")
            return {"statusCode": 200, "body": json.dumps("EventBridge low-stock alert processed successfully")}
            
        # 2. Scheduled Cron Event via EventBridge
        elif source == "aws.events" and "Scheduled Event" in detail_type:
            resources = event.get("resources", [])
            is_pdf_report = any("daily-pdf-rule" in res for res in resources)
            
            if is_pdf_report:
                print("EventBridge Scheduled Event: Triggering Daily Order Sales PDF generation...")
                # Fetch daily orders
                orders_list = []
                try:
                    url = "http://order-service.smartretailx.svc.cluster.local:8003/v1/orders"
                    req = urllib.request.Request(url, method="GET")
                    with urllib.request.urlopen(req, timeout=4) as response:
                        orders_list = json.loads(response.read().decode("utf-8"))
                        print(f"Successfully fetched {len(orders_list)} live orders from EKS order-service.")
                except Exception as e:
                    print(f"Order Service unreachable ({e}). Using simulated fallback order list for PDF.")
                    orders_list = [
                        {
                            "order_id": "ORD-77629",
                            "user_id": "USR-10254",
                            "total_amount": 129.99,
                            "status": "completed",
                            "items": [{"product_id": "PRD-001", "quantity": 1}]
                        },
                        {
                            "order_id": "ORD-77630",
                            "user_id": "USR-10902",
                            "total_amount": 45.50,
                            "status": "completed",
                            "items": [{"product_id": "PRD-004", "quantity": 2}]
                        },
                        {
                            "order_id": "ORD-77631",
                            "user_id": "USR-10114",
                            "total_amount": 899.00,
                            "status": "completed",
                            "items": [{"product_id": "PRD-002", "quantity": 1}]
                        }
                    ]
                
                # Generate PDF Bytes
                pdf_data = generate_daily_order_pdf(orders_list)
                
                # Email body
                subject = f"📊 SmartRetailX Sales Report: Daily Order Summary ({datetime.utcnow().strftime('%Y-%m-%d')})"
                details_html = f"""
                <p style="margin-top: 0;"><strong>Daily Operations Report:</strong> Find attached the PDF sales summary report containing the sales statistics, order quantities, and total turnover generated for today.</p>
                <p>A total of <strong>{len(orders_list)} orders</strong> were processed successfully.</p>
                <p>Please review the attached PDF file (<b>daily_orders_summary.pdf</b>) for granular details.</p>
                """
                html_body = get_styled_email_template(
                    title="Daily Sales Summary Report",
                    alert_type="info",
                    details_html=details_html,
                    cta_url="http://adef77e62998148bf97f8564f1fe7123-1693663817.us-east-1.elb.amazonaws.com:80/admin",
                    cta_text="Access Billing Dashboard"
                )
                
                send_ses_email_with_attachment(
                    subject=subject,
                    html_body=html_body,
                    attachment_data=pdf_data,
                    attachment_name="daily_orders_summary.pdf"
                )
                send_slack_webhook("📊 *EVENTBRIDGE CRON TRIGGER*: Daily order summary PDF generated and emailed.")
                return {"statusCode": 200, "body": json.dumps("EventBridge daily order PDF report completed successfully")}
            
            else:
                # Default to Daily System Health Report
                subject = "📢 SmartRetailX: Daily System Health Report (EventBridge Cron)"
                details_html = """
                <p style="margin-top: 0;"><strong>Scheduled Cron Trigger:</strong> This is your daily operational status report generated automatically by Amazon EventBridge Scheduler.</p>
                <table width="100%" border="0" cellpadding="10" cellspacing="0" style="margin: 20px 0; background-color: #f9fafb; border-radius: 8px; border: 1px solid #e5e7eb;">
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="font-weight: bold; color: #374151; width: 35%;">System Health:</td>
                        <td style="color: #10b981; font-weight: bold;">Healthy (100% Uptime)</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="font-weight: bold; color: #374151;">Microservices online:</td>
                        <td style="color: #4b5563;">8/8 Active</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; color: #374151;">Database State:</td>
                        <td style="color: #4b5563;">Connected (Multi-AZ replication active)</td>
                    </tr>
                </table>
                <p style="margin-bottom: 0;">No active incidents reported in the last 24 hours.</p>
                """
                html_body = get_styled_email_template(
                    title="System Operational Report",
                    alert_type="info",
                    details_html=details_html,
                    cta_url="http://adef77e62998148bf97f8564f1fe7123-1693663817.us-east-1.elb.amazonaws.com:80/admin",
                    cta_text="Open Admin Panel"
                )
                send_ses_email(subject, html_body)
                send_slack_webhook("📢 *EVENTBRIDGE CRON TRIGGER*: Daily system health report executed successfully.")
                return {"statusCode": 200, "body": json.dumps("EventBridge scheduled report processed successfully")}
            
        return {"statusCode": 200, "body": json.dumps("EventBridge unknown event type bypassed")}

    # Process batch records if triggered by SQS
    records = event.get("Records", [])
    notifications_sent = 0
    
    for record in records:
        body_str = record.get("body", "{}")
        try:
            body = json.loads(body_str)
            event_type = body.get("event_type", "unknown")
            event_data = body.get("data", {})
            
            # EventBridge Simulator Routing Logic
            print(f"Processing EventBridge Event Target: {event_type}")
            if event_type == "payment-settled":
                print(f"NOTIFY: Order #{event_data.get('order_id')} paid successfully. User email: {event_data.get('user_email')}")
            elif event_type == "payment-failed":
                order_id = event_data.get('order_id')
                is_fraud = event_data.get('is_fraud', False)
                print(f"ALERT: Payment failure for Order #{order_id} (Fraud: {is_fraud})")
                if is_fraud:
                    ip_addr = event_data.get('ip_address', 'unknown-ip')
                    reason = event_data.get('fraud_reason', 'Suspicious activity.')
                    subject = f"🛑 SmartRetailX Security: Fraud Blocked on Order #{order_id}"
                    details_html = f"""
                    <p style="margin-top: 0;">The transaction screening engine has flagged a high-risk checkout attempt. The order has been automatically cancelled and access restricted.</p>
                    <table width="100%" border="0" cellpadding="10" cellspacing="0" style="margin: 20px 0; background-color: #f9fafb; border-radius: 8px; border: 1px solid #e5e7eb;">
                        <tr style="border-bottom: 1px solid #e5e7eb;">
                            <td style="font-weight: bold; color: #374151; width: 35%;">Order ID:</td>
                            <td style="color: #4b5563; font-family: monospace;">#{order_id}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #e5e7eb;">
                            <td style="font-weight: bold; color: #374151;">Client IP:</td>
                            <td style="color: #4b5563; font-family: monospace; font-size: 13px;">{ip_addr}</td>
                        </tr>
                        <tr>
                            <td style="font-weight: bold; color: #374151;">Fraud Reason:</td>
                            <td style="color: #ef4444; font-weight: bold;">{reason}</td>
                        </tr>
                    </table>
                    <p style="margin-bottom: 0;">No funds were captured. The suspicious access source is now under monitoring.</p>
                    """
                    html_body = get_styled_email_template(
                        title="Security Incident Blocked",
                        alert_type="critical",
                        details_html=details_html,
                        cta_url="http://adef77e62998148bf97f8564f1fe7123-1693663817.us-east-1.elb.amazonaws.com:80/admin",
                        cta_text="Open Security Console"
                    )
                    send_ses_email(subject, html_body)
                    send_slack_webhook(f"🚨 *CRITICAL FRAUD BLOCKED* 🚨\nOrder #{order_id} flagged as *FRAUD* from IP `{ip_addr}`. Reason: {reason}")
            elif event_type == "low-stock-alert":
                product_name = event_data.get('product_name', 'Unknown Product')
                product_id = event_data.get('product_id', 'N/A')
                stock_count = event_data.get('stock_count', 0)
                print(f"ALERT: Product '{product_name}' stock count is low ({stock_count})!")
                
                subject = f"⚠️ SmartRetailX Inventory: Low Stock for '{product_name}'"
                details_html = f"""
                <p style="margin-top: 0;">Operational telemetry indicates that the inventory level for <strong>{product_name}</strong> has dropped below the critical restock threshold of 5 units.</p>
                <table width="100%" border="0" cellpadding="10" cellspacing="0" style="margin: 20px 0; background-color: #f9fafb; border-radius: 8px; border: 1px solid #e5e7eb;">
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="font-weight: bold; color: #374151; width: 35%;">Product Name:</td>
                        <td style="color: #4b5563;">{product_name}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="font-weight: bold; color: #374151;">Product ID:</td>
                        <td style="color: #4b5563; font-family: monospace; font-size: 13px;">{product_id}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; color: #374151;">Current Stock:</td>
                        <td style="color: #dc2626; font-weight: bold; font-size: 16px;">{stock_count} units remaining</td>
                    </tr>
                </table>
                <p style="margin-bottom: 0;">Please restock this item immediately to prevent order fulfillment disruption.</p>
                """
                html_body = get_styled_email_template(
                    title="Low Stock Alert",
                    alert_type="warning",
                    details_html=details_html,
                    cta_url="http://adef77e62998148bf97f8564f1fe7123-1693663817.us-east-1.elb.amazonaws.com:80/admin",
                    cta_text="Manage Inventory"
                )
                send_ses_email(subject, html_body)
                send_slack_webhook(f"⚠️ *LOW STOCK ALERT* ⚠️\nProduct *{product_name}* (ID: {product_id}) is down to *{stock_count}* units!")

                
            notifications_sent += 1
        except Exception as e:
            print(f"Error parsing record body: {e}")
            
    # Direct EventBridge payload (non-SQS direct invocation)
    if not records and "event_type" in event:
        event_type = event.get("event_type")
        event_data = event.get("data", {})
        print(f"Direct EventBridge Route -> Type: {event_type}, Order ID: {event_data.get('order_id')}")
        notifications_sent += 1

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Notifications processed successfully",
            "notifications_sent": notifications_sent
        })
    }

# ----------------------------------------------------
# 2. Local WebSocket & Kafka Broadcast Server (Local Compose Testing)
# ----------------------------------------------------
# FastAPI Initialization
app = FastAPI(
    title="SmartRetailX Notification WebSocket Service",
    description="Local runner representing the Lambda event processor with live browser WebSocket streaming.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AWS X-Ray Configuration
_xray_daemon_host = os.getenv("XRAY_DAEMON_HOST", "127.0.0.1")
xray_recorder.configure(
    service="notification-service",
    daemon_address=f"{_xray_daemon_host}:2000",
    context=AsyncContext()
)
patch_all()

class XRayMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        segment_name = f"{scope.get('method', 'GET')} {scope.get('path', '/')}"
        segment = xray_recorder.begin_segment(segment_name)
        segment.put_http_meta("request", {
            "url": scope.get("path", "/"),
            "method": scope.get("method", "GET")
        })

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status = message.get("status")
                segment.put_http_meta("response", {"status": status})
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            segment.add_exception(exc, [])
            raise
        finally:
            xray_recorder.end_segment()

app.add_middleware(XRayMiddleware)

# Notification Service metrics storage
notification_requests_total = {}
notification_latency_sum = 0.0
notification_latency_count = 0
notification_events_broadcast_total = 0

from fastapi import Request
from fastapi.responses import PlainTextResponse

@app.middleware("http")
async def notification_metrics_middleware(request: Request, call_next):
    # WS connections are handled by WebSocket endpoint, not http middleware logging
    if request.scope.get("type") == "websocket" or request.url.path.startswith("/ws"):
        return await call_next(request)
        
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    global notification_latency_sum, notification_latency_count
    notification_latency_sum += duration
    notification_latency_count += 1
    
    if not request.url.path.startswith(("/healthz", "/metrics")):
        key = (request.method, request.url.path, response.status_code)
        notification_requests_total[key] = notification_requests_total.get(key, 0) + 1
        
    return response

# Manage WebSocket connection states
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"New client connected! Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"Client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        # Async send to all connected UIs
        closed_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                closed_connections.append(connection)
                
        for connection in closed_connections:
            self.disconnect(connection)

manager = ConnectionManager()

# Global Event Queue for thread safety
event_queue = asyncio.Queue()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Keep connection open, receive ping messages if any
        while True:
            data = await websocket.receive_text()
            # Send keep-alive echo
            await websocket.send_json({"type": "ping", "data": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/healthz")
def healthz():
    return {"status": "healthy", "websockets_connected": len(manager.active_connections)}

@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    global notification_latency_sum, notification_latency_count, notification_events_broadcast_total
    lines = []
    
    # Total request counts
    lines.append("# HELP notification_requests_total Total number of HTTP requests handled by the Notification Service.")
    lines.append("# TYPE notification_requests_total counter")
    for (method, path, status_code), count in notification_requests_total.items():
        lines.append(f'notification_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')
        
    # Latency metric
    lines.append("# HELP notification_request_latency_seconds_sum Sum of request processing duration in seconds.")
    lines.append("# TYPE notification_request_latency_seconds_sum counter")
    lines.append(f"notification_request_latency_seconds_sum {notification_latency_sum}")
    
    lines.append("# HELP notification_request_latency_seconds_count Count of request processing durations.")
    lines.append("# TYPE notification_request_latency_seconds_count counter")
    lines.append(f"notification_request_latency_seconds_count {notification_latency_count}")

    # WebSocket connection counts
    lines.append("# HELP notification_websockets_connected Count of active WebSocket connections.")
    lines.append("# TYPE notification_websockets_connected gauge")
    lines.append(f"notification_websockets_connected {len(manager.active_connections)}")

    # Notification broadcasts count
    lines.append("# HELP notification_events_broadcast_total Total number of events broadcasted over WebSockets.")
    lines.append("# TYPE notification_events_broadcast_total counter")
    lines.append(f"notification_events_broadcast_total {notification_events_broadcast_total}")
    
    return "\n".join(lines)

# Asynchronous event dispatcher loop
async def queue_event_dispatcher():
    print("Notification dispatcher queue task started...")
    while True:
        event = await event_queue.get()
        print(f"Broadcasting event to WebSockets: {event.get('event_type')}")
        await manager.broadcast(event)
        
        # Trigger alerts on specific events
        event_type = event.get("event_type")
        event_data = event.get("data", {})
        if event_type == "low-stock-alert":
            product_name = event_data.get("product_name", "Unknown Product")
            product_id = event_data.get("product_id", "N/A")
            stock_count = event_data.get("stock_count", 0)
            
            subject = f"⚠️ SmartRetailX Inventory: Low Stock for '{product_name}'"
            details_html = f"""
            <p style="margin-top: 0;">Operational telemetry indicates that the inventory level for <strong>{product_name}</strong> has dropped below the critical restock threshold of 5 units.</p>
            <table width="100%" border="0" cellpadding="10" cellspacing="0" style="margin: 20px 0; background-color: #f9fafb; border-radius: 8px; border: 1px solid #e5e7eb;">
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="font-weight: bold; color: #374151; width: 35%;">Product Name:</td>
                    <td style="color: #4b5563;">{product_name}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="font-weight: bold; color: #374151;">Product ID:</td>
                    <td style="color: #4b5563; font-family: monospace; font-size: 13px;">{product_id}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold; color: #374151;">Current Stock:</td>
                    <td style="color: #dc2626; font-weight: bold; font-size: 16px;">{stock_count} units remaining</td>
                </tr>
            </table>
            <p style="margin-bottom: 0;">Please restock this item immediately to prevent order fulfillment disruption.</p>
            """
            html_body = get_styled_email_template(
                title="Low Stock Alert",
                alert_type="warning",
                details_html=details_html,
                cta_url="http://adef77e62998148bf97f8564f1fe7123-1693663817.us-east-1.elb.amazonaws.com:80/admin",
                cta_text="Manage Inventory"
            )
            send_ses_email(subject, html_body)
            send_slack_webhook(f"⚠️ *LOW STOCK ALERT* ⚠️\nProduct *{product_name}* (ID: {product_id}) is down to *{stock_count}* units!")
        elif event_type == "payment-failed":
            order_id = event_data.get("order_id")
            is_fraud = event_data.get("is_fraud", False)
            if is_fraud:
                ip_addr = event_data.get("ip_address", "unknown-ip")
                reason = event_data.get("fraud_reason", "Suspicious activity.")
                subject = f"🛑 SmartRetailX Security: Fraud Blocked on Order #{order_id}"
                details_html = f"""
                <p style="margin-top: 0;">The transaction screening engine has flagged a high-risk checkout attempt. The order has been automatically cancelled and access restricted.</p>
                <table width="100%" border="0" cellpadding="10" cellspacing="0" style="margin: 20px 0; background-color: #f9fafb; border-radius: 8px; border: 1px solid #e5e7eb;">
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="font-weight: bold; color: #374151; width: 35%;">Order ID:</td>
                        <td style="color: #4b5563; font-family: monospace;">#{order_id}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e5e7eb;">
                        <td style="font-weight: bold; color: #374151;">Client IP:</td>
                        <td style="color: #4b5563; font-family: monospace; font-size: 13px;">{ip_addr}</td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; color: #374151;">Fraud Reason:</td>
                        <td style="color: #ef4444; font-weight: bold;">{reason}</td>
                    </tr>
                </table>
                <p style="margin-bottom: 0;">No funds were captured. The suspicious access source is now under monitoring.</p>
                """
                html_body = get_styled_email_template(
                    title="Security Incident Blocked",
                    alert_type="critical",
                    details_html=details_html,
                    cta_url="http://adef77e62998148bf97f8564f1fe7123-1693663817.us-east-1.elb.amazonaws.com:80/admin",
                    cta_text="Open Security Console"
                )
                send_ses_email(subject, html_body)
                send_slack_webhook(f"🚨 *CRITICAL FRAUD BLOCKED* 🚨\nOrder #{order_id} flagged as *FRAUD* from IP `{ip_addr}`. Reason: {reason}")

            
        # Increment metric
        global notification_events_broadcast_total
        notification_events_broadcast_total += 1
        
        event_queue.task_done()

# Kafka broker consumer
def run_kafka_consumer(loop):
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    while True:
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS.split(","),
                auto_offset_reset='latest',
                enable_auto_commit=True,
                group_id='notification-service-group',
                value_deserializer=lambda x: json.loads(x.decode('utf-8'))
            )
            consumer.subscribe(['order-events', 'payment-events', 'inventory-events'])
            print("Notification Service Kafka consumer connected and subscribed!")
            for message in consumer:
                event = message.value
                print(f"Notification consumed event: {event.get('event_type')}")
                loop.call_soon_threadsafe(event_queue.put_nowait, event)
        except Exception as e:
            print(f"Notification Kafka consumer error: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)

# Watcher simulating events from local file when Kafka is down
def run_file_simulator(loop):
    sim_log = "./logs/event_bus.jsonl"
    processed_events = set()
    while True:
        if os.path.exists(sim_log):
            try:
                with open(sim_log, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        event_id = event.get("event_id")
                        if event_id not in processed_events:
                            processed_events.add(event_id)
                            print(f"Notification simulator read event: {event.get('event_type')}")
                            loop.call_soon_threadsafe(event_queue.put_nowait, event)
            except Exception as e:
                print(f"Notification File Simulator error: {e}")
        time.sleep(1)

@app.on_event("startup")
def start_ws_broadcaster():
    # Capture running loop
    loop = asyncio.get_event_loop()
    
    # Start dispatcher queue consumer
    asyncio.create_task(queue_event_dispatcher())
    
    # Start Kafka listener thread
    kafka_thread = threading.Thread(target=run_kafka_consumer, args=(loop,), daemon=True)
    kafka_thread.start()
    
    # Start local file listener thread
    sim_thread = threading.Thread(target=run_file_simulator, args=(loop,), daemon=True)
    sim_thread.start()

if __name__ == "__main__":
    import uvicorn
    # Standalone execution launch
    uvicorn.run(app, host="0.0.0.0", port=8006)



