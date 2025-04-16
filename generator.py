import json
import os
import random
import zipfile

def load_json(file_name):
    """Load the JSON file and return its contents."""
    with open(file_name, "r", encoding="utf-8") as file:
        return json.load(file)

def process_question(question):
    """Randomize variables and update question prompt and choices."""
    
    # Create a dictionary to store the randomized values
    randomized_values = {}

    # Loop through each variable in the 'variables' field and randomize it
    for var_name, var_values in question['variables'].items():
        randomized_values[var_name] = random.choice(var_values)
    
    # Update the prompt with the randomized variables
    updated_prompt = question['prompt']
    for var_name, value in randomized_values.items():
        updated_prompt = updated_prompt.replace(var_name, str(value))

    # Update the choices based on the randomized variables
    updated_choices = []
    for choice in question['choices']:
        updated_choice = choice
        for var_name, value in randomized_values.items():
            updated_choice = updated_choice.replace(var_name, str(value))
        updated_choices.append(updated_choice)

    # Update the correct answer based on the randomized variables
    updated_correct_answer = question['correct']
    for var_name, value in randomized_values.items():
        updated_correct_answer = updated_correct_answer.replace(var_name, str(value))

    # Return the processed question with updated prompt, choices, and correct answer
    return {
        'id': question['id'],
        'prompt': updated_prompt,
        'choices': updated_choices,
        'correct': updated_correct_answer
    }

def create_qti_package(questions):
    #create qti package with processed questions

    os.makedirs("qti_temp", exist_ok = True)

    #generate XML files
    manifest_items = []

    for i, q in enumerate(questions) :
    	file_name = f'question{i + 1}.xml'
    	file_path = os.path.join("qti_temp", file_name)
    	manifest_items.append((file_name, q['id']))
    	with open(file_path, "wb") as f :
    		f.write(generate_qti_item_xml(q['id'], q['prompt'], q['choices'], q['correct']))

    #create manifest
    with open("qti_temp/imsmanifest.xml", "w", encoding = "utf-8") as f :
    	f.write(generate_manifest_xml(manifest_items))

    #zip the contents
    zip_name = "qti_package.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf :
    	for root, _, files in os.walk("qti_temp") :
    		for file in files :
    			zipf.write(os.path.join(root,file), file)

    #cleanup
    for file in os.listdir("qti_temp"):
        os.remove(os.path.join("qti_temp", file))
    os.rmdir("qti_temp")

    return zip_name


def main():
    """Main entry point for the script."""
    # Load the questions from the JSON file
    questions = load_json("example.json")["questions"]
    
    # Process the questions
    processed_questions = []
	for q in questions:
    	for _ in range(4):  # Generate 4 variants
        	processed_questions.append(process_question(q))

    
    # Create the QTI package
    qti_package = create_qti_package(processed_questions)
    
    print(f"QTI package created: {qti_package}")

# Only run the script's main logic if executed directly (not imported as a module)
if __name__ == "__main__":
    main()
