from urllib.parse import quote, urlparse




def website_logo_url(website):
    """Return a lightweight website icon fallback when no logo is supplied."""
    if not website:
        return ""
    parsed = urlparse(website if "://" in website else f"https://{website}")
    if not parsed.netloc:
        return ""
    return f"https://www.google.com/s2/favicons?domain={quote(parsed.netloc)}&sz=128"
