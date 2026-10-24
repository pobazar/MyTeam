-- Run only as the operator, never expose these queries via the participant API.
set search_path = myteam, public;
-- Returning people: same stable person ID in multiple published rounds.
select person_id, count(distinct round_id) as rounds
from myteam_member m join myteam_round r on r.id=m.round_id
where r.published_at is not null group by person_id having count(distinct round_id)>1;
-- At least one confirmation, separately from individual answers/missing answers.
select m.meeting_id,
 bool_or(f.outcome='yes') as confirmed_by_someone,
 count(*) filter(where f.id is null) as no_answer,
 count(*) filter(where f.outcome='pending') as not_yet,
 count(*) filter(where f.outcome='no') as did_not_happen
from myteam_member m join myteam_round r on r.id=m.round_id
left join myteam_feedback f on f.member_id=m.id
where r.published_at is not null group by m.meeting_id;
-- Cross-team pairs, including all three internal pairs of a triple; snapshots, not today's profile.
select a.meeting_id,a.person_id,b.person_id,
 a.snapshot->>'team' as team_a,b.snapshot->>'team' as team_b
from myteam_member a join myteam_member b on a.meeting_id=b.meeting_id and a.person_id<b.person_id
join myteam_round r on r.id=a.round_id
where r.published_at is not null and a.snapshot->>'team_group' is not null
and b.snapshot->>'team_group' is not null and a.snapshot->>'team_group'<>b.snapshot->>'team_group';
-- Personal impressions and intentions; missing answers are not negative answers.
select impression,again,count(*) from myteam_feedback where outcome='yes' group by impression,again;
-- Immutable-by-application event revisions (comments are operator-only).
select kind,created_at,person_id,round_id,payload from myteam_analyticsevent order by created_at;
