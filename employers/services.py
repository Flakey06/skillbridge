import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen




def website_logo_url(website):
    """Return a lightweight website icon fallback when no logo is supplied."""
    if not website:
        return ""
    parsed = urlparse(website if "://" in website else f"https://{website}")
    if not parsed.netloc:
        return ""
    return f"https://www.google.com/s2/favicons?domain={quote(parsed.netloc)}&sz=128"


COMPANY_CATALOG = [
    ("Shopee", "https://shopee.sg"), ("Grab", "https://grab.com"),
    ("Tencent", "https://tencent.com"), ("ByteDance", "https://bytedance.com"),
    ("Google", "https://google.com"), ("Microsoft", "https://microsoft.com"),
    ("Amazon", "https://amazon.com"), ("Meta", "https://meta.com"),
    ("Apple", "https://apple.com"), ("Netflix", "https://netflix.com"),
    ("IBM", "https://ibm.com"), ("Oracle", "https://oracle.com"),
    ("SAP", "https://sap.com"), ("Accenture", "https://accenture.com"),
    ("TikTok", "https://tiktok.com"), ("DBS Bank", "https://dbs.com"),
    ("OCBC Bank", "https://ocbc.com"), ("United Overseas Bank", "https://uobgroup.com"),
    ("Singapore Airlines", "https://singaporeair.com"),
    ("GovTech Singapore", "https://tech.gov.sg"),
    ("National University of Singapore (NUS)", "https://nus.edu.sg"),
    ("Nanyang Technological University (NTU)", "https://ntu.edu.sg"),
    ("Singapore Management University (SMU)", "https://smu.edu.sg"),
    ("Singapore University of Technology and Design (SUTD)", "https://sutd.edu.sg"),
    ("Singapore Institute of Technology (SIT)", "https://singaporetech.edu.sg"),
    ("Singapore University of Social Sciences (SUSS)", "https://suss.edu.sg"),
    ("Singapore Polytechnic", "https://sp.edu.sg"),
    ("Ngee Ann Polytechnic", "https://np.edu.sg"),
    ("Temasek Polytechnic", "https://tp.edu.sg"),
    ("Nanyang Polytechnic", "https://nyp.edu.sg"),
    ("Republic Polytechnic", "https://rp.edu.sg"),
]


def company_matches(query, limit=8):
    """Return server-rendered company suggestions without browser scripting."""
    from .models import Company

    query = (query or "").strip()
    if not query:
        return []
    records = {
        website.casefold(): {"name": name, "website": website, "logo_url": website_logo_url(website)}
        for name, website in COMPANY_CATALOG if query.casefold() in name.casefold()
    }
    for company in Company.objects.filter(name__icontains=query).exclude(website="")[:limit]:
        records[company.website.casefold()] = {
            "name": company.name, "website": company.website,
            "logo_url": company.logo_url or website_logo_url(company.website),
        }
    if not records:
        for company in _wikidata_company_matches(query, limit):
            records[company["website"].casefold()] = company
    return list(records.values())[:limit]


def _wikidata_json(params):
    url = "https://www.wikidata.org/w/api.php?" + urlencode({**params, "format": "json", "origin": "*"})
    request = Request(url, headers={"User-Agent": "SkillBridge/1.0 company-profile lookup"})
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _claim_value(entity, property_id):
    for claim in entity.get("claims", {}).get(property_id, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str) and value:
            return value
    return ""


def _wikidata_company_matches(query, limit):
    """Find organizations with an official website in Wikidata.

    Wikidata is a broad public directory, so results remain suggestions that
    the recruiter must review before saving.
    """
    try:
        search = _wikidata_json({
            "action": "wbsearchentities", "search": query, "language": "en",
            "type": "item", "limit": min(limit * 2, 20),
        }).get("search", [])
        ids = [item["id"] for item in search if item.get("id")]
        if not ids:
            return []
        entities = _wikidata_json({
            "action": "wbgetentities", "ids": "|".join(ids),
            "props": "claims|labels|descriptions", "languages": "en",
        }).get("entities", {})
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return []

    results = []
    for item in search:
        entity = entities.get(item.get("id"), {})
        website = _claim_value(entity, "P856")
        if not website or not website.startswith(("https://", "http://")):
            continue
        logo_file = _claim_value(entity, "P154")
        logo_url = (
            "https://commons.wikimedia.org/wiki/Special:Redirect/file/" + quote(logo_file)
            if logo_file else website_logo_url(website)
        )
        results.append({
            "name": item.get("label") or query,
            "website": website,
            "logo_url": logo_url,
            "description": item.get("description", ""),
        })
        if len(results) >= limit:
            break
    return results
