#!/usr/bin/env python3

from __future__ import print_function

import time
import datetime
import pickle
import os.path

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def process_response(response):
    events = response.get('items', [])
    if not events:
        print('No upcoming events found.')
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(start, event['summary'], event['iCalUID'])


def calendar_events(service, **kwargs):
    calendar_events = service.events()
    request = calendar_events.list(**kwargs)
    while True:
        response = request.execute()
        events = response.get('items', [])
        if not events:
            raise StopIteration
        for event in events:
            yield event
        request = calendar_events.list_next(previous_request=request, previous_response=response)


def main():

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

    # Call the Calendar API
    for event in calendar_events(service=service,
                                 calendarId='primary',
                                 timeMin=datetime.datetime.utcnow().isoformat() + 'Z',
                                 maxResults=10,
                                 singleEvents=True,
                                 orderBy='startTime'):
        start = event['start'].get('dateTime', event['start'].get('date'))
        print(start, event['summary'], event['iCalUID'])
        time.sleep(1)


if __name__ == '__main__':
    main()
