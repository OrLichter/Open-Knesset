import datetime
import json
import re
from django.test import TestCase
from django.core.urlresolvers import reverse
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.utils import translation
from django.conf import settings
from tagging.models import Tag,TaggedItem
from laws.models import Vote, VoteAction, Bill, Law
from mks.models import Member,Party,WeeklyPresence,Knesset
from committees.models import Committee
from committees.models import CommitteeMeeting
from agendas.models import Agenda
from knesset.sitemap import sitemaps
from auxiliary.views import CsvView
from django.core import cache
from django.contrib.auth.models import User,Group,Permission

from tag_suggestions.tests import TestApprove, TestForm

class TagDetailViewTest(TestCase):

    def setUp(self):
        self.knesset1 = Knesset.objects.create(number=1,
							start_date=datetime.datetime.today()-datetime.timedelta(days=3),
                            end_date=datetime.datetime.today()-datetime.timedelta(days=1))
        self.knesset2 = Knesset.objects.create(number=2,
                            start_date=datetime.datetime.today()-datetime.timedelta(days=1))
        self.committee_1 = Committee.objects.create(name='c1')
        self.committee_2 = Committee.objects.create(name='c2')
        self.meeting_1 = self.committee_1.meetings.create(date=datetime.datetime.now(),
                                 topics = "django",
                                 protocol_text='''jacob:
I am a perfectionist
adrian:
I have a deadline''')
        self.meeting_1.create_protocol_parts()
        self.meeting_3 = self.committee_1.meetings.create(date=datetime.datetime.now(),
                                 topics = "untagged2",
                                 protocol_text='untagged')
        self.meeting_3.create_protocol_parts()
        self.meeting_4 = self.committee_1.meetings.create(date=datetime.datetime.now(),
                                 topics = "tagged_as_2",
                                 protocol_text='untagged')
        self.meeting_4.create_protocol_parts()
        self.meeting_2 = self.committee_1.meetings.create(date=datetime.datetime.now()-datetime.timedelta(days=2),
                                                         topics = "python",
                                                         protocol_text='m2')
        self.meeting_2.create_protocol_parts()
        self.jacob = User.objects.create_user('jacob', 'jacob@example.com',
                                              'JKM')
        self.adrian = User.objects.create_user('adrian', 'adrian@example.com',
                                              'ADRIAN')
        (self.group, created) = Group.objects.get_or_create(name='Valid Email')
        if created:
            self.group.save()
        self.group.permissions.add(Permission.objects.get(name='Can add annotation'))
        self.jacob.groups.add(self.group)

        ct = ContentType.objects.get_for_model(Tag)
        self.adrian.user_permissions.add(Permission.objects.get(codename='add_tag', content_type=ct))

        self.bill_1 = Bill.objects.create(stage='1', title='bill 1', stage_date=datetime.date.today())
        self.bill_2 = Bill.objects.create(stage='1', title='bill 2', stage_date=datetime.date.today()-datetime.timedelta(days=2))
        self.bill_3 = Bill.objects.create(stage='1', title='bill 3', stage_date=datetime.date.today())
        self.bill_4 = Bill.objects.create(stage='1', title='bill 4', stage_date=datetime.date.today())
        
        self.mk_1 = Member.objects.create(name='mk 1')
        self.topic = self.committee_1.topic_set.create(creator=self.jacob,
                                                title="hello", description="hello world")
                                                
        cm_ct = ContentType.objects.get_for_model(CommitteeMeeting)
        self.tag_1 = Tag.objects.create(name='tag1')
        self.tag_2 = Tag.objects.create(name='tag2')        
        
        self.meeting_1.mks_attended.add(self.mk_1)
        
        TaggedItem._default_manager.get_or_create(tag=self.tag_1, content_type=cm_ct, object_id=self.meeting_1.id)
        TaggedItem._default_manager.get_or_create(tag=self.tag_1, content_type=cm_ct, object_id=self.meeting_2.id)
        TaggedItem._default_manager.get_or_create(tag=self.tag_2, content_type=cm_ct, object_id=self.meeting_4.id)
        
        Tag.objects.add_tag(self.bill_1, 'tag1')
        Tag.objects.add_tag(self.bill_2, 'tag1')
        Tag.objects.add_tag(self.bill_4, 'tag2')
        
        
        self.vote_time_1 = Vote.objects.create(title="vote time 1", time=datetime.datetime.now())
        self.vote_time_2 = Vote.objects.create(title="vote time 2", time=datetime.datetime.now()-datetime.timedelta(days=2))
        self.vote_time_3 = Vote.objects.create(title="vote time 3", time=datetime.datetime.now())
        self.vote_time_4 = Vote.objects.create(title="vote time 4", time=datetime.datetime.now())
        
        self.vote_pre_vote_1 = Vote.objects.create(title="vote pre vote 1", time=datetime.datetime.now()-datetime.timedelta(days=2))
        self.vote_pre_vote_2 = Vote.objects.create(title="vote pre vote 2", time=datetime.datetime.now()-datetime.timedelta(days=2))
        self.vote_pre_vote_3 = Vote.objects.create(title="vote pre vote 3", time=datetime.datetime.now()-datetime.timedelta(days=2))
        self.vote_pre_vote_4 = Vote.objects.create(title="vote pre vote 4", time=datetime.datetime.now()-datetime.timedelta(days=2))
        
        self.vote_first_1 = Vote.objects.create(title="vote first 1", time=datetime.datetime.now()-datetime.timedelta(days=2))
        self.vote_first_2 = Vote.objects.create(title="vote first 2", time=datetime.datetime.now()-datetime.timedelta(days=2))
        self.vote_first_3 = Vote.objects.create(title="vote first 3", time=datetime.datetime.now()-datetime.timedelta(days=2))
        self.vote_first_4 = Vote.objects.create(title="vote first 4", time=datetime.datetime.now()-datetime.timedelta(days=2))
        
        self.vote_approval_1 = Vote.objects.create(title="vote approval 1", time=datetime.datetime.now()-datetime.timedelta(days=2))
        self.vote_approval_2 = Vote.objects.create(title="vote approval 2", time=datetime.datetime.now()-datetime.timedelta(days=2))
        self.vote_approval_3 = Vote.objects.create(title="vote approval 3", time=datetime.datetime.now()-datetime.timedelta(days=2))
        self.vote_approval_4 = Vote.objects.create(title="vote approval 4", time=datetime.datetime.now()-datetime.timedelta(days=2))
        
        vote_ct = ContentType.objects.get_for_model(Vote)
        TaggedItem._default_manager.get_or_create(tag=self.tag_1, content_type=vote_ct, object_id=self.vote_time_1.id)
        TaggedItem._default_manager.get_or_create(tag=self.tag_1, content_type=vote_ct, object_id=self.vote_time_2.id)
        TaggedItem._default_manager.get_or_create(tag=self.tag_2, content_type=vote_ct, object_id=self.vote_time_4.id)

        self.pre_bill_1 = Bill.objects.create(stage='1', title='bill pre 1', stage_date=datetime.date.today())
        self.pre_bill_1.pre_votes.add(self.vote_pre_vote_1)
        self.pre_bill_2 = Bill.objects.create(stage='1', title='bill pre 2', stage_date=datetime.date.today()-datetime.timedelta(days=2))
        self.pre_bill_2.pre_votes.add(self.vote_pre_vote_2)
        self.pre_bill_3 = Bill.objects.create(stage='1', title='bill pre 3', stage_date=datetime.date.today())
        self.pre_bill_3.pre_votes.add(self.vote_pre_vote_3)
        self.pre_bill_4 = Bill.objects.create(stage='1', title='bill pre 4', stage_date=datetime.date.today())
        self.pre_bill_4.pre_votes.add(self.vote_pre_vote_4)
        TaggedItem._default_manager.get_or_create(tag=self.tag_1, content_type=vote_ct, object_id=self.vote_pre_vote_1.id)
        TaggedItem._default_manager.get_or_create(tag=self.tag_1, content_type=vote_ct, object_id=self.vote_pre_vote_2.id)
        TaggedItem._default_manager.get_or_create(tag=self.tag_2, content_type=vote_ct, object_id=self.vote_pre_vote_4.id)

        self.first_bill_1 = Bill.objects.create(stage='1', title='bill first 1', stage_date=datetime.date.today(), first_vote=self.vote_first_1)
        self.first_bill_2 = Bill.objects.create(stage='1', title='bill first 2', stage_date=datetime.date.today()-datetime.timedelta(days=2), first_vote=self.vote_first_2)
        self.first_bill_3 = Bill.objects.create(stage='1', title='bill first 3', stage_date=datetime.date.today(), first_vote=self.vote_first_3)
        self.first_bill_4 = Bill.objects.create(stage='1', title='bill first 4', stage_date=datetime.date.today(), first_vote=self.vote_first_4)
        TaggedItem._default_manager.get_or_create(tag=self.tag_1, content_type=vote_ct, object_id=self.vote_first_1.id)
        TaggedItem._default_manager.get_or_create(tag=self.tag_1, content_type=vote_ct, object_id=self.vote_first_2.id)
        TaggedItem._default_manager.get_or_create(tag=self.tag_2, content_type=vote_ct, object_id=self.vote_first_4.id)

        self.approval_bill_1 = Bill.objects.create(stage='1', title='bill approval 1', stage_date=datetime.date.today(), approval_vote=self.vote_approval_1)
        self.approval_bill_2 = Bill.objects.create(stage='1', title='bill approval 2', stage_date=datetime.date.today()-datetime.timedelta(days=2), approval_vote=self.vote_approval_2)
        self.approval_bill_3 = Bill.objects.create(stage='1', title='bill approval 3', stage_date=datetime.date.today(), approval_vote=self.vote_approval_3)
        self.approval_bill_4 = Bill.objects.create(stage='1', title='bill approval 4', stage_date=datetime.date.today(), approval_vote=self.vote_approval_4)
        TaggedItem._default_manager.get_or_create(tag=self.tag_1, content_type=vote_ct, object_id=self.vote_approval_1.id)
        TaggedItem._default_manager.get_or_create(tag=self.tag_1, content_type=vote_ct, object_id=self.vote_approval_2.id)
        TaggedItem._default_manager.get_or_create(tag=self.tag_2, content_type=vote_ct, object_id=self.vote_approval_4.id)

    def testDefaultKnessetId(self):
        res = self.client.get(reverse('tag-detail',kwargs={'slug':'tag1'}))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'auxiliary/tag_detail.html')
        knesset_id = res.context['knesset_id'].number
        self.assertEqual(knesset_id,2)

    def testInvalidKnessetId(self):
        res = self.client.get(reverse('tag-detail',kwargs={'slug':'tag1'}), {'page':10})
        self.assertEqual(res.status_code, 404)
        
    def testCurrentSelectedKnessetId(self):
        res = self.client.get(reverse('tag-detail',kwargs={'slug':'tag1'}), {'page':2})
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'auxiliary/tag_detail.html')
        knesset_id = res.context['knesset_id'].number
        self.assertEqual(knesset_id,2)
    def testPrevSelectedKnessetId(self):
        res = self.client.get(reverse('tag-detail',kwargs={'slug':'tag1'}), {'page':1})
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'auxiliary/tag_detail.html')
        knesset_id = res.context['knesset_id'].number
        self.assertEqual(knesset_id,1)
        
    def testVisibleCommitteeMeetings(self):
        res = self.client.get(reverse('tag-detail',kwargs={'slug':'tag1'}), {'page':2})
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'auxiliary/tag_detail.html')
        cms = res.context['cms']
        self.assertEqual(len(cms),1)
        self.assertEqual(cms[0].topics, "django")
        
    def testVisibleBills(self):
        res = self.client.get(reverse('tag-detail',kwargs={'slug':'tag1'}), {'page':2})
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'auxiliary/tag_detail.html')
        bills = res.context['bills']
        self.assertEqual(len(bills),1)
        self.assertEqual(bills[0].title, "bill 1")
		

    def testVisibleVotes(self):
        res = self.client.get(reverse('tag-detail',kwargs={'slug':'tag1'}), {'page':2})
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'auxiliary/tag_detail.html')
        votes = res.context['votes']
        print [v.title for v in votes]
        self.assertEqual(len(votes),4)
        self.assertEqual(set([v.title for v in votes]), set([
			"vote time 1",
			"vote pre vote 1",
			"vote first 1",
			"vote approval 1",
		]))
		
class TagResourceTest(TestCase):

    def setUp(self):
        cache.cache.clear()
        self.tags = []
        self.tags.append(Tag.objects.create(name = 'tag1'))
        self.tags.append(Tag.objects.create(name = 'tag2'))
        self.tags.append(Tag.objects.create(name = 'tag3'))

        self.vote = Vote.objects.create(title="vote 1", time=datetime.datetime.now())
        ctype = ContentType.objects.get_for_model(Vote)
        TaggedItem._default_manager.get_or_create(tag=self.tags[0], content_type=ctype, object_id=self.vote.id)
        TaggedItem._default_manager.get_or_create(tag=self.tags[1], content_type=ctype, object_id=self.vote.id)
        self.law = Law.objects.create(title='law 1')
        self.bill = Bill.objects.create(stage='1',
                                          stage_date=datetime.date.today(),
                                          title='bill 1',
                                          law=self.law)
        self.bill2 = Bill.objects.create(stage='2',
                                          stage_date=datetime.date.today(),
                                          title='bill 2',
                                          law=self.law)
        Tag.objects.add_tag(self.bill, 'tag1')
        Tag.objects.add_tag(self.bill2, 'tag3')

    def _reverse_api(self, name, **args):
        args.update(dict(api_name='v2', resource_name='tag'))
        return reverse(name, kwargs=args)

    def test_api_tag_list(self):
        res = self.client.get(self._reverse_api('api_dispatch_list'))
        self.assertEqual(res.status_code, 200)
        res_json = json.loads(res.content)['objects']
        self.assertEqual(len(res_json), 3)
        self.assertEqual(set([x['name'] for x in res_json]), set(Tag.objects.values_list('name',flat=True)))

    def test_api_tag(self):
        res = self.client.get(self._reverse_api('api_dispatch_detail', pk = self.tags[0].id))
        self.assertEqual(res.status_code, 200)
        res_json = json.loads(res.content)
        self.assertEqual(res_json['name'], self.tags[0].name)

    def test_api_tag_not_found(self):
        res = self.client.get(self._reverse_api('api_dispatch_detail', pk = 12345))
        self.assertEqual(res.status_code, 404)

    def test_api_tag_for_vote(self):
        res = self.client.get(self._reverse_api('tags-for-object', app_label='laws',
                                                object_type='vote', object_id=self.vote.id))
        self.assertEqual(res.status_code, 200)
        res_json = json.loads(res.content)['objects']
        self.assertEqual(len(res_json), 2)

    def test_api_related_tags(self):
        res = self.client.get(self._reverse_api('related-tags', app_label='laws',
                                                object_type='law', object_id=self.law.id, related_name='bills'))
        self.assertEqual(res.status_code, 200)
        res_json = json.loads(res.content)['objects']
        self.assertEqual(len(res_json), 2)
        received_tags = set(Tag.objects.get(pk=x) for x in (res_json[0]['id'], res_json[1]['id']))
        self.assertEqual(received_tags, set([self.tags[0], self.tags[2]]))

class InternalLinksTest(TestCase):

    def setUp(self):
        Knesset.objects._current_knesset = None
        #self.vote_1 = Vote.objects.create(time=datetime.now(),title='vote 1')
        self.knesset = Knesset.objects.create(number=1,
                        start_date=datetime.date.today()-datetime.timedelta(days=100))
        self.party_1 = Party.objects.create(name='party 1', number_of_seats=4,
                                            knesset=self.knesset)
        self.vote_1 = Vote.objects.create(title="vote 1", time=datetime.datetime.now())
        self.mks = []
        self.plenum = Committee.objects.create(name='Plenum',type='plenum')
        self.voteactions = []
        self.num_mks = 4
        for i in range(self.num_mks):
            mk = Member.objects.create(name='mk %d' % i, current_party=self.party_1)
            wp = WeeklyPresence(member=mk,date=datetime.date.today(),hours=float(i))
            wp.save()
            self.mks.append(mk)
            if i<2:
                self.voteactions.append(VoteAction.objects.create(member=mk,type='for',vote=self.vote_1, party=mk.current_party))
            else:
                self.voteactions.append(VoteAction.objects.create(member=mk,type='against',vote=self.vote_1, party=mk.current_party))
        self.vote_1.controversy = min(self.vote_1.for_votes_count, self.vote_1.against_votes_count)
        self.vote_1.save()
        self.tags = []
        self.tags.append(Tag.objects.create(name = 'tag1'))
        self.tags.append(Tag.objects.create(name = 'tag2'))
        ctype = ContentType.objects.get_for_model(Vote)
        TaggedItem._default_manager.get_or_create(tag=self.tags[0], content_type=ctype, object_id=self.vote_1.id)
        TaggedItem._default_manager.get_or_create(tag=self.tags[1], content_type=ctype, object_id=self.vote_1.id)
        self.agenda = Agenda.objects.create(name="agenda 1 (public)", public_owner_name="owner", is_public=True)
        self.private_agenda = Agenda.objects.create(name="agenda 2 (private)", public_owner_name="owner")
        self.bill_1 = Bill.objects.create(stage='1', title='bill 1', popular_name="The Bill")
        ctype = ContentType.objects.get_for_model(Bill)
        TaggedItem._default_manager.get_or_create(tag=self.tags[0], content_type=ctype, object_id=self.bill_1.id)
        self.domain = 'http://' + Site.objects.get_current().domain

    def test_internal_links(self):
        """
        Internal links general test.
        This test reads the site, starting from the main page,
        looks for links, and makes sure all internal pages return HTTP200
        """
        from django.conf import settings
        translation.activate(settings.LANGUAGE_CODE)
        visited_links = set()

        test_pages = [reverse('main'), reverse('vote-list'),
                      reverse('bill-list'),
                      reverse('parties-members-list', kwargs={'pk': '1' })]

        redirects = [
            reverse('party-list'), reverse('member-list'),
            reverse('parties-members-index'),
        ]

        for page in test_pages:

            links_to_visit = []
            res = self.client.get(page)
            self.assertEqual(res.status_code, 200)
            visited_links.add(page)
            for link in re.findall("href=\"(.*?)\"",res.content):
                link = link.lower()
                self.failUnless(link, "There seems to be an empty link in %s (href='')" % page)
                if (link in visited_links or link.startswith("http") or
                        link.startswith("//") or link.startswith("#")):
                    continue
                if link.startswith("../"):
                    link = '/' + '/'.join(link.split('/')[1:])
                elif link.startswith("./"):
                    link = link[2:]
                elif link.startswith("."):
                    link = link[1:]
                if not link.startswith("/"): # relative
                    link = "%s%s" % (page,link)

                if link.find(settings.STATIC_URL)>=0: # skip testing static files
                    continue

                links_to_visit.append(link)

            while links_to_visit:
                link = links_to_visit.pop()
                res0 = self.client.get(link)

                if link in redirects:
                    self.assertEqual(res0.status_code, 301, msg="internal redirect %s from page %s seems to be broken" % (link,page))
                else:
                    self.assertEqual(res0.status_code, 200, msg="internal link %s from page %s seems to be broken" % (link,page))
                visited_links.add(link)

        # generate a txt file report of the visited links. for debugging the test
        #visited_links = list(visited_links)
        #visited_links.sort()
        #f = open('internal_links_tested.txt','wt')
        #f.write('\n'.join(visited_links))
        #f.close()


class SiteMapTest(TestCase):

    def setUp(self):
        pass

    def test_sitemap(self):
        res = self.client.get(reverse('sitemap'))
        self.assertEqual(res.status_code, 200)
        for s in sitemaps.keys():
            res = self.client.get(reverse('sitemaps', kwargs={'section':s}))
            self.assertEqual(res.status_code, 200, 'sitemap %s returned %d' %
                             (s,res.status_code))


class CsvViewTest(TestCase):

    class TestModel(object):
        def __init__(self, value):
            self.value = value

        def squared(self):
            return self.value ** 2

    class ConcreteCsvView(CsvView):
        filename = 'test.csv'
        list_display = (("value", "value"),
                        ("squared", "squared"))

    def test_csv_view(self):
        view = self.ConcreteCsvView()
        view.model = self.TestModel
        view.queryset = [self.TestModel(2), self.TestModel(3)]
        response = view.dispatch(None)
        rows = response.content.splitlines()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1], '2,4')
        self.assertEqual(rows[2], '3,9')
