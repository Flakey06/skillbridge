"""Structure saved resume text for display without rewriting its content."""

from .content import RESUME_HEADINGS


def resume_document(content, fallback_name):
    lines = (content or '').splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    name = fallback_name
    if lines:
        first = lines[0].strip()
        if (first.upper().rstrip(':') not in RESUME_HEADINGS
                and len(first) <= 120 and len(first.split()) <= 10
                and '@' not in first and '://' not in first):
            name = lines.pop(0).strip()
    contacts = []
    sections = []
    current = None
    has_headings = any(line.strip().upper().rstrip(':') in RESUME_HEADINGS for line in lines)
    for line in lines:
        text = line.strip()
        if not text:
            continue
        heading = text.upper().rstrip(':')
        if heading in RESUME_HEADINGS:
            current = {'heading': heading.title(), 'lines': []}
            sections.append(current)
        elif current is None and has_headings:
            contacts.append(text)
        else:
            if current is None:
                current = {'heading': '', 'lines': []}
                sections.append(current)
            bullet = text.startswith(('- ', '• ', '* '))
            current['lines'].append({'text': text[2:] if bullet else text, 'bullet': bullet})
    return {'name': name, 'contacts': contacts, 'sections': sections}
