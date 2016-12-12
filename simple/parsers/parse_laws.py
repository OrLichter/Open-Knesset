# encoding: utf-8
import datetime
import logging
import os
import re
import urllib
import urllib2
from HTMLParser import HTMLParseError
from urlparse import urlparse

from BeautifulSoup import BeautifulSoup
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile

import parse_knesset_bill_pdf
from knesset.utils import send_chat_notification
from laws.models import Bill, Law, GovProposal
from links.models import Link, LinkedFile
from mks.models import Knesset
from simple.constants import PRIVATE_LAWS_URL, KNESSET_LAWS_URL, GOV_LAWS_URL
from simple.government_bills.parse_government_bill_pdf import GovProposalParser
from simple.parsers.utils.laws_parser_utils import normalize_correction_title_dashes, clean_line

logger = logging.getLogger("open-knesset.parse_laws")

# don't parse laws from an older knesset
CUTOFF_DATE = datetime.date(2009, 2, 24)


class ParseLaws(object):
    """partially abstract class for parsing laws. contains one function used in few
       cases (private and other laws). this function gives the required page
    """

    url = None

    def get_page_with_param(self, params):
        logger.debug('get_page_with_param: self.url=%s, params=%s' % (self.url, params))
        if not params:
            try:
                html_page = urllib2.urlopen(self.url).read().decode('windows-1255').encode('utf-8')
            except urllib2.URLError as e:
                logger.error("can't open URL: %s" % self.url)
                send_chat_notification(__name__, 'failed to open url', {'url': self.url, 'params': params})
                return None
            try:
                soup = BeautifulSoup(html_page)
            except HTMLParseError as e:
                logger.debug("parsing URL: %s - %s. will try harder." % (self.url, e))
                html_page = re.sub("(?s)<!--.*?-->", " ", html_page)  # cut anything that looks suspicious
                html_page = re.sub("(?s)<script>.*?</script>", " ", html_page)
                html_page = re.sub("(?s)<!.*?>", " ", html_page)
                try:
                    soup = BeautifulSoup(html_page)
                except HTMLParseError as e:
                    logger.debug("error parsing URL: %s - %s" % (self.url, e))
                    send_chat_notification(__name__, 'failed to parse url', {'url': self.url, 'params': None})
                    return None
            return soup
        else:
            data = urllib.urlencode(params)
            try:
                url_data = urllib2.urlopen(self.url, data)
            except urllib2.URLError:
                logger.error("can't open URL: %s" % self.url)
                send_chat_notification(__name__, 'failed to open url', {'url': self.url, 'params': data})
                return None
            html_page = url_data.read().decode('windows-1255').encode('utf-8')
            try:
                soup = BeautifulSoup(html_page)
            except HTMLParseError as e:
                logger.debug("error parsing URL: %s - %s" % (self.url, e))
                send_chat_notification(__name__, 'failed to parse url', {'url': self.url, 'params': data})
                return None
            return soup


class ParsePrivateLaws(ParseLaws):
    """a class that parses private laws proposed
    """

    # the constructor parses the laws data from the required pages
    def __init__(self, days_back):

        self.url = PRIVATE_LAWS_URL
        self.rtf_url = r"http://www.knesset.gov.il/privatelaw"
        self.laws_data = []
        self.parse_pages_days_back(days_back)

    # parses the required pages data
    def parse_pages_days_back(self, days_back):
        today = datetime.date.today()
        last_required_date = today + datetime.timedelta(days=-days_back)
        last_law_checked_date = today
        index = None
        while last_law_checked_date > last_required_date:
            if index:
                params = {'RowStart': index}
            else:
                params = None
            soup_current_page = self.get_page_with_param(params)
            if not soup_current_page:
                return
            index = self.get_param(soup_current_page)
            self.parse_private_laws_page(soup_current_page)
            last_law_checked_date = self.update_last_date()

    def get_param(self, soup):
        name_tag = soup.findAll(
            lambda tag: tag.name == 'a' and tag.has_key('href') and re.match("javascript:SndSelf\((\d+)\);",
                                                                             tag['href']))
        m = re.match("javascript:SndSelf\((\d+)\);", name_tag[0]['href'])
        return m.groups(1)[0]

    def parse_private_laws_page(self, soup):
        name_tag = soup.findAll(lambda tag: tag.name == 'tr' and tag.has_key('valign') and tag['valign'] == 'Top')
        for tag in name_tag:
            tds = tag.findAll(lambda td: td.name == 'td')
            law_data = {}
            law_data['knesset_id'] = int(tds[0].string.strip())
            law_data['law_id'] = int(tds[1].string.strip())
            if tds[2].findAll('a')[0].has_key('href'):
                law_data['text_link'] = self.rtf_url + r"/" + tds[2].findAll('a')[0]['href']
            law_data['law_full_title'] = tds[3].string.strip()
            m = re.match(u'הצעת ([^\(,]*)(.*?\((.*?)\))?(.*?\((.*?)\))?(.*?,(.*))?', law_data['law_full_title'])
            if not m:
                logger.warn("can't parse proposal title: %s" % law_data['law_full_title'])
                continue
            law_data['law_name'] = clean_line(m.group(1))
            comment1 = m.group(3)
            comment2 = m.group(5)
            if comment2:
                law_data['correction'] = clean_line(comment2)
                law_data['comment'] = comment1
            else:
                law_data['comment'] = None
                if comment1:
                    law_data['correction'] = clean_line(comment1)
                else:
                    law_data['correction'] = None
            law_data['correction'] = normalize_correction_title_dashes(law_data['correction'])
            law_data['law_year'] = m.group(7)
            law_data['proposal_date'] = datetime.datetime.strptime(tds[4].string.strip(), '%d/%m/%Y').date()
            names_string = ''.join([unicode(y) for y in tds[5].findAll('font')[0].contents])
            names_string = clean_line(names_string)
            proposers = []
            joiners = []
            if re.search('ONMOUSEOUT', names_string) > 0:
                splitted_names = names_string.split('ONMOUSEOUT')
                joiners = [name for name in re.match('(.*?)\',\'', splitted_names[0]).group(1).split('<br />') if
                           len(name) > 0]
                proposers = splitted_names[1][10:].split('<br />')
            else:
                proposers = names_string.split('<br />')
            law_data['proposers'] = proposers
            law_data['joiners'] = joiners
            self.laws_data.append(law_data)

    def update_last_date(self):
        return self.laws_data[-1]['proposal_date']


class ParseKnessetLaws(ParseLaws):
    """
    A class that parses Knesset Laws (laws after committees)
    the constructor parses the laws data from the required pages
    """

    def __init__(self, min_booklet):

        self.url = KNESSET_LAWS_URL
        self.pdf_url = r"http://www.knesset.gov.il"
        self.laws_data = []
        self.min_booklet = min_booklet
        self.parse_pages_booklet()

    def parse_pages_booklet(self):
        full_page_parsed = True
        index = None
        while full_page_parsed:
            if index:
                params = {'First': index[0], 'Start': index[1]}
            else:
                params = None
            soup_current_page = self.get_page_with_param(params)
            index = self.get_param(soup_current_page)
            full_page_parsed = self.parse_laws_page(soup_current_page)

    def get_param(self, soup):
        name_tag = soup.findAll(
            lambda tag: tag.name == 'a' and tag.has_key('href') and re.match("javascript:SndSelf\((\d+),(\d+)\);",
                                                                             tag['href']))
        if name_tag:
            m = re.match("javascript:SndSelf\((\d+),(\d+)\);", name_tag[0]['href'])
            return m.groups()
        else:
            return None

    def parse_pdf(self, pdf_url):
        return parse_knesset_bill_pdf.parse(pdf_url)

    def parse_laws_page(self, soup):
        name_tags = soup.findAll(lambda tag: tag.name == 'a' and tag.has_key('href') and tag['href'].find(".pdf") >= 0)
        for tag in name_tags:
            pdf_link = self.pdf_url + tag['href']
            booklet = re.search(r"/(\d+)/", tag['href']).groups(1)[0]
            if int(booklet) <= self.min_booklet:
                return False
            pdf_data = self.parse_pdf(pdf_link) or []
            for j in range(len(pdf_data)):  # sometime there is more than 1 law in a pdf
                title = pdf_data[j]['title']
                m = re.findall('[^\(\)]*\((.*?)\)[^\(\)]', title)
                try:
                    comment = m[-1].strip().replace('\n', '').replace('&nbsp;', ' ')
                    law = title[:title.find(comment) - 1]
                except:
                    comment = None
                    law = title.replace(',', '')
                try:
                    correction = m[-2].strip().replace('\n', '').replace('&nbsp;', ' ')
                    law = title[:title.find(correction) - 1]
                except:
                    correction = None
                correction = normalize_correction_title_dashes(correction)
                law = law.strip().replace('\n', '').replace('&nbsp;', ' ')
                if law.find("הצעת ".decode("utf8")) == 0:
                    law = law[5:]

                law_data = {'booklet': booklet, 'link': pdf_link, 'law': law, 'correction': correction,
                            'comment': comment, 'date': pdf_data[j]['date']}
                if 'original_ids' in pdf_data[j]:
                    law_data['original_ids'] = pdf_data[j]['original_ids']
                if 'bill' in pdf_data[j]:
                    law_data['bill'] = pdf_data[j]['bill']
                self.laws_data.append(law_data)
        return True

    def update_booklet(self):
        return int(self.laws_data[-1]['booklet'])


class ParseGovLaws(ParseKnessetLaws):
    def __init__(self, min_booklet):

        self.url = GOV_LAWS_URL
        self.pdf_url = r"http://www.knesset.gov.il"
        self.laws_data = []
        self.min_booklet = min_booklet

    def parse_gov_laws(self):
        """ entry point to start parsing """
        self.parse_pages_booklet()

    def parse_pdf(self, pdf_url):
        """ Grab a single pdf url, using cache via LinkedFile
        """
        existing_count = Link.objects.filter(url=pdf_url).count()
        if existing_count >= 1:
            if existing_count > 1:
                logger.warn("found two objects with the url %s. Taking the first" % pdf_url)
            link = Link.objects.filter(url=pdf_url).first()
        filename = None
        if existing_count > 0:
            files = [f for f in link.linkedfile_set.order_by('last_updated') if f.link_file.name != '']
            if len(files) > 0:
                link_file = files[0]
                filename = link_file.link_file.path
                logger.debug('trying reusing %s from %s' % (pdf_url, filename))
                if not os.path.exists(filename):
                    # for some reason the file can't be found, we'll just d/l
                    # it again
                    filename = None
                    logger.debug('not reusing because file not found')
        if not filename:
            logger.debug('getting %s' % pdf_url)
            contents = urllib2.urlopen(pdf_url).read()
            link_file = LinkedFile()
            saved_filename = os.path.basename(urlparse(pdf_url).path)
            link_file.link_file.save(saved_filename, ContentFile(contents))
            filename = link_file.link_file.path
        try:
            prop = GovProposalParser(filename)
        except Exception:
            logger.exception('Gov proposal exception %s'.format(pdf_url))
            return None
        # TODO: check if parsing handles more than 1 prop in a booklet
        x = {'title': prop.get_title(),
             'date': prop.get_date(),
             # 'bill':prop,
             'link_file': link_file}
        return [x]

    def update_single_bill(self, pdf_link, booklet=None, alt_title=None):
        gp = None
        if booklet is None:
            # get booklet from existing bill
            gps = GovProposal.objects.filter(source_url=pdf_link)
            if gps.count() < 1:
                logger.error('no existing object with given pdf link and no '
                             'booklet given. pdf_link = %s' % pdf_link)
                return
            gp = gps[0]
            booklet = gp.booklet_number
        pdf_data = self.parse_pdf(pdf_link)
        if pdf_data is None:
            return
        for j in range(len(pdf_data)):  # sometime there is more than 1 gov
            # bill in a pdf
            if alt_title:  # just use the given title
                title = alt_title
            else:  # get the title from the PDF file itself.
                # doesn't work so well
                title = pdf_data[j]['title']
            m = re.findall('[^\(\)]*\((.*?)\)[^\(\)]', title)
            try:
                comment = m[-1].strip().replace('\n', '').replace(
                    '&nbsp;', ' ')
                law = title[:title.find(comment) - 1]
            except:
                comment = None
                law = title.replace(',', '')
            try:
                correction = m[-2].strip().replace('\n', '').replace(
                    '&nbsp;', ' ')
                law = title[:title.find(correction) - 1]
            except:
                correction = None
            correction = normalize_correction_title_dashes(correction)
            law = law.strip().replace('\n', '').replace('&nbsp;', ' ')
            if law.find("הצעת ".decode("utf8")) == 0:
                law = law[5:]

            law_data = {'booklet': booklet, 'link': pdf_link,
                        'law': law, 'correction': correction,
                        'comment': comment, 'date': pdf_data[j]['date']}
            if 'original_ids' in pdf_data[j]:
                law_data['original_ids'] = pdf_data[j]['original_ids']
            if 'bill' in pdf_data[j]:
                law_data['bill'] = pdf_data[j]['bill']
            self.laws_data.append(law_data)
            self.create_or_update_single_bill(
                data=law_data,
                pdf_link=pdf_link,
                link_file=pdf_data[j]['link_file'],
                gp=gp)

    def create_or_update_single_bill(self, data, pdf_link, link_file, gp=None):
        """
        data - a dict of data for this gov proposal
        pdf_link - the source url from which the bill is taken
        link_file - a cached version of the pdf
        gp - an existing GovProposal objects. if this is given, it will be
            updated, instead of creating a new object
        """
        if not (data['date']) or CUTOFF_DATE and data['date'] < CUTOFF_DATE:
            return
        law_name = data['law']
        try:
            law, created = Law.objects.get_or_create(title=law_name)
        except Law.MultipleObjectsReturned:
            created = False
            try:
                law = Law.objects.filter(title=law_name, merged_into=None).last()
            except Law.MultipleObjectsReturned:  # How is this possible? probably another bug somewhere
                law = Law.objects.filter(title=law_name).last()
        if created:
            law.save()
        if law.merged_into:
            law = law.merged_into
        title = u''
        if data['correction']:
            title += data['correction']
        if data['comment']:
            title += ' ' + data['comment']
        if len(title) <= 1:
            title = u'חוק חדש'

        k_id = Knesset.objects.get_knesset_by_date(data['date']).pk

        if gp is None:  # create new GovProposal, or look for an identical one
            (gp, created) = GovProposal.objects.get_or_create(
                booklet_number=data['booklet'],
                source_url=data['link'],
                title=title,
                law=law,
                date=data['date'], defaults={'knesset_id': k_id})
            if created:
                gp.save()
                logger.debug("created GovProposal id = %d" % gp.id)

            # look for similar bills
            bill_params = dict(law=law, title=title, stage='3',
                               stage_date=data['date'])
            similar_bills = Bill.objects.filter(**bill_params).order_by('id')
            if len(similar_bills) >= 1:
                b = similar_bills[0]
                if len(similar_bills) > 1:
                    logger.debug("multiple bills detected")
                    for bill in similar_bills:
                        if bill.id == b.id:
                            logger.debug("bill being used now: %d" % bill.id)
                        else:
                            logger.debug("bill with same fields: %d" % bill.id)
            else:  # create a bill
                b = Bill(**bill_params)
                b.save()
                logger.debug("created bill %d" % b.id)

            # see if the found bill is already linked to a gov proposal
            try:
                bill_gp_id = b.gov_proposal.id
            except GovProposal.DoesNotExist:
                bill_gp_id = None
            if (bill_gp_id is None) or (gp.id == b.gov_proposal.id):
                # b is not linked to gp, or linked to the current gp
                gp.bill = b
                gp.save()
            else:
                logger.debug("processing gp %d - matching bill (%d) already has gp"
                             " (%d)" % (gp.id, b.id, b.gov_proposal.id))
        else:  # update a given GovProposal
            # TODO: move to a classmethod
            gp.booklet_number = data['booklet']
            gp.knesset_id = k_id
            gp.source_url = data['link']
            gp.title = title
            gp.law = law
            gp.date = data['date']
            gp.save()

            gp.bill.title = title
            gp.bill.law = law
            gp.bill.save()
            b = gp.bill

        if (link_file is not None) and (link_file.link is None):
            link = Link(title=pdf_link, url=pdf_link,
                        content_type=ContentType.objects.get_for_model(gp),
                        object_pk=str(gp.id))
            link.save()
            link_file.link = link
            link_file.save()
            logger.debug("check updated %s" % b.get_absolute_url())

    def parse_laws_page(self, soup):
        # Fall back to regex, because these pages are too broken to get the
        # <td> element we need with BS"""
        u = unicode(soup)
        pairs = []
        curr_href = None
        for line in u.split('\n'):
            # This builds upon always having the pdf in one line and then the actual title, else would cause errors
            curr_title = None
            if '.pdf' in line:
                curr_href = re.search('href="(.*?)"', line).group(1)
            if 'LawText1">' in line:
                try:
                    curr_title = re.search('LawText1">(.*?)</', line).group(1)
                except AttributeError:
                    curr_title = re.search('LawText1">(.*?)\r', line).group(1)
                pairs.append((curr_title, curr_href))
        if not pairs:
            return False
        for title, href in pairs:
            try:
                pdf_link = self.pdf_url + href
                booklet = re.search(r"/(\d+)/", href).groups(1)[0]
                if int(booklet) <= self.min_booklet:
                    return False
                self.update_single_bill(pdf_link, booklet=booklet, alt_title=title)
            except TypeError:
                logger.exception('law scraping exception pdf_url: %s href %s' % (self.pdf_url, href))
        return True


#############
#   Main    #
#############

if __name__ == '__main__':
    m = ParsePrivateLaws(15)
