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
from job_finder.models import ScoredJob

logger = logging.getLogger(__name__)


def _format_score(score: float) -> str:
    """Format a score for display."""
    return f"{score:.0f}/100"


def generate_html_email(scored_jobs: list[ScoredJob], total_below_threshold: int = 0) -> str:
    """Generate the HTML body for the job digest email."""
    parts = ['<html><body style="font-family: Arial, sans-serif; ' 'color: #333; max-width: 600px; margin: 0 auto;">']
    parts.append("<h2>Job Finder — Daily Digest</h2>")
    count = len(scored_jobs)
    if count == 0:
        parts.append("<p>No new jobs found matching your criteria today.</p>")
    else:
        parts.append(f"<p>Found <strong>{count}</strong> new job" f"{'s' if count != 1 else ''}.</p>")
    for i, scored in enumerate(scored_jobs, 1):
        parts.append(_render_job_html(i, scored))
    if total_below_threshold > 0:
        parts.append(
            f"<hr><p><em>Additional matches: {total_below_threshold} " "jobs below the email threshold.</em></p>"
        )
    parts.append("</body></html>")
    return "\n".join(parts)


def _render_job_html(index: int, scored: ScoredJob) -> str:
    """Render a single job as HTML."""
    job = scored.job
    title = escape(job.title)
    company = escape(job.company)
    location = escape(job.location) if job.location else ""
    score = _format_score(scored.final_score)
    url = job.url if is_valid_url(job.url) else ""

    parts = ['<div style="margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #eee;">']
    parts.append(f'<h3 style="margin: 0 0 4px 0;">{index}. {title}' f"{' — ' + company if company else ''}</h3>")
    parts.append(f'<p style="margin: 2px 0;"><strong>Score:</strong> {score}</p>')
    if location:
        parts.append(f'<p style="margin: 2px 0;"><strong>Location:</strong> {location}</p>')
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
    lines = ["Job Finder — Daily Digest", "=" * 40, ""]
    count = len(scored_jobs)
    if count == 0:
        lines.append("No new jobs found matching your criteria today.")
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
        f"{index}. {job.title} — {job.company}".rstrip(" —"),
        f"   Score: {_format_score(scored.final_score)}",
    ]
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
    msg["Subject"] = "Job Finder — Daily Digest"
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
