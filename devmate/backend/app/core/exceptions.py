"""
Custom exception hierarchy for DevMate's ingestion layer

custom exceptions are just classes that inherit from the Exception (or from another exception)
base class. There is no special syntax beyond that - the class body is empty because these two
classes carry no extra data or behavior; they exist purely to be a distinct, catchable 'type' 
of error.
"""

class DocumentLoadError(Exception):
    "Base class: something went wrong turning a file into a document object"


"""
Inheriting from DocumentLoadError means 'except DocumentLoadError:' catches BOTH
this error and its parent. So this is the same as-is relationship that Java hierarchies
rely on, just without the 'throws' keyword
"""
class UnsupportedFileTypeError(DocumentLoadError):
    "A file in docs/ isn't a type of document our loader can process"

