import feedparser
from datetime import datetime
from Products.CMFCore.utils import getToolByName

try:
    from zope.app.component.hooks import getSite
except ImportError:
    from zope.component.hooks import getSite

from AccessControl.SecurityManagement import newSecurityManager
import urllib2
from urllib2 import HTTPError
from urlparse import urljoin
from BeautifulSoup import BeautifulSoup 
import time
from calendar import timegm
import re

from zope.component import getUtility
from plone.i18n.normalizer.interfaces import IIDNormalizer

url = 'http://news.psu.edu/rss/college/agricultural-sciences'

user_agent = "Mozilla/5.0 (Windows NT 6.3; WOW64; rv:32.0) Gecko/20100101 Firefox/32.0"

# Tags (excluding news-)

valid_tags = [
    'research', 
    'student-stories',
    'students',
    'international',
    'extension',
    'penn-state-extension'
]

IMAGE_FIELD_NAME = 'image'
IMAGE_CAPTION_FIELD_NAME = 'imageCaption'

def sync(context, url=url, valid_tags=valid_tags):
    # Be an admin
    admin = context.acl_users.getUserById('trs22')
    admin = admin.__of__(context.acl_users)
    newSecurityManager(None, admin) 

    print "Syncing RSS feeds from %s" % url
    site = getSite()
    wftool =  getToolByName(site, 'portal_workflow')
    portal_catalog = getToolByName(site, 'portal_catalog')
    numeric_ids = [x for x in portal_catalog.uniqueValuesFor('id') if x.isdigit()]
    news_ids = [x.getId for x in portal_catalog.searchResults({'portal_type' : 'News Item', 'id' : numeric_ids, 'SearchText' : 'news.psu.edu'})]
    
    feed = feedparser.parse(url)

    theReturn = []

    for item in feed['entries']:
        title = item.get('title', None)
        description = item.get('summary_detail', {}).get('value')
        link = item.get('links', [])[0].get('href', None).split('#')[0]

        date_published_parsed = item.get('published_parsed')
        date_published = item.get('published')        

        now = datetime.now()
        dateStamp = now.strftime('%Y-%m-%d %H:%M')
        
        if date_published_parsed:
            local_time = time.localtime(timegm(date_published_parsed))
            dateStamp = time.strftime('%Y-%m-%d %H:%M', local_time)
            this_year = time.strftime('%Y', local_time)
        elif date_published:
            try:
                dateStamp = time.strftime('%Y-%m-%d %H:%M', time.strptime(date_published, '%A, %B %d, %Y - %H:%M'))
            except:
                pass

        this_year = dateStamp.split('-')[0]

        id = str(link.split("/")[4]).split('#')[0]

        if id not in news_ids:
            time.sleep(5)
            if this_year in context.objectIds():
                myContext = context[this_year]
            else:
                myContext = context

            try:
                myContext.invokeFactory(id=id,type_name="News Item",title=title, article_link=link, description=description)
            except:
                continue

            theReturn.append("Created %s" % id)
            
            theArticle = getattr(myContext, id)
            
            # http://plone.org/documentation/how-to/set-creation-date
            theArticle.setCreationDate(dateStamp)
            theArticle.setModificationDate(dateStamp)
            theArticle.setEffectiveDate(dateStamp)
                        
            theArticle.setExcludeFromNav(True)

            # Grab article image and set it as contentleadimage
            html = getHTML(link)

            tags = getTags(html, valid_tags=valid_tags)
            if tags:
                tags = ['news-%s' % x for x in list(tags)]
                theArticle.setSubject(tags)
            setImage(theArticle, html=html)

            # Set the body text
            body_text = getBodyText(html)
            theArticle.setText(body_text)

            # Publish
            if wftool.getInfoFor(theArticle, 'review_state') != 'Published':
                wftool.doActionFor(theArticle, 'publish')

            theArticle.indexObject()
            
        else:
            theReturn.append("Skipped %s" % id)

    return theReturn

def getBodyText(html):
    mySoup = BeautifulSoup(html)
    try:
        body = mySoup.find("div", {'class' : re.compile('field-name-body')})
        item = body.find("div", {'class' : re.compile('field-item($|\s+)')})
    except:
        return ""

    return item.renderContents()

def getTags(html, valid_tags=[]):
    mySoup = BeautifulSoup(html)
    normalizer = getUtility(IIDNormalizer)
    try:
        article_tags = []

        for tags_div in mySoup.findAll("div", {'class' : re.compile('article-related-terms')}):
            items = tags_div.findAll("a")
            article_tags.extend([normalizer.normalize(str(x.contents[0])).strip() for x in items])

        if valid_tags:
            tags = list(set(valid_tags) & set(article_tags))
        else:
            tags = list(article_tags)

        return tags

    except:
        return []

def htmlToPlainText(html):
    site = getSite()
    portal_transforms = getToolByName(site, 'portal_transforms')
    return portal_transforms.convert('html_to_text', html).getData().replace("\n", '').strip()

def getHTML(url):
    try:
        req = urllib2.Request(url, headers={ 'User-Agent': user_agent })
        return urllib2.urlopen(req).read()
    except HTTPError:
        print "404 for %s" % url 
        return ""


def getImageAndCaption(html=None, url=None):

    if not (html or url):
        return (None, None)
    elif not html:
        html = getHTML(url)

    mySoup = BeautifulSoup(html)

    img_url = ""
    img_caption = ""
    imgSrc = ""
    
    for div in mySoup.findAll("div", {'class' : 'image'}):
        for img in div.findAll("img"):
            img_url = img.get('src')
            if img_url:
                parent = div.parent
                for caption in parent.findAll("div", {'class' : 'caption'}):
                    img_caption = htmlToPlainText(caption.prettify())
                    if img_caption:
                        break
                if not img_caption:
                    for span in div.findAll("span", {'property' : 'dc:title'}):
                        img_caption = span.get('content')
                        if img_caption:
                            break
        if img_url:
            break

    if not img_url:
        img_caption = ""
        for ul in mySoup.findAll("ul", {'class' : 'slides'}):
            for li in ul.findAll('li'):
                try:
                    img_url = li.find("div", {'class' : re.compile('field-name-field-image')}).find("img").get('src')
                    img_caption = htmlToPlainText(li.find("div", {'class' : re.compile('field-name-field-flickr-description')}).prettify())
                except:
                    pass
                if img_url:
                    break
    if img_url:
        imgSrc = urljoin(url, img_url)

    if imgSrc:
        imgData = downloadImage(imgSrc)        
        return (imgData, img_caption)
    else:
        return (None, None)

def hasImage(context):
    image_field = context.getField(IMAGE_FIELD_NAME).get(context)
    
    if image_field and image_field.size:
        return True
    else:
        return False

def downloadImage(url):
    try:
        req = urllib2.Request(url, headers={ 'User-Agent': user_agent })
        imgFile = urllib2.urlopen(req)
    except HTTPError:
        return None
    else:
        imgData = imgFile.read()            
        return imgData

def setImage(theArticle, image_url=None, html=None):
    # Given an article, and either an image URL or a set of HTML, sets the image
    # and caption for the article.

    theImage = theImageCaption = ""

    if image_url:
        theImage = downloadImage(image_url)
        theImageCaption = ""
    else:
        if not html:
            if hasattr(theArticle, 'getRemoteUrl'):
                url = theArticle.getRemoteUrl()
            elif hasattr(theArticle, 'article_link'):
                url = theArticle.article_link
            else:
                url = None

            if url:
                html = getHTML(url)            
            else:
                return None

        # Grab article image and caption
        (theImage, theImageCaption) = getImageAndCaption(html=html)

    if theImage:
        theArticle.getField(IMAGE_FIELD_NAME).set(theArticle, theImage)
        theArticle.getField(IMAGE_CAPTION_FIELD_NAME).set(theArticle, theImageCaption)
        theArticle.reindexObject()
        print "setImage for %s" % theArticle.id
    else:
        print "No Image for %s" % theArticle.id


        
def retroSetImages(context):
    for theArticle in context.listFolderContents(contentFilter={"portal_type" : "News Item"}):
    
        setImage(theArticle)
