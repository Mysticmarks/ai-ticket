import json
import logging
from ai_ticket.backends.kobold_client import get_kobold_completion

# Basic logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def on_event(event_data: dict):
    """
    Handles an event, extracts a prompt, gets a completion from KoboldCPP, and returns the result.
    Implements standardized input validation and error handling.
    """
    logging.info(f"on_event received data: {event_data}")

    if not isinstance(event_data, dict):
        logging.error("Invalid input format: event_data is not a dictionary.")
        return {"error": "invalid_input_format", "details": "Event data must be a dictionary."}

    content_str = event_data.get("content")
    if content_str is None: # Check for None explicitly, as empty string might be valid for some prompts
        logging.error("Missing 'content' field in event_data.")
        return {"error": "missing_content_field", "details": "'content' field is missing in event data."}

    # Prompt extraction logic (simplified for now, can be expanded)
    # For this version, we assume content_str itself can be the prompt or JSON needing parsing
    prompt_text = None
    try:
        # Attempt to parse content_str as JSON
        inner_data = json.loads(content_str)
        if isinstance(inner_data, dict):
            if "messages" in inner_data and isinstance(inner_data["messages"], list):
                user_prompts = [
                    msg.get("content") for msg in inner_data["messages"]
                    if isinstance(msg, dict) and msg.get("role") == "user" and msg.get("content")
                ]
                if user_prompts:
                    prompt_text = "\n".join(user_prompts)
            elif "prompt" in inner_data: # Support direct "prompt" key in JSON
                prompt_text = inner_data.get("prompt")

            if not prompt_text: # If JSON but no known prompt structure, stringify content
                 prompt_text = json.dumps(inner_data) # Use the full JSON string as prompt

        elif isinstance(inner_data, str): # If JSON loads to a plain string
            prompt_text = inner_data
        else: # Other JSON types (list, number, boolean)
            prompt_text = json.dumps(inner_data)

    except json.JSONDecodeError:
        # If not JSON, assume content_str is the direct prompt
        prompt_text = content_str
    except TypeError: # Handles if content_str is not bytes, string or bytearray for json.loads
        logging.warning(f"TypeError during prompt extraction, falling back to raw content string. Content: {content_str}")
        prompt_text = str(content_str) # Ensure it's a string

    if not prompt_text and not isinstance(prompt_text, str): # Check if prompt_text is None or not a string
        logging.error("Prompt extraction failed: Could not derive a valid string prompt from 'content'.")
        return {"error": "prompt_extraction_failed", "details": "Could not derive a valid string prompt from 'content'."}

    # Handle empty string prompt if it's not desired (optional, depends on backend capability)
    # For now, allow empty string prompts to be passed to the backend.

    print(f"Extracted prompt: '{prompt_text}'")

    result = get_kobold_completion(prompt=prompt_text)

    if "completion" in result:
        print(f"KoboldCPP completion: {result['completion']}")
        return {"completion": result['completion']}
    else:
        # Error already printed by get_kobold_completion
        print(f"Failed to get completion from KoboldCPP. Error: {result.get('error')}")
        return {"error": result.get("error", "Failed to get completion from KoboldCPP.")}
