"""Initialize Jobs for Nautobot and DCMaXX."""
import csv
import json
from nautobot.core.celery import register_jobs
from .constants import HAS_NAUTOBOT_APP_CISCO_SDN
from django.core.exceptions import ValidationError
from django.db.models import F
from nautobot.extras.jobs import BooleanVar, Job, FileVar, ObjectVar, IntegerVar
from nautobot.extras.models import Contact, Team
if HAS_NAUTOBOT_APP_CISCO_SDN:
    from nautobot_app_cisco_sdn.models import EPG

from dcm_nautobot_extensions.ssot.integrations.dcmaxx.jobs import jobs as dcmaxx_jobs

jobs = datapop_jobs

name = "Data Population Jobs"

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
        teams_set = set()
        contacts_dict = {}
        for row in reader:
            # Add Team to list if it doesn't exist
            business_unit = row.get('business_unit', None)
            if business_unit:
                teams_set.add(business_unit)
            # Add Contact to Contact list if doesn't exist
            wayne_uid = row.get('business_unit.bu_head.u_wayne_uid', None)
            if wayne_uid not in contacts_dict.keys():
                contact_phone = row.get('business_unit.bu_head.phone', None).lstrip("'")
                contact_email = row.get('business_unit.bu_head.email', None).lower()
                contact_name = row.get('business_unit.bu_head', None)
            if not all([contact_name, contact_email, contact_phone]):
                self.logger.info(
                    msg=f"Cannot Load Contact {row}. Missing Contact Information.",
                )
                continue
            app_id, app_name = row.get('number', None), row.get('name', None)
            app_stage, app_status = row.get('life_cycle_stage', None), row.get('life_cycle_stage_status', None)
            app_dict = { app_id: { "app_name": app_name, "app_stage": app_stage, "app_status": app_status }}
            # Init Contact or Append App
            try:
                contact_app_dict = contacts_dict[wayne_uid]["owned_apps"]
                contact_app_dict.update(app_dict)
            except KeyError:
                contacts_dict[wayne_uid] = {
                    "contact_name": contact_name,
                    "contact_phone": contact_phone,
                    "contact_email": contact_email,
                    "contact_team": business_unit,
                    "owned_apps": app_dict,
                }    
        # Create Teams if they don't Exist
        existing_teams = set(Team.objects.filter(name__in=teams_set).values_list("name", flat=True))
        missing_teams = teams_set - existing_teams
        new_teams = [Team(name=bu_name) for bu_name in missing_teams]
        if new_teams:
            Team.objects.bulk_create(new_teams)

        ## If Contact exists, add App to list
        for wayne_uid, contact in contacts_dict.items():
            contact_qs = Contact.objects.filter(
                    name = contact.get("contact_name"),
                    phone = contact.get("contact_phone"),
                    email = contact.get("contact_email"),
                    teams__name = contact.get("contact_team"))
            if contact_qs.exists():
                # if contact exists just try to update app list
                ORMcontact = contact_qs.first()
                ORMcontact.custom_field_data["owned_apps"] = json.dumps(contact.get("owned_apps"))
            else:
                ORMteam = Team.objects.filter(name=contact.get("contact_team")).first()
                ORMcontact = Contact.objects.create(
                    name = contact.get("contact_name"),
                    phone = contact.get("contact_phone"),
                    email = contact.get("contact_email"),
                    )
                ORMcontact.teams.set([ORMteam])
                ORMcontact.custom_field_data["wayne_uid"] = wayne_uid
                ORMcontact.custom_field_data["owned_apps"] = json.dumps(contact.get("owned_apps"))
            try:
                ORMcontact.validated_save()
            except ValidationError:
                self.logger.warning(
                    msg=f"Cannot Load Contact {wayne_uid}. Validation Error.",
                )
                continue            

register_jobs(*jobs, ServiceNowContactSync)
