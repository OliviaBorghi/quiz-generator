import json
import os
import random
import zipfile
import re
import shutil
import hashlib
import io
import matplotlib.pyplot as plt
from lxml import etree as ET
from lxml.etree import QName
from matplotlib import rcParams
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from PIL import Image

def load_json(file_name):
    """Load the JSON file and return its contents."""
    with open(file_name, "r", encoding="utf-8") as file:
        return json.load(file)

def sanitize_latex_expr(latex_expr):
    # Generate a hash of the sanitized expression to ensure uniqueness
    hash_object = hashlib.md5(latex_expr.encode())
    hash_digest = hash_object.hexdigest()[:8]  # Take the first 8 characters of the hash

    # Append the hash to the sanitized expression
    sanitized_expr_with_hash = f"{hash_digest}.png"
    
    return sanitized_expr_with_hash

def save_latex_image(latex_str, image_filename, target_px_height=16, fontsize=12, dpi=200, padding_px=4):
    """Render LaTeX as a small inline image (~16px high)."""
    if not latex_str.strip():
        print("Empty LaTeX string detected, skipping...")
        return

    try:
        rcParams.update({
            "text.usetex": False,
            "mathtext.fontset": "cm",
            "font.size": fontsize,
        })

        fig = plt.figure(figsize=(0.01, 0.01))
        text = fig.text(0, 0, f"${latex_str}$", fontsize=fontsize)

        canvas = FigureCanvas(fig)
        canvas.draw()

        # Get bounding box of the text
        bbox = text.get_window_extent(renderer=canvas.get_renderer())
        bbox_inches = bbox.transformed(fig.dpi_scale_trans.inverted())

        # Add padding in inches
        padding_inch = padding_px / dpi
        padded_bbox = bbox_inches.expanded(1.0 + padding_inch / bbox_inches.width,
                                           1.0 + padding_inch / bbox_inches.height)

        # Resize the figure to match the new padded bounding box
        fig.set_size_inches(padded_bbox.width, padded_bbox.height)

        # Render again and save
        canvas.draw()
        fig.savefig(image_filename, dpi=dpi, bbox_inches='tight', pad_inches=padding_inch, transparent=True)

        plt.close(fig)


    except Exception as e:
        print(f"Error saving LaTeX image: {latex_str}\n{e}")

def evaluate_embedded_expressions(s: str) -> str:
    def eval_match(match):
        expr = match.group(1)
        try:
            result = eval(expr)
        except Exception as e:
            result = f"[eval error: {e}]"
        return str(result)

    # Evaluate all nested eval{...} expressions
    while re.search(r'eval{([^{}]*)}', s):
        s = re.sub(r'eval{([^{}]*)}', eval_match, s)

    return s


def process_question(question, version_id):
    """Randomize variables and update question prompt and choices."""
    # Create a dictionary to store the randomized values
    randomized_values = {}

    # Loop through each variable in the 'variables' field and randomize it
    for var_name, var_values in question['variables'].items():
        randomized_values[var_name] = random.choice(var_values)
    
    # Update the prompt with the randomized variables (using ~ as placeholders)
    updated_prompt = question['prompt']
    for var_name, value in randomized_values.items():
        updated_prompt = updated_prompt.replace(f'~{var_name}', str(value))
        updated_prompt = evaluate_embedded_expressions(updated_prompt)

    # Update the choices based on the randomized variables
    updated_choices = []
    for choice in question['choices']:
        updated_choice = choice
        for var_name, value in randomized_values.items():
            updated_choice = updated_choice.replace(f'~{var_name}', str(value))

        updated_choice = evaluate_embedded_expressions(updated_choice)
        updated_choices.append(updated_choice)

    # Update the correct answer based on the randomized variables
    updated_correct_answer = question['correct']
    for var_name, value in randomized_values.items():
        updated_correct_answer = updated_correct_answer.replace(f'~{var_name}', str(value))
    updated_correct_answer = evaluate_embedded_expressions(updated_correct_answer)

    # Return the processed question with updated prompt, choices, and correct answer
    return {
        'id': f"{question['id']}_v{version_id}",  # Append version id to make each question unique
        'prompt': updated_prompt,
        'choices': updated_choices,
        'correct': updated_correct_answer
    }

def create_qti_package(questions):
    """Create a QTI package containing questions and images."""
    os.makedirs("qti_temp", exist_ok=True)
    os.makedirs("qti_temp/images", exist_ok=True)  # Ensure images folder is inside qti_temp

    # Generate XML files
    manifest_items = []
    image_files = []

    for i, q in enumerate(questions):
        file_name = f'question{i + 1}.xml'
        file_path = os.path.join("qti_temp", file_name)
        manifest_items.append((file_name, q['id']))

        latex_images = generate_latex_images(q['prompt'], q['choices'], q['id'])

        # Save images for LaTeX equations in prompt and choices
        for image in latex_images:
            image_filename = os.path.join("qti_temp/images", image[1])
            save_latex_image(image[0], image_filename)
            image_files.append(image_filename) #add image file name for manifest to parse

        with open(file_path, "wb") as f:
            f.write(generate_qti_item_xml(q['id'], q['prompt'], q['choices'], q['correct'], latex_images).encode('utf-8'))

    # Create the manifest XML file
    with open("qti_temp/imsmanifest.xml", "w", encoding="utf-8") as f:
        f.write(generate_manifest_xml(manifest_items, image_files))

    # Zip the contents, including the images folder
    zip_name = "qti_package.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk("qti_temp"):
            for file in files:
                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), "qti_temp"))

    # Clean up
    for file in os.listdir("qti_temp"):
        file_path = os.path.join("qti_temp", file)
        if os.path.isdir(file_path):
            shutil.rmtree(file_path)
        else:
            os.remove(file_path)
    os.rmdir("qti_temp")

    return zip_name

def generate_latex_images(prompt, choices, question_id):
    """Generate images for LaTeX equations in prompt and choices."""
    latex_images = []
    for text in [prompt] + choices:
        latex_matches = re.findall(r'\$(.+?)\$', text)
        for latex_expr in latex_matches:
            filename = sanitize_latex_expr(latex_expr)
            latex_images.append((latex_expr,filename))

    if not latex_images:
        print(f"Warning: No LaTeX expressions found for question {question_id}")
    
    return latex_images

def process_text_with_latex(prompt, latex_images, image_index):
    """
    Process a text prompt, extract LaTeX expressions, and return the text along with a list of LaTeX expressions
    for image generation. This function does not call `save_latex_image`, leaving that to be handled elsewhere.
    """

    # Regular expression to find LaTeX expressions between $...$
    latex_pattern = r'(\$.*?\$)'  # Non-greedy match for $...$

    segments = []
    last_index = 0

    # Process the prompt and find LaTeX expressions
    for match in re.finditer(latex_pattern, prompt):
        start, end = match.span()
        
        # Add regular text before LaTeX expression
        if start > last_index:
            segments.append(('text', prompt[last_index:start]))  # Regular text before LaTeX

        # Extract the LaTeX expression (without the $ symbols)
        latex_str = prompt[start + 1:end - 1]  # Remove $ symbols

        # Add LaTeX image placeholder (just the placeholder for now)
        segments.append(('latex', latex_str))  # Store LaTeX expression as a placeholder

        last_index = end  # Update the last index for the next segment

    # Add any remaining text after the last LaTeX expression
    if last_index < len(prompt):
        segments.append(('text', prompt[last_index:]))

    # Now, construct the final HTML with <img> tags for LaTeX images
    final_html = ""
    for segment_type, content in segments:
        if segment_type == 'text':
            final_html += content  # Add regular text directly
        elif segment_type == 'latex':
            final_html += f'<img src="images/{latex_images[image_index][1]}" alt="LaTeX Image" />'  # Placeholder for LaTeX images
            image_index +=1
    return final_html, image_index

def generate_qti_item_xml(question_id, prompt, choices, correct, latex_images):
    """Generate QTI 1.2 XML for a single multiple choice question."""
    Element = ET.ElementTree
    SubElement = ET.SubElement

    prompt_html, image_index = process_text_with_latex(prompt,latex_images,0)

    # Generate images for each choice and use them in the choices
    choice_images = []
    for choice in choices:
        choice_html, image_index = process_text_with_latex(choice, latex_images, image_index)
        # Create <img> HTML for LaTeX image in choice
        choice_images.append(choice_html)


    # Create the root item element
    item = ET.Element("item", {"ident": question_id, "title": question_id})

    # Add presentation section
    presentation = SubElement(item, "presentation")
    material = SubElement(presentation, "material")
    mattext = SubElement(material, "mattext", attrib={"texttype": "text/html"})
    mattext.text = prompt_html

    # Add response section
    response_lid = SubElement(presentation, "response_lid", attrib={"ident": "response1", "rcardinality": "Single"})
    render_choice = SubElement(response_lid, "render_choice")

    # Add choices to response section
    for i, choice_html in enumerate(choice_images):
        ident = f"choice{i + 1}"
        response_label = SubElement(render_choice, "response_label", attrib={"ident": ident})
        choice_material = SubElement(response_label, "material")
        choice_mattext = SubElement(choice_material, "mattext", attrib={"texttype": "text/html"})
        choice_mattext.text = choice_html

    # Add resprocessing section for feedback and scoring
    resprocessing = SubElement(item, "resprocessing")
    outcomes = SubElement(resprocessing, "outcomes")
    SubElement(outcomes, "decvar", attrib={"varname": "SCORE", "vartype": "Decimal", "minvalue": "0", "maxvalue": "100", "cutvalue": "50"})

    # Identify correct answer
    correct_index = choices.index(correct)
    correct_ident = f"choice{correct_index + 1}"

    respcondition = SubElement(resprocessing, "respcondition", attrib={"continue": "No"})
    conditionvar = SubElement(respcondition, "conditionvar")
    varequal = SubElement(conditionvar, "varequal", attrib={"respident": "response1"})
    varequal.text = correct_ident
    SubElement(respcondition, "setvar", attrib={"action": "Set"}).text = "100"
    SubElement(respcondition, "displayfeedback", attrib={"feedbacktype": "Response", "linkrefid": "correct"})

    # Now wrap the generated item with the full QTI structure
    questestinterop = ET.Element("questestinterop")
    assessment = SubElement(questestinterop, "assessment", title="My Quiz")
    section = SubElement(assessment, "section", ident="root_section")

    # Add the item to the section
    section.append(item)

    # Prettify the XML output using the prettify function
    return prettify(questestinterop)

def generate_manifest_xml(items, image_files):
    """Generate imsmanifest.xml content for a list of QTI items and images."""
    ns = {
        '': "http://www.imsglobal.org/xsd/imscp_v1p1",  # Default namespace
        'imsqti': "http://www.imsglobal.org/xsd/imsqti_v1p2",  # QTI namespace
        'xsi': "http://www.w3.org/2001/XMLSchema-instance",
    }

    # Create the manifest element with proper namespaces and schemaLocation
    manifest = ET.Element(
        QName(ns[''], 'manifest'),
        {
            QName(ns['xsi'], 'schemaLocation'): (
                "http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd "
                "http://www.imsglobal.org/xsd/imsqti_v1p2 imsqti_v1p2.xsd"
            ),
            "identifier": "man00001"
        }
    )

    # Create organizations and resources elements
    organizations = ET.SubElement(manifest, QName(ns[''], 'organizations'))
    resources = ET.SubElement(manifest, QName(ns[''], 'resources'))

    # Add QTI items to the resources
    for filename, identifier in items:
        resource = ET.SubElement(
            resources,
            QName(ns[''], 'resource'),
            {
                "identifier": identifier,
                "type": "imsqti_xmlv1p2",  # Use the correct QTI 1.2 type
                "href": filename
            }
        )
        # Add the associated file(s) for the resource
        ET.SubElement(resource, QName(ns[''], 'file'), {"href": filename})
        for image_filename in image_files:
            ET.SubElement(resource, QName(ns[''], 'file'), {"href": f"images/{os.path.basename(image_filename)}"})

    return prettify(manifest)

def wrap_with_qti_structure(item_xml):
    qti_header = '''<?xml version="1.0" encoding="UTF-8"?>
<questestinterop>
  <assessment title="My Quiz">
    <section ident="root_section">
'''
    qti_footer = '''    </section>
  </assessment>
</questestinterop>'''

    return qti_header + item_xml + qti_footer

def prettify(elem):
    # Using lxml's tostring function with no escape
    # Serialize the tree to a string with 'xml' encoding, no escaping
    xml_bytes = ET.tostring(elem, pretty_print=True, encoding="utf-8", xml_declaration=True, method="xml")
    xml_str = xml_bytes.decode("utf-8")
    

    # Replace escaped characters with literal ones
    xml_str = xml_str.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    xml_str = xml_str.replace("ns0:", '').replace("/ns0:",'')
    return xml_str

def main():
    """Main entry point for the script."""
    questions = load_json("example.json")["questions"]
    
    # Process the questions and generate randomized versions
    processed_questions = []
    version_id = 1
    for q in questions:
        for _ in range(1):  # Creating 4 randomized versions of each question
            processed_questions.append(process_question(q, version_id))
            version_id += 1
    
    # Create the QTI package
    qti_package = create_qti_package(processed_questions)
    print(f"QTI package created: {qti_package}")

if __name__ == "__main__":
    main()
