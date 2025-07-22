import os
import gradio as gr
import re

# Import the required Vertex AI libraries
try:
    import vertexai
    from vertexai.preview.language_models import TextToSpeechModel
except ImportError:
    # This will be printed in the Cloud Run logs if the library is missing
    print("FATAL ERROR: The 'google-cloud-aiplatform' library is not installed.")
    print("Please ensure it's listed in your requirements.txt file for deployment.")
    exit()

# --- Configuration ---
CHARACTER_VOICES = {
    "Krishna": "text-to-speech-en-in-standard-c",
    "Radha": "text-to-speech-en-in-wavenet-d",
    "Ganesha": "text-to-speech-en-us-wavenet-e",
    "Narrator": "text-to-speech-en-us-wavenet-f",
    "Friend1": "text-to-speech-en-us-standard-c",
    "Friend2": "text-to-speech-en-au-wavenet-b",
}

# --- Cloud Run Specific Configuration ---
# The Cloud Run file system is read-only, except for the /tmp directory.
# We check if the 'K_SERVICE' environment variable exists, which confirms we are on Cloud Run.
if os.environ.get('K_SERVICE'):
    OUTPUT_DIR = "/tmp/voice_overs"
else:
    OUTPUT_DIR = "voice_overs" # For local testing
os.makedirs(OUTPUT_DIR, exist_ok=True)


# --- Core Functions ---

def initialize_vertex_ai():
    """Initializes the Vertex AI SDK using environment variables."""
    # On Cloud Run, the Project ID is best set as an environment variable.
    project_id = os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GCP_LOCATION", "us-central1")
    if not project_id:
        raise ValueError("Configuration Error: GCP_PROJECT_ID environment variable is not set. Please set it in the Cloud Run deployment settings.")
    try:
        print("Initializing Vertex AI...")
        vertexai.init(project=project_id, location=location)
        print(f"Vertex AI initialized successfully for project: {project_id}")
    except Exception as e:
        raise RuntimeError(f"Vertex AI Init Failed. Check Service Account permissions. Original error: {e}") from e

def generate_audio_for_line(character_name, voice_model_name, dialogue_text, output_filename):
    """Generates a single audio file."""
    if not dialogue_text:
        return False, "No dialogue text remaining after removing brackets."
    try:
        model = TextToSpeechModel.from_pretrained(voice_model_name)
        response = model.predict(dialogue_text)
        with open(output_filename, "wb") as audio_file:
            audio_file.write(response.audio_data)
        return True, ""
    except Exception as e:
        # Provide a more detailed error message for debugging.
        return False, f"API Error for '{character_name}': {e}"

def generate_voice_over(script_file_obj, *args):
    """Main Gradio function to process the script. This is now robust."""
    if script_file_obj is None: return "Please upload a script file.", "", gr.Button(visible=False)
    if not script_file_obj.name.lower().endswith('.txt'): return "Invalid File Type: Please upload a .txt file.", "", gr.Button(visible=False)
    try:
        initialize_vertex_ai()
    except (ValueError, RuntimeError) as e:
        return str(e), "", gr.Button(visible=False)
    
    output_html, error_summary, audio_files_generated_count, line_processed_count = "", [], 0, 0
    try:
        script_content = script_file_obj.read().decode('utf-8')
    except Exception as e:
        return f"Error reading script file: {e}", "", gr.Button(visible=False)
        
    for i, line in enumerate(script_content.splitlines()):
        line = line.strip()
        if not line: continue
        line_processed_count += 1
        parts = line.split(':', 1)
        if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
            error_summary.append(f"Line {i+1} (Format Error): '{line}'")
            continue
        character_name, original_dialogue = parts[0].strip(), parts[1].strip()
        cleaned_dialogue = re.sub(r'\[.*?\]', '', original_dialogue).strip()
        cleaned_dialogue = re.sub(r'\s+', ' ', cleaned_dialogue)
        voice_model_name = CHARACTER_VOICES.get(character_name)
        if not voice_model_name:
            error_summary.append(f"Line {i+1}: Character '{character_name}' not configured.")
            continue
        filename = os.path.join(OUTPUT_DIR, f"{line_processed_count:03d}_{character_name}.mp3")
        success, error_message = generate_audio_for_line(character_name, voice_model_name, cleaned_dialogue, filename)
        if success:
            audio_files_generated_count += 1
            # Gradio on Cloud Run can serve files directly from the temp directory
            output_html += f"<p><strong>{character_name}:</strong> {original_dialogue}</p><audio controls src='file={filename}'></audio><br><br>"
        else:
            error_summary.append(f"Line {i+1} ({character_name}): {error_message}")
            
    status_message = f"Processed {line_processed_count} lines. Generated {audio_files_generated_count} files."
    if error_summary: status_message += "<br><br><strong>Errors:</strong><br>" + "<br>".join(error_summary)
    if not output_html: output_html = "No audio generated. Check status for errors."
    return status_message, output_html, gr.Button(visible=(audio_files_generated_count > 0))

def clear_generated_files():
    """Removes files from the temporary directory."""
    deleted_count = 0
    if not os.path.exists(OUTPUT_DIR): return "Directory does not exist.", "", gr.Button(visible=False)
    for filename in os.listdir(OUTPUT_DIR):
        try: os.remove(os.path.join(OUTPUT_DIR, filename)); deleted_count += 1
        except Exception as e: print(f"Error deleting file {filename}: {e}")
    return f"Cleared {deleted_count} files.", "", gr.Button(visible=False)

# --- Gradio UI Definition ---
with gr.Blocks(title="Voice-over Production Tool") as demo:
    gr.Markdown("# 🎙️ Buddy Tales Production Tool (Version 5.0 - Cloud Run)")
    gr.Markdown("This version is running live on Google Cloud. It supports inline directorial notes.")
    with gr.Row():
        with gr.Column(scale=1): script_upload = gr.File(label="Upload Script (.txt)", file_types=[".txt"], type="file"); generate_button = gr.Button("Generate Voice-over", variant="primary"); clear_button = gr.Button("Clear Generated Files", visible=False)
        with gr.Column(scale=2): status_output = gr.Markdown(value="Waiting for script...", label="Status"); output_results = gr.HTML(label="Generated Audio")
    generate_button.click(fn=generate_voice_over, inputs=script_upload, outputs=[status_output, output_results, clear_button])
    clear_button.click(fn=clear_generated_files, inputs=[], outputs=[status_output, output_results, clear_button])

# This assignment is needed for the deployment server (Gunicorn) to find the app.
app = demo

# This block is for local testing only and will not run on Cloud Run.
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get('PORT', 7860)))