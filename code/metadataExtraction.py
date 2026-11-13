"""
Extracts forensic metadata from a PDF and saves it as JSON.

Sections collected: Document Info, XMP consistency, fonts, images,
annotations, file syntax and attachments. Anything unusual is added
to the "flags" list. The JSON is what will eventually be given to the AI.
"""

import json
import os
import re

from collections import Counter

import pikepdf

from config import pdftest_path  # Provides the test PDF for direct execution.


# --------------------------------------------------
# File paths
# --------------------------------------------------

# Build paths from this file's location so the working folder does not matter.
script_dir = os.path.dirname(os.path.abspath(__file__))

output_path = os.path.join(script_dir, "..", "AI_data", "pdf_analysis.json")

# --------------------------------------------------
# Small helper functions
# --------------------------------------------------

def clean_value(value):
    """Convert pikepdf values into Python values that can be saved as JSON."""

    # Preserve missing values rather than turning them into the text "None".
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    # Clean each item because collections may contain PDF-specific objects.
    if isinstance(value, (list, tuple, pikepdf.Array)):
        return [clean_value(item) for item in value]

    # Use text for objects that JSON cannot store directly.
    return str(value)


def normalize_font_name(font_name):
    """
    Remove PDF formatting from a font name.
    Example: /ABCDEF+Arial-BoldMT -> Arial-BoldMT
    """

    if font_name is None:
        return None

    # PDF name formatting is not part of the actual font name.
    font_name = str(font_name).replace("/", "")

    # Subset prefixes can differ even when pages use the same underlying font.
    return re.sub(r"^[A-Z]{6}\+", "", font_name)


def optional_int(value):
    """Return int(value), or None when the value is missing."""

    # Keep missing dimensions distinct from a recorded dimension of zero.
    return int(value) if value is not None else None


def compare_metadata(docinfo_value, xmp_value):
    """
    Compare a Document Info value with the same field from XMP.
    Returns: "match", "mismatch" or "missing"
    """

    # Missing evidence is different from two recorded values disagreeing.
    if docinfo_value is None or xmp_value is None:
        return "missing"

    docinfo_value = clean_value(docinfo_value)
    xmp_value = clean_value(xmp_value)

    # XMP may list several authors, so check whether the Document Info author appears.
    if isinstance(xmp_value, list):
        if str(docinfo_value) in [str(value) for value in xmp_value]:
            return "match"

        return "mismatch"

    # Ignore surrounding spaces so harmless formatting does not cause a mismatch.
    if str(docinfo_value).strip() == str(xmp_value).strip():
        return "match"

    return "mismatch"


def summarize_page_pattern(pattern_by_page):
    """
    Find the most common pattern across pages (a font set, an image count...).

    Args:
        pattern_by_page: dict of page number -> that page's pattern

    Returns:
        (most_common_pattern, pages_with_it, pages_without_it, has_majority)
        has_majority is True when more than half of the pages share the pattern.
    """

    counts = Counter(pattern_by_page.values())
    most_common, frequency = counts.most_common(1)[0]

    normal_pages = [
        page for page, pattern in pattern_by_page.items()
        if pattern == most_common
    ]

    different_pages = [
        page for page, pattern in pattern_by_page.items()
        if pattern != most_common
    ]

    # The most frequent pattern is not necessarily shared by a majority.
    has_majority = frequency > len(pattern_by_page) / 2

    return most_common, normal_pages, different_pages, has_majority


def create_analysis_structure():
    """Empty version of the final structure that will be given to the AI."""

    # Keep the same output sections even when some evidence is unavailable.
    # Flags identify findings for review; they do not establish forgery.
    return {
        "metadata": {},
        "xmp_consistency": {},
        "fonts": {
            "pages": {},
            "cross_page_analysis": {}
        },
        "images": {
            "pages": {},
            "cross_page_analysis": {}
        },
        "annotations": {
            "pages": {}
        },
        "syntax": {},
        "attachments": {},
        "flags": []
    }


# --------------------------------------------------
# 1. Document Info metadata
# --------------------------------------------------

def extract_doc_info(pdf, analysis):
    docinfo = pdf.docinfo

    # Preserve recorded values for comparison without treating them as verified facts.
    analysis["metadata"] = {
        "creation_date": clean_value(docinfo.get("/CreationDate")),
        "modification_date": clean_value(docinfo.get("/ModDate")),
        "creator": clean_value(docinfo.get("/Creator")),
        "producer": clean_value(docinfo.get("/Producer")),
        "author": clean_value(docinfo.get("/Author"))
    }


# --------------------------------------------------
# 2. XMP consistency
# --------------------------------------------------

def extract_xmp_metadata(pdf):
    xmp = pdf.open_metadata()

    # An empty result lets later comparisons report missing XMP evidence.
    if not xmp:
        return {}

    # Use the same field names as Document Info to simplify comparison.
    return {
        "creation_date": clean_value(xmp.get("xmp:CreateDate")),
        "modification_date": clean_value(xmp.get("xmp:ModifyDate")),
        "creator": clean_value(xmp.get("xmp:CreatorTool")),
        "producer": clean_value(xmp.get("pdf:Producer")),
        "author": clean_value(xmp.get("dc:creator"))
    }


def compare_docinfo_with_xmp(xmp_values, analysis):
    # Skip dates until both formats are converted to a common representation.
    # Different date strings can describe the same moment.
    fields_to_compare = ("creator", "producer", "author")

    comparisons = {
        field: compare_metadata(analysis["metadata"][field], xmp_values.get(field))
        for field in fields_to_compare
    }

    # Keep the source values so reported differences can be inspected.
    analysis["xmp_consistency"] = {
        "xmp_metadata": xmp_values,
        "comparisons": comparisons
    }

    for field, result in comparisons.items():
        # Flag disagreement, not the absence of an optional metadata field.
        if result == "mismatch":
            analysis["flags"].append({
                "category": "metadata",
                "type": "xmp_mismatch",
                "field": field,
                "evidence": f"Document Info and XMP values differ for {field}"
            })

    return comparisons


# --------------------------------------------------
# 3. Fonts
# --------------------------------------------------

def collect_fonts(resources, visited=None):
    """
    Find font resources.

    Also checks inside Form XObjects because some PDF content
    can be stored inside them.
    """

    # Create a separate tracking set for each initial call.
    if visited is None:
        visited = set()

    fonts_found = []

    if resources is None:
        return fonts_found

    font_resources = resources.get("/Font")

    if font_resources:
        for font_object in font_resources.values():
            fonts_found.append({
                "Font": normalize_font_name(font_object.get("/BaseFont")),
            })

    # Forms can contain fonts that are absent from the page's main resource list.
    xobjects = resources.get("/XObject")

    if xobjects:
        for xobject in xobjects.values():
            if str(xobject.get("/Subtype")) != "/Form":
                continue

            # Avoid repeated work and circular references between nested forms.
            object_id = xobject.objgen

            if object_id in visited:
                continue

            visited.add(object_id)

            fonts_found.extend(
                collect_fonts(xobject.get("/Resources"), visited)
            )

    return fonts_found


def remove_duplicate_fonts(fonts):
    """Remove duplicate fonts on the same page. Returns {font name: font record}."""

    unique_fonts = {}

    for font in fonts:
        font_name = font["Font"]

        # Count each named font once, even if several resources refer to it.
        if font_name:
            unique_fonts[font_name] = font

    return unique_fonts


def extract_fonts(pdf, analysis):
    font_usage = {}
    font_sets = {}

    for page_num, page in enumerate(pdf.pages, start=1):
        unique_fonts = remove_duplicate_fonts(collect_fonts(page.resources))
        font_list = list(unique_fonts.values())

        # Report resource findings without claiming every listed font is visibly used.
        analysis["fonts"]["pages"][str(page_num)] = {
            "status": (
                "font_resources_found"
                if font_list
                else "no_named_font_resources_found"
            ),
            "font_count": len(font_list),
            "fonts": font_list
        }

        # Keep page references so unusual fonts can be located.
        for font_name in unique_fonts:
            font_usage.setdefault(font_name, []).append(page_num)

        # Sort names so resource order does not affect comparisons.
        # Exclude pages without named fonts from this particular comparison.
        if unique_fonts:
            font_sets[page_num] = tuple(sorted(unique_fonts))

    if not font_sets:
        analysis["fonts"]["cross_page_analysis"] = {
            "status": "no_named_font_resources_found"
        }
        return

    most_common_fonts, normal_pages, different_pages, has_majority = (
        summarize_page_pattern(font_sets)
    )

    analysis["fonts"]["cross_page_analysis"] = {
        "font_usage": {
            name: {"page_count": len(pages), "pages": pages}
            for name, pages in font_usage.items()
        },
        "most_common_font_set": list(most_common_fonts),
        "pages_using_most_common_font_set": normal_pages,
        "pages_with_different_font_set": different_pages
    }

    # Flag differences only when a majority of the compared pages share one pattern.
    if has_majority:
        common_fonts = set(most_common_fonts)

        for page_num in different_pages:
            page_fonts = set(font_sets[page_num])

            # Show the exact differences so the reviewer can assess their significance.
            analysis["flags"].append({
                "category": "fonts",
                "page": page_num,
                "type": "font_pattern_difference",
                "unexpected_fonts": sorted(page_fonts - common_fonts),
                "missing_common_fonts": sorted(common_fonts - page_fonts),
                "evidence": (
                    f"Page {page_num} has a different font resource pattern "
                    "from the majority of pages with named fonts."
                )
            })


# --------------------------------------------------
# 4. Images
# --------------------------------------------------

def extract_images(pdf, analysis):
    image_counts = {}

    for page_num, page in enumerate(pdf.pages, start=1):
        # Use an empty collection when no images are returned.
        images = page.get_images() or {}

        # Keep dimensions as context for reviewing differences in page images.
        image_list = [
            {
                "name": str(image_name),
                "width": optional_int(image_object.get("/Width")),
                "height": optional_int(image_object.get("/Height"))
            }
            for image_name, image_object in images.items()
        ]

        image_counts[page_num] = len(image_list)

        analysis["images"]["pages"][str(page_num)] = {
            "image_count": len(image_list),
            "images": image_list
        }

    # Avoid requesting a most-common value from an empty collection.
    if not image_counts:
        analysis["images"]["cross_page_analysis"] = {
            "status": "no_pages_found"
        }
        return

    common_count, normal_pages, different_pages, has_majority = (
        summarize_page_pattern(image_counts)
    )

    analysis["images"]["cross_page_analysis"] = {
        "most_common_image_count": common_count,
        "pages_with_most_common_image_count": normal_pages,
        "pages_with_different_image_count": different_pages
    }

    # Require a majority before treating a different image count as an exception.
    if has_majority:
        for page_num in different_pages:
            analysis["flags"].append({
                "category": "images",
                "page": page_num,
                "type": "image_count_difference",
                "evidence": (
                    f"Page {page_num} contains {image_counts[page_num]} "
                    f"image object(s); the most common count is {common_count}."
                )
            })


# --------------------------------------------------
# 5. Annotations
# --------------------------------------------------

def extract_annotations(pdf, analysis):
    for page_num, page in enumerate(pdf.pages, start=1):
        annotations = page.obj.get("/Annots")

        # Keep type and location so annotations can be checked on the page.
        annotation_list = [
            {
                "type": clean_value(annotation.get("/Subtype")),
                "rectangle": clean_value(annotation.get("/Rect"))
            }
            for annotation in annotations or []
        ]

        analysis["annotations"]["pages"][str(page_num)] = {
            "annotation_count": len(annotation_list),
            "annotations": annotation_list
        }

        # Annotations deserve inspection, but may simply be links or other normal features.
        if annotation_list:
            analysis["flags"].append({
                "category": "annotations",
                "page": page_num,
                "type": "annotations_present",
                "evidence": (
                    f"Page {page_num} contains "
                    f"{len(annotation_list)} annotation(s)."
                )
            })


# --------------------------------------------------
# 6. Syntax
# --------------------------------------------------

def extract_syntax(pdf, pdf_path, analysis):
    # Read the original bytes because marker counts concern the saved file structure.
    with open(pdf_path, "rb") as file:
        raw_pdf = file.read()

    eof_count = raw_pdf.count(b"%%EOF")

    analysis["syntax"] = {
        "pdf_version": str(pdf.pdf_version),
        "number_of_pages": len(pdf.pages),
        "encrypted": pdf.is_encrypted,
        "eof_marker_count": eof_count,
        "startxref_count": raw_pdf.count(b"startxref")
    }

    # Multiple markers may reflect appended updates, including legitimate changes.
    # Raw byte counts alone do not confirm an editing history.
    if eof_count > 1:
        analysis["flags"].append({
            "category": "syntax",
            "type": "multiple_eof_markers",
            "evidence": f"{eof_count} %%EOF markers were found."
        })


# --------------------------------------------------
# 7. Attachments
# --------------------------------------------------

def extract_attachments(pdf, analysis):
    attachments = pdf.attachments
    attachment_list = []

    for filename in attachments.keys():
        # Read the embedded file to measure its content size.
        data = attachments[filename].get_file().read_bytes()

        attachment_list.append({
            "filename": filename,
            "size_bytes": len(data)
        })

    analysis["attachments"] = {
        "attachment_count": len(attachment_list),
        "files": attachment_list
    }

    # Make embedded files visible to the reviewer even though their contents are not analyzed.
    if attachment_list:
        analysis["flags"].append({
            "category": "attachments",
            "type": "embedded_files_present",
            "evidence": f"{len(attachment_list)} embedded attachment(s) found."
        })


# --------------------------------------------------
# Saving and main entry point
# --------------------------------------------------

def save_analysis(analysis, output_path):
    output_dir = os.path.dirname(output_path)

    # Create missing folders, but allow filenames that use the current folder.
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        # Keep the report readable and preserve non-English characters.
        json.dump(analysis, file, indent=4, ensure_ascii=False)


def extract_metadata(pdf_path, output_path):
    # Start fresh so findings from separate PDFs cannot mix.
    analysis = create_analysis_structure()

    # Close the PDF automatically, including when an extraction step fails.
    with pikepdf.open(pdf_path) as pdf:
        extract_doc_info(pdf, analysis)

        # Collect Document Info first because the XMP comparison depends on it.
        xmp_values = extract_xmp_metadata(pdf)
        compare_docinfo_with_xmp(xmp_values, analysis)

        extract_fonts(pdf, analysis)
        extract_images(pdf, analysis)
        extract_annotations(pdf, analysis)
        extract_syntax(pdf, pdf_path, analysis)
        extract_attachments(pdf, analysis)

    # Save only after every extraction step finishes successfully.
    save_analysis(analysis, output_path)

    return analysis


# Allow standalone testing without running extraction when another script imports this file.
if __name__ == "__main__":
    extract_metadata(pdftest_path, output_path)