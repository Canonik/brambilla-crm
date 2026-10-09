"""Default HubSpot-like state: object types, properties, pipelines, association types."""
import json

from . import db
from .util import now_iso

# ---------------------------------------------------------------- object types
OBJECT_TYPES = {
    "contacts": {"id": "0-1", "singular": "contact", "search": ["firstname", "lastname", "email", "phone", "company"], "created": "createdate", "modified": "lastmodifieddate"},
    "companies": {"id": "0-2", "singular": "company", "search": ["name", "domain", "city", "state", "partita_iva"], "created": "createdate", "modified": "hs_lastmodifieddate"},
    "deals": {"id": "0-3", "singular": "deal", "search": ["dealname"], "created": "createdate", "modified": "hs_lastmodifieddate"},
    "tickets": {"id": "0-5", "singular": "ticket", "search": ["subject", "content"], "created": "createdate", "modified": "hs_lastmodifieddate"},
    "products": {"id": "0-7", "singular": "product", "search": ["name", "hs_sku", "description"], "created": "createdate", "modified": "hs_lastmodifieddate"},
    "line_items": {"id": "0-8", "singular": "line_item", "search": ["name", "hs_sku"], "created": "createdate", "modified": "hs_lastmodifieddate"},
    "quotes": {"id": "0-14", "singular": "quote", "search": ["hs_title"], "created": "hs_createdate", "modified": "hs_lastmodifieddate"},
    "notes": {"id": "0-46", "singular": "note", "search": ["hs_note_body"], "created": "hs_createdate", "modified": "hs_lastmodifieddate"},
    "calls": {"id": "0-48", "singular": "call", "search": ["hs_call_body", "hs_call_title"], "created": "hs_createdate", "modified": "hs_lastmodifieddate"},
    "emails": {"id": "0-49", "singular": "email", "search": ["hs_email_text", "hs_email_subject"], "created": "hs_createdate", "modified": "hs_lastmodifieddate"},
    "meetings": {"id": "0-47", "singular": "meeting", "search": ["hs_meeting_body", "hs_meeting_title"], "created": "hs_createdate", "modified": "hs_lastmodifieddate"},
    "tasks": {"id": "0-27", "singular": "task", "search": ["hs_task_subject", "hs_task_body"], "created": "hs_createdate", "modified": "hs_lastmodifieddate"},
    "communications": {"id": "0-18", "singular": "communication", "search": ["hs_communication_body"], "created": "hs_createdate", "modified": "hs_lastmodifieddate"},
    "postal_mail": {"id": "0-116", "singular": "postal_mail", "search": ["hs_postal_mail_body"], "created": "hs_createdate", "modified": "hs_lastmodifieddate"},
}
ACTIVITY_TYPES = {"notes", "calls", "emails", "meetings", "tasks", "communications", "postal_mail"}

_ALIASES: dict[str, str] = {}
for _k, _v in OBJECT_TYPES.items():
    _ALIASES[_k] = _k
    _ALIASES[_v["singular"]] = _k
    _ALIASES[_v["id"]] = _k
_ALIASES.update({"company": "companies", "contact": "contacts", "deal": "deals", "ticket": "tickets", "product": "products", "line_item": "line_items", "lineitem": "line_items", "line-items": "line_items", "note": "notes", "call": "calls", "email": "emails", "meeting": "meetings", "task": "tasks"})


def resolve_type(name: str) -> str | None:
    if name is None:
        return None
    return _ALIASES.get(name.strip().lower())


def type_id(name: str) -> str:
    return OBJECT_TYPES[name]["id"]


# ---------------------------------------------------------------- properties
def _p(name, label, type_, field_type, group, *, options=None, unique=False, read_only=False, hidden=False, calculated=False, description=""):
    return {
        "name": name, "label": label, "type": type_, "fieldType": field_type, "description": description,
        "groupName": group, "options": options or [], "displayOrder": -1, "calculated": calculated, "externalOptions": False,
        "hasUniqueValue": unique, "hidden": hidden, "hubspotDefined": True, "formField": False,
        "modificationMetadata": {"archivable": True, "readOnlyDefinition": True, "readOnlyValue": read_only or calculated},
        "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z", "archived": False,
    }


def _opts(*vals):
    return [{"label": v[0], "value": v[1], "displayOrder": i, "hidden": False} for i, v in enumerate(vals)]


LIFECYCLE_OPTIONS = _opts(("Subscriber", "subscriber"), ("Lead", "lead"), ("Marketing Qualified Lead", "marketingqualifiedlead"), ("Sales Qualified Lead", "salesqualifiedlead"), ("Opportunity", "opportunity"), ("Customer", "customer"), ("Evangelist", "evangelist"), ("Other", "other"))
PRIORITY_OPTIONS = _opts(("Low", "LOW"), ("Medium", "MEDIUM"), ("High", "HIGH"), ("Urgent", "URGENT"))
CURRENCY_OPTIONS = _opts(("EUR", "EUR"), ("USD", "USD"), ("GBP", "GBP"), ("CHF", "CHF"))
TASK_STATUS_OPTIONS = _opts(("Not started", "NOT_STARTED"), ("In progress", "IN_PROGRESS"), ("Waiting", "WAITING"), ("Completed", "COMPLETED"), ("Deferred", "DEFERRED"))
TASK_PRIORITY_OPTIONS = _opts(("Low", "LOW"), ("Medium", "MEDIUM"), ("High", "HIGH"))
TASK_TYPE_OPTIONS = _opts(("Call", "CALL"), ("Email", "EMAIL"), ("To-do", "TODO"))

_SYS = lambda created, modified: [  # noqa: E731
    _p(created, "Create Date", "datetime", "date", "contactinformation" if created == "createdate" else "activity", read_only=True),
    _p(modified, "Last Modified Date", "datetime", "date", "contactinformation" if created == "createdate" else "activity", read_only=True),
    _p("hs_object_id", "Record ID", "number", "number", "contactinformation" if created == "createdate" else "activity", read_only=True),
    _p("hubspot_owner_id", "Owner", "enumeration", "select", "contactinformation" if created == "createdate" else "activity"),
    _p("hs_created_by_user_id", "Created by user ID", "number", "number", "activity", read_only=True),
    _p("hs_updated_by_user_id", "Updated by user ID", "number", "number", "activity", read_only=True),
]

DEFAULT_PROPERTIES: dict[str, list[dict]] = {
    "contacts": [
        _p("email", "Email", "string", "text", "contactinformation"),
        _p("hs_additional_emails", "Additional email addresses", "enumeration", "checkbox", "contactinformation"),
        _p("firstname", "First Name", "string", "text", "contactinformation"),
        _p("lastname", "Last Name", "string", "text", "contactinformation"),
        _p("phone", "Phone Number", "string", "phonenumber", "contactinformation"),
        _p("mobilephone", "Mobile Phone Number", "string", "phonenumber", "contactinformation"),
        _p("company", "Company Name", "string", "text", "contactinformation"),
        _p("jobtitle", "Job Title", "string", "text", "contactinformation"),
        _p("website", "Website URL", "string", "text", "contactinformation"),
        _p("address", "Street Address", "string", "text", "contactinformation"),
        _p("city", "City", "string", "text", "contactinformation"),
        _p("state", "State/Region", "string", "text", "contactinformation"),
        _p("zip", "Postal Code", "string", "text", "contactinformation"),
        _p("country", "Country/Region", "string", "text", "contactinformation"),
        _p("lifecyclestage", "Lifecycle Stage", "enumeration", "radio", "contactinformation", options=LIFECYCLE_OPTIONS),
        _p("hs_lead_status", "Lead Status", "enumeration", "radio", "contactinformation", options=_opts(("New", "NEW"), ("Open", "OPEN"), ("In progress", "IN_PROGRESS"), ("Open deal", "OPEN_DEAL"), ("Unqualified", "UNQUALIFIED"), ("Attempted to contact", "ATTEMPTED_TO_CONTACT"), ("Connected", "CONNECTED"), ("Bad timing", "BAD_TIMING"))),
        _p("associatedcompanyid", "Primary Associated Company ID", "number", "number", "contactinformation", read_only=True),
        _p("hs_email_domain", "Email Domain", "string", "text", "contactinformation", read_only=True),
        _p("notes_last_updated", "Last Activity Date", "datetime", "date", "contactinformation", read_only=True),
        _p("hs_full_name_or_email", "Full name or email", "string", "text", "contactinformation", read_only=True),
        *_SYS("createdate", "lastmodifieddate"),
    ],
    "companies": [
        _p("name", "Company name", "string", "text", "companyinformation"),
        _p("domain", "Company Domain Name", "string", "text", "companyinformation"),
        _p("hs_additional_domains", "Additional Domains", "enumeration", "checkbox", "companyinformation"),
        _p("website", "Website URL", "string", "text", "companyinformation"),
        _p("phone", "Phone Number", "string", "phonenumber", "companyinformation"),
        _p("address", "Street Address", "string", "text", "companyinformation"),
        _p("city", "City", "string", "text", "companyinformation"),
        _p("state", "State/Region", "string", "text", "companyinformation"),
        _p("zip", "Postal Code", "string", "text", "companyinformation"),
        _p("country", "Country/Region", "string", "text", "companyinformation"),
        _p("industry", "Industry", "string", "text", "companyinformation"),
        _p("description", "Description", "string", "textarea", "companyinformation"),
        _p("type", "Type", "enumeration", "select", "companyinformation", options=_opts(("Prospect", "PROSPECT"), ("Partner", "PARTNER"), ("Reseller", "RESELLER"), ("Vendor", "VENDOR"), ("Other", "OTHER"))),
        _p("numberofemployees", "Number of Employees", "number", "number", "companyinformation"),
        _p("annualrevenue", "Annual Revenue", "number", "number", "companyinformation"),
        _p("lifecyclestage", "Lifecycle Stage", "enumeration", "radio", "companyinformation", options=LIFECYCLE_OPTIONS),
        _p("num_associated_contacts", "Number of Associated Contacts", "number", "number", "companyinformation", read_only=True),
        *_SYS("createdate", "hs_lastmodifieddate"),
    ],
    "deals": [
        _p("dealname", "Deal Name", "string", "text", "dealinformation"),
        _p("amount", "Amount", "number", "number", "dealinformation"),
        _p("deal_currency_code", "Currency", "enumeration", "select", "dealinformation", options=CURRENCY_OPTIONS),
        _p("closedate", "Close Date", "datetime", "date", "dealinformation"),
        _p("dealstage", "Deal Stage", "enumeration", "radio", "dealinformation"),
        _p("pipeline", "Pipeline", "enumeration", "radio", "dealinformation"),
        _p("dealtype", "Deal Type", "enumeration", "radio", "dealinformation", options=_opts(("New Business", "newbusiness"), ("Existing Business", "existingbusiness"))),
        _p("description", "Deal Description", "string", "textarea", "dealinformation"),
        _p("hs_priority", "Priority", "enumeration", "select", "dealinformation", options=_opts(("Low", "low"), ("Medium", "medium"), ("High", "high"))),
        _p("hs_deal_stage_probability", "Deal probability", "number", "number", "dealinformation", read_only=True),
        _p("hs_is_closed", "Is Deal Closed?", "bool", "booleancheckbox", "dealinformation", read_only=True),
        _p("hs_is_closed_won", "Is Closed Won", "bool", "booleancheckbox", "dealinformation", read_only=True),
        _p("hs_is_closed_lost", "Is closed lost", "bool", "booleancheckbox", "dealinformation", read_only=True),
        _p("hs_closed_amount", "Closed Amount", "number", "number", "dealinformation", read_only=True),
        _p("amount_in_home_currency", "Amount in company currency", "number", "number", "dealinformation", read_only=True),
        _p("num_associated_contacts", "Number of Associated Contacts", "number", "number", "dealinformation", read_only=True),
        _p("hs_closed_won_date", "Closed Won Date", "datetime", "date", "dealinformation", read_only=True),
        _p("hs_closed_lost_date", "Closed Lost Date", "datetime", "date", "dealinformation", read_only=True),
        *_SYS("createdate", "hs_lastmodifieddate"),
    ],
    "tickets": [
        _p("subject", "Ticket name", "string", "text", "ticketinformation"),
        _p("content", "Ticket description", "string", "textarea", "ticketinformation"),
        _p("hs_pipeline", "Pipeline", "enumeration", "select", "ticketinformation"),
        _p("hs_pipeline_stage", "Ticket status", "enumeration", "select", "ticketinformation"),
        _p("hs_ticket_priority", "Priority", "enumeration", "select", "ticketinformation", options=PRIORITY_OPTIONS),
        _p("hs_ticket_category", "Category", "enumeration", "checkbox", "ticketinformation", options=_opts(("Product issue", "PRODUCT_ISSUE"), ("Billing issue", "BILLING_ISSUE"), ("Feature request", "FEATURE_REQUEST"), ("General inquiry", "GENERAL_INQUIRY"))),
        _p("closed_date", "Close date", "datetime", "date", "ticketinformation"),
        _p("source_type", "Source", "enumeration", "select", "ticketinformation", options=_opts(("Chat", "CHAT"), ("Email", "EMAIL"), ("Form", "FORM"), ("Phone", "PHONE"))),
        _p("hs_resolution", "Resolution", "enumeration", "select", "ticketinformation"),
        _p("hs_ticket_id", "Ticket ID", "number", "number", "ticketinformation", read_only=True),
        _p("hs_num_associated_contacts", "Number of Associated Contacts", "number", "number", "ticketinformation", read_only=True),
        *_SYS("createdate", "hs_lastmodifieddate"),
    ],
    "products": [
        _p("name", "Name", "string", "text", "productinformation"),
        _p("description", "Description", "string", "textarea", "productinformation"),
        _p("price", "Unit price", "number", "number", "productinformation"),
        _p("hs_sku", "SKU", "string", "text", "productinformation"),
        _p("hs_cost_of_goods_sold", "Unit cost", "number", "number", "productinformation"),
        _p("hs_recurring_billing_period", "Term", "string", "text", "productinformation"),
        _p("hs_product_type", "Product Type", "enumeration", "select", "productinformation", options=_opts(("Inventory", "inventory"), ("Non-inventory", "non-inventory"), ("Service", "service"))),
        _p("hs_unit", "Unit", "string", "text", "productinformation"),
        *_SYS("createdate", "hs_lastmodifieddate"),
    ],
    "line_items": [
        _p("name", "Name", "string", "text", "lineiteminformation"),
        _p("description", "Description", "string", "textarea", "lineiteminformation"),
        _p("quantity", "Quantity", "number", "number", "lineiteminformation"),
        _p("price", "Unit price", "number", "number", "lineiteminformation"),
        _p("amount", "Net price", "number", "number", "lineiteminformation", read_only=True),
        _p("discount", "Unit discount", "number", "number", "lineiteminformation"),
        _p("hs_discount_percentage", "Discount percentage", "number", "number", "lineiteminformation"),
        _p("hs_total_discount", "Total discount", "number", "number", "lineiteminformation", read_only=True),
        _p("hs_product_id", "Product ID", "number", "number", "lineiteminformation"),
        _p("hs_sku", "SKU", "string", "text", "lineiteminformation"),
        _p("hs_line_item_currency_code", "Currency", "enumeration", "select", "lineiteminformation", options=CURRENCY_OPTIONS),
        _p("hs_position_on_quote", "Position on quote", "number", "number", "lineiteminformation"),
        *_SYS("createdate", "hs_lastmodifieddate"),
    ],
    "quotes": [
        _p("hs_title", "Quote name", "string", "text", "quoteinformation"),
        _p("hs_expiration_date", "Expiration date", "datetime", "date", "quoteinformation"),
        _p("hs_status", "Quote status", "enumeration", "select", "quoteinformation", options=_opts(("Draft", "DRAFT"), ("Pending approval", "PENDING_APPROVAL"), ("Approved", "APPROVED"), ("Rejected", "REJECTED"))),
        _p("hs_quote_amount", "Quote amount", "number", "number", "quoteinformation", read_only=True),
        _p("hs_currency", "Currency", "enumeration", "select", "quoteinformation", options=CURRENCY_OPTIONS),
        *_SYS("hs_createdate", "hs_lastmodifieddate"),
    ],
    "notes": [
        _p("hs_note_body", "Note body", "string", "html", "note"),
        _p("hs_timestamp", "Activity date", "datetime", "date", "note"),
        _p("hs_attachment_ids", "Attached file IDs", "enumeration", "checkbox", "note"),
        *_SYS("hs_createdate", "hs_lastmodifieddate"),
    ],
    "calls": [
        _p("hs_call_body", "Call notes", "string", "html", "call"),
        _p("hs_call_title", "Call Title", "string", "text", "call"),
        _p("hs_call_duration", "Call duration", "number", "number", "call"),
        _p("hs_call_direction", "Call direction", "enumeration", "select", "call", options=_opts(("Inbound", "INBOUND"), ("Outbound", "OUTBOUND"))),
        _p("hs_call_status", "Call status", "enumeration", "select", "call", options=_opts(("Busy", "BUSY"), ("Calling CRM user", "CALLING_CRM_USER"), ("Canceled", "CANCELED"), ("Completed", "COMPLETED"), ("Connecting", "CONNECTING"), ("Failed", "FAILED"), ("In progress", "IN_PROGRESS"), ("Missed", "MISSED"), ("No answer", "NO_ANSWER"), ("Queued", "QUEUED"), ("Ringing", "RINGING"))),
        _p("hs_call_disposition", "Call outcome", "string", "text", "call"),
        _p("hs_call_from_number", "From number", "string", "text", "call"),
        _p("hs_call_to_number", "To number", "string", "text", "call"),
        _p("hs_call_recording_url", "Recording URL", "string", "text", "call"),
        _p("hs_timestamp", "Activity date", "datetime", "date", "call"),
        *_SYS("hs_createdate", "hs_lastmodifieddate"),
    ],
    "emails": [
        _p("hs_email_text", "Email body", "string", "textarea", "email"),
        _p("hs_email_html", "Email HTML", "string", "html", "email"),
        _p("hs_email_subject", "Subject", "string", "text", "email"),
        _p("hs_email_direction", "Direction", "enumeration", "select", "email", options=_opts(("Email", "EMAIL"), ("Incoming email", "INCOMING_EMAIL"), ("Forwarded email", "FORWARDED_EMAIL"))),
        _p("hs_email_status", "Status", "enumeration", "select", "email", options=_opts(("Bounced", "BOUNCED"), ("Failed", "FAILED"), ("Scheduled", "SCHEDULED"), ("Sending", "SENDING"), ("Sent", "SENT"))),
        _p("hs_email_headers", "Headers", "string", "text", "email"),
        _p("hs_timestamp", "Activity date", "datetime", "date", "email"),
        *_SYS("hs_createdate", "hs_lastmodifieddate"),
    ],
    "meetings": [
        _p("hs_meeting_body", "Meeting description", "string", "html", "meeting"),
        _p("hs_meeting_title", "Meeting title", "string", "text", "meeting"),
        _p("hs_internal_meeting_notes", "Internal notes", "string", "html", "meeting"),
        _p("hs_meeting_location", "Location", "string", "text", "meeting"),
        _p("hs_meeting_start_time", "Start time", "datetime", "date", "meeting"),
        _p("hs_meeting_end_time", "End time", "datetime", "date", "meeting"),
        _p("hs_meeting_outcome", "Outcome", "enumeration", "select", "meeting", options=_opts(("Scheduled", "SCHEDULED"), ("Completed", "COMPLETED"), ("Rescheduled", "RESCHEDULED"), ("No show", "NO_SHOW"), ("Canceled", "CANCELED"))),
        _p("hs_timestamp", "Activity date", "datetime", "date", "meeting"),
        *_SYS("hs_createdate", "hs_lastmodifieddate"),
    ],
    "tasks": [
        _p("hs_task_subject", "Task title", "string", "text", "task"),
        _p("hs_task_body", "Notes", "string", "html", "task"),
        _p("hs_task_status", "Task status", "enumeration", "select", "task", options=TASK_STATUS_OPTIONS),
        _p("hs_task_priority", "Priority", "enumeration", "select", "task", options=TASK_PRIORITY_OPTIONS),
        _p("hs_task_type", "Task type", "enumeration", "select", "task", options=TASK_TYPE_OPTIONS),
        _p("hs_timestamp", "Due date", "datetime", "date", "task"),
        _p("hs_task_completion_date", "Completion date", "datetime", "date", "task"),
        *_SYS("hs_createdate", "hs_lastmodifieddate"),
    ],
    "communications": [
        _p("hs_communication_body", "Body", "string", "html", "communication"),
        _p("hs_communication_channel_type", "Channel", "enumeration", "select", "communication", options=_opts(("WhatsApp", "WHATS_APP"), ("LinkedIn", "LINKEDIN_MESSAGE"), ("SMS", "SMS"))),
        _p("hs_communication_logged_from", "Logged from", "string", "text", "communication"),
        _p("hs_timestamp", "Activity date", "datetime", "date", "communication"),
        *_SYS("hs_createdate", "hs_lastmodifieddate"),
    ],
    "postal_mail": [
        _p("hs_postal_mail_body", "Body", "string", "html", "postal_mail"),
        _p("hs_timestamp", "Activity date", "datetime", "date", "postal_mail"),
        *_SYS("hs_createdate", "hs_lastmodifieddate"),
    ],
}

READ_ONLY_PROPERTIES = {"hs_object_id", "createdate", "hs_createdate", "lastmodifieddate", "hs_lastmodifieddate", "hs_created_by_user_id", "hs_updated_by_user_id", "hs_deal_stage_probability", "hs_is_closed", "hs_is_closed_won", "hs_is_closed_lost", "hs_closed_amount", "amount_in_home_currency", "num_associated_contacts", "hs_num_associated_contacts", "hs_email_domain", "hs_full_name_or_email", "hs_ticket_id", "hs_closed_won_date", "hs_closed_lost_date", "amount_li", "hs_total_discount", "hs_quote_amount", "notes_last_updated"}

DEFAULT_GROUPS = {
    "contacts": [("contactinformation", "Contact information")],
    "companies": [("companyinformation", "Company information")],
    "deals": [("dealinformation", "Deal information")],
    "tickets": [("ticketinformation", "Ticket information")],
    "products": [("productinformation", "Product information")],
    "line_items": [("lineiteminformation", "Line item information")],
    "quotes": [("quoteinformation", "Quote information")],
    "notes": [("note", "Note"), ("activity", "Activity")],
    "calls": [("call", "Call"), ("activity", "Activity")],
    "emails": [("email", "Email"), ("activity", "Activity")],
    "meetings": [("meeting", "Meeting"), ("activity", "Activity")],
    "tasks": [("task", "Task"), ("activity", "Activity")],
    "communications": [("communication", "Communication"), ("activity", "Activity")],
    "postal_mail": [("postal_mail", "Postal mail"), ("activity", "Activity")],
}

# properties returned when the caller does not ask for specific ones
DEFAULT_RESPONSE_PROPERTIES = {
    "contacts": ["createdate", "email", "firstname", "hs_object_id", "lastmodifieddate", "lastname"],
    "companies": ["createdate", "domain", "hs_lastmodifieddate", "hs_object_id", "name"],
    "deals": ["amount", "closedate", "createdate", "dealname", "dealstage", "hs_lastmodifieddate", "hs_object_id", "pipeline"],
    "tickets": ["content", "createdate", "hs_lastmodifieddate", "hs_object_id", "hs_pipeline", "hs_pipeline_stage", "hs_ticket_category", "hs_ticket_priority", "subject"],
}

# ---------------------------------------------------------------- pipelines
def _stage(id_, label, order, **meta):
    return {"id": id_, "label": label, "displayOrder": order, "metadata": {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in meta.items()}, "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z", "archived": False, "writePermissions": "CRM_PERMISSIONS_ENFORCEMENT"}


def default_pipelines() -> dict[str, list[dict]]:
    deal = {
        "id": "default", "label": "Sales Pipeline", "displayOrder": 0, "archived": False,
        "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
        "stages": [
            _stage("appointmentscheduled", "Appointment Scheduled", 0, isClosed=False, probability=0.2),
            _stage("qualifiedtobuy", "Qualified To Buy", 1, isClosed=False, probability=0.4),
            _stage("presentationscheduled", "Presentation Scheduled", 2, isClosed=False, probability=0.6),
            _stage("decisionmakerboughtin", "Decision Maker Bought-In", 3, isClosed=False, probability=0.8),
            _stage("contractsent", "Contract Sent", 4, isClosed=False, probability=0.9),
            _stage("closedwon", "Closed Won", 5, isClosed=True, probability=1.0),
            _stage("closedlost", "Closed Lost", 6, isClosed=True, probability=0.0),
        ],
    }
    ticket = {
        "id": "0", "label": "Support Pipeline", "displayOrder": 0, "archived": False,
        "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
        "stages": [
            _stage("1", "New", 0, ticketState="OPEN"),
            _stage("2", "Waiting on contact", 1, ticketState="OPEN"),
            _stage("3", "Waiting on us", 2, ticketState="OPEN"),
            _stage("4", "Closed", 3, ticketState="CLOSED"),
        ],
    }
    return {"deals": [deal], "tickets": [ticket]}


# ---------------------------------------------------------------- association types
# (type_id, from, to, label, name, inverse_type_id)
HUBSPOT_ASSOCIATION_TYPES = [
    (1, "contacts", "companies", "Primary", "contact_to_company", 2),
    (2, "companies", "contacts", "Primary", "company_to_contact", 1),
    (279, "contacts", "companies", None, "contact_to_company_unlabeled", 280),
    (280, "companies", "contacts", None, "company_to_contact_unlabeled", 279),
    (3, "deals", "contacts", None, "deal_to_contact", 4),
    (4, "contacts", "deals", None, "contact_to_deal", 3),
    (5, "deals", "companies", "Primary", "deal_to_company", 6),
    (6, "companies", "deals", "Primary", "company_to_deal", 5),
    (341, "deals", "companies", None, "deal_to_company_unlabeled", 342),
    (342, "companies", "deals", None, "company_to_deal_unlabeled", 341),
    (15, "contacts", "tickets", None, "contact_to_ticket", 16),
    (16, "tickets", "contacts", None, "ticket_to_contact", 15),
    (26, "tickets", "companies", "Primary", "ticket_to_company", 25),
    (25, "companies", "tickets", "Primary", "company_to_ticket", 26),
    (339, "tickets", "companies", None, "ticket_to_company_unlabeled", 340),
    (340, "companies", "tickets", None, "company_to_ticket_unlabeled", 339),
    (27, "deals", "tickets", None, "deal_to_ticket", 28),
    (28, "tickets", "deals", None, "ticket_to_deal", 27),
    (19, "deals", "line_items", None, "deal_to_line_item", 20),
    (20, "line_items", "deals", None, "line_item_to_deal", 19),
    (63, "deals", "quotes", None, "deal_to_quote", 64),
    (64, "quotes", "deals", None, "quote_to_deal", 63),
    (67, "quotes", "line_items", None, "quote_to_line_item", 68),
    (68, "line_items", "quotes", None, "line_item_to_quote", 67),
    (449, "contacts", "contacts", None, "contact_to_contact", 449),
    (450, "companies", "companies", None, "company_to_company", 450),
    (451, "deals", "deals", None, "deal_to_deal", 451),
    (452, "tickets", "tickets", None, "ticket_to_ticket", 452),
    (13, "companies", "companies", "Parent Company", "parent_to_child_company", 14),
    (14, "companies", "companies", "Child Company", "child_to_parent_company", 13),
    # line items <-> products (not in HubSpot's public table; kept stable here)
    (901, "line_items", "products", "Product", "line_item_to_product", 902),
    (902, "products", "line_items", "Line item", "product_to_line_item", 901),
    # activities (HubSpot: activity -> object ids are the even ones, e.g. note_to_contact 202)
    (202, "notes", "contacts", None, "note_to_contact", 201), (201, "contacts", "notes", None, "contact_to_note", 202),
    (190, "notes", "companies", None, "note_to_company", 189), (189, "companies", "notes", None, "company_to_note", 190),
    (214, "notes", "deals", None, "note_to_deal", 213), (213, "deals", "notes", None, "deal_to_note", 214),
    (228, "notes", "tickets", None, "note_to_ticket", 227), (227, "tickets", "notes", None, "ticket_to_note", 228),
    (194, "calls", "contacts", None, "call_to_contact", 193), (193, "contacts", "calls", None, "contact_to_call", 194),
    (182, "calls", "companies", None, "call_to_company", 181), (181, "companies", "calls", None, "company_to_call", 182),
    (206, "calls", "deals", None, "call_to_deal", 205), (205, "deals", "calls", None, "deal_to_call", 206),
    (220, "calls", "tickets", None, "call_to_ticket", 219), (219, "tickets", "calls", None, "ticket_to_call", 220),
    (198, "emails", "contacts", None, "email_to_contact", 197), (197, "contacts", "emails", None, "contact_to_email", 198),
    (186, "emails", "companies", None, "email_to_company", 185), (185, "companies", "emails", None, "company_to_email", 186),
    (210, "emails", "deals", None, "email_to_deal", 209), (209, "deals", "emails", None, "deal_to_email", 210),
    (224, "emails", "tickets", None, "email_to_ticket", 223), (223, "tickets", "emails", None, "ticket_to_email", 224),
    (200, "meetings", "contacts", None, "meeting_to_contact", 199), (199, "contacts", "meetings", None, "contact_to_meeting", 200),
    (188, "meetings", "companies", None, "meeting_to_company", 187), (187, "companies", "meetings", None, "company_to_meeting", 188),
    (212, "meetings", "deals", None, "meeting_to_deal", 211), (211, "deals", "meetings", None, "deal_to_meeting", 212),
    (226, "meetings", "tickets", None, "meeting_to_ticket", 225), (225, "tickets", "meetings", None, "ticket_to_meeting", 226),
    (204, "tasks", "contacts", None, "task_to_contact", 203), (203, "contacts", "tasks", None, "contact_to_task", 204),
    (192, "tasks", "companies", None, "task_to_company", 191), (191, "companies", "tasks", None, "company_to_task", 192),
    (216, "tasks", "deals", None, "task_to_deal", 215), (215, "deals", "tasks", None, "deal_to_task", 216),
    (230, "tasks", "tickets", None, "task_to_ticket", 229), (229, "tickets", "tasks", None, "ticket_to_task", 230),
    (82, "communications", "contacts", None, "communication_to_contact", 81), (81, "contacts", "communications", None, "contact_to_communication", 82),
    (88, "communications", "companies", None, "communication_to_company", 87), (87, "companies", "communications", None, "company_to_communication", 88),
    (86, "communications", "deals", None, "communication_to_deal", 85), (85, "deals", "communications", None, "deal_to_communication", 86),
    (84, "communications", "tickets", None, "communication_to_ticket", 83), (83, "tickets", "communications", None, "ticket_to_communication", 84),
    (454, "postal_mail", "contacts", None, "postal_mail_to_contact", 453), (453, "contacts", "postal_mail", None, "contact_to_postal_mail", 454),
    (460, "postal_mail", "companies", None, "postal_mail_to_company", 459), (459, "companies", "postal_mail", None, "company_to_postal_mail", 460),
    (458, "postal_mail", "deals", None, "postal_mail_to_deal", 457), (457, "deals", "postal_mail", None, "deal_to_postal_mail", 458),
    (456, "postal_mail", "tickets", None, "postal_mail_to_ticket", 455), (455, "tickets", "postal_mail", None, "ticket_to_postal_mail", 456),
    (69, "quotes", "contacts", None, "quote_to_contact", 70), (70, "contacts", "quotes", None, "contact_to_quote", 69),
    (71, "quotes", "companies", None, "quote_to_company", 72), (72, "companies", "quotes", None, "company_to_quote", 71),
]
ASSOC_BY_ID = {t[0]: t for t in HUBSPOT_ASSOCIATION_TYPES}
# default (unlabeled) type for a pair
DEFAULT_ASSOC: dict[tuple[str, str], int] = {}
PRIMARY_ASSOC: dict[tuple[str, str], int] = {}
for _t in HUBSPOT_ASSOCIATION_TYPES:
    key = (_t[1], _t[2])
    if _t[3] is None and key not in DEFAULT_ASSOC:
        DEFAULT_ASSOC[key] = _t[0]
    if _t[3] == "Primary":
        PRIMARY_ASSOC[key] = _t[0]
for _t in HUBSPOT_ASSOCIATION_TYPES:
    key = (_t[1], _t[2])
    if key not in DEFAULT_ASSOC:
        DEFAULT_ASSOC[key] = _t[0]


def default_type_id(from_type: str, to_type: str) -> int | None:
    return DEFAULT_ASSOC.get((from_type, to_type))


def inverse_type_id(type_id: int) -> int | None:
    t = ASSOC_BY_ID.get(type_id)
    return t[5] if t else None


# ---------------------------------------------------------------- bootstrap
def ensure_defaults(conn=None, *, reset: bool = False) -> None:
    """Seed missing defaults at startup; replace metadata only for an explicit reset."""
    if conn is None:
        with db.connection() as c:
            ensure_defaults(c, reset=reset)
            c.commit()
        return
    ts = now_iso()
    rows = []
    for ot, props in DEFAULT_PROPERTIES.items():
        for p in props:
            d = dict(p)
            d["createdAt"] = ts
            d["updatedAt"] = ts
            rows.append((ot, p["name"], json.dumps(d)))
    if reset:
        conn.execute("DELETE FROM properties")
    conn.cursor().executemany("INSERT INTO properties (object_type, name, definition) VALUES (%s, %s, %s::jsonb) ON CONFLICT (object_type, name) DO NOTHING", rows)
    grows = []
    for ot, groups in DEFAULT_GROUPS.items():
        for i, (name, label) in enumerate(groups):
            grows.append((ot, name, json.dumps({"name": name, "label": label, "displayOrder": i, "archived": False})))
    if reset:
        conn.execute("DELETE FROM property_groups")
    conn.cursor().executemany("INSERT INTO property_groups (object_type, name, definition) VALUES (%s, %s, %s::jsonb) ON CONFLICT (object_type, name) DO NOTHING", grows)
    if reset:
        conn.execute("DELETE FROM pipelines")
    for ot, pls in default_pipelines().items():
        for pl in pls:
            pl = json.loads(json.dumps(pl))
            pl["createdAt"] = ts
            pl["updatedAt"] = ts
            for s in pl["stages"]:
                s["createdAt"] = ts
                s["updatedAt"] = ts
            conn.execute("INSERT INTO pipelines (object_type, id, definition) VALUES (%s, %s, %s::jsonb) ON CONFLICT (object_type, id) DO NOTHING", (ot, pl["id"], json.dumps(pl)))
    if reset:
        conn.execute("DELETE FROM association_labels")
    conn.cursor().executemany(
        "INSERT INTO association_labels (type_id, from_type, to_type, label, name, category, inverse_type_id) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (type_id) DO NOTHING",
        [(t[0], t[1], t[2], t[3], t[4], "USER_DEFINED" if t[0] in (901, 902) else "HUBSPOT_DEFINED", t[5]) for t in HUBSPOT_ASSOCIATION_TYPES],
    )
