from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import sanitize_address


class ResendBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        import resend

        resend.api_key = settings.RESEND_API_KEY
        count = 0
        for message in email_messages:
            try:
                # Django validates header values before they reach the API.
                message.message()
                payload = {"from": sanitize_address(message.from_email, "utf-8"),
                           "to": message.to, "subject": message.subject, "text": message.body}
                if message.reply_to:
                    payload["reply_to"] = message.reply_to[0]
                options = {"idempotency_key": message.extra_headers["X-Submission-ID"]}
                result = resend.Emails.send(payload, options)
                if not result.get("id"):
                    raise RuntimeError("Resend did not confirm the notification.")
                count += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return count
