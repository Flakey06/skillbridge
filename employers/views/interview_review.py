"""Server-rendered review of completed interviews and uploaded transcripts."""
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import recruiter_required
from applications.models import Interview, InterviewReview
from employers.interview_review.forms import ReviewForm, QuestionFormSet
from employers.interview_review.transcripts import parse_turns, sample_questions, suggest_answers, extractive_summary
from .common import _context


@recruiter_required
def interview_review(request, interview_id):
    interview = get_object_or_404(Interview.objects.select_related('application__job', 'application__candidate'),
        pk=interview_id, application__job__created_by=request.user)
    saved = InterviewReview.objects.filter(interview=interview).first()
    initial = {'transcript': interview.transcript, 'summary': interview.summary,
               'candidate_speaker': saved.candidate_speaker if saved else '',
               'overall_notes': saved.overall_notes if saved else '',
               'loose_notes': saved.loose_notes if saved else ''}
    rows = saved.questions if saved else [{'question': q} for q in sample_questions(interview.application.job)]
    data = request.POST.copy() if request.method == 'POST' else None
    upload_error = ''
    if data is not None and request.FILES.get('transcript_file'):
        upload = request.FILES['transcript_file']
        if not upload.name.lower().endswith('.txt') or upload.size > 2 * 1024 * 1024:
            upload_error = 'Upload a .txt file no larger than 2 MB.'
        else:
            try:
                data['transcript'] = upload.read().decode('utf-8-sig')
            except UnicodeDecodeError:
                upload_error = 'Save the transcript as UTF-8 text and upload it again.'
    remove_index = data.get('remove_question', '') if data is not None else ''
    if remove_index.isdecimal() and 0 <= int(remove_index) < 30:
        data[f'questions-{int(remove_index)}-DELETE'] = 'on'
        data['action'] = 'remove_question'
    text = data.get('transcript', '') if data is not None else initial['transcript']
    turns = parse_turns(text)
    speakers = list(dict.fromkeys(turn['speaker'] for turn in turns))
    form = ReviewForm(data, request.FILES or None, initial=initial, speakers=speakers)
    formset = QuestionFormSet(data, initial=rows, prefix='questions')
    if data is not None:
        form_valid, questions_valid = form.is_valid(), formset.is_valid()
        if upload_error:
            form.add_error('transcript_file', upload_error)
            form_valid = False
        if form_valid and questions_valid:
            rows = [{k: v for k, v in row.items() if k != 'DELETE'} for row in formset.cleaned_data
                    if row and not row.get('DELETE')]
            action = data.get('action')
            if action == 'add_question':
                if len(rows) < 30:
                    rows.append({'question': ''})
                else:
                    messages.warning(request, 'A review can contain up to 30 questions.')
            elif action == 'notes_to_questions':
                existing = {row['question'].strip().casefold() for row in rows}
                for line in form.cleaned_data['loose_notes'].splitlines():
                    question = line.strip().lstrip('-• ').strip()
                    if question and question.casefold() not in existing and len(rows) < 30:
                        rows.append({'question': question[:1000]})
                        existing.add(question.casefold())
                messages.info(request, 'Added note lines as questions. Review their wording and save the workspace to keep them.')
            elif action == 'analyse':
                speaker = form.cleaned_data['candidate_speaker']
                if not turns:
                    form.add_error('transcript', 'No speaker-labelled turns found. Use lines such as “Alex: question” and “Sarah: answer”.')
                    form_valid = False
                elif not speaker:
                    form.add_error('candidate_speaker', 'Choose the candidate’s speaker name, then match answers.')
                    form_valid = False
                else:
                    rows = suggest_answers(rows, turns, speaker)
                    suggested_count = sum(bool(row.get('source_question')) and bool(row.get('answer')) for row in rows)
                    if suggested_count:
                        messages.info(request, f'{suggested_count} question(s) have suggested answers from {speaker}. Check the answer fields in the middle column.')
                    else:
                        messages.warning(request, 'No answers could be matched. Check that the selected candidate speaker is the person answering questions, and that your question wording matches the transcript.')
                    if not data.get('summary', '').strip():
                        data['summary'] = extractive_summary(rows)
            elif action in {'save', 'remove_question'}:
                with transaction.atomic():
                    InterviewReview.objects.update_or_create(interview=interview, defaults={
                        'candidate_speaker': form.cleaned_data['candidate_speaker'], 'questions': rows,
                        'overall_notes': form.cleaned_data['overall_notes'],
                        'loose_notes': form.cleaned_data['loose_notes'], 'reviewed_by': request.user})
                    interview.transcript = form.cleaned_data['transcript']
                    interview.summary = form.cleaned_data['summary']
                    interview.save(update_fields=['transcript', 'summary'])
                messages.success(request, 'Question removed and workspace saved.' if action == 'remove_question' else 'Interview review saved.')
                return redirect('recruiter_interview_review', interview_id=interview.pk)
            # Redisplay preview/add actions without saving or losing the entered text.
            if form_valid:
                form = ReviewForm(initial={key: data.get(key, '') for key in initial}, speakers=speakers)
                formset = QuestionFormSet(initial=rows, prefix='questions')
    speaker_previews = [{'name': name, 'example': next(turn['text'][:240] for turn in turns if turn['speaker'] == name)} for name in speakers]
    return render(request, 'employers/interview_review.html', _context(request,
        interview=interview, form=form, question_formset=formset,
        transcript_turn_count=len(turns), speaker_previews=speaker_previews))


@recruiter_required
def interviews(request):
    entries = Interview.objects.filter(application__job__created_by=request.user).select_related(
        'application__candidate', 'application__job').order_by('-scheduled_start')
    return render(request, 'employers/interviews.html', _context(request, interviews=entries))
