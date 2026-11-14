"""Aggregate human interview ratings independently of automated matching scores."""
from decimal import Decimal, ROUND_HALF_UP


def compile_interview_rating(reviews):
    ratings = []
    total = 0
    for review in reviews:
        for question in review.questions:
            total += 1
            rating = question.get('rating')
            if isinstance(rating, int) and not isinstance(rating, bool) and 1 <= rating <= 5:
                ratings.append(rating)
    if not ratings:
        return None
    average = Decimal(sum(ratings)) / len(ratings)
    return {
        'average': average.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP),
        'percentage': int((average * 20).quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
        'rated_count': len(ratings), 'question_count': total,
    }
