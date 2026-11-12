import os
import re
import json
from collections import Counter

import pikepdf


# --------------------------------------------------
# File paths
# --------------------------------------------------

script_dir = os.path.dirname(os.path.abspath(__file__))

output_path = os.path.join(script_dir, "..", "AI_data", "pdf_analysis.json")


# --------------------------------------------------
# Small helper functions
# --------------------------------------------------

"""
Converts pikepdf values into Python values that can be serialized as JSON
"""
def clean_value(value):
    # Keep None; JSON will represent it as null
    if value is None:
        return None

    # Keep basic types that JSON can represent directly
    if isinstance(value, (str, int, float, bool)):
        return value

    # Convert these collections into a list, cleaning each item
    if isinstance(value, (list, tuple, pikepdf.Array)):
        return [clean_value(item) for item in value]

    # Convert any other value to a string
    return str(value)


"""
    Remove PDF formatting from font names.

    Example:
    /ABCDEF+Arial-BoldMT
            ↓
    Arial-BoldMT
"""
def normalize_font_name(font_name):
    if font_name is None:
        return None

    #to remove /
    font_name = str(font_name).replace("/", "")

    # Remove subset prefix such as ABCDEF+
    font_name = re.sub(r"^[A-Z]{6}\+", "", font_name)

    return font_name


def compare_metadata(docinfo_value, xmp_value):
    """
    Compare Document Info metadata with XMP metadata.

    Returns:
        match
        mismatch
        missing
    """

    if docinfo_value is None or xmp_value is None:
        return "missing"

    docinfo_value = clean_value(docinfo_value)
    xmp_value = clean_value(xmp_value)

    # XMP author can sometimes be stored as a list
    if isinstance(xmp_value, list):
        if str(docinfo_value) in [str(value) for value in xmp_value]:
            return "match"

        return "mismatch"

    if str(docinfo_value).strip() == str(xmp_value).strip():
        return "match"

    return "mismatch"

# --------------------------------------------------
# Final structure
# This is what will eventually be given to the AI
# --------------------------------------------------    
def create_analysis_structure():
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


# ==================================================
# 1. METADATA
# Metadata = collects the normal PDF Document Info 
# values like creation date, creator, producer, author.
# ==================================================
def extract_doc_info(pdf, analysis):

    docinfo = pdf.docinfo

    #analysis = create_analysis_structure()

    analysis["metadata"] = {
        "creation_date": clean_value(docinfo.get("/CreationDate")),
        "modification_date": clean_value(docinfo.get("/ModDate")),
        "creator": clean_value(docinfo.get("/Creator")),
        "producer": clean_value(docinfo.get("/Producer")),
        "author": clean_value(docinfo.get("/Author"))
    }


# ==================================================
# 2. XMP CONSISTENCY
# XMP Consistency = collects the XMP versions of 
# those same fields and compares them against Document 
# Info.
# ==================================================
def extract_xmp_metadata(pdf):

    xmp_values = {}

    if pdf.xmp_metadata:

        xmp = pdf.xmp_metadata

        xmp_values = {
            "creation_date": clean_value(xmp.get("xmp:CreateDate")),
            "modification_date": clean_value(xmp.get("xmp:ModifyDate")),
            "creator": clean_value(xmp.get("xmp:CreatorTool")),
            "producer": clean_value(xmp.get("pdf:Producer")),
            "author": clean_value(xmp.get("dc:creator"))
        }

    return xmp_values

from config import pdftest_path, poppler_path #just for now

def compare_docinfo_with_xmp(xmp_values, analysis):
    comparisons = {}

    '''
        I need to normalize the dates in bith doc info and xmp before 
        comparing them and they are not in the same format which makes 
        the comparison fails all the time
    '''
    # fields_to_compare = ("creation_date", "modification_date", "creator", "producer", "author")
    fields_to_compare = ("creator", "producer", "author")

    for field in fields_to_compare:

        docinfo_value = analysis["metadata"][field]
        xmp_value = xmp_values.get(field)

        comparisons[field] = compare_metadata(
            docinfo_value,
            xmp_value
        )

    analysis["xmp_consistency"] = {
    "xmp_metadata": xmp_values,
    "comparisons": comparisons
    }

    for field, result in comparisons.items():
        if result == "mismatch":
            analysis["flags"].append({
                "category": "metadata",
                "type": "xmp_mismatch",
                "field": field,
                "evidence": f"Document Info and XMP values differ for {field}"
            })        

    return comparisons


# ==================================================
# 3. FONTS
# This Fonts section extracts and stores which fonts appear on each page.
# ==================================================

def collect_fonts(resources, visited=None):
    """
    Find font resources.

    Also checks inside Form XObjects because some PDF content
    can be stored inside them.
    """

    if visited is None:
        visited = set()

    fonts_found = []

    if resources is None:
        return fonts_found


    # ----------------------------
    # Fonts
    # ----------------------------

    font_resources = resources.get("/Font")

    if font_resources:

        for font_name, font_object in font_resources.items():

            base_font = font_object.get("/BaseFont")

            fonts_found.append({
                "Font": normalize_font_name(base_font),
            })


    # ----------------------------
    # Look inside Form XObjects
    # ----------------------------

    xobjects = resources.get("/XObject")

    if xobjects:

        for object_name, xobject in xobjects.items():

            subtype = xobject.get("/Subtype")

            if str(subtype) == "/Form":

                object_id = xobject.objgen

                # Prevent repeatedly reading the same object
                if object_id in visited:
                    continue

                visited.add(object_id)

                form_resources = xobject.get("/Resources")

                fonts_found.extend(
                    collect_fonts(
                        form_resources,
                        visited
                    )
                )

    return fonts_found

def remove_duplicate_fonts(fonts):
    # Remove duplicate fonts on the same page
    
    unique_fonts = {}

    for font in fonts:
        font_name = font["Font"]

        if font_name:
            unique_fonts[font_name] = font
        
    return unique_fonts

from collections import Counter

def extract_fonts(pdf, analysis):
    font_usage = {}
    font_sets = {}

    for page_num, page in enumerate(pdf.pages, start=1):
        # This dictionary maps each font name to its font record.
        unique_fonts = remove_duplicate_fonts(collect_fonts(page.resources))
        font_list = list(unique_fonts.values())

        analysis["fonts"]["pages"][str(page_num)] = {
            "status": (
                "font_resources_found"
                if font_list
                else "no_named_font_resources_found"
            ),
            "font_count": len(font_list),
            "fonts": font_list
        }

        # Record which pages use each font.
        for font_name in unique_fonts:
            font_usage.setdefault(font_name, []).append(page_num)

        # Save this page's font set for the cross-page comparison.
        if unique_fonts:
            font_sets[page_num] = tuple(sorted(unique_fonts.keys()))

    if not font_sets:
        analysis["fonts"]["cross_page_analysis"] = {
            "status": "no_named_font_resources_found"
        }
        return

    pattern_counts = Counter(font_sets.values())
    most_common_fonts, frequency = pattern_counts.most_common(1)[0]

    normal_pages = [
        page_num for page_num, fonts in font_sets.items()
        if fonts == most_common_fonts
    ]
    different_pages = [
        page_num for page_num, fonts in font_sets.items()
        if fonts != most_common_fonts
    ]

    analysis["fonts"]["cross_page_analysis"] = {
        "font_usage": {
            name: {"page_count": len(pages), "pages": pages}
            for name, pages in font_usage.items()
        },
        "most_common_font_set": list(most_common_fonts),
        "pages_using_most_common_font_set": normal_pages,
        "pages_with_different_font_set": different_pages
    }

    # Create flags only when more than half of pages with named fonts
    # share the same font pattern.
    if frequency > len(font_sets) / 2:
        common_fonts = set(most_common_fonts)

        for page_num in different_pages:
            page_fonts = set(font_sets[page_num])

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



def extract_images(pdf, analysis):
    image_counts = {}

    for page_num, page in enumerate(pdf.pages, start=1):
        # get_images() can return None, so use an empty dictionary in that case.
        images = page.get_images() or {}
        image_list = []

        for image_name, image_object in images.items():
            width = image_object.get("/Width")
            height = image_object.get("/Height")

            image_list.append({
                "name": str(image_name),
                "width": int(width) if width is not None else None,
                "height": int(height) if height is not None else None
            })

        image_counts[page_num] = len(image_list)
        analysis["images"]["pages"][str(page_num)] = {
            "image_count": len(image_list),
            "images": image_list
        }

    if not image_counts:
        analysis["images"]["cross_page_analysis"] = {
            "status": "no_pages_found"
        }
        return

    counts = Counter(image_counts.values())
    common_count, frequency = counts.most_common(1)[0]

    normal_pages = [
        page for page, count in image_counts.items()
        if count == common_count
    ]
    different_pages = [
        page for page, count in image_counts.items()
        if count != common_count
    ]

    analysis["images"]["cross_page_analysis"] = {
        "most_common_image_count": common_count,
        "pages_with_most_common_image_count": normal_pages,
        "pages_with_different_image_count": different_pages
    }

    if frequency > len(image_counts) / 2:
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


def extract_annotations(pdf, analysis):
    for page_num, page in enumerate(pdf.pages, start=1):
        annotations = page.obj.get("/Annots")
        annotation_list = []

        if annotations:
            for annotation in annotations:
                annotation_list.append({
                    "type": clean_value(annotation.get("/Subtype")),
                    "rectangle": clean_value(annotation.get("/Rect"))
                })

        analysis["annotations"]["pages"][str(page_num)] = {
            "annotation_count": len(annotation_list),
            "annotations": annotation_list
        }

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


def extract_syntax(pdf, pdf_path, analysis):
    analysis["syntax"] = {
        "pdf_version": str(pdf.pdf_version),
        "number_of_pages": len(pdf.pages),
        "encrypted": pdf.is_encrypted
    }

    with open(pdf_path, "rb") as file:
        raw_pdf = file.read()

    eof_count = raw_pdf.count(b"%%EOF")
    startxref_count = raw_pdf.count(b"startxref")

    analysis["syntax"]["eof_marker_count"] = eof_count
    analysis["syntax"]["startxref_count"] = startxref_count

    if eof_count > 1:
        analysis["flags"].append({
            "category": "syntax",
            "type": "multiple_eof_markers",
            "evidence": f"{eof_count} %%EOF markers were found."
        })


def extract_attachments(pdf, analysis):
    attachment_list = []

    for filename in pdf.attachments.keys():
        attachment = pdf.attachments[filename]
        data = attachment.get_file().read_bytes()

        attachment_list.append({
            "filename": filename,
            "size_bytes": len(data)
        })

    analysis["attachments"] = {
        "attachment_count": len(attachment_list),
        "files": attachment_list
    }

    if attachment_list:
        analysis["flags"].append({
            "category": "attachments",
            "type": "embedded_files_present",
            "evidence": (
                f"{len(attachment_list)} embedded attachment(s) found."
            )
        })

def save_analysis(analysis, output_path):
    output_dir = os.path.dirname(output_path)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(analysis, file, indent=4, ensure_ascii=False)


def extract_metadata(pdf_path, output_path):
    analysis = create_analysis_structure()

    with pikepdf.open(pdf_path) as pdf:
        extract_doc_info(pdf, analysis)

        xmp_values = extract_xmp_metadata(pdf)
        compare_docinfo_with_xmp(xmp_values, analysis)

        extract_fonts(pdf, analysis)
        extract_images(pdf, analysis)
        extract_annotations(pdf, analysis)
        extract_syntax(pdf, pdf_path, analysis)
        extract_attachments(pdf, analysis)

    save_analysis(analysis, output_path)
    return analysis

if __name__ == "__main__":
    extract_metadata(pdftest_path, output_path)