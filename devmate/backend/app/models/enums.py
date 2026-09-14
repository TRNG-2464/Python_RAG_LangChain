"""
DevMate - Northbeam engineering assistant
Day1 - this file holds enumberated types shared across all domain models
"""

'''
this is a milti-line comment
'''

#Enum is Python's version of the Java 'enum' type
from enum import Enum #this is a single line comment; everything after the # is commented out

#class declaration in Python uses the 'class' keyword
class DocumentCategory(str, Enum):
    """
    Inheriting from (str, Enum) means each member IS a string too - 
    DocumentCategory.RUNBOOK == "Runbook" evaluates to true.
    """
    RUNBOOK = "Runbook"
    WIKI = "Wiki"
    POSTMORTEM = "Postmortem"
    ONBOARDING = "Onboarding"

class TicketPriority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

class TicketStatus(str, Enum):
    OPEN = "Open"
    IN_PROGRESS = "In-Progress"
    RESOLVED = "Resolved"
    CLOSED = "Closed"