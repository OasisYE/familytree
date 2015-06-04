from datetime import date
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from people.relations import describe_relative
from sets import Set
from tinymce.models import HTMLField

class Person(models.Model):
    '''The main class of the model. Every individual is represented by a person
    record.'''
    forename = models.CharField(max_length=20)
    middle_names = models.CharField(blank=True, max_length=50)
    surname = models.CharField(max_length=30)
    maiden_name = models.CharField(blank=True, max_length=30) # Maiden name is optional.
    gender = models.CharField(max_length=1, choices=(('M', 'Male'), ('F', 'Female')))
    date_of_birth = models.DateField(blank=True, null=True)
    date_of_death = models.DateField(blank=True, null=True)
    deceased = models.BooleanField()
    mother = models.ForeignKey('self', blank=True, null=True, limit_choices_to={'gender': 'F'}, related_name='children_of_mother')
    father = models.ForeignKey('self', blank=True, null=True, limit_choices_to={'gender': 'M'}, related_name='children_of_father')
    notes = HTMLField(blank=True)

    def name(self, use_middle_names=True, use_maiden_name=False):
        '''Returns the full name of this person.'''
        name = " ".join([self.forename, self.middle_names]) if use_middle_names and self.middle_names else self.forename
        if self.maiden_name != "":
            return name + " " + (self.maiden_name if use_maiden_name else self.surname + u" (n\xe9e " + self.maiden_name + ")")
        else:
            return name + " " + self.surname

    def age(self):
        '''Calculate the person's age in years.'''
        if not self.date_of_birth or (self.deceased and not self.date_of_death):
            return None
        end = self.date_of_death if self.deceased else date.today()
        years = end.year - self.date_of_birth.year
        if end.month < self.date_of_birth.month or (end.month == self.date_of_birth.month and end.day < self.date_of_birth.day):
            years -= 1
        return years

    def spouses(self):
        '''Return a list of anybody that this person is or was married to.'''
        if self.gender == 'F':
            return [m.husband for m in self.husband_of.all()]
        else:
            return [m.wife for m in self.wife_of.all()]

    def siblings(self):
        '''Returns a list of this person's brothers and sisters, including
        half-siblings.'''
        return Person.objects.filter(~Q(id=self.id),
                                     Q(~Q(father=None), father=self.father) | Q(~Q(mother=None), mother=self.mother)).order_by('date_of_birth')

    def children(self):
        '''Returns a list of this person's children.'''
        offspring = self.children_of_mother if self.gender == 'F' else self.children_of_father
        return offspring.order_by('date_of_birth')

    def descendants(self):
        '''Returns a list of this person's descendants (their children and all
        of their children's descendents).'''
        descendants = []
        children = self.children()
        descendants += children
        for child in children:
            descendants += child.descendants()
        return descendants

    def annotated_descendants(self):
        '''Returns a list of this person's descendants annotated with the name
        of the relationship to this person (so a list of (Person, relationship)
        tuples.'''
        annotated = []
        for descendant in self.descendants():
            annotated.append((descendant, describe_relative(self, descendant)))
        return annotated

    # Returns a dictionary of this person's ancestors.  The ancestors are the
    # keys and each value is the distance (number of generations) from this
    # person to that ancestor (e.g parent is 1, grandparent is 2, etc.)
    def _ancestor_distances(self, offset=0):
        '''Returns a dictionary of this person's ancestors (their parents and
        all of their parents's ancestors) with distance to each ancestor.'''
        ancestors = {}
        if self.mother:
            ancestors[self.mother] = offset + 1
            ancestors.update(self.mother._ancestor_distances(offset + 1))
        if self.father:
            ancestors[self.father] = offset + 1
            ancestors.update(self.father._ancestor_distances(offset + 1))
        return ancestors

    def ancestors(self):
        '''Returns a list of this person's ancestors (their parents and all of
        their parent's ancestors).'''
        return self.ancestor_distances().keys()

    def annotated_ancestors(self):
        '''Returns a list of this person's ancestors annotated with the name of
        the relationship to this person (so a list of (Person, relationship)
        tuples.'''
        ancestors = self.ancestors()
        annotated_ancestors = []
        for ancestor in ancestors:
            annotated_ancestors.append((ancestor, describe_relative(self, ancestor)))
        return annotated_ancestors

    def relatives(self):
        '''Returns a list of all of this person's blood relatives. The first
        item in each tuple is the person and the second is the relationship.'''
        # Two people are related by blood if they share a common ancestor.
        ancestors = self.ancestors()
        # For efficiency, only consider root ancestors since their
        # descendants' blood relatives will be a subset of theirs and don't need
        # to be considered separately.
        root_ancestors = [p for p in ancestors if not (p.father and p.mother)] or [self]
        relatives = Set(root_ancestors)
        for ancestor in root_ancestors:
            relatives.update(ancestor.descendants())
        relatives.remove(self) # This person can't be their own relative.
        annotated_relatives = []
        for relative in relatives:
            annotated_relatives.append((relative, describe_relative(self, relative)))
        return annotated_relatives

    def photos(self):
        '''Returns a list of all photos associated with this person.'''
        return Photograph.objects.filter(person=self)

    def clean(self):
        if self.date_of_death and not self.deceased:
            raise ValidationError('Cannot specify date of death for living person.')

    def __unicode__(self):
        return self.name()


class Marriage(models.Model):
    '''The marriage record links spouses.'''
    husband = models.ForeignKey(Person, limit_choices_to={'gender': 'M'}, related_name='wife_of')
    wife = models.ForeignKey(Person, limit_choices_to={'gender': 'F'}, related_name='husband_of')
    wedding_date = models.DateField(blank=True, null=True)
    divorce_date = models.DateField(blank=True, null=True)

    def __unicode__(self):
        return self.husband.name(False) + ' & ' + self.wife.name(False, True)


class Photograph(models.Model):
    '''The photograph record combines an image with an optional caption and date
    and links it to a person.'''
    image = models.ImageField(upload_to='uploads', blank=True, null=True)
    person = models.ForeignKey(Person)
    caption = models.TextField(blank=True)
    date = models.DateField(blank=True, null=True)

    def __unicode__(self):
        return self.image.url
