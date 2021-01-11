#!/usr/bin/env python3

from __future__ import print_function

import argparse
import datetime
import os.path
import pickle
import re
import sys
import time

import googleapiclient
import ics

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar']


class Summary(object):

    def __init__(self):
        self.count = 0
        self.failing_uids = []


def calendar_events(service, **kwargs):
    calendar_events = service.events()
    request = calendar_events.list(**kwargs)
    while True:
        response = request.execute()
        events = response.get('items', [])
        if not events:
            return
        for event in events:
            yield event
        request = calendar_events.list_next(previous_request=request, previous_response=response)


def ics_event_uids(path):
    # Unfortunately Calendar.app seems to be able to generate corrupt ICS files (certainly the ics package doesn't know
    # how to handle then), so this performs an incredibly rudimentary regex-based approach to getting the event UIDs.
    # At least it's fast. 🤦🏻‍♂️
    expression = re.compile(r"^UID:(.+)$")
    with open(path) as fh:
        for line in fh.readlines():
            matches = expression.match(line.strip())
            if matches:
                yield matches.group(1)


def write_with_flush(output):
    sys.stdout.write(output)
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Find all events from Google Calendar that exist in an ICS file")
    parser.add_argument('ics', help="ICS file containing events to search for")
    parser.add_argument('--delete', action='store_true', default=False, help="delete the matching events")
    parser.add_argument('--verbose', action='store_true', default=False, help="show verbose output")
    options = parser.parse_args()
    ics_path = os.path.abspath(options.ics)

    creds = None

    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('calendar', 'v3', credentials=creds)

    calendar_id = 'primary'

    summary = Summary()

    # Iterate over the UIDs in the ICS file.
    for uid in ics_event_uids(ics_path):

        summary.count = summary.count + 1

        # Search for a corresponding Google Calendar event.
        try:
            time.sleep(0.05)
            event = next(calendar_events(service=service,
                                         calendarId=calendar_id,
                                         maxResults=1,
                                         singleEvents=True,
                                         iCalUID=uid))
            write_with_flush(".")
        except StopIteration:
            write_with_flush("x")
            summary.failing_uids.append(uid)
            continue

        if options.verbose:
            write_with_flush("\n")
            recurring_event = 'recurringEventId' in event
            event_id =  event['id']
            start = event['start'].get('dateTime', event['start'].get('date'))
            description = event['summary'] if 'summary' in event else event['description']
            print(f"{start} {description} [{uid} -> {event_id}]")

        if options.delete:
            # This logic is a little murky and feels a bit off, however it seems to be necessary by observation of the
            # API behaviour; sometimes it seems recurrences get orphaned and it's not possible to delete their parent
            # event. In this case, we want to fallback to deleting the events themselves.
            try:
                if recurring_event:
                    service.events().delete(calendarId=calendar_id, eventId=event['recurringEventId']).execute()
                else:
                    service.events().delete(calendarId=calendar_id, eventId=event['id']).execute()
            except googleapiclient.errors.HttpError as error:
                # If we failed to delete a recurring event, then delete the leaf node instead.
                if recurring_event:
                    service.events().delete(calendarId=calendar_id, eventId=event['id']).execute()
                else:
                    raise error

    write_with_flush("\n")

    print(f"ICS contains {summary.count} events.")
    if summary.failing_uids:
        print(f"Failed to find {len(summary.failing_uids)} events.")
        print("\t" + "\n\t".join(summary.failing_uids))


if __name__ == '__main__':
    main()
