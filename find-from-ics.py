#!/usr/bin/env python3

from __future__ import print_function

import argparse
import datetime
import os
import pickle
import re
import sys
import time

import googleapiclient
import icalendar
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

    @property
    def failure_count(self):
        return len(self.failing_uids)

    @property
    def failure_percentage(self):
        return int((self.count / self.failure_count) * 100)


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


def authorize():
    credentials = None

    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            credentials = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not credentials or not credentials.valid:

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            credentials = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(credentials, token)

    return credentials


class ICS(object):

    def __init__(self, path):
        with open(path) as fh:
            self.calendar = icalendar.Calendar.from_ical(fh.read())

    def find_component(self, uid):
        for component in self.calendar.walk():
            if component.get('uid') == uid:
                return component
        raise KeyError(uid)


def icalendar_component_summary(component):
    tab_size = 2
    description = component.get('description')
    if description is not None:
        description = indent(description, " " * (tab_size + 2))
    return f"{component.get('uid')}\n\t- {component.name}\n\t- {component.get('summary')}\n\t- {description}".expandtabs(tab_size)


def indent_line(string, indent):
    rows, columns = os.popen('stty size', 'r').read().split()
    columns = int(columns)
    width = columns - len(indent)
    return indent.join([string[i:i+width] for i in range(0, len(string), width)])


def indent(string, indent):
    return f"\n{indent}".join([indent_line(line, indent) for line in string.split("\n")])


def icalendar_uids(ics):
    for component in ics.calendar.walk():
        yield component.get('uid')


def main():
    parser = argparse.ArgumentParser(description="Find all events from Google Calendar that exist in an ICS file")
    parser.add_argument('ics', help="ICS file containing events to search for")
    parser.add_argument('--delete', action='store_true', default=False, help="delete the matching events")
    parser.add_argument('--verbose', action='store_true', default=False, help="show verbose output")
    parser.add_argument('--limit', type=int, default=None, help="limit the number of events processed")
    options = parser.parse_args()
    ics_path = os.path.abspath(options.ics)

    credentials = authorize()
    service = build('calendar', 'v3', credentials=credentials)
    calendar_id = 'primary'
    summary = Summary()

    print("Loading ICS file...")
    ics = ICS(ics_path)

    # Iterate over the UIDs in the ICS file.
    print("Searching for events...")
    # for uid in ics_event_uids(ics_path):
    for uid in icalendar_uids(ics):

        if options.limit is not None and summary.count >= options.limit:
            break

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

        recurring_event = 'recurringEventId' in event
        event_id =  event['id']
        start = event['start'].get('dateTime', event['start'].get('date'))
        description = event['summary'] if 'summary' in event else event['description']

        if options.verbose:
            write_with_flush("\n")
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

    print(f"ICS contains {summary.count} events")
    if summary.failing_uids:
        print(f"Failed to find {summary.failure_count} events ({summary.failure_percentage}%)")
        failing_components = [ics.find_component(uid=uid) for uid in summary.failing_uids]
        failing_components = [component for component in failing_components if (component.name != "VALARM" and component.get('summary') is not None)]
        print("Missing events:")
        for component in failing_components:
            print(icalendar_component_summary(component))


if __name__ == '__main__':
    main()
