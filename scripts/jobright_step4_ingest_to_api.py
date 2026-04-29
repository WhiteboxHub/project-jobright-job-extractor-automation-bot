#!/usr/bin/env python3
"""
Jobright Step 4: Ingest to API
===============================
Transforms categorized job data into the backend API format and performs bulk ingestion.
"""

import json
import os
import sys
import argparse
import requests
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from core.logger import logger
from core.auth_service import auth_service, BaseAPIClient
from config.settings import settings

def _clean_company_name(raw: str) -> str:
    """Extract just the company name, stripping description after colon."""
    if not raw:
        return raw
    name = raw.split(':')[0].strip()
    name = name.rstrip('.,;-').strip()
    return name or raw

def _normalize_employment_mode(raw: str) -> str:
    """Normalize employment mode to lowercase API values."""
    if not raw:
        return 'onsite'
    r = str(raw).strip().lower()
    if 'remote' in r:
        return 'remote'
    elif 'hybrid' in r:
        return 'hybrid'
    else:
        return 'onsite'

def _normalize_position_type(raw: str) -> str:
    """Normalize position type to lowercase API values."""
    if not raw:
        return 'full_time'
    r = str(raw).strip().lower()
    if 'contract' in r:
        return 'contract'
    elif 'intern' in r:
        return 'internship'
    elif 'part' in r:
        return 'part_time'
    else:
        return 'full_time'

def _is_junk_company(name: str) -> bool:
    """Filter out known junk company names."""
    if not name: return True
    junk = ['unknown', 'n/a', 'none', 'test', 'jobright', 'hiring cafe', 'linkedin']
    return name.lower().strip() in junk

def _build_job_listing(job: dict) -> dict:
    """Build a standard job object for the backend API."""
    title = (job.get('title') or "Unknown Title")[:255]
    company = _clean_company_name(job.get('company') or "Unknown Company")
    location = job.get('location') or ""
    
    if _is_junk_company(company):
        return None

    return {
        "title": title.lower().strip(),
        "company_name": company.lower().strip(),
        "location": location.lower().strip(),
        "city": (job.get('city') or "").lower().strip(),
        "state": (job.get('state') or "").lower().strip(),
        "country": (job.get('country') or "united states").lower().strip(),
        "position_type": _normalize_position_type(job.get('job_type')),
        "employment_mode": _normalize_employment_mode(job.get('work_mode')),
        "source": "jobright",
        "source_uid": job.get('job_id'),
        "job_url": job.get('ats_url') or job.get('jobright_url'),
        "description": job.get('company_description') or job.get('description') or "",
        "status": "open",
        "salary": job.get('salary'),
        "seniority": job.get('seniority')
    }

def ingest_to_api(json_path: str):
    """Process job data and send it to the backend API."""
    input_path = Path(json_path)
    if not input_path.exists():
        logger.error(f"File not found: {json_path}")
        return

    # Initialize API Client
    client = BaseAPIClient()
    
    # Get token to verify auth works
    token = auth_service.get_access_token()
    if not token:
        logger.error("Authentication failed. Check .env AUTH_USERNAME/PASSWORD.")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    processed_count = 0
    batch_data = []
    
    by_ats = data.get('by_ats', {})
    for platform, jobs in by_ats.items():
        logger.info(f"Processing {len(jobs)} jobs for platform: {platform}")
        
        for job in jobs:
            try:
                job_listing = _build_job_listing(job)
                if job_listing:
                    batch_data.append(job_listing)
                
                # Send in batches of 50
                if len(batch_data) >= 50:
                    _send_batch(client, batch_data)
                    processed_count += len(batch_data)
                    batch_data = []
            except Exception as e:
                logger.error(f"Error preparing job {job.get('job_id')}: {e}")

    # Final batch
    if batch_data:
        _send_batch(client, batch_data)
        processed_count += len(batch_data)
    
    logger.info(f"✅ Step 4 complete. Total jobs sent to API: {processed_count}")

def _send_batch(client, batch):
    """Helper to send a batch of positions to the API."""
    endpoint = "positions/bulk"
    payload = {"positions": batch}
    try:
        response = client.post(endpoint, json=payload, timeout=30)
        response.raise_for_status()
        res_data = response.json()
        logger.info(f"Batch success: {res_data.get('inserted', 0)} inserted, {res_data.get('skipped', 0)} duplicates")
    except Exception as e:
        logger.error(f"Failed to send batch to API: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest job data into the backend API.")
    parser.add_argument("--input", default=str(ROOT / "jobright_by_ats.json"), help="Path to by_ats JSON")
    args = parser.parse_args()
    
    ingest_to_api(args.input)