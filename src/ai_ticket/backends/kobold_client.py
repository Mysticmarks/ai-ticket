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

    try:
        response = requests.post(chat_endpoint, headers=headers, json=chat_payload, timeout=120)
        response.raise_for_status()
        completion_data = response.json()
        if completion_data.get("choices") and completion_data["choices"][0].get("message"):
            return completion_data["choices"][0]["message"]["content"].strip()
    except requests.exceptions.RequestException as e:
        print(f"Error with chat completions endpoint {chat_endpoint}: {e}. Trying plain completions.")

        completion_payload = {
            "model": "koboldcpp-model",
            "prompt": prompt,
            "max_tokens": max_length,
            "temperature": temperature,
            "top_p": top_p,
        }
        try:
            response = requests.post(completion_endpoint, headers=headers, json=completion_payload, timeout=120)
            response.raise_for_status()
            completion_data = response.json()
            if completion_data.get("choices") and completion_data["choices"][0].get("text"):
                return completion_data["choices"][0]["text"].strip()
        except requests.exceptions.RequestException as e_fallback:
            print(f"Error with plain completions endpoint {completion_endpoint}: {e_fallback}")
            return None

    return None # Should not be reached if logic is correct
