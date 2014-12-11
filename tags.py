import urllib2
import re
import time

data = {
    'extension': ['cooperative-extension', 'penn-state-cooperative-extension', 'extension', 'penn-state-extension'],
    'aec' : ['earth-and-environment', 'chesapeake-bay', 'energy', 'water', 'water-quality', 'environmental-engineering', 'environment', 'environmental-stewardship', 'forestry']
}


def setTags(context, tag):
    # Tag Feeds
    
    print "Settings %s within %s" % (tag, context.absolute_url())

    if tag not in data.keys():
        return False
    else:
        urls = data[tag] 

    print "Urls to search: %s" % ", ".join(urls)
    
    linkRegex = re.compile("<link>http://news.psu.edu/story/(\d+)/.*?</link>", re.I|re.M)
    
    found_articles = False
    
    for u in urls:
        print "Sleeping 10"
        time.sleep(10)
        tag_url = 'http://news.psu.edu/rss/tag/%s' % u
        print "Grabbing %s" % tag_url
        rss = urllib2.urlopen(tag_url).read()
        for m in re.finditer(linkRegex, rss):
            link = m.group(1)
            if link in context.objectIds():
                story = context[link]
                subject = list(story.Subject())
                if not subject.count('news-%s' % tag):
                    subject.append('news-%s' % tag)
                    print "New subject for %s : %s" % (link, str(subject))
                    found_articles = True
                    story.setSubject(tuple(subject))
                    story.reindexObject()
                    
    return found_articles
    
    