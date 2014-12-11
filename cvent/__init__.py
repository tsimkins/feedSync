#!/usr/bin/python

# Zope imports
from zope.component import getSiteManager
from Products.CMFCore.utils import getToolByName
from AccessControl.SecurityManagement import newSecurityManager
from HTMLParser import HTMLParseError
#import transaction

# My imports
from BeautifulSoup import BeautifulSoup
from time import strptime, strftime
import urllib2
import sys
import re

def agsciEvents(soup, summaryURL):
    results = []

    for eventRow in soup.findAll('table', {'class':'calLinks'}):
    
        dateCell = eventRow.find('td', {'class':'BodyTextBold1'})
        
        eventDate = strftime("%Y-%m-%d", strptime(dateCell.contents[0].strip(), "%B %d, %Y"))
        
        for eventCell in eventRow.findAll('td', {'class':'BodyText1'}):
            eventLink = eventCell.find('a')
            eventId = eventLink['e']
            eventTitle = str(eventLink.contents[0])
            eventURL = getCventSummaryURL(summaryURL % eventId)

            results.append((eventLink, eventId, eventTitle, eventDate, eventURL))

    return results

def extensionEvents(soup, summaryURL):
    results = []
    
    eventTable = soup.find('table', {'id' : 'listMode'})

    for eventRow in eventTable.findAll('td', {'class':re.compile("ListCellBgrd1")}):
    
        eventTitle = eventRow.find('td', {'class':'BodyTextBold1'}).contents[0]
        
        for eventLink in eventRow.findAll('a'):
            eventDateText =  eventLink.contents[0].strip()     
            eventDate = strftime("%Y-%m-%d", strptime(eventDateText, "%m/%d/%y"))
            eventId = eventLink['e']
            eventURL = getCventSummaryURL(summaryURL % eventId)

            results.append((eventLink, eventId, eventTitle, eventDate, eventURL))

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
                 parseSoup=agsciEvents,
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
    
    # Grab CVENT data and create events
    page = urllib2.urlopen(cventURL)
    myHTML = "\n".join(page).replace(r'\"', '"')

    # Broken img tag was causing a parse error.
    removeImage = re.compile("</*img.*?", re.I|re.M)
    myHTML = removeImage.sub("", myHTML)

    soup = BeautifulSoup(myHTML)
    cventIDs = []
    
    # Get listing of events, and their cventid if it exists
    for myEvent in context.listFolderContents(contentFilter={"portal_type" : "Event"}):
        cventIDs.append(myEvent.id)
        myCventID = myEvent.getProperty('cventid')
        if myCventID:
            cventIDs.append(myCventID)
    
    for (eventLink, eventId, eventTitle, eventDate, eventURL) in parseSoup(soup, summaryURL):

        eventTitle = eventTitle.decode("utf-8")

        if not cventIDs.count(eventId):
            newEvents.append("<li><a href=\"%s/%s\">%s</a></li>" % (conferenceURL, eventId, eventTitle))
    
            context.invokeFactory(type_name="Event",
                    id=eventId,
                    title=eventTitle,
                    start_date=eventDate,
                    end_date=eventDate,
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
            #newEvents.append("<li>NOT: <a href=\"%s/%s\">%s</a></li>" % (conferenceURL, eventId, eventLink.contents[0]))

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
