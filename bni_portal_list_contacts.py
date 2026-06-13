from curl_cffi import requests
from bs4 import BeautifulSoup
import re


def run(headers, user_input):
    """List CRM contacts with pagination and sorting."""
    base_url = BASE_URL.rstrip("/")

    # Parse input
    page = user_input.get("page", 1)
    sort = user_input.get("sort")

    try:
        page = int(page)
    except (TypeError, ValueError):
        return {'status_code': 400, 'body': {'error': 'page must be an integer'}}

    valid_sorts = ["name", "email", "roleID", "companyName", "created", "userLastVisit"]
    if sort and sort not in valid_sorts:
        return {'status_code': 400, 'body': {'error': f'sort must be one of: {", ".join(valid_sorts)}'}}

    # Build URL
    url = f"{base_url}/crmContacts/admin"
    params = {}
    if sort:
        params["sort"] = sort
    if page > 1:
        params["CrmContacts_page"] = str(page)

    try:
        contacts, total_count = _fetch_contacts(url, params, headers)
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
            'contacts': contacts
        }
    }

# === PRIVATE ===

def _fetch_contacts(url, params, headers):
    """Fetch and parse contacts from the CRM admin page."""
    # Make request - initial page load uses GET
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
    # A login page won't have the contacts grid data
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

    # Parse contact rows
    contacts = []
    rows = soup.find_all("tr", class_="list-row")
    for row in rows:
        contact = {}

        # Contact ID from row id attribute
        contact["contact_id"] = row.get("id", "")

        # User ID from userID attribute (BS4 lowercases attribute names)
        contact["user_id"] = row.get("userid", "")

        # Title/job title from sd-oscar-grid-view-row attribute
        title_attr = row.get("sd-oscar-grid-view-row", "")
        title_match = re.search(r"'title'\s*:\s*'([^']*)'", title_attr)
        if title_match:
            contact["title"] = title_match.group(1) if title_match.group(1) != "null" else ""
        else:
            # Check for null value
            null_match = re.search(r"'title'\s*:\s*null", title_attr)
            contact["title"] = ""

        cells = row.find_all("td")
        if len(cells) < 9:
            continue

        # Avatar cell (cells[1]) - extract name from img title or figure title
        avatar_cell = cells[1]
        img = avatar_cell.find("img")
        figure = avatar_cell.find("figure")
        avatar_name = ""
        if img and img.get("title"):
            avatar_name = img["title"]
        elif figure and figure.get("title"):
            avatar_name = figure["title"]

        # Role (cells[2])
        role_div = cells[2].find("div", class_="userRole")
        contact["role"] = role_div.get_text(strip=True) if role_div else ""

        # Name (cells[3])
        name_cell = cells[3]
        name_link = name_cell.find("a")
        contact["name"] = name_link.get_text(strip=True) if name_link else avatar_name

        # Check if primary contact (star icon)
        star_icon = name_cell.find("i", class_="sd-primary-star")
        contact["is_primary"] = star_icon is not None

        # Email (cells[4])
        email_cell = cells[4]
        email_input = email_cell.find("input", attrs={"ng-value": True})
        if email_input:
            # ng-value is like "'email@domain.com'"
            ng_val = email_input.get("ng-value", "")
            contact["email"] = ng_val.strip("'")
        else:
            email_link = email_cell.find("a")
            contact["email"] = email_link.get_text(strip=True) if email_link else ""

        # Companies (cells[5])
        company_cell = cells[5]
        companies = []
        # Company names can be in img alt/title or div title
        company_links = company_cell.find_all("a")
        for comp_link in company_links:
            comp_img = comp_link.find("img")
            comp_div = comp_link.find("div")
            comp_name = ""
            comp_id = ""

            # Extract company ID from href like /crmCompany/2089635/people
            href = comp_link.get("href", "")
            comp_id_match = re.search(r"/crmCompany/(\d+)", href)
            if comp_id_match:
                comp_id = comp_id_match.group(1)

            if comp_img and comp_img.get("alt") and comp_img["alt"] != "Company Logo":
                comp_name = comp_img["alt"]
            elif comp_div and comp_div.get("title"):
                comp_name = comp_div["title"]
            elif comp_img and comp_img.get("title"):
                comp_name = comp_img["title"]

            if comp_id:
                companies.append({"company_id": comp_id, "name": comp_name})

        contact["companies"] = companies

        # Created date (cells[6])
        contact["created"] = cells[6].get_text(strip=True)

        # Last login (cells[7])
        contact["last_login"] = cells[7].get_text(strip=True)

        contacts.append(contact)

    return contacts, total_count
