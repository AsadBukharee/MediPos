"""Firebase Cloud Messaging sender. Imported lazily so the app runs without Firebase configured."""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)
_app = None


class PushNotConfigured(Exception):
    pass


def _firebase():
    global _app
    if not settings.FIREBASE_CREDENTIALS_FILE:
        raise PushNotConfigured("FIREBASE_CREDENTIALS_FILE is not set.")
    import firebase_admin
    from firebase_admin import credentials

    if _app is None:
        _app = firebase_admin.initialize_app(credentials.Certificate(settings.FIREBASE_CREDENTIALS_FILE))
    return _app


def send_push(tokens: list[str], title: str, body: str, data: dict) -> tuple[int, list[str]]:
    """Returns (delivered count, tokens FCM says are no longer valid).

    Android gets a data-only message in the shape expo-notifications expects (title / message /
    body-as-JSON / categoryId / channelId), so the app can show "Add to Order List" and "Skip"
    action buttons even when it is in the background. iOS gets a normal APNs alert.
    """
    app = _firebase()
    from firebase_admin import messaging

    category = str(data.get("category", ""))
    message = messaging.MulticastMessage(
        tokens=tokens,
        data={
            "title": title,
            "message": body,
            "body": json.dumps(data, default=str),
            "categoryId": category,
            "channelId": "stock-alerts" if category == "stock_alert" else "general",
        },
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(payload=messaging.APNSPayload(aps=messaging.Aps(
            alert=messaging.ApsAlert(title=title, body=body), sound="default", category=category or None))),
    )
    response = messaging.send_each_for_multicast(message, app=app)
    invalid = []
    for token, result in zip(tokens, response.responses):
        if not result.success and isinstance(result.exception, (messaging.UnregisteredError, messaging.SenderIdMismatchError)):
            invalid.append(token)
    return response.success_count, invalid
