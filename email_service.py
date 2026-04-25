"""
email_service.py — RouteCore email alerts via Resend.

Triggered automatically when:
  - Shipment status changes to 'Delayed'    → delay alert
  - Shipment status changes to 'Delivered'  → delivery confirmation
  - Shipment is dispatched                  → dispatch notification to driver

Environment variables required (set in .env locally, Render dashboard in production):
  RESEND_API_KEY   → your Resend API key (starts with re_)
  FROM_EMAIL       → verified sender email (e.g. alerts@routecore.io)
"""

import os
import resend as resend_client

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL     = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")  # fallback for testing
APP_NAME       = "RouteCore"


def _send(to: str, subject: str, html: str) -> dict:
    if not RESEND_API_KEY:
        print("[Email] RESEND_API_KEY not set — skipping.")
        return {"success": False, "error": "RESEND_API_KEY not configured"}
    try:
        resend_client.api_key = RESEND_API_KEY
        params = {
            "from": FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        email = resend_client.Emails.send(params)
        print(f"[Email] Sent '{subject}' to {to} — id: {email['id']}")
        return {"success": True, "id": email["id"]}
    except Exception as e:
        print(f"[Email] Send failed: {e}")
        return {"success": False, "error": str(e)}


# ── Email templates ────────────────────────────────────────────────────────────

def _base_template(content: str) -> str:
    """Wrap content in a clean dark-themed HTML email."""
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>RouteCore</title>
</head>
<body style="margin:0;padding:0;background:#0a0c10;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0c10;padding:40px 20px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

        <!-- Header -->
        <tr><td style="background:#12151c;border:1px solid #252a38;border-radius:12px 12px 0 0;padding:24px 32px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td>
                <span style="display:inline-block;background:#3b82f6;border-radius:6px;padding:6px 10px;margin-right:10px;vertical-align:middle;">
                  <span style="color:white;font-size:14px;font-weight:700;">RC</span>
                </span>
                <span style="color:#e8eaf0;font-size:18px;font-weight:700;vertical-align:middle;">RouteCore</span>
              </td>
              <td align="right" style="color:#6b7280;font-size:12px;">Logistics Management</td>
            </tr>
          </table>
        </td></tr>

        <!-- Body -->
        <tr><td style="background:#1a1e28;border-left:1px solid #252a38;border-right:1px solid #252a38;padding:32px;">
          {content}
        </td></tr>

        <!-- Footer -->
        <tr><td style="background:#12151c;border:1px solid #252a38;border-top:none;border-radius:0 0 12px 12px;padding:20px 32px;">
          <p style="color:#6b7280;font-size:12px;margin:0;text-align:center;">
            This is an automated alert from RouteCore &mdash; your logistics management platform.<br/>
            <a href="#" style="color:#3b82f6;text-decoration:none;">View Dashboard</a>
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _detail_row(label: str, value: str) -> str:
    return f"""
    <tr>
      <td style="padding:8px 0;color:#6b7280;font-size:13px;width:140px;vertical-align:top;">{label}</td>
      <td style="padding:8px 0;color:#e8eaf0;font-size:13px;font-weight:500;vertical-align:top;">{value or "—"}</td>
    </tr>"""


# ── Alert functions ────────────────────────────────────────────────────────────

def send_delay_alert(to_email: str, shipment: dict, customer_name: str = "") -> dict:
    """Send a delay alert email when a shipment is marked Delayed."""
    sid = shipment.get("id", "N/A")
    subject = f"⚠️ Shipment Delayed — {sid}"

    content = f"""
    <h2 style="color:#f59e0b;font-size:22px;font-weight:700;margin:0 0 8px;">Shipment Delayed</h2>
    <p style="color:#9ca3af;font-size:14px;margin:0 0 24px;">
      Shipment <strong style="color:#e8eaf0;">{sid}</strong> has been marked as delayed and requires attention.
    </p>

    <div style="background:#2d1f00;border:1px solid #92400e;border-radius:8px;padding:16px;margin-bottom:24px;">
      <p style="color:#f59e0b;font-size:13px;font-weight:600;margin:0;">
        ⚠️ Action may be required — please review this shipment in your dashboard.
      </p>
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #252a38;">
      {_detail_row("Shipment ID", sid)}
      {_detail_row("Customer", customer_name)}
      {_detail_row("Origin", shipment.get("origin"))}
      {_detail_row("Destination", shipment.get("destination"))}
      {_detail_row("Carrier", shipment.get("carrier"))}
      {_detail_row("Container #", shipment.get("container_number"))}
      {_detail_row("Tracking #", shipment.get("tracking_number"))}
      {_detail_row("ETA", shipment.get("eta"))}
      {_detail_row("Notes", shipment.get("notes"))}
    </table>

    <div style="margin-top:28px;">
      <a href="#" style="display:inline-block;background:#3b82f6;color:white;text-decoration:none;padding:12px 24px;border-radius:7px;font-size:14px;font-weight:600;">
        View Shipment Dashboard
      </a>
    </div>"""

    return _send(to_email, subject, _base_template(content))


def send_delivery_confirmation(to_email: str, shipment: dict, customer_name: str = "") -> dict:
    """Send a delivery confirmation email when a shipment is marked Delivered."""
    sid = shipment.get("id", "N/A")
    subject = f"✅ Shipment Delivered — {sid}"

    content = f"""
    <h2 style="color:#34d399;font-size:22px;font-weight:700;margin:0 0 8px;">Shipment Delivered</h2>
    <p style="color:#9ca3af;font-size:14px;margin:0 0 24px;">
      Great news — shipment <strong style="color:#e8eaf0;">{sid}</strong> has been successfully delivered.
    </p>

    <div style="background:#0d2818;border:1px solid #065f46;border-radius:8px;padding:16px;margin-bottom:24px;">
      <p style="color:#34d399;font-size:13px;font-weight:600;margin:0;">
        ✅ Delivery complete. No further action required.
      </p>
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #252a38;">
      {_detail_row("Shipment ID", sid)}
      {_detail_row("Customer", customer_name)}
      {_detail_row("Origin", shipment.get("origin"))}
      {_detail_row("Destination", shipment.get("destination"))}
      {_detail_row("Carrier", shipment.get("carrier"))}
      {_detail_row("Container #", shipment.get("container_number"))}
      {_detail_row("Tracking #", shipment.get("tracking_number"))}
      {_detail_row("Delivered On", shipment.get("eta"))}
      {_detail_row("Notes", shipment.get("notes"))}
    </table>

    <div style="margin-top:28px;">
      <a href="#" style="display:inline-block;background:#3b82f6;color:white;text-decoration:none;padding:12px 24px;border-radius:7px;font-size:14px;font-weight:600;">
        View Shipment Dashboard
      </a>
    </div>"""

    return _send(to_email, subject, _base_template(content))


def send_dispatch_notification(to_email: str, shipment: dict, driver: dict) -> dict:
    """Send a dispatch notification to a driver when they are assigned a pickup."""
    sid = shipment.get("id", "N/A")
    subject = f"📦 New Pickup Assignment — {sid}"

    content = f"""
    <h2 style="color:#60a5fa;font-size:22px;font-weight:700;margin:0 0 8px;">New Pickup Assignment</h2>
    <p style="color:#9ca3af;font-size:14px;margin:0 0 24px;">
      Hi <strong style="color:#e8eaf0;">{driver.get("name", "Driver")}</strong>,
      you have been assigned a new container pickup. Please review the details below.
    </p>

    <div style="background:#0d1f3c;border:1px solid #1e40af;border-radius:8px;padding:16px;margin-bottom:24px;">
      <p style="color:#60a5fa;font-size:13px;font-weight:600;margin:0;">
        📦 Please confirm receipt and proceed to the pickup location.
      </p>
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #252a38;">
      {_detail_row("Shipment ID", sid)}
      {_detail_row("Container #", shipment.get("container_number"))}
      {_detail_row("Pickup Location", shipment.get("origin"))}
      {_detail_row("Deliver To", shipment.get("destination"))}
      {_detail_row("Carrier", shipment.get("carrier"))}
      {_detail_row("Tracking #", shipment.get("tracking_number"))}
      {_detail_row("ETA", shipment.get("eta"))}
      {_detail_row("Notes", shipment.get("notes"))}
    </table>

    <div style="margin-top:28px;padding:16px;background:#12151c;border:1px solid #252a38;border-radius:8px;">
      <p style="color:#6b7280;font-size:12px;margin:0 0 4px;">Your contact for this shipment:</p>
      <p style="color:#e8eaf0;font-size:13px;font-weight:600;margin:0;">RouteCore Dispatch</p>
    </div>"""

    return _send(to_email, subject, _base_template(content))
