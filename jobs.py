"""Initialize Jobs for Nautobot."""
import csv
import json
from nautobot.core.celery import register_jobs
from django.core.exceptions import ValidationError
from nautobot.extras.jobs import BooleanVar, Job, FileVar, ObjectVar, IntegerVar
from nautobot.extras.models import Status
from nautobot.dcim.models import Device, Location, LocationType

# jobs = datapop_jobs

name = "Data Population Jobs"

loc_suffix = {
    "BR": "Branch", 
    "DC": "Data Center",
}
state_prefix = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia"
}

class WayneImportLocations(Job):
    """Add normalized locations from CSV file."""

    file = FileVar(
        label="Wayne Locations CSV",
        description="name,city,state",
    )

    def __init__(self):
        """Initialize Job."""
        super().__init__()

    class Meta:  # pylint: disable=too-few-public-methods
        """Job specific meta."""

        name = "WayneLocationsCSV ⟹ Nautobot"
        description = "Add normalized locations from CSV file."
        read_only = False

    def run(self, *args, **data):
        """Run method is automatically called."""
        self.data = data
        expected_headers = [
            "name",
            "city",
            "state",
        ]
        # Read file
        lines_of_text = [line.decode("utf-8-sig") for line in self.data['file'].readlines()]
        reader = csv.DictReader(lines_of_text)
        # Validate required headers present in CSV
        if not all(header in reader.fieldnames for header in expected_headers):
            raise ValidationError("Missing Required Fields in CSV file.")
        for row in reader:
            # Do data validation per requirements row by row.
            # validation location name
            location_name = row.get('name', None)
            if not location_name:
                self.logger.info(
                    msg=f"Cannot Load Location {row}. Missing Location Name.",
                )
                continue
            # validate location type
            location_type_suffix = location_name.split("-")[-1]
            if location_type_suffix in loc_suffix.keys():
                location_type__name = loc_suffix.get(location_type_suffix)
            else:
                self.logger.info(
                    msg=f"Cannot Load Location {row}. Invalid LocationType.",
                )
                continue
            # if location name/type exists, ignore and continue: idempotency
            location_qs = Location.objects.filter(
                name=location_name,
                location_type__name=location_type__name,
            ).first()
            if location_qs.exists():
                self.logger.info(
                    msg=f"Skipping Location {row}. Already exists.",
                )
                continue
            # Validate State
            state_raw = row.get('state', None)
            if not state_raw:
                self.logger.info(
                    msg=f"Cannot Load Location {row}. Missing State Name.",
                )
                continue
            if state_raw.upper() in state_prefix.keys():
                state_name = state_prefix.get(state_raw.upper())
            elif state_raw in state_prefix.values():
                state_name = state_raw
            else:
                self.logger.info(
                    msg=f"Cannot Load Location {row}. Invalid US State.",
                )
                continue
            # Validate City
            city_name = row.get('city', None)
            if not city_name:
                self.logger.info(
                    msg=f"Cannot Load Location {row}. Missing City Name.",
                )
                continue
            # Create location and associated Objects.
            active_status, _ = Status.objects.get_or_create(name="Active")
            try:
                state, created = Location.objects.get_or_create(
                    name = state_name,
                    location_type__name = "State",
                    status = active_status,
                )
                if created:
                    state.validated_save()
                city, created = Location.objects.get_or_create(
                    name = state_name,
                    location_type__name = "City",
                    status = active_status,
                    parent = state,
                )
                if created:
                    city.validated_save()
                new_loc = Location.objects.create(
                    name = location_name,
                    location_type__name = location_type__name,
                    status = active_status,
                    parent = city,
                )
                new_loc.validated_save()
            except ValidationError:
                self.logger.warning(
                    msg=f"Cannot Load Location {row}. Validation Error.",
                )
                continue            
            

register_jobs(*jobs, WayneImportLocations)
