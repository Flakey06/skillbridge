"""Excel snapshot of staff statistics; called only by the staff-protected view."""
from io import BytesIO
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook


def statistics_workbook(context):
    book = Workbook()
    book.remove(book.active)

    def sheet(name, headings, rows):
        page = book.create_sheet(name)
        page.append(headings)
        for row in rows:
            # All strings are literal, including user-controlled names beginning '='.
            page.append(list(row))
            for cell in page[page.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
        page.freeze_panes = 'A2'
        page.auto_filter.ref = page.dimensions
        for column in page.columns:
            page.column_dimensions[column[0].column_letter].width = min(60, max(18, max(len(str(c.value or '')) for c in column) + 2))

    match = context['match_statistics']
    sheet('Overview', ['Metric', 'Value'], context['metrics'] + [
        ('Snapshot (SGT)', timezone.localtime(context['updated_at']).isoformat()),
        ('Overview range', 'All recorded history through snapshot time'),
        ('Successfully matched candidates', match['matched']),
        ('Match denominator: registered candidates', match['total']),
        ('Successful match percent', match['percent']),
    ])
    sheet('Application Progress', ['Status', 'Applications', 'Percent of all applications'],
          [(r['label'], r['count'], r['percentage']) for r in context['statuses']])
    sheet('Onboarding', ['Role', 'Registered (denominator)', 'Completed', 'Not recorded', 'Completion percent'],
          [(r['label'], r['total'], r['completed'], r['not_recorded'], r['percent']) for r in context['onboarding_statistics']])
    sheet('Top Jobs', ['Job', 'Company', 'Applications (all history)'],
          [(j.title, j.company.name, j.application_total) for j in context['popular_jobs']])
    sheet('Payments', ['Payer', 'Email', 'Amount', 'Currency', 'Status', 'Paid at (SGT)'],
          [(p.user.username, p.user.email, p.amount, p.currency, p.status,
            timezone.localtime(p.paid_at).isoformat() if p.paid_at else '') for p in context['payment_records']])
    charts = context['member_charts']
    sheet('Member Categories', ['Category', 'Members', 'Percent', 'Denominator', 'From (inclusive)', 'To (inclusive)', 'Role'],
          [(c['name'], c['count'], c['percent'], charts['total'], charts['from'] or 'First record',
            charts['to'] or 'Latest record', charts['role']) for c in charts['categories']])
    sheet('Member Growth', ['Date', 'New members', 'Cumulative in selected range', 'Category filter'],
          [(r['day'], r['new'], r['count'], charts['selected'] or 'All categories') for r in charts['growth']])
    output = BytesIO()
    book.save(output)
    response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="skillbridge-statistics.xlsx"'
    return response
