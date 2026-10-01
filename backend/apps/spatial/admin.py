from django import forms
from django.contrib import admin
from django.contrib.gis.geos import Point

from .models import Spot


class SpotForm(forms.ModelForm):
    latitude = forms.FloatField(min_value=-90, max_value=90)
    longitude = forms.FloatField(min_value=-180, max_value=180)

    class Meta:
        model = Spot
        exclude = ("location",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.location:
            self.fields["latitude"].initial = self.instance.location.y
            self.fields["longitude"].initial = self.instance.location.x

    def clean(self):
        data = super().clean()
        if "longitude" in data and "latitude" in data:
            self.instance.location = Point(data["longitude"], data["latitude"], srid=4326)
        return data


@admin.register(Spot)
class SpotAdmin(admin.ModelAdmin):
    form = SpotForm
    list_display = ("code", "name", "interaction_radius_m", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)
