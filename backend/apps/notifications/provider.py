import time
from dataclasses import dataclass
from datetime import timedelta

from billiard.exceptions import SoftTimeLimitExceeded
from django.conf import settings


@dataclass(frozen=True)
class Outcome:
    code: str = ""
    message_id: str = ""
    retryable: bool = False
    unregistered: bool = False
    retry_after: int = 0


def send(*, token, message):
    if not settings.PUSH_ENABLED:
        return Outcome(code="provider_disabled")
    # Lazy initialization: normal API/auth does not require Firebase credentials.
    import firebase_admin
    from firebase_admin import exceptions, messaging
    from requests import exceptions as network

    try:
        try:
            app = firebase_admin.get_app("chii-push")
        except ValueError:
            app = firebase_admin.initialize_app(
                options={
                    "projectId": settings.FIREBASE_PROJECT_ID,
                    "httpTimeout": 10,
                },
                name="chii-push",
            )
        # Pinned SDK has no public retry configuration; contain the transport override here.
        # Disable SDK POST retries so the DB attempt limit remains authoritative.
        from requests.adapters import HTTPAdapter

        client = messaging._get_messaging_service(app)._client
        client.session.mount("https://fcm.googleapis.com", HTTPAdapter(max_retries=0))
        payload = messaging.Message(
            fid=token,
            notification=messaging.Notification(title=message.title, body=message.body),
            data={
                "version": "1",
                "message_id": str(message.pk),
                "type": "OPERATOR_TEST",
                "destination": "HOME",
            },
            android=messaging.AndroidConfig(
                ttl=timedelta(minutes=5),
                notification=messaging.AndroidNotification(channel_id="operator_test"),
            ),
            apns=messaging.APNSConfig(
                headers={
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                    "apns-expiration": str(int(time.time()) + 300),
                },
                payload=messaging.APNSPayload(aps=messaging.Aps(sound="default")),
            ),
        )
        return Outcome(message_id=messaging.send(payload, app=app))
    except messaging.UnregisteredError:
        return Outcome(code="unregistered", unregistered=True)
    except (
        exceptions.UnavailableError,
        exceptions.InternalError,
        exceptions.DeadlineExceededError,
    ) as exc:
        retry_after = 0
        response = getattr(exc, "http_response", None)
        if response is not None:
            value = response.headers.get("Retry-After", "")
            if value.isdigit():
                retry_after = int(value)
        return Outcome(code="provider_transient", retryable=True, retry_after=retry_after)
    except SoftTimeLimitExceeded:
        raise
    except network.SSLError:
        return Outcome(code="provider_tls_error")
    except (network.Timeout, network.ConnectionError):
        return Outcome(code="network_transient", retryable=True)
    except (exceptions.InvalidArgumentError, ValueError):
        return Outcome(code="invalid_payload_or_config")
    except Exception:
        # SDK error messages can include tokens, credentials and external response bodies.
        return Outcome(code="provider_permanent")
