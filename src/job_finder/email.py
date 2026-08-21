"""HTML email generation and SMTP sending."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from job_finder.config import EmailConfig
from job_finder.matching import is_valid_url
from job_finder.models import Job, ScoredJob

logger = logging.getLogger(__name__)


def match_rating(score: float) -> str:
    """Convert a numeric score (0–100) into a qualitative rating label."""
    if score >= 70:
        return "Very strong"
    if score >= 65:
        return "Strong"
    if score >= 60:
        return "Good"
    if score >= 55:
        return "Fair"
    return "Weak"


def rating_color(score: float) -> str:
    """Return a hex colour for a given match score."""
    if score >= 70:
        return "#2e7d32"  # dark green
    if score >= 65:
        return "#00695c"  # teal
    if score >= 60:
        return "#1565c0"  # blue
    if score >= 55:
        return "#e65100"  # dark orange
    return "#757575"  # grey


def format_salary(job: Job) -> str:
    """Format salary range for display, if available."""
    if job.salary_min is not None and job.salary_max is not None:
        return f"£{job.salary_min:,.0f}–£{job.salary_max:,.0f}"
    if job.salary_min is not None:
        return f"£{job.salary_min:,.0f}"
    if job.salary_max is not None:
        return f"up to £{job.salary_max:,.0f}"
    return ""


def generate_html_email(scored_jobs: list[ScoredJob], total_below_threshold: int = 0) -> str:
    """Generate the HTML body for the job digest email."""
    parts = ['<html><body style="font-family: Arial, sans-serif; ' 'color: #333; max-width: 600px; margin: 0 auto;">']
    parts.append(
        '<div style="background-color: #1a365d; color: #fff; padding: 16px 20px; '
        'border-radius: 6px 6px 0 0; margin-bottom: 20px;">'
        '<h2 style="margin: 0;">Job Finder — Weekly Digest</h2>'
        "</div>"
    )
    count = len(scored_jobs)
    if count == 0:
        parts.append("<p>No new jobs found matching your criteria this week.</p>")
    else:
        parts.append(f"<p>Found <strong>{count}</strong> new job" f"{'s' if count != 1 else ''}.</p>")
    for i, scored in enumerate(scored_jobs, 1):
        parts.append(_render_job_html(i, scored))
    if total_below_threshold > 0:
        parts.append(
            f"<hr><p><em>Additional matches: {total_below_threshold} " "jobs below the email threshold.</em></p>"
        )
    parts.append(
        '<div style="background-color: #1a365d; color: #fff; padding: 10px 20px; '
        "border-radius: 0 0 6px 6px; margin-top: 24px; text-align: center; "
        'font-size: 12px;">Job Finder</div>'
    )
    parts.append("</body></html>")
    return "\n".join(parts)


def _render_job_html(index: int, scored: ScoredJob) -> str:
    """Render a single job as HTML."""
    job = scored.job
    title = escape(job.title)
    company = escape(job.company)
    location = escape(job.location) if job.location else ""
    url = job.url if is_valid_url(job.url) else ""
    rating = match_rating(scored.final_score)
    color = rating_color(scored.final_score)

    parts = [
        '<div style="margin-bottom: 20px; padding: 16px 20px; '
        "background-color: #f9fafb; border-left: 4px solid #1a365d; "
        'border-radius: 0 4px 4px 0;">'
    ]
    parts.append(f'<h3 style="margin: 0 0 6px 0; color: #1a365d;">{index}. {title}</h3>')
    parts.append(
        f'<p style="margin: 2px 0;">'
        f'<span style="background-color: {color}; color: #fff; padding: 2px 10px; '
        f'border-radius: 4px; font-size: 13px; font-weight: bold;">{escape(rating)}</span>'
        f"</p>"
    )
    if company:
        parts.append(f'<p style="margin: 2px 0; color: #555;"><strong>Company:</strong> {company}</p>')
    salary = format_salary(job)
    if salary:
        parts.append(f'<p style="margin: 2px 0; color: #2e7d32;"><strong>Salary:</strong> {escape(salary)}</p>')
    if location:
        parts.append(f'<p style="margin: 2px 0; color: #555;"><strong>Location:</strong> {location}</p>')
    if scored.strengths:
        parts.append('<p style="margin: 8px 0 2px 0;"><strong>Why it matches:</strong></p><ul>')
        for s in scored.strengths:
            parts.append(f"<li>{escape(s)}</li>")
        parts.append("</ul>")
    if scored.concerns:
        parts.append('<p style="margin: 8px 0 2px 0;"><strong>Potential concerns:</strong></p><ul>')
        for c in scored.concerns:
            parts.append(f"<li>{escape(c)}</li>")
        parts.append("</ul>")
    if url:
        parts.append(f'<p style="margin: 8px 0;"><a href="{escape(url)}">View job</a></p>')
    parts.append("</div>")
    return "\n".join(parts)


def generate_text_email(scored_jobs: list[ScoredJob], total_below_threshold: int = 0) -> str:
    """Generate a plain-text alternative for the job digest email."""
    lines = ["Job Finder — Weekly Digest", "=" * 40, ""]
    count = len(scored_jobs)
    if count == 0:
        lines.append("No new jobs found matching your criteria this week.")
    else:
        lines.append(f"Found {count} new job{'s' if count != 1 else ''}.")
    lines.append("")
    for i, scored in enumerate(scored_jobs, 1):
        lines.append(_render_job_text(i, scored))
    if total_below_threshold > 0:
        lines.append("-" * 40)
        lines.append(f"Additional matches: {total_below_threshold} jobs below the email threshold.")
    return "\n".join(lines)


def _render_job_text(index: int, scored: ScoredJob) -> str:
    """Render a single job as plain text."""
    job = scored.job
    lines = [
        f"{index}. {job.title}",
        f"   {match_rating(scored.final_score)}",
    ]
    if job.company:
        lines.append(f"   Company: {job.company}")
    salary = format_salary(job)
    if salary:
        lines.append(f"   Salary: {salary}")
    if job.location:
        lines.append(f"   Location: {job.location}")
    if scored.strengths:
        lines.append("   Why it matches:")
        for s in scored.strengths:
            lines.append(f"   - {s}")
    if scored.concerns:
        lines.append("   Potential concerns:")
        for c in scored.concerns:
            lines.append(f"   - {c}")
    if is_valid_url(job.url):
        lines.append(f"   View job: {job.url}")
    lines.append("")
    return "\n".join(lines)


def build_message(
    html_body: str,
    text_body: str,
    config: EmailConfig,
) -> MIMEMultipart:
    """Build a MIME multipart message with HTML and plain-text alternatives."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Job Finder — Weekly Digest"
    msg["From"] = config.email_from
    msg["To"] = config.email_to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def send_email(
    html_body: str,
    text_body: str,
    config: EmailConfig,
) -> None:
    """Send the digest email via SMTP."""
    if not config.smtp_host:
        raise ValueError("SMTP_HOST is not configured.")
    if not config.email_from or not config.email_to:
        raise ValueError("EMAIL_FROM and EMAIL_TO must be configured.")
    msg = build_message(html_body, text_body, config)
    context = ssl.create_default_context()
    port = config.smtp_port
    logger.info("Sending email to %s via %s:%d", config.email_to, config.smtp_host, port)
    if port == 465:
        with smtplib.SMTP_SSL(config.smtp_host, port, context=context) as server:
            _login_and_send(server, config, msg)
    else:
        with smtplib.SMTP(config.smtp_host, port) as server:
            server.starttls(context=context)
            _login_and_send(server, config, msg)
    logger.info("Email sent successfully")


def _login_and_send(server: smtplib.SMTP, config: EmailConfig, msg: MIMEMultipart) -> None:
    """Log in (if credentials provided) and send the message."""
    if config.smtp_username and config.smtp_password:
        server.login(config.smtp_username, config.smtp_password)
    server.sendmail(config.email_from, [config.email_to], msg.as_string())
