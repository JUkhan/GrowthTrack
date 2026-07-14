# Edge Case Hunt — GrowthTrack PRD

```json
[
  {
    "location": "FR-1",
    "trigger_condition": "Repeated invalid login attempts against an Administrator account",
    "guard_snippet": "Add FR-1 consequence: N consecutive invalid attempts locks the account for a defined cooldown.",
    "potential_consequence": "Brute-force credential attacks against the only login role go unmitigated."
  },
  {
    "location": "FR-1 / FR-9",
    "trigger_condition": "No Administrator exists yet to create the first Administrator account",
    "guard_snippet": "Add: a documented bootstrap/seed process creates the initial Administrator outside FR-9's admin-creates-admin flow.",
    "potential_consequence": "System has no defined path to its first working login."
  },
  {
    "location": "FR-1",
    "trigger_condition": "Administrator forgets their password",
    "guard_snippet": "Add FR-1 consequence: a defined out-of-band password-reset flow exists.",
    "potential_consequence": "A locked-out Administrator has no self-service recovery path."
  },
  {
    "location": "FR-1 / FR-9",
    "trigger_condition": "Administrator account edited or deleted while a session token is still valid",
    "guard_snippet": "Add: deleting/deactivating an Administrator invalidates any outstanding JWT sessions for that account.",
    "potential_consequence": "A removed Administrator can keep acting until natural token expiry."
  },
  {
    "location": "FR-2",
    "trigger_condition": "A Sales User or Manager is promoted to Administrator role",
    "guard_snippet": "Add FR-2 consequence: promotion to Administrator triggers portal credential issuance as a distinct step.",
    "potential_consequence": "Promoted user has an Administrator role but no way to log in."
  },
  {
    "location": "FR-2 / §3 Glossary (Role)",
    "trigger_condition": "A Sales User's Role changes (e.g., promoted to Manager) between sends",
    "guard_snippet": "Add: Role changes take effect for WhatsApp content routing/formatting starting with the next send.",
    "potential_consequence": "Recipient keeps receiving content formatted for their old role after promotion."
  },
  {
    "location": "FR-2 / FR-9",
    "trigger_condition": "The last remaining Administrator account is deleted",
    "guard_snippet": "Add: system blocks deletion/deactivation of the last active Administrator account.",
    "potential_consequence": "Portal becomes permanently inaccessible with no one able to create a replacement."
  },
  {
    "location": "FR-3",
    "trigger_condition": "Zero Sales Teams configured, or a team with zero members",
    "guard_snippet": "Add FR-3 consequence: Dashboard shows an explicit empty state per section when no teams/members exist.",
    "potential_consequence": "Team performance panel could render blank or error with no explanation."
  },
  {
    "location": "FR-3",
    "trigger_condition": "Source data for the day is missing or stale when Dashboard loads",
    "guard_snippet": "Add FR-3 consequence: Dashboard flags stale/missing source data explicitly instead of showing default values.",
    "potential_consequence": "Administrator mistakes missing data for genuinely zero sales."
  },
  {
    "location": "FR-3",
    "trigger_condition": "Notification status queried while a scheduled/manual send is still mid-dispatch",
    "guard_snippet": "Add: notification status includes an explicit in-progress state distinct from success/failure.",
    "potential_consequence": "Dashboard shows a stale or misleading final status during an active send."
  },
  {
    "location": "FR-4",
    "trigger_condition": "Brand sales data for the day is missing or references an unrecognized brand",
    "guard_snippet": "Add FR-4 consequence: records with missing/malformed brand data are excluded and flagged, not silently ranked.",
    "potential_consequence": "Brand lists silently omit or misrank brands with no error signal."
  },
  {
    "location": "FR-4",
    "trigger_condition": "Two brands tie on Sales/Growth for Rank ordering",
    "guard_snippet": "Add: define a deterministic tie-break rule (e.g., alphabetical) when values tie.",
    "potential_consequence": "Rank order is non-deterministic and can flip between runs."
  },
  {
    "location": "FR-4",
    "trigger_condition": "A brand qualifies for more than one of Top/Low-Performing/Focus simultaneously",
    "guard_snippet": "Add: define whether the three brand categories are mutually exclusive.",
    "potential_consequence": "Same brand appears contradictorily in two lists with no resolution rule."
  },
  {
    "location": "FR-5",
    "trigger_condition": "A Territory has zero Doctors",
    "guard_snippet": "Add FR-5 consequence: an empty doctor list renders an explicit 'no doctors in territory' state.",
    "potential_consequence": "Recipients in doctor-less territories get an unexplained gap in their report."
  },
  {
    "location": "FR-5",
    "trigger_condition": "A Doctor record is missing Territory or Target Priority",
    "guard_snippet": "Add: doctor records missing Territory or Target Priority are excluded and flagged, not silently ranked.",
    "potential_consequence": "Visit list mis-ranks or drops doctors with no audit trail."
  },
  {
    "location": "FR-5",
    "trigger_condition": "Two Doctors share identical Target Priority",
    "guard_snippet": "Add: define a deterministic tie-break rule when Target Priority values tie.",
    "potential_consequence": "Doctor visit order is non-deterministic and can flip between reports."
  },
  {
    "location": "FR-5 / FR-6",
    "trigger_condition": "A territory or brand dataset has many qualifying entries for one report",
    "guard_snippet": "Add: define a maximum entry count or truncation rule for doctor/brand lists in the Daily Report.",
    "potential_consequence": "Long lists could break WhatsApp message formatting or size limits."
  },
  {
    "location": "FR-6",
    "trigger_condition": "A person is reachable as an individual Recipient and via a Group/Team simultaneously",
    "guard_snippet": "Add: define de-duplication so a recipient reachable by multiple mechanisms gets exactly one Daily Report.",
    "potential_consequence": "Same person receives duplicate Daily Reports each scheduled run."
  },
  {
    "location": "FR-6",
    "trigger_condition": "Scheduled run fires with zero configured Recipients",
    "guard_snippet": "Add: a run with zero configured Recipients still logs a completed run with zero sends.",
    "potential_consequence": "Unclear whether an empty run counts as success, failure, or goes unlogged."
  },
  {
    "location": "FR-6 / FR-9",
    "trigger_condition": "Administrator edits/removes a Recipient's contact info while their send is in flight",
    "guard_snippet": "Add: in-flight sends use a locked snapshot of recipient data taken at generation time.",
    "potential_consequence": "A send could dispatch to a stale or half-updated phone number."
  },
  {
    "location": "FR-6 / FR-10",
    "trigger_condition": "Recipient revokes opt-in after generation begins but before their message dispatches",
    "guard_snippet": "Add: opt-out is checked immediately before dispatch, not only at generation start, aborting the in-flight send.",
    "potential_consequence": "Recipient could receive a message after opting out within the same cycle."
  },
  {
    "location": "FR-6",
    "trigger_condition": "Recipient roster is large enough to strain the 60s generation / 5min delivery targets",
    "guard_snippet": "Add NFR: define the maximum recipient count the 60s/5min targets are guaranteed for, given BSP rate limits.",
    "potential_consequence": "Large rosters could silently miss the 5-minute delivery target with no defined ceiling."
  },
  {
    "location": "FR-6",
    "trigger_condition": "Administrator changes the global schedule time while a run is pending or in progress",
    "guard_snippet": "Add: schedule changes apply from the next full day's run, never mid-run.",
    "potential_consequence": "Same-day schedule edit could cause a duplicate or skipped run."
  },
  {
    "location": "FR-6",
    "trigger_condition": "Scheduled trigger fires but the day's Source System data hasn't finished importing",
    "guard_snippet": "Add FR-6 consequence: if source data is unavailable at trigger time, the run holds/retries rather than sending stale figures.",
    "potential_consequence": "Recipients receive a report with stale or blank figures with no indication."
  },
  {
    "location": "§3 Glossary / FR-7 / SM-3",
    "trigger_condition": "'Send event' (the unit no-duplicate and retry logic apply to) is never defined",
    "guard_snippet": "Add a Glossary entry defining the boundary of a 'send event' (e.g., one Recipient x one trigger).",
    "potential_consequence": "Retries, manual resends, and overlapping targeting can't be judged duplicate or distinct."
  },
  {
    "location": "FR-7",
    "trigger_condition": "A recipient's retries are exhausted and the failure is logged",
    "guard_snippet": "Add FR-7 consequence: state whether retry-exhausted recipients are eligible for the next scheduled run or need manual resend.",
    "potential_consequence": "Recipient could remain permanently unreached with no defined recovery path."
  },
  {
    "location": "FR-7 / FR-11 / FR-12",
    "trigger_condition": "'Operational day' boundary used for same-day visibility is never defined against Asia/Dhaka",
    "guard_snippet": "Add a definition of 'operational day' boundaries (timezone and cutover time).",
    "potential_consequence": "A late-night retry near midnight could be logged as met or missed inconsistently."
  },
  {
    "location": "FR-8",
    "trigger_condition": "Administrator attempts to send a Manual Notification with zero Recipients selected",
    "guard_snippet": "Add FR-8 consequence: sending is blocked unless at least one Recipient is selected.",
    "potential_consequence": "An accidental empty send could be triggered with nothing meaningful logged."
  },
  {
    "location": "FR-8 / FR-9",
    "trigger_condition": "Selected recipients overlap across individual/group/team selection in one manual send",
    "guard_snippet": "Add FR-8 consequence: overlapping recipient selections are de-duplicated before send.",
    "potential_consequence": "A recipient selected individually and via their team receives the notification twice."
  },
  {
    "location": "FR-8 / §9 Cost",
    "trigger_condition": "Administrator composes free-text content that must also be a billed Meta template message",
    "guard_snippet": "Add: clarify whether Manual Notification free text fits pre-approved template variable fields or needs its own template approval.",
    "potential_consequence": "Administrator composes a message WhatsApp/Twilio rejects at send time as non-compliant."
  },
  {
    "location": "FR-8",
    "trigger_condition": "Administrator attaches 'current performance report' before today's Daily Report has generated",
    "guard_snippet": "Add: attaching a report before today's has generated attaches the most recent prior report, explicitly dated.",
    "potential_consequence": "Attachment references stale or non-existent data without indicating its period."
  },
  {
    "location": "FR-9",
    "trigger_condition": "Two Administrator sessions edit the same Recipient record concurrently",
    "guard_snippet": "Add FR-9 consequence: concurrent edits use optimistic locking, rejecting the stale write.",
    "potential_consequence": "One Administrator's edit silently overwrites another's without warning."
  },
  {
    "location": "FR-9",
    "trigger_condition": "A User/Group/Channel is removed while still a member of a Sales Team or Recipient Group",
    "guard_snippet": "Add: removal that is still referenced by a Team/Group either cascades or is blocked with a dependency warning.",
    "potential_consequence": "Dangling membership reference causes an orphaned or malformed send target."
  },
  {
    "location": "FR-9",
    "trigger_condition": "The same phone number/WhatsApp ID is entered as more than one Recipient record",
    "guard_snippet": "Add FR-9 consequence: directory enforces uniqueness on phone number/WhatsApp ID per recipient.",
    "potential_consequence": "Same real number entered twice causes duplicate real-world deliveries undetected by dedup logic."
  },
  {
    "location": "FR-9 / FR-6",
    "trigger_condition": "A Recipient is added after today's scheduled run has already started its delivery window",
    "guard_snippet": "Add: recipients added after today's run has started receive their first report on the next scheduled run.",
    "potential_consequence": "Unclear whether a just-added recipient is owed today's report or waits until tomorrow."
  },
  {
    "location": "FR-10",
    "trigger_condition": "Opt-in consent applies to a Recipient Group/Channel/Team rather than one individual",
    "guard_snippet": "Add FR-10 consequence: define how consent is captured/verified per individual member when the target is a Group/Channel/Team.",
    "potential_consequence": "Messages reach individual numbers who never personally opted in if only the group is marked consented."
  },
  {
    "location": "FR-10",
    "trigger_condition": "A new Recipient is created before any consent action is recorded",
    "guard_snippet": "Add FR-10 consequence: newly created Recipients default to opted-out until consent is explicitly captured.",
    "potential_consequence": "Ambiguous default could let deliveries start before consent is actually confirmed."
  },
  {
    "location": "FR-10",
    "trigger_condition": "A previously opted-out Recipient needs to opt back in",
    "guard_snippet": "Add FR-10 consequence: define how an opted-out Recipient can be re-enabled for delivery.",
    "potential_consequence": "Opted-out recipient has no defined way back onto delivery once corrected."
  },
  {
    "location": "FR-11",
    "trigger_condition": "A send is targeted at a Group/Channel/Team rather than an individual",
    "guard_snippet": "Add FR-11 consequence: history is filterable down to each individual downstream recipient, even when targeted via a group/team.",
    "potential_consequence": "Administrator cannot confirm whether a specific team member actually received a group send."
  },
  {
    "location": "FR-11",
    "trigger_condition": "A send is retried multiple times before success or exhaustion",
    "guard_snippet": "Add: define whether each retry attempt appears as its own history row or an attempt count within one row.",
    "potential_consequence": "Retry history is invisible or ambiguous when reconciling delivery outcomes."
  },
  {
    "location": "FR-11 / FR-12",
    "trigger_condition": "Notification History/Audit Log volume grows over time",
    "guard_snippet": "Add NFR: define a maximum load/filter-query time for Notification History and Audit Log views.",
    "potential_consequence": "History queries degrade unbounded as log volume grows with no performance floor."
  },
  {
    "location": "FR-12",
    "trigger_condition": "Audit Log write fails independently of the administrative action it is logging",
    "guard_snippet": "Add FR-12 consequence: the administrative action and its audit log write succeed or fail atomically together.",
    "potential_consequence": "Action takes effect with no audit trail, breaking the 100% completeness target (SM-5)."
  },
  {
    "location": "FR-12",
    "trigger_condition": "A login attempt fails (invalid credentials)",
    "guard_snippet": "Add FR-12 consequence: specify whether failed login attempts are also audit-logged, not just successful ones.",
    "potential_consequence": "Brute-force or credential-stuffing attempts against FR-1 go untracked."
  },
  {
    "location": "FR-12",
    "trigger_condition": "Schedule reconfiguration, opt-in/opt-out toggles, or manual-send triggering occur",
    "guard_snippet": "Add FR-12 consequence: extend audited action scope explicitly to schedule changes and opt-in/opt-out toggles.",
    "potential_consequence": "Administrative actions with real operational impact go unrecorded in the Audit Log."
  }
]
```
