import json
import os
import random
import zipfile
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re



def load_json(file_name):
    """Load the JSON file and return its contents."""
    with open(file_name, "r", encoding="utf-8") as file:
        return json.load(file)

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
        'id': f"{question['id']}_v{version_id}",  # Append version id to make each question unique        'prompt': updated_prompt,
        'prompt': updated_prompt,
        'choices': updated_choices,
        'correct': updated_correct_answer
    }

def create_qti_package(questions):
    # Create QTI package with processed questions
    os.makedirs("qti_temp", exist_ok=True)

    # Generate XML files
    manifest_items = []

    for i, q in enumerate(questions):
        file_name = f'question{i + 1}.xml'
        file_path = os.path.join("qti_temp", file_name)
        manifest_items.append((file_name, q['id']))
        with open(file_path, "wb") as f:
            # Encode the string returned by generate_qti_item_xml() into bytes
            f.write(generate_qti_item_xml(q['id'], q['prompt'], q['choices'], q['correct']).encode('utf-8'))

    # Create manifest
    with open("qti_temp/imsmanifest.xml", "w", encoding="utf-8") as f:
        # This should write a string, not bytes
        f.write(generate_manifest_xml(manifest_items))

    # Zip the contents
    zip_name = "qti_package.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk("qti_temp"):
            for file in files:
                zipf.write(os.path.join(root, file), file)

    # Clean up
    for file in os.listdir("qti_temp"):
        os.remove(os.path.join("qti_temp", file))
    os.rmdir("qti_temp")

    return zip_name



def convert_latex_to_mathjax(text):
    """Convert LaTeX delimited by $...$ into Canvas-friendly MathJax."""
    return re.sub(r'\$(.+?)\$', r'<script type="math/tex">\1</script>', text)

def generate_qti_item_xml(question_id, prompt, choices, correct):
    """Generate QTI 1.2 XML for a single multiple choice question."""
    Element = ET.ElementTree
    SubElement = ET.SubElement

    # Convert LaTeX to MathJax HTML format
    prompt_html = convert_latex_to_mathjax(prompt)
    choices_html = [convert_latex_to_mathjax(c) for c in choices]

    item = ET.Element("item", {"ident": question_id, "title": question_id})

    presentation = SubElement(item, "presentation")
    material = SubElement(presentation, "material")
    mattext = SubElement(material, "mattext", attrib={"texttype": "text/html"})
    # Ensure raw HTML is inserted directly without escaping
    mattext.text = prompt_html

    response_lid = SubElement(presentation, "response_lid", attrib={"ident": "response1", "rcardinality": "Single"})
    render_choice = SubElement(response_lid, "render_choice")

    for i, choice_text in enumerate(choices_html):
        ident = f"choice{i + 1}"
        response_label = SubElement(render_choice, "response_label", attrib={"ident": ident})
        choice_material = SubElement(response_label, "material")
        choice_mattext = SubElement(choice_material, "mattext", attrib={"texttype": "text/html"})
        # Ensure raw HTML is inserted directly without escaping
        choice_mattext.text = choice_text

    # Resprocessing section
    resprocessing = SubElement(item, "resprocessing")
    outcomes = SubElement(resprocessing, "outcomes")
    SubElement(outcomes, "decvar", attrib={"varname": "SCORE", "vartype": "Decimal", "minvalue": "0", "maxvalue": "100", "cutvalue": "50"})

    correct_index = choices.index(correct)
    correct_ident = f"choice{correct_index + 1}"

    respcondition = SubElement(resprocessing, "respcondition", attrib={"continue": "No"})
    conditionvar = SubElement(respcondition, "conditionvar")
    varequal = SubElement(conditionvar, "varequal", attrib={"respident": "response1"})
    varequal.text = correct_ident
    SubElement(respcondition, "setvar", attrib={"action": "Set"}).text = "100"
    SubElement(respcondition, "displayfeedback", attrib={"feedbacktype": "Response", "linkrefid": "correct"})

    return prettify(item).decode('utf-8')


def generate_manifest_xml(items):
    """
    Generate imsmanifest.xml content for a list of QTI items.
    
    Args:
        items (list of tuples): Each tuple contains (filename, identifier)
    
    Returns:
        str: The pretty-printed XML string for the manifest
    """
    ns = {
        'xmlns': "http://www.imsglobal.org/xsd/imscp_v1p1",
        'xmlns:imsmd': "http://www.imsglobal.org/xsd/imsmd_v1p2",
        'xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance",
        'xsi:schemaLocation': "http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd"
    }

    manifest = ET.Element("manifest", attrib={"identifier": "MANIFEST1", **ns})
    
    organizations = ET.SubElement(manifest, "organizations")
    resources = ET.SubElement(manifest, "resources")

    for filename, identifier in items:
        ET.SubElement(resources, "resource", {
            "identifier": identifier,
            "type": "imsqti_item_xmlv1p1",
            "href": filename
        })

    # Convert the XML element tree to a string
    return prettify(manifest).decode('utf-8')


def prettify(elem):
    """Return a pretty-printed XML string for the Element."""
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ", encoding="utf-8")


def main():
    """Main entry point for the script."""
    questions = load_json("example.json")["questions"]
    
    # Process the questions and generate randomized versions
    processed_questions = []
    version_id = 1
    for q in questions:
        for _ in range(4):  # Creating 4 randomized versions of each question
            processed_questions.append(process_question(q, version_id))
            version_id += 1
    
    # Create the QTI package
    qti_package = create_qti_package(processed_questions)
    print(f"QTI package created: {qti_package}")


# Only run the script's main logic if executed directly (not imported as a module)
if __name__ == "__main__":
    main()
