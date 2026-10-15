import html
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
        platforms = data.get("platforms") or []
        by_ats = data.get("by_ats") or {}
        
        total_jobs = sum(len(jobs) for jobs in by_ats.values())
        escaped_source = html.escape(str(source))
        
        # Build HTML table for platforms
        table_rows = ""
        for platform in sorted(platforms):
            count = len(by_ats.get(platform, []))
            escaped_platform = html.escape(str(platform))
            table_rows += f"""
            <tr>
                <td style="padding: 12px 15px; font-size: 13px; color: #334155; border-bottom: 1px solid #f1f5f9; text-transform: capitalize;">{escaped_platform}</td>
                <td style="padding: 12px 15px; font-size: 13px; font-weight: 600; text-align: right; color: #1e40af; border-bottom: 1px solid #f1f5f9;">{count}</td>
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
                
                escaped_id = html.escape(str(job.get('job_id', 'N/A')))
                escaped_title = html.escape(str(title))
                escaped_url = html.escape(str(url), quote=True)
                    
                platform_links += f"""
                <li style="margin-bottom: 8px; color: #3b82f6;">
                    <span style="color: #64748b; font-size: 11px; font-family: monospace; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; margin-right: 4px;">[{escaped_id}]</span>
                    <a href="{escaped_url}" style="color: #2563eb; text-decoration: none; font-size: 13px; font-weight: 500;">{escaped_title}</a>
                </li>
                """
                total_links_added += 1
                platform_jobs_added += 1
            
            if platform_links:
                remaining_in_platform = len(jobs) - platform_jobs_added
                escaped_platform_name = html.escape(str(platform))
                more_footer = f'<li style="list-style: none; color: #94a3b8; font-size: 12px; margin-top: 6px;">... and {remaining_in_platform} more on {escaped_platform_name}</li>' if remaining_in_platform > 0 else ""
                
                links_section += f"""
                <div style="margin-top: 15px; background-color: #f8fafc; padding: 16px 20px; border-radius: 8px; border: 1px solid #e2e8f0;">
                    <h4 style="color: #1e40af; margin: 0 0 12px 0; text-transform: capitalize; border-left: 3px solid #3b82f6; padding-left: 10px; font-size: 14px; font-weight: 600;">{escaped_platform_name}</h4>
                    <ol style="padding-left: 22px; margin: 0; color: #64748b;">
                        {platform_links}
                        {more_footer}
                    </ol>
                </div>
                """

        html_content = f"""
        <html>
            <head>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f4f7f9; color: #333; }}
                    .header {{ background: linear-gradient(135deg, #1e4eb8 0%, #3b82f6 100%); color: white; padding: 35px 25px 45px 25px; text-align: left; border-radius: 8px 8px 0 0; }}
                    .header h1 {{ margin: 8px 0 4px 0; font-size: 24px; font-weight: bold; color: #ffffff; }}
                    .header p {{ margin: 0; font-size: 13px; opacity: 0.9; }}
                    .header .sub {{ font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.85; }}
                    .content {{ padding: 30px; max-width: 680px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-top: -20px; }}
                    .intro-text {{ color: #64748b; font-size: 14px; line-height: 1.6; margin-top: 0; margin-bottom: 25px; }}
                    .card-blue {{ background-color: #eff6ff; border: 1px solid #dbeafe; color: #1e40af; padding: 18px 20px; border-radius: 8px; text-align: center; }}
                    .card-blue .val {{ font-size: 28px; font-weight: bold; display: block; margin-bottom: 4px; color: #1e40af; }}
                    .card-blue .lab {{ font-size: 10px; font-weight: bold; text-transform: uppercase; color: #64748b; letter-spacing: 0.5px; }}
                    .section-title {{ font-size: 16px; font-weight: bold; margin: 25px 0 12px 0; display: flex; align-items: center; color: #1e293b; }}
                    table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
                    th {{ background-color: #f8fafc; color: #64748b; font-size: 11px; text-transform: uppercase; text-align: left; padding: 12px 15px; border-bottom: 1px solid #e2e8f0; }}
                    td {{ padding: 12px 15px; font-size: 13px; border-bottom: 1px solid #f1f5f9; }}
                    .footer {{ text-align: center; padding: 25px 20px 10px 20px; font-size: 12px; color: #94a3b8; line-height: 1.6; }}
                </style>
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f4f7f9; color: #333;">
                <div style="max-width: 680px; margin: 20px auto;">
                    <div style="background: linear-gradient(135deg, #1e4eb8 0%, #3b82f6 100%); color: white; padding: 35px 25px 45px 25px; text-align: left; border-radius: 8px 8px 0 0;">
                        <div style="font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.85;">WHITEBOX LEARNING</div>
                        <h1 style="margin: 8px 0 4px 0; font-size: 24px; font-weight: bold; color: #ffffff;">{APPLICATION_NAME} — Result Summary</h1>
                        <p style="margin: 0; font-size: 13px; opacity: 0.9;">Scraping pipeline completed for {escaped_source}</p>
                    </div>

                    <div style="padding: 30px; background: #ffffff; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-top: -20px;">
                        <p style="color: #64748b; font-size: 14px; line-height: 1.6; margin-top: 0; margin-bottom: 25px;">
                            The automated scraping pipeline has completed. Below is the summary of jobs found on <strong>{escaped_source}</strong>.
                        </p>

                        <div style="margin-bottom: 25px;">
                            <div style="padding: 18px 20px; border-radius: 8px; text-align: center; background-color: #eff6ff; border: 1px solid #dbeafe; color: #1e40af;">
                                <span style="font-size: 28px; font-weight: bold; display: block; margin-bottom: 4px; color: #1e40af;">{total_jobs}</span>
                                <span style="font-size: 10px; font-weight: bold; text-transform: uppercase; color: #64748b; letter-spacing: 0.5px;">TOTAL JOBS DISCOVERED</span>
                            </div>
                        </div>

                        <div style="font-size: 16px; font-weight: bold; margin: 25px 0 12px 0; color: #1e293b;">
                            <span style="margin-right: 8px;">📊</span> Breakdown by Platform
                        </div>

                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                            <thead>
                                <tr>
                                    <th style="background-color: #f8fafc; color: #64748b; font-size: 11px; text-transform: uppercase; text-align: left; padding: 12px 15px; border-bottom: 1px solid #e2e8f0;">ATS Platform</th>
                                    <th style="background-color: #f8fafc; color: #64748b; font-size: 11px; text-transform: uppercase; text-align: right; padding: 12px 15px; border-bottom: 1px solid #e2e8f0;">Count</th>
                                </tr>
                            </thead>
                            <tbody>
                                {table_rows}
                            </tbody>
                        </table>

                        <div style="margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 20px;">
                            <div style="font-size: 16px; font-weight: bold; margin-bottom: 15px; color: #1e293b;">
                                <span style="margin-right: 8px;">🔗</span> Sample Job Listings
                            </div>
                            {links_section}
                        </div>
                    </div>

                    <div style="text-align: center; padding: 25px 20px 10px 20px; font-size: 12px; color: #94a3b8; line-height: 1.6;">
                        This is an automated report from {APPLICATION_NAME}.<br>
                        The full data set is attached as a JSON file.
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
