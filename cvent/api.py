#!/usr/bin/python

# Zope imports
from zope.component import getSiteManager
from Products.CMFCore.utils import getToolByName
from AccessControl.SecurityManagement import newSecurityManager
from DateTime import DateTime

# My imports
from time import strptime, strftime
import urllib2
import sys
import re

# SOAP Imports
from suds.client import Client
from suds.plugin import MessagePlugin
from datetime import datetime, timedelta

# API URL
url = 'https://api.cvent.com/soap/V200611.ASMX?WSDL'

# Define plugin for fixing namespace issues
class fixNamespace(MessagePlugin):
    def marshalled(self, context):
        # Fix Ids namespace in Retrieve
        for i in context.envelope.childrenAtPath('ns1:Body/ns0:Retrieve/ns0:Ids'):
            i.setPrefix('ns2')

# Grab event info from Cvent
def getCventEvents(acct_num='',
                 login_name='',
                 passwd='',
                 start_datestamp='',
                 end_datestamp='',
                 uid=None,
                 skip_ids=[]):

    def toUID(u):
        segments = [8, 4, 4, 4, 12]
        values = []
        u = u.upper().replace('-', '')
        if len(u) == sum(segments):
            for i in range(0,len(segments)):
                l = segments[i]
                s = sum(segments[x] for x in range(0,i))
                values.append(u[s:s+l])
        return "-".join(values)
            

    # Results list
    results = []

    # Login and set auth header
    # http://blog.milford.io/2011/11/code-example-using-python-suds-to-access-the-bronto-api/

    client = Client(url, plugins=[fixNamespace()])
    login = client.service.Login(acct_num, login_name, passwd)
    session_header = client.factory.create("CventSessionHeader")
    session_header.CventSessionValue = login._CventSessionHeader
    client.set_options(soapheaders=session_header)


    # Get Updated objects
    _CvObjectType = client.factory.create('ns1:CvObjectType')

    if uid:
        rv = client.service.Retrieve(_CvObjectType.Event, {'Id' : [toUID(uid)]})
    else:
        updated = client.service.GetUpdated(_CvObjectType.Event, start_datestamp, end_datestamp)
        # Remove 'skip_ids' from list, and regenerate
        if skip_ids:
            new_ids = set(updated[0]) - set(skip_ids)
            updated = {'Id' : list(new_ids)}
        rv = client.service.Retrieve(_CvObjectType.Event, updated)


    # Package object data

    for (t,objects) in rv:
        for o in objects:
            if not hasattr(o, '_EventLaunchDate'):
                # Skip unlaunched Events
                continue

            # Initialize data
            r = {}
    
            r['id'] = unicode(o._Id).lower()
            r['Title'] = unicode(o._EventTitle)
            if o._City and o._StateCode:
                r['location'] = str('%s, %s' % (o._City, o._StateCode))
            else:
                r['location'] = 'N/A'
            r['zip_code'] = str(o._PostalCode)
            r['start'] = DateTime(o._EventStartDate)
            if hasattr(o, '_EventEndDate'):
                r['end'] = DateTime(o._EventEndDate)
            else:
                r['end'] = r['start']
            r['category'] = str(o._Category)

            for u in o.WeblinkDetail:
                if u._Target == 'Event Summary':
                   r['url'] = u._URL
                   break
    
            results.append(r)
    
    return results


def importEvents(context,
                 acct_num='',
                 login_name='',
                 passwd='',
                 emailUsers=['trs22'],
                 eventsURL="https://agsci.psu.edu/conferences/event-calendar",
                 owner=None,
                 daysback=7,
                 uid=None,
                 skip_ids=[]):

    # Return values
    myStatus = []
    newEvents = []

    # Date calculations
    end = datetime.utcnow()
    start = end - timedelta(daysback)
    
    start_datestamp = start.strftime('%Y-%m-%dT%H:%M:%S')
    end_datestamp = end.strftime('%Y-%m-%dT%H:%M:%S')

    # More Zopey goodness to set owner of events

    if owner:
        admin = context.acl_users.getUserById(owner)
    else:
        admin = context.acl_users.getUserById('trs22')

    admin = admin.__of__(context.acl_users)
    newSecurityManager(None, admin)

    portal = getSiteManager(context)
    
    # Extension ZIP Tool
    zipcode_tool = getToolByName(portal, 'extension_zipcode_tool', None)

    # Extension Course Tool
    course_tool = getToolByName(portal, 'extension_course_tool', None)

    # Get listing of events, and their cventid if it exists    
    cventIDs = []

    for myEvent in context.listFolderContents(contentFilter={"portal_type" : "Event"}):
        cventIDs.append(myEvent.id)
        myCventID = myEvent.getProperty('cventid')
        if myCventID:
            cventIDs.append(myCventID)


    cventData = getCventEvents(acct_num=acct_num,
                               login_name=login_name,
                               passwd=passwd,
                               start_datestamp=start_datestamp,
                               end_datestamp=end_datestamp,
                               uid=uid,
                               skip_ids=skip_ids)

    for r in cventData:
        # Basic Data
        eventLink = r.get('url')
        eventId = r.get('id')
        eventTitle = r.get('Title')
        eventStart = r.get('start')
        eventEnd = r.get('end')
        eventURL = r.get('url')
        eventLocation = r.get('location')
        eventZIPCode = r.get('zip_code')
        
        # Translations and date manipulation

        #eventTitle = eventTitle.decode("utf-8")
        
        eventStartDate = eventStart.strftime("%Y-%m-%d")
        eventStartTime = eventStart.strftime("%H:%M:%S")
        eventEndDate = eventEnd.strftime("%Y-%m-%d")
        eventEndTime = eventEnd.strftime("%H:%M:%S")

        if not cventIDs.count(eventId):
            newEvents.append("<li><a href=\"%s/%s\">%s</a></li>" % (eventsURL, eventId, eventTitle))

            context.invokeFactory(type_name="Event",
                    id=eventId,
                    title=eventTitle,
                    start_date=eventStartDate,
                    end_date=eventEndDate,
                    start_time=eventStartTime,
                    stop_time=eventEndTime,
                    event_url=eventURL,
                    location=eventLocation)

            myObject = getattr(context, eventId)
            myObject.manage_addProperty('cventid', eventId, 'string')
            myObject.setExcludeFromNav(True)
            myObject.setLayout("event_redirect_view")

            # Extension-specific fields
            if zipcode_tool:
                myObject.zip_code = eventZIPCode
                zipInfo = zipcode_tool.getZIPInfo(eventZIPCode)
                if zipInfo:
                    myObject.extension_counties = (zipInfo[2], )

            if course_tool:

                # Set the course
                course = course_tool.getCourseForEventTitle(eventTitle)

                if course:
                    myObject.extension_courses = (course, )
                    
                    # Set the program/topic based on what the course has.
                    
                    results = course_tool.getCourseInfo(course)

                    if results:
                        r = results[0]
                        if r.extension_topics:
                            myObject.extension_topics = tuple(r.extension_topics)
                        if r.extension_subtopics:
                            myObject.extension_subtopics = tuple(r.extension_subtopics)
                        

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

    myStatus.append("Finished Loading")

    return "\n".join(myStatus)

