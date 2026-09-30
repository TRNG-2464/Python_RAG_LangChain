from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

# How do we use a pydantic model
class Book(BaseModel):
    isbn: str = Field(description="This is the ISBN number for the book, and should fit the format of an ISBN: 978-0201633610")
    title: str = Field(description="This is the title string for the book, it should follow book titling rules")
    description: str = Field(description="This is a description of the book")
