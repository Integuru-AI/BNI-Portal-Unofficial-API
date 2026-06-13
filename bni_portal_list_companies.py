from curl_cffi import requests
from bs4 import BeautifulSoup
import re


def run(headers, user_input):
    """List CRM companies with pagination and sorting."""
    base_url = BASE_URL.rstrip("/")

    # Parse input
    page = user_input.get("page", 1)
    sort = user_input.get("sort")

    try:
        page = int(page)
    except (TypeError, ValueError):
        return {'status_code': 400, 'body': {'error': 'page must be an integer'}}

    valid_sorts = ["name", "primaryCompanyRoleID", "category", "primaryContactFullName", "created"]
    if sort and sort not in valid_sorts:
        return {'status_code': 400, 'body': {'error': f'sort must be one of: {", ".join(valid_sorts)}'}}

    # Build URL
    url = f"{base_url}/crmCompany/admin"
    params = {}
    if sort:
        params["sort"] = sort
    if page > 1:
        params["CrmCompany_page"] = str(page)

    try:
        companies, total_count = _fetch_companies(url, params, headers)
    except PermissionError as e:
        return {'status_code': 401, 'body': {'error': str(e)}}
    except Exception as e:
        return {'status_code': 500, 'body': {'error': str(e)}}

    page_size = 20
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    return {
        'status_code': 200,
        'body': {
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'companies': companies
        }
    }

# === PRIVATE ===

def _fetch_companies(url, params, headers):
    """Fetch and parse companies from the CRM admin page."""
    # Make request
    req_headers = {
        **headers,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
    }

    response = requests.get(
        url,
        params=params,
        headers=req_headers,
        impersonate="chrome110",
        timeout=30
    )

    # Check for auth failure
    if response.status_code == 302 or "/login" in response.url or response.status_code == 401:
        raise PermissionError('Session expired')

    if response.status_code != 200:
        raise Exception(f'Request failed with status {response.status_code}')

    html = response.text

    # Check if we got a login page instead of data
    if 'list-row' not in html and ('id="login-form"' in html or 'action="/login"' in html.lower()):
        raise PermissionError('Session expired')

    # Parse HTML
    soup = BeautifulSoup(html, "html.parser")

    # Extract total count from first data row
    total_count = 0
    first_row = soup.find("tr", class_="list-row")
    if first_row and first_row.get("data-total-items-count"):
        try:
            total_count = int(first_row["data-total-items-count"])
        except (ValueError, TypeError):
            total_count = 0

    # Parse company rows
    companies = []
    rows = soup.find_all("tr", class_="list-row")
    for row in rows:
        company = {}

        # Company ID from row id attribute
        company["company_id"] = row.get("id", "")

        cells = row.find_all("td")
        if len(cells) < 8:
            continue

        # Role (cells[2])
        role_div = cells[2].find("div", class_="userRole")
        company["role"] = role_div.get_text(strip=True) if role_div else ""

        # Name (cells[3]) - direct text content
        company["name"] = cells[3].get_text(strip=True)

        # Category (cells[4]) - from sd-category-pill config or plain text
        category_cell = cells[4]
        category_pill = category_cell.find("sd-category-pill")
        if category_pill:
            config_attr = category_pill.get("config", "")
            label_match = re.search(r"'label'\s*:\s*'([^']*)'", config_attr)
            company["category"] = label_match.group(1) if label_match else ""
        else:
            cat_text = category_cell.get_text(strip=True)
            company["category"] = "" if cat_text == "No Category Assigned" else cat_text

        # Primary Contact (cells[5])
        contact_cell = cells[5]
        contact_link = contact_cell.find("a")
        if contact_link:
            # Extract contact name (first text node, before the <p> status)
            contact_name_parts = []
            for child in contact_link.children:
                if isinstance(child, str):
                    contact_name_parts.append(child.strip())
                else:
                    break
            company["primary_contact"] = " ".join(contact_name_parts).strip()

            # Extract contact ID from href like /crmContacts/8270643
            href = contact_link.get("href", "")
            contact_id_match = re.search(r"/crmContacts/(\d+)", href)
            company["primary_contact_id"] = contact_id_match.group(1) if contact_id_match else ""

            # Extract invitation status from <p> tag
            status_p = contact_link.find("p")
            company["primary_contact_status"] = status_p.get_text(strip=True) if status_p else ""
        else:
            company["primary_contact"] = ""
            company["primary_contact_id"] = ""
            company["primary_contact_status"] = ""

        # Created date (cells[6])
        company["created"] = cells[6].get_text(strip=True)

        companies.append(company)

    return companies, total_count
