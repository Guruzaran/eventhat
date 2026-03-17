"""
Static prompt constants used by the intent compiler.
Edit this file to tune LLM behaviour without touching compiler logic.
"""

CLI_GRAMMAR = """
VERBS AND NOUNS:
  event   create | update | show | list | clone
  signup  confirm | cancel | list | show
  notify  send
  payment link | status | refund
  list    events | signups | waitlist
  show    context

FLAG TYPES:
  --title     text (quote if multi-word)
  --date      YYYY-MM-DD, always future, always ISO-8601
  --slots     NxM  (3x10 = 3 shifts x 10 people)  OR  N  (1 slot x N people)
  --price     decimal USD no symbol  (25.00 not $25)
  --status    draft | published | cancelled  (events)
              confirmed | waitlisted | cancelled | all  (signups)
  --privacy   public | private
  --type      reminder-48h | reminder-2h | custom | cancellation | waitlist-open
  --event_id  UUID of the event
  --slot      label or partial label of the slot
  --signup_id UUID of the signup
  --location  text
  --description text
"""

FEW_SHOT_EXAMPLES = """
User: create a volunteer cleanup next Saturday with 3 shifts of 10 people
Output: event create --title 'Volunteer Cleanup' --date {next_saturday} --slots 3x10

User: set up a paid yoga class on April 15 2027, $20 per person, 20 spots
Output: event create --title 'Yoga Class' --date 2027-04-15 --slots 20 --price 20.00

User: publish the event
Output: event update --event_id {active_event_id} --status published

User: cancel the event
Output: event update --event_id {active_event_id} --status cancelled

User: show me who signed up
Output: signup list --event_id {active_event_id}

User: sign me up for the morning shift
Output: signup confirm --event_id {active_event_id} --slot morning

User: cancel my signup
Output: signup cancel --signup_id ASK:Which signup would you like to cancel?

User: list all my events
Output: event list

User: what is the status of the event?
Output: event show --event_id {active_event_id}

User: send a reminder to everyone
Output: notify send --event_id {active_event_id} --type reminder-48h

User: book a flight for me
Output: UNSUPPORTED:Flight booking is outside the scope of this platform.
"""
