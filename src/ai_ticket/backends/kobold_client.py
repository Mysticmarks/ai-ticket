import os
import requests
import json

DEFAULT_KOBOLDCPP_API_URL = "http://localhost:5001/api" # Common default for KoboldCPP

def get_kobold_completion(prompt: str,
                          kobold_url: str = None,
                          max_length: int = 150,
                          temperature: float = 0.7,
                          top_p: float = 1.0
                         ):
    """
    Fetches a text completion from a KoboldCPP API.

    It first tries the OpenAI-compatible chat completions endpoint (/v1/chat/completions)
    and falls back to the plain completions endpoint (/v1/completions) if the first fails.

    Args:
        prompt: The text prompt to send to the LLM.
        kobold_url: The base URL of the KoboldCPP API. If None, it defaults to
                    the value of the KOBOLDCPP_API_URL environment variable, or
                    DEFAULT_KOBOLDCPP_API_URL if the environment variable is not set.
        max_length: The maximum number of tokens to generate.
        temperature: The sampling temperature.
        top_p: The nucleus sampling probability.

    Returns:
        The completed text string if successful, or None if all attempts fail.
    """
    if kobold_url is None:
        kobold_url = os.getenv("KOBOLDCPP_API_URL", DEFAULT_KOBOLDCPP_API_URL)

    # Prioritize /v1/chat/completions, fallback to /v1/completions
    chat_endpoint = f"{kobold_url.rstrip('/')}/v1/chat/completions"
    completion_endpoint = f"{kobold_url.rstrip('/')}/v1/completions"

    headers = {"Content-Type": "application/json"}

    chat_payload = {
        "model": "koboldcpp-model", # Can be arbitrary for local KoboldCPP
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_length,
        "temperature": temperature,
        "top_p": top_p,
    }

    chat_payload = {
        "model": "koboldcpp-model",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_length,
        "temperature": temperature,
        "top_p": top_p,
    }

    try:
        response = requests.post(chat_endpoint, headers=headers, json=chat_payload, timeout=120)
        response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
        completion_data = response.json()
        if completion_data.get("choices") and \
           isinstance(completion_data["choices"], list) and \
           len(completion_data["choices"]) > 0 and \
           completion_data["choices"][0].get("message") and \
           isinstance(completion_data["choices"][0]["message"], dict) and \
           completion_data["choices"][0]["message"].get("content"):
            return {"completion": completion_data["choices"][0]["message"]["content"].strip()}
        else:
            error_msg = f"Unexpected response structure from chat endpoint {chat_endpoint}: {completion_data}"
            print(error_msg)
            return {"error": error_msg}
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP error with chat completions endpoint {chat_endpoint}: {e}. Response: {e.response.text if e.response else 'No response text'}"
        print(error_msg)
        # Fall through to try plain completions endpoint
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error with chat completions endpoint {chat_endpoint}: {e}."
        print(error_msg)
        # Fall through to try plain completions endpoint
    except json.JSONDecodeError as e:
        error_msg = f"JSON decode error from chat endpoint {chat_endpoint} response: {e}. Response text: {response.text if 'response' in locals() else 'N/A'}"
        print(error_msg)
        # Fall through to try plain completions endpoint


    # Fallback to /v1/completions
    print(f"Trying plain completions endpoint: {completion_endpoint}")
    completion_payload = {
        "model": "koboldcpp-model",
        "prompt": prompt,
        "max_tokens": max_length,
        "temperature": temperature,
        "top_p": top_p,
    }
    try:
        response = requests.post(completion_endpoint, headers=headers, json=completion_payload, timeout=120)
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
        completion_data = response.json()
        if completion_data.get("choices") and \
           isinstance(completion_data["choices"], list) and \
           len(completion_data["choices"]) > 0 and \
           completion_data["choices"][0].get("text"):
            return {"completion": completion_data["choices"][0]["text"].strip()}
        else:
            error_msg = f"Unexpected response structure from plain completions endpoint {completion_endpoint}: {completion_data}"
            print(error_msg)
            return {"error": error_msg}
    except requests.exceptions.HTTPError as e_fallback:
        error_msg = f"HTTP error with plain completions endpoint {completion_endpoint}: {e_fallback}. Response: {e_fallback.response.text if e_fallback.response else 'No response text'}"
        print(error_msg)
        return {"error": error_msg}
    except requests.exceptions.RequestException as e_fallback:
        error_msg = f"Request error with plain completions endpoint {completion_endpoint}: {e_fallback}"
        print(error_msg)
        return {"error": error_msg}
    except json.JSONDecodeError as e_fallback:
        error_msg = f"JSON decode error from plain completions endpoint {completion_endpoint} response: {e_fallback}. Response text: {response.text if 'response' in locals() else 'N/A'}"
        print(error_msg)
        return {"error": error_msg}

    # Should only be reached if all attempts fail and errors are returned above
    return {"error": "All attempts to contact KoboldCPP API failed."}
