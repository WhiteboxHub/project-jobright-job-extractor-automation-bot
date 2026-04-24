import json
import smtplib
import re
from email.message import EmailMessage
from pathlib import Path

from config.settings import settings
from core.logger import logger

APPLICATION_NAME = "Jobright.ai Data Pipeline"


class EmailReporter:
    @staticmethod
    def send_report(by_ats_json_path: str):
        """
        Reads the by_ats.json file and sends an HTML summary report via SMTP.
        """
        # Validate SMTP configuration
        if not all([settings.SMTP_SERVER, settings.SMTP_USERNAME, settings.SMTP_PASSWORD, settings.REPORT_RECEIVER_EMAIL]):
            logger.warning("[EMAIL] SMTP configurations are not fully set up. Skipping email report.")
            return

        json_path = Path(by_ats_json_path)
        if not json_path.exists():
            logger.error(f"[EMAIL] Report file not found: {by_ats_json_path}")
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"[EMAIL] Failed to open/parse {by_ats_json_path}: {e}")
            return

        # Extract data for the report
        source = data.get("source", "jobright.ai")
        platforms = data.get("platforms", [])
        by_ats = data.get("by_ats", {})
        
        total_jobs = sum(len(jobs) for jobs in by_ats.values())
        
        # Build HTML table for platforms
        table_rows = ""
        for platform in sorted(platforms):
            count = len(by_ats.get(platform, []))
            table_rows += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-transform: capitalize;">{platform}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right; font-weight: bold; color: #3498db;">{count}</td>
            </tr>
            """

        # Build HTML for Sample Job Links (Max 25 total)
        MAX_LINKS = 25
        links_section = ""
        total_links_added = 0
        
        sorted_platforms = sorted(platforms)
        
        for platform in sorted_platforms:
            if total_links_added >= MAX_LINKS:
                break
                
            jobs = by_ats.get(platform, [])
            if not jobs:
                continue
                
            platform_links = ""
            platform_jobs_added = 0
            
            for job in jobs:
                if total_links_added >= MAX_LINKS:
                    break
                
                title = job.get("job_tittle") or job.get("title") or "Unknown Title"
                url = job.get("ats_url") or job.get("jobright_url")
                if not url:
                    continue
                    
                platform_links += f"""
                <li style="margin-bottom: 6px; color: #3498db;">
                    <span style="color: #95a5a6; font-size: 11px; font-family: monospace;">[{job.get('job_id', 'N/A')}]</span>
                    <a href="{url}" style="color: #3498db; text-decoration: none; font-size: 14px; font-weight: 500;">{title}</a>
                </li>
                """
                total_links_added += 1
                platform_jobs_added += 1
            
            if platform_links:
                remaining_in_platform = len(jobs) - platform_jobs_added
                more_footer = f'<li style="list-style: none; color: #95a5a6; font-size: 12px; margin-top: 4px;">... and {remaining_in_platform} more on {platform}</li>' if remaining_in_platform > 0 else ""
                
                links_section += f"""
                <div style="margin-top: 20px;">
                    <h4 style="color: #34495e; margin-bottom: 10px; text-transform: capitalize; border-left: 3px solid #3498db; padding-left: 10px; font-size: 15px;">{platform}</h4>
                    <ol style="padding-left: 25px; margin: 0; color: #7f8c8d;">
                        {platform_links}
                        {more_footer}
                    </ol>
                </div>
                """

        html_content = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f9f9f9; color: #333; margin: 0; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08);">
                    <h2 style="color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; margin-top: 0;">{APPLICATION_NAME} — Result Summary</h2>
                    <p style="font-size: 16px; color: #555;">The automated scraping pipeline has completed. Below is the summary of jobs found on <strong>{source}</strong>.</p>
                    <div style="background: #ebf5fb; border-radius: 8px; padding: 20px; margin-bottom: 25px;">
                        <span style="display: block; font-size: 14px; color: #5dade2; text-transform: uppercase; font-weight: bold; margin-bottom: 5px;">Total Jobs Discovered</span>
                        <span style="font-size: 32px; font-weight: bold; color: #2e86c1;">{total_jobs}</span>
                    </div>
                    <h3 style="color: #2c3e50; font-size: 18px; margin-bottom: 15px;">Breakdown by Platform</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background-color: #f8f9fa;">
                                <th style="text-align: left; padding: 10px; border-bottom: 2px solid #dee2e6; color: #7f8c8d;">ATS Platform</th>
                                <th style="text-align: right; padding: 10px; border-bottom: 2px solid #dee2e6; color: #7f8c8d;">Count</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>
                    <div style="margin-top: 30px; border-top: 2px solid #f1f1f1; padding-top: 20px;">
                        <h3 style="color: #2c3e50; font-size: 18px; margin-bottom: 15px;">Sample Job Listings</h3>
                        {links_section}
                    </div>
                </div>
            </body>
        </html>
        """

        msg = EmailMessage()
        msg["Subject"] = f"[{APPLICATION_NAME}] {total_jobs} jobs discovered on {source}"
        msg['From'] = settings.SENDER_EMAIL or settings.SMTP_USERNAME
        msg['To'] = settings.REPORT_RECEIVER_EMAIL
        msg.add_alternative(html_content, subtype='html')

        try:
            with open(json_path, 'rb') as f:
                json_data = f.read()
            msg.add_attachment(json_data, maintype="application", subtype="json", filename=json_path.name)
        except Exception:
            pass

        try:
            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT, timeout=30) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
            logger.info(f"[EMAIL] Successfully sent report to {settings.REPORT_RECEIVER_EMAIL}")
        except Exception as e:
            logger.error(f"[EMAIL] Failed to send email: {e}")

email_reporter = EmailReporter()
