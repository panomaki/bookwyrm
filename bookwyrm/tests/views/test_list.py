""" test for app action functionality """
import json
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.template.response import TemplateResponse
from django.test import TestCase
from django.test.client import RequestFactory

from bookwyrm import models, views
from bookwyrm.activitypub import ActivitypubResponse

# pylint: disable=unused-argument
class ListViews(TestCase):
    """ tag views"""

    def setUp(self):
        """ we need basic test data and mocks """
        self.factory = RequestFactory()
        self.local_user = models.User.objects.create_user(
            "mouse@local.com",
            "mouse@mouse.com",
            "mouseword",
            local=True,
            localname="mouse",
            remote_id="https://example.com/users/mouse",
        )
        self.rat = models.User.objects.create_user(
            "rat@local.com",
            "rat@rat.com",
            "ratword",
            local=True,
            localname="rat",
            remote_id="https://example.com/users/rat",
        )
        work = models.Work.objects.create(title="Work")
        self.book = models.Edition.objects.create(
            title="Example Edition",
            remote_id="https://example.com/book/1",
            parent_work=work,
        )
        work_two = models.Work.objects.create(title="Labori")
        self.book_two = models.Edition.objects.create(
            title="Example Edition 2",
            remote_id="https://example.com/book/2",
            parent_work=work_two,
        )
        work_three = models.Work.objects.create(title="Trabajar")
        self.book_three = models.Edition.objects.create(
            title="Example Edition 3",
            remote_id="https://example.com/book/3",
            parent_work=work_three,
        )
        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            self.list = models.List.objects.create(
                name="Test List", user=self.local_user
            )
        self.anonymous_user = AnonymousUser
        self.anonymous_user.is_authenticated = False
        models.SiteSettings.objects.create()

    def test_lists_page(self):
        """ there are so many views, this just makes sure it LOADS """
        view = views.Lists.as_view()
        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            models.List.objects.create(name="Public list", user=self.local_user)
            models.List.objects.create(
                name="Private list", privacy="direct", user=self.local_user
            )
        request = self.factory.get("")
        request.user = self.local_user

        result = view(request)
        self.assertIsInstance(result, TemplateResponse)
        result.render()
        self.assertEqual(result.status_code, 200)

        request.user = self.anonymous_user

        result = view(request)
        self.assertIsInstance(result, TemplateResponse)
        result.render()
        self.assertEqual(result.status_code, 200)

    def test_lists_create(self):
        """ create list view """
        view = views.Lists.as_view()
        request = self.factory.post(
            "",
            {
                "name": "A list",
                "description": "wow",
                "privacy": "unlisted",
                "curation": "open",
                "user": self.local_user.id,
            },
        )
        request.user = self.local_user
        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay") as mock:
            result = view(request)

        self.assertEqual(mock.call_count, 1)
        activity = json.loads(mock.call_args[0][1])
        self.assertEqual(activity["type"], "Create")
        self.assertEqual(activity["actor"], self.local_user.remote_id)

        self.assertEqual(result.status_code, 302)
        new_list = models.List.objects.filter(name="A list").get()
        self.assertEqual(new_list.description, "wow")
        self.assertEqual(new_list.privacy, "unlisted")
        self.assertEqual(new_list.curation, "open")

    def test_list_page(self):
        """ there are so many views, this just makes sure it LOADS """
        view = views.List.as_view()
        request = self.factory.get("")
        request.user = self.local_user

        with patch("bookwyrm.views.list.is_api_request") as is_api:
            is_api.return_value = False
            result = view(request, self.list.id)
        self.assertIsInstance(result, TemplateResponse)
        result.render()
        self.assertEqual(result.status_code, 200)

        request.user = self.anonymous_user
        with patch("bookwyrm.views.list.is_api_request") as is_api:
            is_api.return_value = False
            result = view(request, self.list.id)
        self.assertIsInstance(result, TemplateResponse)
        result.render()
        self.assertEqual(result.status_code, 200)

        with patch("bookwyrm.views.list.is_api_request") as is_api:
            is_api.return_value = True
            result = view(request, self.list.id)
        self.assertIsInstance(result, ActivitypubResponse)
        self.assertEqual(result.status_code, 200)

        request = self.factory.get("/?page=1")
        request.user = self.local_user
        with patch("bookwyrm.views.list.is_api_request") as is_api:
            is_api.return_value = True
            result = view(request, self.list.id)
        self.assertIsInstance(result, ActivitypubResponse)
        self.assertEqual(result.status_code, 200)

    def test_list_edit(self):
        """ edit a list """
        view = views.List.as_view()
        request = self.factory.post(
            "",
            {
                "name": "New Name",
                "description": "wow",
                "privacy": "direct",
                "curation": "curated",
                "user": self.local_user.id,
            },
        )
        request.user = self.local_user

        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay") as mock:
            result = view(request, self.list.id)

        self.assertEqual(mock.call_count, 1)
        activity = json.loads(mock.call_args[0][1])
        self.assertEqual(activity["type"], "Update")
        self.assertEqual(activity["actor"], self.local_user.remote_id)
        self.assertEqual(activity["object"]["id"], self.list.remote_id)

        self.assertEqual(result.status_code, 302)

        self.list.refresh_from_db()
        self.assertEqual(self.list.name, "New Name")
        self.assertEqual(self.list.description, "wow")
        self.assertEqual(self.list.privacy, "direct")
        self.assertEqual(self.list.curation, "curated")

    def test_curate_page(self):
        """ there are so many views, this just makes sure it LOADS """
        view = views.Curate.as_view()
        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            models.List.objects.create(name="Public list", user=self.local_user)
            models.List.objects.create(
                name="Private list", privacy="direct", user=self.local_user
            )
        request = self.factory.get("")
        request.user = self.local_user

        result = view(request, self.list.id)
        self.assertIsInstance(result, TemplateResponse)
        result.render()
        self.assertEqual(result.status_code, 200)

        request.user = self.anonymous_user
        result = view(request, self.list.id)
        self.assertEqual(result.status_code, 302)

    def test_curate_approve(self):
        """ approve a pending item """
        view = views.Curate.as_view()
        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            pending = models.ListItem.objects.create(
                book_list=self.list,
                user=self.local_user,
                book=self.book,
                approved=False,
                order=1,
            )

        request = self.factory.post(
            "",
            {
                "item": pending.id,
                "approved": "true",
            },
        )
        request.user = self.local_user

        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay") as mock:
            view(request, self.list.id)

        self.assertEqual(mock.call_count, 1)
        activity = json.loads(mock.call_args[0][1])
        self.assertEqual(activity["type"], "Add")
        self.assertEqual(activity["actor"], self.local_user.remote_id)
        self.assertEqual(activity["target"], self.list.remote_id)

        pending.refresh_from_db()
        self.assertEqual(self.list.books.count(), 1)
        self.assertEqual(self.list.listitem_set.first(), pending)
        self.assertTrue(pending.approved)

    def test_curate_reject(self):
        """ approve a pending item """
        view = views.Curate.as_view()
        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            pending = models.ListItem.objects.create(
                book_list=self.list,
                user=self.local_user,
                book=self.book,
                approved=False,
                order=1,
            )

        request = self.factory.post(
            "",
            {
                "item": pending.id,
                "approved": "false",
            },
        )
        request.user = self.local_user

        view(request, self.list.id)

        self.assertFalse(self.list.books.exists())
        self.assertFalse(models.ListItem.objects.exists())

    def test_add_book(self):
        """ put a book on a list """
        request = self.factory.post(
            "",
            {
                "book": self.book.id,
                "list": self.list.id,
            },
        )
        request.user = self.local_user

        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay") as mock:
            views.list.add_book(request)
            self.assertEqual(mock.call_count, 1)
            activity = json.loads(mock.call_args[0][1])
            self.assertEqual(activity["type"], "Add")
            self.assertEqual(activity["actor"], self.local_user.remote_id)
            self.assertEqual(activity["target"], self.list.remote_id)

        item = self.list.listitem_set.get()
        self.assertEqual(item.book, self.book)
        self.assertEqual(item.user, self.local_user)
        self.assertTrue(item.approved)

    def test_add_two_books(self):
        """
        Putting two books on the list. The first should have an order value of
        1 and the second should have an order value of 2.
        """
        request_one = self.factory.post(
            "",
            {
                "book": self.book.id,
                "list": self.list.id,
            },
        )
        request_one.user = self.local_user

        request_two = self.factory.post(
            "",
            {
                "book": self.book_two.id,
                "list": self.list.id,
            },
        )
        request_two.user = self.local_user
        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            views.list.add_book(request_one)
            views.list.add_book(request_two)

        items = self.list.listitem_set.order_by("order").all()
        self.assertEqual(items[0].book, self.book)
        self.assertEqual(items[1].book, self.book_two)
        self.assertEqual(items[0].order, 1)
        self.assertEqual(items[1].order, 2)

    def test_add_three_books_and_remove_second(self):
        """
        Put three books on a list and then remove the one in the middle. The
        ordering of the list should adjust to not have a gap.
        """
        request_one = self.factory.post(
            "",
            {
                "book": self.book.id,
                "list": self.list.id,
            },
        )
        request_one.user = self.local_user

        request_two = self.factory.post(
            "",
            {
                "book": self.book_two.id,
                "list": self.list.id,
            },
        )
        request_two.user = self.local_user

        request_three = self.factory.post(
            "",
            {
                "book": self.book_three.id,
                "list": self.list.id,
            },
        )
        request_three.user = self.local_user

        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            views.list.add_book(request_one)
            views.list.add_book(request_two)
            views.list.add_book(request_three)

        items = self.list.listitem_set.order_by("order").all()
        self.assertEqual(items[0].book, self.book)
        self.assertEqual(items[1].book, self.book_two)
        self.assertEqual(items[2].book, self.book_three)
        self.assertEqual(items[0].order, 1)
        self.assertEqual(items[1].order, 2)
        self.assertEqual(items[2].order, 3)

        remove_request = self.factory.post("", {"item": items[1].id})
        remove_request.user = self.local_user
        views.list.remove_book(remove_request, self.list.id)
        items = self.list.listitem_set.order_by("order").all()
        self.assertEqual(items[0].book, self.book)
        self.assertEqual(items[1].book, self.book_three)
        self.assertEqual(items[0].order, 1)
        self.assertEqual(items[1].order, 2)

    def test_add_three_books_and_move_last_to_first(self):
        """
        Put three books on the list and move the last book to the first
        position.
        """
        request_one = self.factory.post(
            "",
            {
                "book": self.book.id,
                "list": self.list.id,
            },
        )
        request_one.user = self.local_user

        request_two = self.factory.post(
            "",
            {
                "book": self.book_two.id,
                "list": self.list.id,
            },
        )
        request_two.user = self.local_user

        request_three = self.factory.post(
            "",
            {
                "book": self.book_three.id,
                "list": self.list.id,
            },
        )
        request_three.user = self.local_user

        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            views.list.add_book(request_one)
            views.list.add_book(request_two)
            views.list.add_book(request_three)

        items = self.list.listitem_set.order_by("order").all()
        self.assertEqual(items[0].book, self.book)
        self.assertEqual(items[1].book, self.book_two)
        self.assertEqual(items[2].book, self.book_three)
        self.assertEqual(items[0].order, 1)
        self.assertEqual(items[1].order, 2)
        self.assertEqual(items[2].order, 3)

        set_position_request = self.factory.post("", {"position": 1})
        set_position_request.user = self.local_user
        views.list.set_book_position(set_position_request, items[2].id)
        items = self.list.listitem_set.order_by("order").all()
        self.assertEqual(items[0].book, self.book_three)
        self.assertEqual(items[1].book, self.book)
        self.assertEqual(items[2].book, self.book_two)
        self.assertEqual(items[0].order, 1)
        self.assertEqual(items[1].order, 2)
        self.assertEqual(items[2].order, 3)

    def test_add_book_outsider(self):
        """ put a book on a list """
        self.list.curation = "open"
        self.list.save(broadcast=False)
        request = self.factory.post(
            "",
            {
                "book": self.book.id,
                "list": self.list.id,
            },
        )
        request.user = self.rat

        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay") as mock:
            views.list.add_book(request)
            self.assertEqual(mock.call_count, 1)
            activity = json.loads(mock.call_args[0][1])
            self.assertEqual(activity["type"], "Add")
            self.assertEqual(activity["actor"], self.rat.remote_id)
            self.assertEqual(activity["target"], self.list.remote_id)

        item = self.list.listitem_set.get()
        self.assertEqual(item.book, self.book)
        self.assertEqual(item.user, self.rat)
        self.assertTrue(item.approved)

    def test_add_book_pending(self):
        """ put a book on a list awaiting approval """
        self.list.curation = "curated"
        self.list.save(broadcast=False)
        request = self.factory.post(
            "",
            {
                "book": self.book.id,
                "list": self.list.id,
            },
        )
        request.user = self.rat

        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay") as mock:
            views.list.add_book(request)

        self.assertEqual(mock.call_count, 1)
        activity = json.loads(mock.call_args[0][1])

        self.assertEqual(activity["type"], "Add")
        self.assertEqual(activity["actor"], self.rat.remote_id)
        self.assertEqual(activity["target"], self.list.remote_id)

        item = self.list.listitem_set.get()
        self.assertEqual(activity["object"]["id"], item.remote_id)

        self.assertEqual(item.book, self.book)
        self.assertEqual(item.user, self.rat)
        self.assertFalse(item.approved)

    def test_add_book_self_curated(self):
        """ put a book on a list automatically approved """
        self.list.curation = "curated"
        self.list.save(broadcast=False)
        request = self.factory.post(
            "",
            {
                "book": self.book.id,
                "list": self.list.id,
            },
        )
        request.user = self.local_user

        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay") as mock:
            views.list.add_book(request)
            self.assertEqual(mock.call_count, 1)
            activity = json.loads(mock.call_args[0][1])
            self.assertEqual(activity["type"], "Add")
            self.assertEqual(activity["actor"], self.local_user.remote_id)
            self.assertEqual(activity["target"], self.list.remote_id)

        item = self.list.listitem_set.get()
        self.assertEqual(item.book, self.book)
        self.assertEqual(item.user, self.local_user)
        self.assertTrue(item.approved)

    def test_remove_book(self):
        """ take an item off a list """

        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            item = models.ListItem.objects.create(
                book_list=self.list,
                user=self.local_user,
                book=self.book,
                order=1,
            )
        self.assertTrue(self.list.listitem_set.exists())

        request = self.factory.post(
            "",
            {
                "item": item.id,
            },
        )
        request.user = self.local_user

        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            views.list.remove_book(request, self.list.id)
        self.assertFalse(self.list.listitem_set.exists())

    def test_remove_book_unauthorized(self):
        """ take an item off a list """
        with patch("bookwyrm.models.activitypub_mixin.broadcast_task.delay"):
            item = models.ListItem.objects.create(
                book_list=self.list, user=self.local_user, book=self.book, order=1
            )
        self.assertTrue(self.list.listitem_set.exists())
        request = self.factory.post(
            "",
            {
                "item": item.id,
            },
        )
        request.user = self.rat

        views.list.remove_book(request, self.list.id)
        self.assertTrue(self.list.listitem_set.exists())
