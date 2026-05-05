#!/usr/bin/env python3
"""
download_data.py
----------------
Downloads the Microsoft Forms Excel file from OneDrive
and converts it to a CSV for the dashboard generator.

The OneDrive sharing URL is stored as a GitHub Secret: ONEDRIVE_URL
"""

import os
import csv
import requests
import openpyxl
from io import BytesIO

ONEDRIVE_URL = os.environ.get('ONEDRIVE_URL', '')
OUTPUT_CSV   = 'data/outreach_data.csv'

def onedrive_to_direct(url):
    """
    Convert a standard OneDrive share URL to a direct download URL.
    Works for both personal OneDrive and SharePoint/OneDrive for Business.
    """
    # If it already looks like a direct download, use as-is
    if 'download=1' in url or 'download.aspx' in url.lower():
        return url

    # For personal OneDrive share links (1drv.ms or onedrive.live.com)
    if '1drv.ms' in url or 'onedrive.live.com' in url:
        # Replace resid/view params with download=1
        return url.replace('redir?', 'download?').replace('embed?', 'download?') + '&download=1'

    # For SharePoint / OneDrive for Business
    # Convert sharing URL to download URL
    if 'sharepoint.com' in url or 'my.sharepoint.com' in url:
        # Append download=1 if not present
        sep = '&' if '?' in url else '?'
        return url + sep + 'download=1'

    # Fallback — try appending download param
    sep = '&' if '?' in url else '?'
    return url + sep + 'download=1'


def download_excel(url):
    """Download the Excel file and return as bytes."""
    direct_url = onedrive_to_direct(url)
    print(f"Downloading from OneDrive...")

    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; NeuroEngage-Bot/1.0)'
    }

    response = requests.get(direct_url, headers=headers, timeout=30, allow_redirects=True)
    response.raise_for_status()

    content_type = response.headers.get('Content-Type', '')
    print(f"Response: {response.status_code} | Content-Type: {content_type} | Size: {len(response.content)} bytes")

    return response.content


def excel_to_csv(excel_bytes, output_path):
    """Convert first sheet of Excel file to CSV."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    wb = openpyxl.load_workbook(BytesIO(excel_bytes), data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Excel file appears to be empty.")

    print(f"Excel sheet: {ws.title} | Rows: {len(rows)} | Columns: {len(rows[0])}")

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        for row in rows:
            # Convert None to empty string
            writer.writerow(['' if v is None else str(v) for v in row])

    print(f"Saved CSV: {output_path} ({len(rows)-1} data rows)")


def main():
    if not ONEDRIVE_URL:
        raise EnvironmentError(
            "ONEDRIVE_URL secret is not set.\n"
            "Go to your GitHub repo > Settings > Secrets and variables > Actions\n"
            "and add a secret named ONEDRIVE_URL with your OneDrive sharing link."
        )

    excel_bytes = download_excel(ONEDRIVE_URL)
    excel_to_csv(excel_bytes, OUTPUT_CSV)
    print("Download complete.")


if __name__ == '__main__':
    main()
