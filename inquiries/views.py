import logging
import uuid

from django.contrib import messages
from django.core import signing
from django.db import DatabaseError, transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from .forms import ContactForm
from .models import Inquiry
from .services import consume_rate_limit, notify_owner
from portfolio.services.content import get_site
from portfolio.service_content import ServiceKind


logger = logging.getLogger(__name__)
SALT = "portfolio-inquiry"


def issue_token(request):
    if "inquiry_nonce" not in request.session:
        request.session["inquiry_nonce"] = uuid.uuid4().hex
    return signing.dumps({"id": str(uuid.uuid4()), "nonce": request.session["inquiry_nonce"]}, salt=SALT)


def contact(request):
    if request.method == "GET":
        selection = request.GET.get("service", "")
        form = ContactForm(initial={"submission_token": issue_token(request),
                                    "service": selection if selection in ServiceKind.values else ""})
    else:
        form = ContactForm(request.POST)
        if form.is_valid():
            try:
                token = signing.loads(form.cleaned_data["submission_token"], salt=SALT, max_age=86400)
                if token["nonce"] != request.session.get("inquiry_nonce"):
                    raise signing.BadSignature()
                submission_id = uuid.UUID(token["id"])
            except (signing.BadSignature, KeyError, ValueError, TypeError):
                form.add_error(None, _("This form has expired. Please submit your message again."))
                form.data = form.data.copy()
                form.data["submission_token"] = issue_token(request)
            else:
                try:
                    if form.cleaned_data["website"] or Inquiry.objects.filter(submission_id=submission_id).exists():
                        messages.success(request, _("Thanks for getting in touch."))
                        return redirect("contact")
                    if not consume_rate_limit(request):
                        form.add_error(None, _("Too many messages. Please try again later."))
                        return render(request, "portfolio/contact.html", {"form": form}, status=429)
                    values = {field: form.cleaned_data[field] for field in
                              ("name", "email", "organization", "assignment_type", "service", "event_date", "location", "message")}
                    with transaction.atomic():
                        inquiry, created = Inquiry.objects.get_or_create(submission_id=submission_id,
                            defaults={**values, "language": request.LANGUAGE_CODE})
                        if created:
                            inquiry.photos.set(form.cleaned_data["selected_photos"])
                except DatabaseError:
                    logger.exception("Could not persist an inquiry.")
                    form.add_error(None, _("Your message could not be saved. Please try again."))
                else:
                    if created:
                        try:
                            notify_owner(inquiry)
                        except Exception:
                            logger.exception("The saved inquiry could not be notified.")
                    messages.success(request, _("Thanks for getting in touch."))
                    return redirect("contact")
    return render(request, "portfolio/contact.html", {"form": form,
        "page_description": get_site(request).contact_intro})
