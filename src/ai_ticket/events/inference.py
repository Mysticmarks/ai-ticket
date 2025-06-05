import json
from ai_ticket.backends.kobold_client import get_kobold_completion

def on_event(event_data: dict):
    """
    Handles an event, extracts a prompt, gets a completion from KoboldCPP, and returns the result.

    The `event_data` is expected to be a dictionary containing a "content" field.
    The "content" can be:
    1. A JSON string representing a dictionary with a "messages" key (list of OpenAI-style
       message objects), from which user messages are extracted and joined to form the prompt.
    2. A JSON string representing a dictionary with a "prompt" key.
    3. A plain text string that is used directly as the prompt.
    4. Any other JSON structure will be stringified and used as a prompt as a fallback.

    Args:
        event_data: A dictionary containing the event data. Must include a "content" field.

    Returns:
        A dictionary with either a "completion" key and the LLM's response,
        or an "error" key with an error message.
    """
    print(f"on_event received data: {event_data}")

    content_str = event_data.get("content")
    if not content_str:
        print("No 'content' field in event_data.")
        return {"error": "No 'content' field in event_data."}

    prompt_text = None
    try:
        inner_data = json.loads(content_str)
        if isinstance(inner_data, dict):
            if "messages" in inner_data and isinstance(inner_data["messages"], list):
                user_prompts = [
                    msg.get("content") for msg in inner_data["messages"]
                    if isinstance(msg, dict) and msg.get("role") == "user" and msg.get("content")
                ]
                if user_prompts:
                    prompt_text = "\n".join(user_prompts)
            elif "prompt" in inner_data:
                prompt_text = inner_data.get("prompt")
            else: # Fallback if structure is unknown but valid JSON
                prompt_text = content_str
        else: # If inner_data is not a dict (e.g. just a string after json.loads)
             prompt_text = str(inner_data)

    except json.JSONDecodeError:
        prompt_text = content_str # Assume content_str is the direct prompt
    except TypeError: # Handles if content_str is not bytes, string or bytearray for json.loads
        prompt_text = str(content_str)


    if not prompt_text: # Final check if prompt_text ended up empty or None
        print("Could not extract a valid prompt from 'content'.")
        return {"error": "Could not extract a valid prompt from 'content'."}

    print(f"Extracted prompt: '{prompt_text}'")

    result = get_kobold_completion(prompt=prompt_text)

    if "completion" in result:
        print(f"KoboldCPP completion: {result['completion']}")
        return {"completion": result['completion']}
    else:
        # Error already printed by get_kobold_completion
        print(f"Failed to get completion from KoboldCPP. Error: {result.get('error')}")
        return {"error": result.get("error", "Failed to get completion from KoboldCPP.")}
