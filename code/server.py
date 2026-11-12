from mcp.server.fastmcp import FastMCP
from metadataExtraction import extract_metadata
from config import pdftest_path

mcp = FastMCP("pdf-tools")

@mcp.tool()
def analyze_pdf_metadata() -> dict:
    """Extract internal metadata, fonts, images, annotations, syntax and
    attachment info from the currently selected bank-statement PDF."""
    return extract_metadata(pdftest_path)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")