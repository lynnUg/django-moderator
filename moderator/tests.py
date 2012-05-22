from unittest import TestCase

from django.contrib.comments.models import Comment
from django.core import management
from moderator.models import ClassifiedComment, ClassifierState, Word


class DjangoClassifierTestCase(TestCase):

    def setUp(self):
        from moderator.classifier import DjangoClassifier
        self.classifier = DjangoClassifier()

    def test_init(self):
        # With a classifier created it's state object should be stored.
        ClassifierState.objects.get()

        # State's counts should be loaded in the classifier.
        # On initial creation of classifier counts are 0.
        self.failUnlessEqual(self.classifier.nspam, 0)
        self.failUnlessEqual(self.classifier.nham, 0)

        # On subsequent load counts are loaded from state.
        self.classifier.nspam = 10
        self.classifier.nham = 20
        self.classifier.store()
        self.classifier = self.classifier.__class__()
        self.failUnlessEqual(self.classifier.nspam, 10)
        self.failUnlessEqual(self.classifier.nham, 20)

    def test_get_state(self):
        # Setup
        ClassifierState.objects.all().delete()

        # States are unique for type.
        self.classifier = self.classifier.__class__()
        self.classifier = self.classifier.__class__()
        self.classifier = self.classifier.__class__()
        self.classifier = self.classifier.__class__()
        self.failUnlessEqual(ClassifierState.objects.all().count(), 1)

        # On initial creation of state counts are 0.
        state = self.classifier.get_state()
        self.failUnlessEqual(state.spam_count, 0)
        self.failUnlessEqual(state.ham_count, 0)

    def test_store(self):
        state = ClassifierState.objects.get()
        self.failIfEqual(state.spam_count, 50, \
                'Internal checking test is not testing existing values')
        self.failIfEqual(state.ham_count, 100, \
                'Internal checking test is not testing existing values')

        # On store classifier counts should be saved to DB.
        self.classifier.nspam = 50
        self.classifier.nham = 100
        self.classifier.store()
        state = ClassifierState.objects.get()
        self.failUnlessEqual(state.spam_count, 50)
        self.failUnlessEqual(state.ham_count, 100)

    def test_wordinfoget(self):
        # Without any existing words should not create Word,
        # just return word_info with zero counts.
        Word.objects.all().delete()
        self.failIf(Word.objects.all(), \
                "Internal check, no words should exist now")
        word_info = self.classifier._wordinfoget('test')
        self.failUnlessEqual(word_info.spamcount, 0)
        self.failUnlessEqual(word_info.hamcount, 0)

        # With existing words should load counts from DB.
        Word.objects.create(word="test", spam_count=10, ham_count=20)
        word_info = self.classifier._wordinfoget('test')
        self.failUnlessEqual(word_info.spamcount, 10)
        self.failUnlessEqual(word_info.hamcount, 20)

    def test_wordinfoset(self):
        # Without any existing words should create Word with count from record.
        Word.objects.all().delete()
        self.failIf(Word.objects.all(), \
                "Internal check, no words should exist now")
        word_info = self.classifier.WordInfoClass()
        word_info.spamcount = 200
        word_info.hamcount = 500
        self.classifier._wordinfoset('test', word_info)
        word = Word.objects.get()
        self.failUnlessEqual(word.word, 'test')
        self.failUnlessEqual(word.spam_count, 200)
        self.failUnlessEqual(word.ham_count, 500)

        # Without existing word should update counts from record.
        word_info.spamcount = 222
        word_info.hamcount = 555
        self.classifier._wordinfoset('test', word_info)
        word = Word.objects.get()
        self.failUnlessEqual(word.word, 'test')
        self.failUnlessEqual(word.spam_count, 222)
        self.failUnlessEqual(word.ham_count, 555)


class ManagementCommandTestCase(TestCase):
    def setUp(self):
        from moderator import utils
        self.utils = utils

    def test_classifycomments(self):
        # Initial comment setup.
        spam_comment = Comment.objects.create(content_type_id=1, \
                site_id=1, comment="very bad spam")
        ham_comment = Comment.objects.create(content_type_id=1, \
                site_id=1, comment="awesome tasty ham")
        unsure_comment = Comment.objects.create(content_type_id=1, \
                site_id=1, comment="awesome spam")
        untrained_comment = Comment.objects.create(content_type_id=1, \
                site_id=1, comment="foo bar")

        # Initial training
        self.utils.train(spam_comment, True)
        self.utils.train(ham_comment, False)

        management.call_command('classifycomments')

        self.failUnlessEqual(ClassifiedComment.objects.all().count(), 4, \
                "We should now have 4 classified comments")

        # Comment previously trained as spam should be classed as spam.
        ClassifiedComment.objects.get(comment=spam_comment, cls='spam')

        # Comment previously trained as ham should be classed as ham.
        ClassifiedComment.objects.get(comment=ham_comment, cls='ham')

        # Comment containing words previously trained as both
        # spam and ham should be classed as unsure.
        ClassifiedComment.objects.get(comment=unsure_comment, cls='unsure')

        # Comment containing words not previously trained should be
        # classed as unsure.
        ClassifiedComment.objects.get(comment=untrained_comment, cls='unsure')


class UtilsTestCase(TestCase):

    def setUp(self):
        from moderator import utils
        self.utils = utils

    def test_train(self):
        from moderator.classifier import classifier
        # Reset counts to zero
        classifier.bayes.nspam = 0
        classifier.bayes.nham = 0
        classifier.store()

        Word.objects.all().delete()
        self.failIf(Word.objects.all(), \
                "Internal check, no words should exist now")

        self.failUnlessEqual(classifier.bayes.nham, 0, \
                "No ham has been trained yet, should be 0")
        self.failUnlessEqual(classifier.bayes.nspam, 0, \
                "No spam has been trained yet, should be 0")

        comment = Comment.objects.create(content_type_id=1, site_id=1, \
                comment="very bad spam")
        self.utils.train(comment, True)

        # Now we should have word objects for each word in the comment,
        # each having spam count of 1 and ham count of 0.
        self.failUnless(Word.objects.get(word='very', spam_count=1, \
                ham_count=0))
        self.failUnless(Word.objects.get(word='bad', spam_count=1, \
                ham_count=0))
        self.failUnless(Word.objects.get(word='spam', spam_count=1, \
                ham_count=0))

        self.failUnlessEqual(classifier.bayes.nham, 0, \
                "No ham has been trained yet, should still be 0")
        self.failUnlessEqual(classifier.bayes.nspam, 1, \
                "Spam has been trained, should be 1")

        comment = Comment.objects.create(content_type_id=1, site_id=1, \
                comment="awesome tasty ham")
        self.utils.train(comment, False)

        # Now we should have word objects for each word in the comment,
        # each having ham count of 1 and spam count of 0.
        self.failUnless(Word.objects.get(word='awesome', spam_count=0, \
                ham_count=1))
        self.failUnless(Word.objects.get(word='tasty', spam_count=0, \
                ham_count=1))
        self.failUnless(Word.objects.get(word='ham', spam_count=0, \
                ham_count=1))

        self.failUnlessEqual(classifier.bayes.nham, 1, \
                "Ham has been trained, should still 1")
        self.failUnlessEqual(classifier.bayes.nspam, 1, \
                "No more spam has been trained, should still be 1")

        # Training should store state
        state = ClassifierState.objects.get()
        self.failUnlessEqual(state.spam_count, 1)
        self.failUnlessEqual(state.ham_count, 1)

    def test_get_class(self):
        # Initial comment setup.
        spam_comment = Comment.objects.create(content_type_id=1, \
                site_id=1, comment="very bad spam")
        ham_comment = Comment.objects.create(content_type_id=1, \
                site_id=1, comment="awesome tasty ham")
        unsure_comment = Comment.objects.create(content_type_id=1, \
                site_id=1, comment="awesome spam")
        untrained_comment = Comment.objects.create(content_type_id=1, \
                site_id=1, comment="foo bar")

        # Initial training
        self.utils.train(spam_comment, True)
        self.utils.train(ham_comment, False)

        # Comment previously trained as spam should be classed as spam.
        self.failUnlessEqual(self.utils.get_class(spam_comment), 'spam')

        # Comment previously trained as ham should be classed as ham.
        self.failUnlessEqual(self.utils.get_class(ham_comment), 'ham')

        # Comment containing words previously trained as both
        # spam and ham should be classed as unsure.
        self.failUnlessEqual(self.utils.get_class(unsure_comment), 'unsure')

        # Comment containing words not previously trained should be
        # classed as unsure.
        self.failUnlessEqual(self.utils.get_class(untrained_comment), 'unsure')