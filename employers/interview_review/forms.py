from django import forms
from django.forms import formset_factory


class ReviewForm(forms.Form):
    transcript_file = forms.FileField(required=False, label='Transcript (.txt)', widget=forms.FileInput(attrs={'accept': '.txt'}))
    transcript = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 8}))
    candidate_speaker = forms.ChoiceField(required=False, label='Candidate speaker')
    summary = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 6}), label='Transcript answer summary')
    loose_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 5}), label='Loose thoughts and question ideas')
    overall_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4}))

    def __init__(self, *args, speakers=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['candidate_speaker'].choices = [('', 'Choose the candidate’s speaker name')] + [(name, name) for name in speakers]

    def clean_transcript_file(self):
        upload = self.cleaned_data.get('transcript_file')
        if upload and (not upload.name.lower().endswith('.txt') or upload.size > 2 * 1024 * 1024):
            raise forms.ValidationError('Upload a .txt file no larger than 2 MB.')
        return upload


class QuestionForm(forms.Form):
    question = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={'rows': 2}))
    answer = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4}), label='Candidate answer — review and edit')
    rating = forms.TypedChoiceField(required=False, coerce=int, empty_value=None,
        choices=[('', 'Not rated')] + [(i, text) for i, text in enumerate([
            '1 — No relevant evidence', '2 — Limited evidence', '3 — Meets expectations',
            '4 — Strong evidence', '5 — Exceptional evidence'], 1)])
    source_question = forms.CharField(required=False, widget=forms.HiddenInput)
    match_note = forms.CharField(required=False, widget=forms.HiddenInput)


QuestionFormSet = formset_factory(QuestionForm, extra=0, can_delete=True, max_num=30, validate_max=True, absolute_max=30)
