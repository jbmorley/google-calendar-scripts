# google-calendar-scripts

## Installation

1. Checkout the scripts:

   ```
   git clone git@github.com:jbmorley/google-calendar-scripts.git
   cd google-calendar-scripts
   pipenv install
   ```

2. Generate Google API credentials as described in [Step 1](https://developers.google.com/calendar/quickstart/python#step_1_turn_on_the) of the [Google Calendar API Python Quickstart](https://developers.google.com/calendar/quickstart/python).

## Scripts

### find-from-ics

Search Google Calendar for events corresponding to the UIDs in an ICS file, optionally deleting them. This was created to help undo a failed/partial Google Calendar ICS import without destroying other data in Google Calendar.
