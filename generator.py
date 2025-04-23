import json
import os
import random
import zipfile
import re
import shutil
import hashlib
import io
import uuid
import urllib.parse
from lxml import etree as ET
from lxml.etree import QName

def load_json(file_name):
    """Load the JSON file and return its contents."""
    with open(file_name, "r", encoding="utf-8") as file:
        return json.load(file)

def generate_canvas_url(latex: str, base_url: str = "https://canvas.lms.unimelb.edu.au/equation_images", scale: int = 1) -> str:
    first_encoded = urllib.parse.quote(latex)
    double_encoded = urllib.parse.quote(first_encoded)
    return f"{base_url}/{double_encoded}?scale={scale}"

def process_text_with_canvas_latex(prompt):
    """
    Process a text prompt with inline LaTeX expressions in $...$ and return HTML where LaTeX is rendered
    using Canvas-hosted equation image URLs.
    """
    latex_pattern = r'(\$.*?\$)'  # Match LaTeX expressions between $...$
    segments = []
    last_index = 0

    for match in re.finditer(latex_pattern, prompt):
        start, end = match.span()

        # Add text before LaTeX
        if start > last_index:
            segments.append(('text', prompt[last_index:start]))

        # Extract the LaTeX content (strip $ symbols)
        latex_str = prompt[start + 1:end - 1]
        segments.append(('latex', latex_str))

        last_index = end

    # Add any trailing text
    if last_index < len(prompt):
        segments.append(('text', prompt[last_index:]))

    # Now assemble final HTML
    final_html = ""
    for segment_type, content in segments:
        if segment_type == 'text':
            final_html += content
        elif segment_type == 'latex':
            img_url = generate_canvas_url(content)
            img_tag = (
                f'<img class="equation_image" title="{content}" '
                f'src="{img_url}" alt="LaTeX: {content}" '
                f'data-equation-content="{content}" data-ignore-a11y-check="" loading="lazy">'
            )
            final_html += img_tag

    return final_html

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
    """Create a QTI package containing questions and manifest."""
    os.makedirs("qti_temp", exist_ok=True)

    # Generate XML files
    manifest_items = []

    for i, q in enumerate(questions):
        file_name = f'question{i + 1}.xml'
        file_path = os.path.join("qti_temp", file_name)
        manifest_items.append((file_name, q['id']))

        with open(file_path, "wb") as f:
            f.write(generate_qti_item_xml(q['id'], q['prompt'], q['choices'], q['correct']).encode('utf-8'))

    # Create the manifest XML file
    with open("qti_temp/imsmanifest.xml", "w", encoding="utf-8") as f:
        f.write(generate_manifest_xml(manifest_items))

    quiz_title = "Generated Quiz"
    # Create assessment meta XML file
    with open("qti_temp/assessment_meta.xml", "w", encoding="utf-8") as f:
        f.write(generate_assessment_meta_xml(quiz_title, manifest_items))
    
    # Zip the contents
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

def generate_qti_item_xml(question_id, prompt, choices, correct):
    """Generate QTI 1.2 XML for a single multiple choice question."""
    Element = ET.ElementTree
    SubElement = ET.SubElement

    prompt_html = process_text_with_canvas_latex(prompt)

    # Generate urls for each choice and use them in the choices
    choice_urls = []
    for choice in choices:
        choice_html = process_text_with_canvas_latex(choice)
        choice_urls.append(choice_html)

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
    for i, choice_html in enumerate(choice_urls):
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

    # Add only the item (no assessment structure)
    questestinterop.append(item)

    # Prettify the XML output using the prettify function
    return prettify(questestinterop)

def generate_manifest_xml(items):
    """Generate imsmanifest.xml content for a list of QTI items"""
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

     # Add each item as a resource
    for item in items:
        filename = item[0]
        ET.SubElement(
            resources,
            QName(ns[''], 'resource'),
            {
                "identifier": f"res_{filename}",
                "type": "imsqti_item_xmlv1p2",
                "href": filename
            }
        )

    # Add a resource for assessment_meta.xml
    ET.SubElement(
        resources,
        QName(ns[''], 'resource'),
        {
            "identifier": "res_assessment_meta",
            "type": "imsqti_test_xmlv1p2",
             "href": "assessment_meta.xml" 
        }
    )

    return prettify(manifest)

def generate_assessment_meta_xml(quiz_title, items, shuffle_answers=True, assignment_group_id=None):
    """Generate assessment_meta.xml content for a Canvas QTI quiz"""
    nsmap = {
        None: "http://canvas.instructure.com/xsd/cccv1p0",  # default namespace
        "xsi": "http://www.w3.org/2001/XMLSchema-instance"
    }
    quiz = ET.Element("quiz", nsmap=nsmap)
    quiz.set("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation", "http://canvas.instructure.com/xsd/cccv1p0 cccv1p0.xsd")

    ET.SubElement(quiz, "title").text = quiz_title
    ET.SubElement(quiz, "description").text = "<p>To come</p>"
    ET.SubElement(quiz, "shuffle_answers").text = "true" if shuffle_answers else "false"
    ET.SubElement(quiz, "scoring_policy").text = "keep_highest"
    ET.SubElement(quiz, "hide_results")
    ET.SubElement(quiz, "quiz_type").text = "practice_quiz"
    ET.SubElement(quiz, "points_possible").text = str(len(items))
    ET.SubElement(quiz, "require_lockdown_browser").text = "false"
    ET.SubElement(quiz, "require_lockdown_browser_for_results").text = "false"
    ET.SubElement(quiz, "require_lockdown_browser_monitor").text = "false"
    ET.SubElement(quiz, "lockdown_browser_monitor_data")
    ET.SubElement(quiz, "show_correct_answers").text = "true"
    ET.SubElement(quiz, "anonymous_submissions").text = "false"
    ET.SubElement(quiz, "could_be_locked").text = "false"
    ET.SubElement(quiz, "disable_timer_autosubmission").text = "false"
    ET.SubElement(quiz, "allowed_attempts").text = "1"
    ET.SubElement(quiz, "one_question_at_a_time").text = "false"
    ET.SubElement(quiz, "cant_go_back").text = "false"
    ET.SubElement(quiz, "available").text = "false"
    ET.SubElement(quiz, "one_time_results").text = "false"
    ET.SubElement(quiz, "show_correct_answers_last_attempt").text = "false"
    ET.SubElement(quiz, "only_visible_to_overrides").text = "false"
    ET.SubElement(quiz, "module_locked").text = "false"

    if assignment_group_id:
        ET.SubElement(quiz, "assignment_group_identifierref").text = assignment_group_id

    ET.SubElement(quiz, "assignment_overrides")

    return prettify(quiz)

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
