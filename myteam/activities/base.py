"""Shared outcome and achievement contract for weekly activities."""
class WeeklyActivity:
    def final_feedback(self,answer):
        return answer.outcome=='no' or (answer.outcome=='yes' and bool(answer.rating or (answer.impression and answer.again)))
    def feedback_form(self,*args,**kwargs):
        from myteam.feedback import FeedbackForm
        return FeedbackForm(*args,**kwargs)
    def achievement_earned(self,person_id):
        from myteam.models import Feedback
        return Feedback.objects.filter(member__person_id=person_id,member__round__activity=self.key,outcome='yes').exists()
