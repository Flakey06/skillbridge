"""Parse timestamped speaker turns and suggest answers without external services."""
import re
from difflib import SequenceMatcher
from resumes.services import _job_skills


def parse_turns(text):
    turns = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.isdigit() or '-->' in line or line == 'WEBVTT':
            continue
        match = re.match(r'^([^:]{1,100}):\s*(.*)$', line)
        if match:
            turns.append({'speaker': match[1].strip(), 'text': match[2]})
        elif turns:
            turns[-1]['text'] += ' ' + line
    return turns


def sample_questions(job):
    skills = _job_skills(job)[:6]
    questions = [f'Describe a specific example of how you used {skill}. What did you do and what was the outcome?' for skill in skills]
    return questions + [f'What experience best prepares you for the {job.title} role?',
                        'Describe a difficult problem you solved. What was your contribution and the result?']


STOP = set('a an the is are was were be to of for in on and or you your how what did do describe specific example used use outcome experience tell me about with this that it'.split())


def tokens(text):
    return set(re.findall(r'[a-z0-9+#]+', text.lower())) - STOP


def question_answer_exchanges(turns, candidate_speaker):
    exchanges = []
    for index, turn in enumerate(turns):
        if turn['speaker'] == candidate_speaker:
            continue
        # A speaker selection mistake must not turn answer statements into questions.
        text = turn['text'].strip()
        if '?' not in text and not re.match(
                r'^(describe|explain|tell me|walk me|give (?:me |an? )|how|what|why|when|where|which|can you|could you|do you|have you)\b',
                text, re.I):
            continue
        answers = []
        for reply in turns[index + 1:]:
            if reply['speaker'] != candidate_speaker:
                break
            answers.append(reply['text'])
        exchanges.append((turn['text'], '\n'.join(answers)))
    return exchanges


def suggest_answers(rows, turns, candidate_speaker):
    exchanges = question_answer_exchanges(turns, candidate_speaker)
    result = []
    for row in rows:
        row = dict(row)
        # Preserve recruiter edits; rerunning matching only fills blank answers.
        if not row.get('answer'):
            ranked = []
            for question, answer in exchanges:
                if not answer:
                    continue
                left, right = tokens(row['question']), tokens(question)
                coverage = len(left & right) / len(left) if left else 0
                similarity = SequenceMatcher(None, row['question'].lower(), question.lower()).ratio()
                score = max(coverage, similarity)
                ranked.append((score, question, answer))
            if ranked:
                score, question, answer = max(ranked)
                if score >= .45:
                    row.update(answer=answer, source_question=question,
                               match_note=f'Suggested local text match ({round(score * 100)}% similarity); check against the transcript.')
        result.append(row)
    return result


def extractive_summary(rows):
    return '\n\n'.join(f"{row['question']}\n{row['answer'][:600]}" for row in rows if row.get('answer'))


def additional_transcript_questions(rows, turns, candidate_speaker):
    """Questions not linked to the prepared list; suggestions require recruiter review."""
    linked = {(row.get('source_question') or '').strip().casefold() for row in rows}
    prepared = {(row.get('question') or '').strip().casefold() for row in rows}
    return [{'question': question, 'answer': answer} for question, answer in
            question_answer_exchanges(turns, candidate_speaker)
            if question.strip().casefold() not in linked | prepared]
