#!/usr/bin/python

# Zope imports
from zope.component import getSiteManager
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import safe_unicode
from AccessControl.SecurityManagement import newSecurityManager
from HTMLParser import HTMLParseError
#import transaction

# My imports
from BeautifulSoup import BeautifulSoup
from DateTime import DateTime
from time import strptime, strftime
import urllib2
import sys
import re
import requests

def getCventEvents(calendar_url, summaryURL):

    def fmt_date(x):
        return DateTime(x.replace("T", ' ') + " US/Eastern")

    results = []

    response = requests.get(calendar_url)

    if response.status_code == 200:

        for _ in response.json():

            eventId = _['id']
            eventTitle = _['title']
            eventStartDate = fmt_date(_['startDate'])
            eventEndDate = fmt_date(_['endDate'])
            eventURL = getCventSummaryURL(summaryURL % eventId)
            eventLocation = _.get('location', '')

            results.append((eventId, eventTitle, eventStartDate, eventEndDate, eventURL, eventLocation))

    return results

def getCventSummaryURL(url):
    page = urllib2.urlopen(url)
    new_url = page.geturl()
    if '?' in new_url:
        new_url = new_url.split('?')[0]
    return new_url

def importEvents(context, emailUsers=['trs22'],
                 cventURL = "http://guest.cvent.com/EVENTS/Calendar/Calendar.aspx?cal=9d9ed7b8-dd56-46d5-b5b3-8fb79e05acaf",
                 summaryURL = "http://guest.cvent.com/EVENTS/info/summary.aspx?e=%s",
                 conferenceURL="https://agsci.psu.edu/conferences/event-calendar",
                 parseSoup=None,
                 calendar_url="https://agsci.psu.edu/cvent.json",
                 owner=None):

    myStatus = []
    newEvents = []

    # More Zopey goodness

    if owner:
        admin = context.acl_users.getUserById(owner)
    else:
        admin = context.acl_users.getUserById('trs22')

    admin = admin.__of__(context.acl_users)
    newSecurityManager(None, admin)

    portal = getSiteManager(context)

    cventIDs = []

    # Get listing of events, and their cventid if it exists
    for myEvent in context.listFolderContents(contentFilter={"portal_type" : "Event"}):
        cventIDs.append(myEvent.id)
        myCventID = myEvent.getProperty('cventid')
        if myCventID:
            cventIDs.append(myCventID)

    for (
        eventId,
        eventTitle,
        eventStartDate,
        eventEndDate,
        eventURL,
        eventLocation
    ) in getCventEvents(calendar_url, summaryURL):

        eventTitle = safe_unicode(eventTitle)

        if not cventIDs.count(eventId):
            newEvents.append("<li><a href=\"%s/%s\">%s</a></li>" % (conferenceURL, eventId, eventTitle))

            context.invokeFactory(type_name="Event",
                    id=eventId,
                    title=eventTitle,
                    start_date=eventStartDate.strftime('%Y-%m-%d'),
                    start_time=eventStartDate.strftime('%H:%M'),
                    end_date=eventEndDate.strftime('%Y-%m-%d'),
                    stop_time=eventEndDate.strftime('%H:%M'),
                    event_url=eventURL,
                    location="")

            myObject = getattr(context, eventId)
            myObject.manage_addProperty('cventid', eventId, 'string')
            myObject.setExcludeFromNav(True)
            myObject.setLayout("event_redirect_view")
            myObject.reindexObject()

            myStatus.append("Created event %s (id %s)" % (eventTitle, eventId))

        else:
            myStatus.append("Skipped event %s (id %s)" % (eventTitle, eventId))

    if newEvents:
        myStatus.append("Sending email to: %s" % ", ".join(emailUsers))
        mFrom = "do.not.reply@psu.edu"
        mSubj = "CVENT Events Imported: %s" % portal.getId()
        mTitle = "<p><strong>The following events from cvent have been imported.</strong></p>"
        statusText = "\n".join(newEvents)
        mailHost = context.MailHost

        for myUser in emailUsers:
            mTo = "%s@psu.edu" % myUser

            mMsg = "\n".join(["\n\n", mTitle, "<ul>", statusText, "<ul>"])
            mailHost.secureSend(mMsg.encode('utf-8'), mto=mTo, mfrom=mFrom, subject=mSubj, subtype='html')

    #transaction.commit()
    myStatus.append("Finished Loading")
    return "\n".join(myStatus)
    #return newEvents
