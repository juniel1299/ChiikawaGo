"""Synthetic fixtures only; refuse the normal development database."""
import os
import sys
sys.path.insert(0, "/app")
import django
from django.db import connection

django.setup()
from django.contrib.gis.geos import Point
from apps.accounts.models import User
from apps.characters.models import Character, CharacterVariant
from apps.spatial.models import Spot
from apps.encounters.models import SpawnRule

assert connection.settings_dict['NAME'] == 'chii_mobile_test'
user, _ = User.objects.get_or_create(email='mobile@example.invalid', defaults={'display_name': 'Mobile fixture'})
user.set_password(os.environ['CHII_TEST_PASSWORD'])
user.save()
character, _ = Character.objects.get_or_create(code='mobile-fixture', defaults={'name': 'Test character'})
variant, _ = CharacterVariant.objects.get_or_create(character=character, code='base', defaults={'name': 'Base'})
spot, _ = Spot.objects.get_or_create(code='mobile-fixture', defaults={'name':'Synthetic spot', 'location':Point(127,37,srid=4326)})
SpawnRule.objects.get_or_create(spot=spot, character_variant=variant)
print('Synthetic mobile fixtures ready')
