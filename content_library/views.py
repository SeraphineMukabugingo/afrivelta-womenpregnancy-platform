from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from organizations.access import accessible_organizations
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ContentItemForm, ContentSourceForm
from .models import ContentItem, ContentSource


def can_view_internal_content(user):
    permissions = (
        "create_content",
        "submit_content",
        "review_content",
        "publish_content",
    )
    return user.is_superuser or any(
        user.has_perm(f"content_library.{code}")
        for code in permissions
    )


def editable_content_for(user):
    if user.is_superuser:
        return ContentItem.objects.all()
    return ContentItem.objects.filter(
        submitted_by=user,
        organization__in=accessible_organizations(user),
    )


def reviewable_content_for(user):
    if user.is_superuser:
        return ContentItem.objects.all()
    return ContentItem.objects.filter(
        organization__in=accessible_organizations(user)
    )


def visible_content_for(user):
    if user.is_superuser:
        return ContentItem.objects.all()

    own_published = Q(
        organization__in=accessible_organizations(user),
        is_published=True,
        review_status=ContentItem.ReviewStatus.APPROVED,
    )
    shared_published = Q(
        is_shared=True,
        is_published=True,
        review_status=ContentItem.ReviewStatus.APPROVED,
    )

    if can_view_internal_content(user):
        return ContentItem.objects.filter(
            Q(organization__in=accessible_organizations(user))
            | shared_published
        ).distinct()

    return ContentItem.objects.filter(
        own_published | shared_published
    ).distinct()


@login_required
def content_list(request):
    items = visible_content_for(request.user)

    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(body__icontains=query)
        )

    items = items.order_by("-updated_at")

    return render(
        request,
        "content_library/content_list.html",
        {
            "items": items,
            "search_query": query,
        },
    )


@permission_required("content_library.create_content", raise_exception=True)
def content_create(request):
    if request.method == "POST":
        form = ContentItemForm(
            request.POST,
            organizations=accessible_organizations(request.user),
        )
        if form.is_valid():
            item = form.save(commit=False)
            item.submitted_by = request.user
            item.review_status = ContentItem.ReviewStatus.DRAFT
            item.is_published = False
            item.save()

            messages.success(
                request,
                "Draft created. Add source references before submitting for review.",
            )
            return redirect("content-library-detail", pk=item.pk)
    else:
        form = ContentItemForm(
            organizations=accessible_organizations(request.user),
        )

    return render(
        request,
        "content_library/content_form.html",
        {
            "form": form,
            "page_title": "Create Educational Content",
            "button_label": "Save Draft",
        },
    )


@login_required
def content_detail(request, pk):
    allowed_items = visible_content_for(request.user)

    item = get_object_or_404(
        allowed_items.prefetch_related("sources"),
        pk=pk,
    )

    return render(
        request,
        "content_library/content_detail.html",
        {"item": item},
    )


@permission_required("content_library.create_content", raise_exception=True)
def content_update(request, pk):
    item = get_object_or_404(editable_content_for(request.user), pk=pk)

    if item.review_status == ContentItem.ReviewStatus.ARCHIVED:
        messages.error(request, "Archived content cannot be edited.")
        return redirect("content-library-detail", pk=item.pk)

    if request.method == "POST":
        form = ContentItemForm(
            request.POST,
            instance=item,
            organizations=accessible_organizations(request.user),
        )
        if form.is_valid():
            item = form.save(commit=False)

            # Any edit requires a fresh review before republication.
            item.review_status = ContentItem.ReviewStatus.DRAFT
            item.is_published = False
            item.is_shared = False
            item.reviewed_by = None
            item.reviewed_at = None
            item.published_at = None
            item.save()

            messages.success(
                request,
                "Changes saved as a draft. The content must be reviewed again.",
            )
            return redirect("content-library-detail", pk=item.pk)
    else:
        form = ContentItemForm(
            instance=item,
            organizations=accessible_organizations(request.user),
        )

    return render(
        request,
        "content_library/content_form.html",
        {
            "form": form,
            "item": item,
            "page_title": "Edit Educational Content",
            "button_label": "Save Draft",
        },
    )


@permission_required("content_library.create_content", raise_exception=True)
def content_source_create(request, pk):
    item = get_object_or_404(editable_content_for(request.user), pk=pk)

    if item.review_status == ContentItem.ReviewStatus.ARCHIVED:
        messages.error(request, "Archived content cannot be changed.")
        return redirect("content-library-detail", pk=item.pk)

    if request.method == "POST":
        form = ContentSourceForm(request.POST)
        if form.is_valid():
            source = form.save(commit=False)
            source.content_item = item
            source.save()

            messages.success(request, "Source reference added.")
            return redirect("content-library-detail", pk=item.pk)
    else:
        form = ContentSourceForm()

    return render(
        request,
        "content_library/source_form.html",
        {
            "form": form,
            "item": item,
        },
    )


@permission_required("content_library.submit_content", raise_exception=True)
def content_submit_for_review(request, pk):
    item = get_object_or_404(editable_content_for(request.user), pk=pk)

    if request.method != "POST":
        messages.warning(request, "Use the Submit for Review button.")
        return redirect("content-library-detail", pk=item.pk)

    if item.review_status not in [
        ContentItem.ReviewStatus.DRAFT,
        ContentItem.ReviewStatus.CHANGES_REQUESTED,
    ]:
        messages.error(request, "This content cannot be submitted in its current state.")
        return redirect("content-library-detail", pk=item.pk)

    if not item.sources.exists():
        messages.error(
            request,
            "Add at least one source reference before submitting for review.",
        )
        return redirect("content-library-detail", pk=item.pk)

    item.review_status = ContentItem.ReviewStatus.IN_REVIEW
    item.is_published = False
    item.reviewed_by = None
    item.reviewed_at = None
    item.published_at = None
    item.save()

    messages.success(request, "Content submitted for review.")
    return redirect("content-library-detail", pk=item.pk)


@permission_required("content_library.review_content", raise_exception=True)
def content_review(request, pk):
    item = get_object_or_404(
        reviewable_content_for(request.user), pk=pk
    )

    if request.method != "POST":
        messages.warning(request, "Use a review action on the content page.")
        return redirect("content-library-detail", pk=item.pk)

    if item.review_status != ContentItem.ReviewStatus.IN_REVIEW:
        messages.error(request, "Only content under review can be reviewed.")
        return redirect("content-library-detail", pk=item.pk)

    action = request.POST.get("action", "")
    if action not in {"approve", "request_changes"}:
        messages.error(request, "Unrecognised review action.")
        return redirect("content-library-detail", pk=item.pk)

    # Health content should not be approved by its original submitter.
    if item.submitted_by_id == request.user.pk:
        messages.error(
            request,
            "A different authorised reviewer must approve this content.",
        )
        return redirect("content-library-detail", pk=item.pk)

    item.reviewed_by = request.user
    item.reviewed_at = timezone.now()
    item.reviewer_notes = request.POST.get("reviewer_notes", "").strip()
    item.is_published = False
    item.published_at = None

    if action == "approve":
        item.review_status = ContentItem.ReviewStatus.APPROVED
        message = "Content approved. It is not public until it is published."
    else:
        item.review_status = ContentItem.ReviewStatus.CHANGES_REQUESTED
        message = "Changes requested. Edit the draft and resubmit it."

    item.save()
    messages.success(request, message)
    return redirect("content-library-detail", pk=item.pk)


@permission_required("content_library.publish_content", raise_exception=True)
def content_publish(request, pk):
    item = get_object_or_404(
        reviewable_content_for(request.user), pk=pk
    )

    if request.method != "POST":
        messages.warning(request, "Use the Publish button.")
        return redirect("content-library-detail", pk=item.pk)

    if item.review_status != ContentItem.ReviewStatus.APPROVED:
        messages.error(request, "Only approved content can be published.")
        return redirect("content-library-detail", pk=item.pk)

    if not item.reviewed_by_id:
        messages.error(
            request,
            "A recorded reviewer approval is required before publication.",
        )
        return redirect("content-library-detail", pk=item.pk)

    item.is_published = True
    item.published_at = timezone.now()
    item.save()

    messages.success(request, "Approved content has been published.")
    return redirect("content-library-detail", pk=item.pk)
