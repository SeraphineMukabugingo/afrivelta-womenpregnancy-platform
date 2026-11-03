import csv
from calendar import monthrange
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .services import build_reporting_data


def shift_month(value, offset):
    """Move a date by whole calendar months safely."""
    month_index = value.year * 12 + value.month - 1 + offset
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def get_reporting_period(request):
    raw_start = request.GET.get("start_date", "").strip()
    raw_end = request.GET.get("end_date", "").strip()

    period = request.GET.get("period", "").strip()
    if not period:
        period = "custom" if raw_start or raw_end else "all"

    today = timezone.localdate()
    month_start = date(today.year, today.month, 1)

    if period == "all":
        return None, None, None

    if period == "this_month":
        return month_start, today, None

    if period == "last_month":
        end_date = month_start - timedelta(days=1)
        start_date = shift_month(month_start, -1)
        return start_date, end_date, None

    quarter_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = date(today.year, quarter_month, 1)

    if period == "this_quarter":
        return quarter_start, today, None

    if period == "last_quarter":
        previous_quarter_end = quarter_start - timedelta(days=1)
        previous_quarter_month = (
            ((previous_quarter_end.month - 1) // 3) * 3 + 1
        )
        previous_quarter_start = date(
            previous_quarter_end.year,
            previous_quarter_month,
            1,
        )
        return previous_quarter_start, previous_quarter_end, None

    if period == "year_to_date":
        return date(today.year, 1, 1), today, None

    if period == "last_12_months":
        return shift_month(month_start, -11), today, None

    if period == "custom":
        start_date = parse_date(raw_start) if raw_start else None
        end_date = parse_date(raw_end) if raw_end else None

        if raw_start and start_date is None:
            return None, None, "Invalid start date."

        if raw_end and end_date is None:
            return None, None, "Invalid end date."

        if start_date and end_date and start_date > end_date:
            return None, None, "Start date must not be after end date."

        return start_date, end_date, None

    return None, None, "Invalid reporting period."


def get_report(request):
    start_date, end_date, error = get_reporting_period(request)

    if error:
        return None, error

    try:
        report = build_reporting_data(
            request.user,
            start_date=start_date,
            end_date=end_date,
        )
    except PermissionError:
        raise PermissionDenied

    report["selected_period"] = (
        request.GET.get("period", "").strip()
        or (
            "custom"
            if request.GET.get("start_date") or request.GET.get("end_date")
            else "all"
        )
    )

    return report, None


@login_required
def impact_dashboard(request):
    report, error = get_report(request)

    if error:
        return HttpResponseBadRequest(error)

    return render(
        request,
        "reporting/impact_dashboard.html",
        {"report": report},
    )


def add_metric_rows(writer, section, metrics, fields):
    if metrics is None:
        return

    for key, label in fields:
        writer.writerow([section, label, metrics.get(key, "")])

    for key, label in (
        ("statuses", "Status"),
        ("activity_statuses", "Activity status"),
        ("milestone_statuses", "Milestone status"),
    ):
        for item in metrics.get(key, []):
            writer.writerow([
                section,
                f"{label}: {item['label']}",
                item["count"],
            ])

    for district in metrics.get("districts", []):
        writer.writerow([
            section,
            f"Providers in district: {district['district']}",
            district["total"],
        ])


@login_required
def export_impact_csv(request):
    report, error = get_report(request)

    if error:
        return HttpResponseBadRequest(error)

    response = HttpResponse(
        content_type="text/csv; charset=utf-8"
    )

    filename = (
        f"afrivelta_impact_report_"
        f"{timezone.localdate().strftime('%Y%m%d')}.csv"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    writer = csv.writer(response)
    writer.writerow(["AFRIVELTA WomenPregnancy Platform"])
    writer.writerow(["Generated", report["generated_at"].isoformat()])
    writer.writerow(["Start date", report["period_start"] or "All records"])
    writer.writerow(["End date", report["period_end"] or "All records"])
    writer.writerow([])
    writer.writerow(["Reporting section", "Indicator", "Value"])

    add_metric_rows(
        writer,
        "Organizations",
        report["organization_metrics"],
        [
            ("total", "Total organizations"),
            ("active", "Active organizations"),
            ("pending", "Pending organizations"),
            ("suspended", "Suspended organizations"),
            ("rejected", "Rejected organizations"),
        ],
    )

    add_metric_rows(
        writer,
        "Programmes",
        report["programme"],
        [
            ("total", "Total programmes"),
            ("active", "Active programmes"),
            ("completed", "Completed programmes"),
            ("activity_total", "Total activities"),
            ("activity_completed", "Completed activities"),
            ("activity_average_progress", "Average activity progress (%)"),
            ("milestone_total", "Total milestones"),
            ("milestone_achieved", "Achieved milestones"),
            ("milestone_at_risk", "At-risk milestones"),
            ("milestone_delayed", "Delayed milestones"),
            ("milestone_overdue", "Overdue milestones"),
        ],
    )

    add_metric_rows(
        writer,
        "Education",
        report["education"],
        [
            ("total", "Total content items"),
            ("unassigned", "Unassigned content items"),
            ("shared", "Shared content items"),
            ("published", "Published content"),
            ("in_review", "Content under review"),
            ("approved", "Approved content"),
        ],
    )

    add_metric_rows(
        writer,
        "Service providers",
        report["providers"],
        [
            ("total", "Total providers"),
            ("active", "Active providers"),
            ("verified", "Verified providers"),
            ("pending", "Providers pending verification"),
        ],
    )

    add_metric_rows(
        writer,
        "Referrals",
        report["referrals"],
        [
            ("total", "Total referrals"),
            ("open", "Open referrals"),
            ("completed", "Completed referrals"),
            ("follow_up_overdue", "Overdue follow-ups"),
        ],
    )

    trends = report.get("trends", {})
    trend_metrics = trends.get("metrics", [])

    if trend_metrics:
        headers = [metric["label"] for metric in trend_metrics]

        writer.writerow([])
        writer.writerow(["Monthly performance trends"])
        writer.writerow(["Period"] + headers)

        for row in trends.get("monthly", []):
            writer.writerow([row["period_label"]] + row["values"])

        writer.writerow([])
        writer.writerow(["Quarterly performance trends"])
        writer.writerow(["Period"] + headers)

        for row in trends.get("quarterly", []):
            writer.writerow([row["period_label"]] + row["values"])

    return response



def build_results_narrative(report, period_label):
    """Generate a cautious narrative from recorded reporting indicators."""
    paragraphs = []

    organizations = report.get("organization_scope", [])
    names = [item["name"] for item in organizations]

    if names:
        scope = ", ".join(names)
        paragraphs.append(
            f"This report covers {len(names)} organization(s): {scope}."
        )
    else:
        paragraphs.append(
            "No organization records were available in this reporting scope."
        )

    programme = report.get("programme")
    if programme is not None:
        paragraphs.append(
            f"During {period_label}, {programme['total']} programme "
            f"record(s) were created. Of these, {programme['active']} "
            f"are currently marked active and {programme['completed']} "
            f"are currently marked completed."
        )

        paragraphs.append(
            f"The reporting period includes {programme['activity_total']} "
            f"activity record(s), of which "
            f"{programme['activity_completed']} are currently marked "
            f"completed. Average recorded activity progress is "
            f"{programme['activity_average_progress']}%."
        )

        paragraphs.append(
            f"There are {programme['milestone_total']} milestone "
            f"record(s) in the reporting period, with "
            f"{programme['milestone_achieved']} currently marked achieved, "
            f"{programme['milestone_at_risk']} at risk and "
            f"{programme['milestone_delayed']} delayed."
        )

        paragraphs.append(
            f"{programme['milestone_evidence_count']} milestone(s) "
            "have recorded evidence summaries or internal references "
            "within the reporting period."
        )

    education = report.get("education")
    if education is not None:
        paragraphs.append(
            f"The platform recorded {education['total']} educational "
            f"content item(s) during {period_label}. Among those records, "
            f"{education['published']} are currently published, "
            f"{education['approved']} approved and "
            f"{education['in_review']} under review."
        )

    providers = report.get("providers")
    if providers is not None:
        paragraphs.append(
            f"There were {providers['total']} provider registration "
            f"record(s) during the reporting period. Of those records, "
            f"{providers['active']} are currently active and "
            f"{providers['verified']} currently have verified status."
        )

    referrals = report.get("referrals")
    if referrals is not None:
        paragraphs.append(
            f"The platform recorded {referrals['total']} referral "
            f"record(s) during {period_label}. "
            f"{referrals['open']} are currently open, "
            f"{referrals['completed']} are currently marked completed, "
            f"and {referrals['follow_up_overdue']} have overdue follow-ups."
        )

    paragraphs.append(
        "These indicators describe records and service outputs. "
        "They do not independently establish changes in pregnancy "
        "outcomes or population health outcomes."
    )

    return paragraphs

@login_required
def quarterly_impact_report(request):
    """Render a print-ready aggregate impact report."""

    allowed_periods = {
        "last_quarter",
        "this_quarter",
        "custom",
    }

    query = request.GET.copy()
    selected_period = query.get("period", "").strip()

    if not selected_period:
        selected_period = "last_quarter"
        query["period"] = selected_period

    if selected_period not in allowed_periods:
        return HttpResponseBadRequest(
            "Choose the current quarter, previous quarter, or custom dates."
        )

    request.GET = query
    report, error = get_report(request)

    if error:
        return HttpResponseBadRequest(error)

    start = report["period_start"]
    end = report["period_end"]

    if start and end:
        quarter_number = ((start.month - 1) // 3) + 1
        end_quarter = ((end.month - 1) // 3) + 1

        if start.year == end.year and quarter_number == end_quarter:
            period_label = (
                f"Q{quarter_number} {start.year} "
                f"({start:%d %b} – {end:%d %b %Y})"
            )
        else:
            period_label = (
                f"{start:%d %b %Y} – {end:%d %b %Y}"
            )
    elif start:
        period_label = f"From {start:%d %b %Y}"
    elif end:
        period_label = f"Until {end:%d %b %Y}"
    else:
        period_label = "All recorded history"

    section_specs = [
        (
            "Organization portfolio",
            "organization_metrics",
            [
                ("total", "Total organizations"),
                ("active", "Active organizations"),
                ("pending", "Pending applications"),
                ("suspended", "Suspended organizations"),
                ("rejected", "Rejected applications"),
            ],
        ),
        (
            "Programme implementation",
            "programme",
            [
                ("total", "Total programmes"),
                ("active", "Active programmes"),
                ("completed", "Completed programmes"),
                ("activity_total", "Activities recorded"),
                ("activity_completed", "Completed activities"),
                ("activity_average_progress", "Average activity progress (%)"),
                ("milestone_total", "Milestones recorded"),
                ("milestone_achieved", "Milestones achieved"),
                ("milestone_at_risk", "Milestones at risk"),
                ("milestone_delayed", "Delayed milestones"),
                ("milestone_overdue", "Overdue milestones"),
            ],
        ),
        (
            "Education and content",
            "education",
            [
                ("total", "Content items recorded"),
                ("published", "Published content"),
                ("approved", "Approved content"),
                ("in_review", "Content under review"),
                ("shared", "Shared content"),
                ("unassigned", "Unassigned legacy content"),
            ],
        ),
        (
            "Healthcare service providers",
            "providers",
            [
                ("total", "Providers registered"),
                ("active", "Active providers"),
                ("verified", "Verified providers"),
                ("pending", "Providers awaiting verification"),
            ],
        ),
        (
            "Referral performance",
            "referrals",
            [
                ("total", "Referrals recorded"),
                ("open", "Open referrals"),
                ("completed", "Completed referrals"),
                ("follow_up_overdue", "Overdue follow-ups"),
            ],
        ),
    ]

    sections = []

    for title, key, fields in section_specs:
        metrics = report.get(key)

        if metrics is None:
            continue

        rows = [
            {"label": label, "value": metrics.get(field, 0)}
            for field, label in fields
            if field in metrics
        ]

        statuses = metrics.get("statuses", [])

        sections.append({
            "title": title,
            "rows": rows,
            "statuses": statuses,
            "evidence": (
                metrics.get("milestone_evidence_items", [])
                if key == "programme"
                else []
            ),
        })

    executive_summary = []

    summary_fields = [
        ("programme", "total", "Programmes recorded"),
        ("programme", "activity_completed", "Activities completed"),
        ("education", "published", "Educational items published"),
        ("providers", "verified", "Verified providers"),
        ("referrals", "completed", "Referrals completed"),
    ]

    for section_key, field, label in summary_fields:
        metrics = report.get(section_key)

        if metrics is not None and field in metrics:
            executive_summary.append({
                "label": label,
                "value": metrics[field],
            })

    return render(
        request,
        "reporting/quarterly_impact_report.html",
        {
            "report": report,
            "period_label": period_label,
            "sections": sections,
            "executive_summary": executive_summary,
            "results_narrative": build_results_narrative(
                report, period_label
            ),
        },
    )
