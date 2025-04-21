import json
import os
import random
import zipfile
from lxml import etree as ET
import re
import matplotlib.pyplot as plt
import shutil
import matplotlib.backends.backend_agg as agg
from lxml.etree import QName

import hashlib

import html


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



def save_latex_image(latex_str, image_filename):
    """Save LaTeX string as a compact image with dynamic figure size."""
    if not latex_str:
        print("Empty LaTeX string detected, skipping...")
        return

    try:
        # Estimate width based on string length (characters) — tune scaling as needed
        base_width = 0  # Minimum width
        width_per_char = 0.01  # Add this much width per character
        estimated_width = base_width + width_per_char * len(latex_str)
        height = 0.4  # Constant height for inline math

        fig, ax = plt.subplots(figsize=(estimated_width, height))
        ax.text(0.5, 0.5, f'${latex_str}$', fontsize=14, ha='center', va='center')

        ax.set_axis_off()

        canvas = agg.FigureCanvasAgg(fig)
        canvas.print_figure(image_filename, dpi=200, bbox_inches='tight', pad_inches=0.05)

        plt.close(fig)
    except Exception as e:
        print(f"Error saving LaTeX image for expression: {latex_str}. Error: {e}")



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

    # Update the choices based on the randomized variables
    updated_choices = []
    for choice in question['choices']:
        updated_choice = choice
        for var_name, value in randomized_values.items():
            updated_choice = updated_choice.replace(f'~{var_name}', str(value))
        updated_choices.append(updated_choice)

    # Update the correct answer based on the randomized variables
    updated_correct_answer = question['correct']
    for var_name, value in randomized_values.items():
        updated_correct_answer = updated_correct_answer.replace(f'~{var_name}', str(value))

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


def generate_qti_item_xml(question_id, prompt, choices, correct, latex_images):
    """Generate QTI 1.2 XML for a single multiple choice question."""
    Element = ET.ElementTree
    SubElement = ET.SubElement

    # Separate prompt into text and LaTeX expression
    prompt_text = prompt.split('$')[0].strip()  # Surrounding text before LaTeX
    prompt_latex = prompt.split('$')[1] if '$' in prompt else ""  # LaTeX expression between $ symbols

    # Create <img> HTML for LaTeX image in prompt
    if prompt_latex:
        prompt_html = f'{prompt_text} <img src="images/{latex_images[0][1]}" alt="Question Image" />'
    else:
        prompt_html = f'{prompt_text}'

    # Generate images for each choice and use them in the choices
    choice_images = []
    for i, choice in enumerate(choices):
        choice_text = choice.split('$')[0].strip()  # Surrounding text before LaTeX
        choice_latex = choice.split('$')[1] if '$' in choice else ""  # LaTeX expression between $ symbols

        # Create <img> HTML for LaTeX image in choice
        if choice_latex:
            choice_html = f'{choice_text} <img src="images/{latex_images[i + 1][1]}" alt="Choice Image {i + 1}" />'
            choice_images.append(choice_html)

        else:
            choice_html = f'{choice_text}'


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

    # Return the prettified XML
    return prettify(item)



def generate_manifest_xml(items, image_files):
    """Generate imsmanifest.xml content for a list of QTI items and images."""
    ns = {
        '': "http://www.imsglobal.org/xsd/imscp_v1p1",  # Default namespace
        'imsmd': "http://www.imsglobal.org/xsd/imsmd_v1p2",
        'xsi': "http://www.w3.org/2001/XMLSchema-instance",
    }

    manifest = ET.Element(
        QName(ns[''], 'manifest'),
        {
            QName(ns['xsi'], 'schemaLocation'): "http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd"
        }
    )

    organizations = ET.SubElement(manifest, QName(ns[''], 'organizations'))
    resources = ET.SubElement(manifest, QName(ns[''], 'resources'))

    # Add QTI items to the manifest
    for filename, identifier in items:
        ET.SubElement(
            resources,
            QName(ns[''], 'resource'),
            {
                "identifier": identifier,
                "type": "imsqti_item_xmlv1p1",
                "href": filename
            }
        )

    # Add image resources to the manifest
    for image_filename in image_files:
        image_identifier = f"image_{os.path.basename(image_filename)}"  # Unique identifier for the image
        ET.SubElement(
            resources,
            QName(ns[''], 'resource'),
            {
                "identifier": image_identifier,
                "type": "image/png",  # Assuming images are in JPEG format, change if needed
                "href": f"images/{os.path.basename(image_filename)}"
            }
        )

    return prettify(manifest)


def prettify(elem):
    # Using lxml's tostring function with no escape
    # Serialize the tree to a string with 'xml' encoding, no escaping
    xml_bytes = ET.tostring(elem, pretty_print=True, encoding="utf-8", xml_declaration=True, method="xml")
    if isinstance(xml_bytes, bytes):
        xml_str = xml_bytes.decode("utf-8")
    else:
        xml_str = xml_bytes  # already a string

    # Replace escaped characters with literal ones
    xml_str = xml_str.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")

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
