import os
import requests
import json
import time
import logging

# Basic logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DEFAULT_KOBOLDCPP_API_URL = "http://localhost:5001/api" # Common default for KoboldCPP
MAX_RETRIES = 3

def get_kobold_completion(prompt: str,
                          kobold_url: str = None,
                          max_length: int = 150,
                          temperature: float = 0.7,
                          top_p: float = 1.0
                         ):
    """
    Fetches a text completion from a KoboldCPP API with retries and standardized error handling.
    Tries OpenAI-compatible chat completions endpoint, then plain completions endpoint.
    """
    actual_kobold_url = kobold_url or os.getenv("KOBOLDCPP_API_URL")
    if not actual_kobold_url:
        logging.error("KOBOLDCPP_API_URL is not set.")
        return {"error": "configuration_error", "details": "KOBOLDCPP_API_URL is not set."}

    # Ensure no trailing slash for proper endpoint joining
    actual_kobold_url = actual_kobold_url.rstrip('/')

    endpoints_payloads = [
        (
            f"{actual_kobold_url}/v1/chat/completions",
            {
                "model": "koboldcpp-model",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_length, "temperature": temperature, "top_p": top_p
            },
            lambda data: data.get("choices") and isinstance(data["choices"], list) and len(data["choices"]) > 0 and \
                         data["choices"][0].get("message") and isinstance(data["choices"][0]["message"], dict) and \
                         data["choices"][0]["message"].get("content"),
            lambda data: data["choices"][0]["message"]["content"].strip(),
            "chat"
        ),
        (
            f"{actual_kobold_url}/v1/completions",
            {
                "model": "koboldcpp-model",
                "prompt": prompt,
                "max_tokens": max_length, "temperature": temperature, "top_p": top_p
            },
            lambda data: data.get("choices") and isinstance(data["choices"], list) and len(data["choices"]) > 0 and \
                         data["choices"][0].get("text"),
            lambda data: data["choices"][0]["text"].strip(),
            "plain"
        )
    ]

    headers = {"Content-Type": "application/json"}
    last_exception = None

    for endpoint_url, payload, validator, extractor, endpoint_type in endpoints_payloads:
        logging.info(f"Attempting to contact KoboldCPP API via {endpoint_type} endpoint: {endpoint_url}")
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(endpoint_url, headers=headers, json=payload, timeout=120)
                response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)

                try:
                    completion_data = response.json()
                except json.JSONDecodeError as e:
                    logging.error(f"JSON decode error from {endpoint_type} endpoint {endpoint_url}: {e}. Response text: {response.text[:100]}...")
                    # Treat as a non-retryable error for this endpoint, try next endpoint or fail
                    last_exception = e
                    # This error type is specific enough to break retry for this endpoint
                    return {"error": "api_response_format_error", "details": f"Failed to decode JSON response from KoboldCPP API ({endpoint_type} endpoint). Response text snippet: {response.text[:200]}"}


                if validator(completion_data):
                    logging.info(f"Successfully received completion from {endpoint_type} endpoint.")
                    return {"completion": extractor(completion_data)}
                else:
                    logging.error(f"Unexpected response structure from {endpoint_type} endpoint {endpoint_url}: {completion_data}")
                    # Treat as a non-retryable error for this endpoint, try next endpoint or fail
                    return {"error": "api_response_structure_error", "details": f"Unexpected JSON structure in KoboldCPP API response from {endpoint_type} endpoint. Data: {str(completion_data)[:200]}"}

            except requests.exceptions.HTTPError as e:
                last_exception = e
                status_code = e.response.status_code
                logging.warning(f"HTTP error on attempt {attempt + 1}/{MAX_RETRIES} for {endpoint_type} endpoint {endpoint_url}: {e}. Status: {status_code}")
                if status_code in [401, 403]:
                    return {"error": "api_authentication_error", "details": f"KoboldCPP API request failed due to authentication/authorization ({endpoint_type} endpoint). Status: {status_code}"}
                elif status_code == 429:
                    retry_after_str = e.response.headers.get("Retry-After")
                    wait_time = int(retry_after_str) if retry_after_str and retry_after_str.isdigit() else (1 * (2**attempt))
                    logging.info(f"Rate limit hit (429). Retrying after {wait_time} seconds.")
                    time.sleep(wait_time)
                    # continue to next attempt
                elif 400 <= status_code < 500: # Other client errors
                    return {"error": "api_client_error", "details": f"KoboldCPP API request failed with client error ({endpoint_type} endpoint). Status: {status_code}, Response: {e.response.text[:200]}"}
                elif 500 <= status_code < 600: # Server errors, retry
                    if attempt < MAX_RETRIES - 1:
                        wait_time = 1 * (2**attempt)
                        logging.info(f"Server error ({status_code}). Retrying after {wait_time} seconds.")
                        time.sleep(wait_time)
                    else:
                        logging.error(f"Server error ({status_code}) on final attempt for {endpoint_type} endpoint.")
                        # Fall through to outer loop to try next endpoint or return final error
                else: # Other HTTP errors, don't retry for this endpoint
                    break # break from retry loop, try next endpoint

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exception = e
                logging.warning(f"Connection/Timeout error on attempt {attempt + 1}/{MAX_RETRIES} for {endpoint_type} endpoint {endpoint_url}: {e}")
                if attempt < MAX_RETRIES - 1:
                    wait_time = 1 * (2**attempt)
                    logging.info(f"Retrying after {wait_time} seconds.")
                    time.sleep(wait_time)
                else:
                    logging.error(f"Connection/Timeout error on final attempt for {endpoint_type} endpoint.")
                    # Fall through to outer loop to try next endpoint or return final error

            except requests.exceptions.RequestException as e: # Catch other request-related errors
                last_exception = e
                logging.error(f"Unexpected request error for {endpoint_type} endpoint {endpoint_url}: {e}")
                # Don't retry for unknown request errors for this endpoint, try next or fail
                break # break from retry loop, try next endpoint

        if isinstance(last_exception, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)) or \
           (isinstance(last_exception, requests.exceptions.HTTPError) and 500 <= last_exception.response.status_code < 600):
            # If this endpoint failed on retries for connection/timeout/5xx, continue to next endpoint
            continue
        elif last_exception: # For other errors that broke the retry loop for this endpoint
            # If there was an error like 4xx (not 429), JSONDecode, or other RequestException,
            # and it was returned, we shouldn't proceed to the next endpoint.
            # The error should have been returned already.
            # This path is more of a safeguard.
            break


    # If all endpoints and their retries failed
    if last_exception:
        if isinstance(last_exception, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)) or \
           (isinstance(last_exception, requests.exceptions.HTTPError) and 500 <= last_exception.response.status_code < 600):
            return {"error": "api_connection_error", "details": f"Failed to connect to KoboldCPP API after multiple attempts. Last error: {str(last_exception)}"}
        elif isinstance(last_exception, requests.exceptions.RequestException):
             return {"error": "api_request_error", "details": f"An unexpected error occurred during the request to KoboldCPP API. Last error: {str(last_exception)}"}

    return {"error": "api_unknown_error", "details": "All attempts to contact KoboldCPP API failed without a specific categorized error."}

